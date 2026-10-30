// Encodes variable-rate JPEG screencast frames into a constant-rate H.264 MP4 with macOS AVFoundation (no ffmpeg).
// Usage: swift tools/encode_frames.swift <frames.tsv: path<TAB>timestamp> <out.mp4> [fps]
import AVFoundation
import CoreGraphics
import Foundation
import ImageIO

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: encode_frames <frames.tsv> <out.mp4> [fps]"); exit(2) }
let fps = Int32(args.count > 3 ? Int(args[3]) ?? 30 : 30)
let rows: [(String, Double)] = try String(contentsOfFile: args[1], encoding: .utf8)
    .split(separator: "\n").compactMap { line in
        let parts = line.split(separator: "\t")
        guard parts.count == 2, let t = Double(parts[1]) else { return nil }
        return (String(parts[0]), t)
    }
guard let first = rows.first, let last = rows.last else { print("no frames"); exit(1) }
let t0 = first.1
let duration = last.1 - t0 + 1.5  // hold the last frame briefly

func loadImage(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}
guard let firstImage = loadImage(first.0) else { print("cannot read \(first.0)"); exit(1) }
let width = firstImage.width, height = firstImage.height

let out = URL(fileURLWithPath: args[2])
try? FileManager.default.removeItem(at: out)
let writer = try AVAssetWriter(outputURL: out, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 10_000_000,
                                      AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel],
])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height,
])
writer.add(input)
guard writer.startWriting() else { print("cannot start: \(String(describing: writer.error))"); exit(1) }
writer.startSession(atSourceTime: .zero)

func pixelBuffer(_ image: CGImage) -> CVPixelBuffer? {
    var pb: CVPixelBuffer?
    guard let pool = adaptor.pixelBufferPool, CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pb) == kCVReturnSuccess,
          let buf = pb else { return nil }
    CVPixelBufferLockBaseAddress(buf, [])
    defer { CVPixelBufferUnlockBaseAddress(buf, []) }
    guard let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: width, height: height, bitsPerComponent: 8,
                              bytesPerRow: CVPixelBufferGetBytesPerRow(buf), space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
                                  | CGBitmapInfo.byteOrder32Little.rawValue) else { return nil }
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return buf
}

let total = Int(duration * Double(fps))
var source = 0
var current = pixelBuffer(firstImage)
for k in 0..<total {  // constant frame rate: repeat the latest screencast frame until a newer one exists
    let t = t0 + Double(k) / Double(fps)
    var next = source
    while next + 1 < rows.count && rows[next + 1].1 <= t { next += 1 }
    if next != source, let img = loadImage(rows[next].0) {
        current = pixelBuffer(img)
        source = next
    }
    while !input.isReadyForMoreMediaData { usleep(2000) }
    if let buf = current { adaptor.append(buf, withPresentationTime: CMTime(value: CMTimeValue(k), timescale: fps)) }
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
guard writer.status == .completed else { print("failed: \(String(describing: writer.error))"); exit(1) }
print("wrote \(out.path): \(total) frames, \(String(format: "%.1f", duration)) s, \(width)x\(height)")
