"""Generate and mix a German voiceover for the local demo."""
import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import time
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT / "DEMO.md"
VOICE_DIR = ROOT / "docs" / "demo" / "voice"
SILENT_VIDEO = ROOT / "docs" / "demo" / "accessdesk2-demo.mp4"
SUBTITLED_VIDEO = ROOT / "docs" / "demo" / "accessdesk2-demo-untertitel.mp4"
OUTPUT_VIDEO = ROOT / "docs" / "demo" / "accessdesk2-demo-ton.mp4"
OUTPUT_SUBTITLED_VIDEO = ROOT / "docs" / "demo" / "accessdesk2-demo-ton-untertitel.mp4"
MODEL = "eleven_multilingual_v2"
# Premade Rachel voice ID from ElevenLabs' Voice Picker, checked 2026-10-30:
# https://ui.elevenlabs.io/docs/components/voice-picker
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"
GEMINI_TEXT_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_VOICE = "Charon"
ALTERNATE_GEMINI_VOICE = "Kore"
ELEVENLABS_API = "https://api.elevenlabs.io/v1"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
TOTAL_SECONDS = 120.0
OUTPUT_FORMAT = "mp3_44100_128"
SPEAKER_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.8,
    "style": 0.15,
    "use_speaker_boost": True,
}
_gemini_last_request = 0.0


@dataclass(frozen=True)
class DemoRow:
    start: int
    end: int
    text: str

    @property
    def slot_seconds(self):
        return self.end - self.start


@dataclass(frozen=True)
class VoiceClip:
    path: Path
    start: float


class VoiceoverError(RuntimeError):
    pass


def parse_demo_rows(markdown):
    rows = []
    for line in markdown.splitlines():
        if not re.match(r"^\|\s*\d+:\d\d\s*\|", line):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        start = _parse_time(columns[0])
        text = columns[2].strip()
        if text and ord(text[0]) == 0x201E:
            text = text[1:]
        if text and ord(text[-1]) == 0x201C:
            text = text[:-1]
        elif len(text) >= 2 and text[0] == text[-1] == '"':
            text = text[1:-1]
        rows.append((start, text.strip()))

    if len(rows) != 12:
        raise VoiceoverError(f"Expected 12 timed DEMO.md rows, found {len(rows)}.")
    result = []
    for index, (start, text) in enumerate(rows):
        end = rows[index + 1][0] if index + 1 < len(rows) else int(TOTAL_SECONDS)
        if end <= start or end > TOTAL_SECONDS:
            raise VoiceoverError(f"Invalid time slot for demo row {index + 1}.")
        result.append(DemoRow(start, end, text))
    return result


def load_demo_rows(path=DEMO_PATH):
    return parse_demo_rows(Path(path).read_text(encoding="utf-8"))


def cache_key(text, voice, model, settings):
    encoded = json.dumps(
        [text, voice, model, settings],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def cached_voice_clip(
    text,
    voice,
    model,
    settings,
    key,
    cache_dir=VOICE_DIR,
    provider="elevenlabs",
    force=False,
):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = cache_key(text, voice, model, settings)
    destination = cache_dir / f"{digest}.mp3"
    if force or not destination.exists():
        if provider == "gemini":
            _gemini_tts_to_mp3(text, voice, model, key, destination)
            return destination
        if provider != "elevenlabs":
            raise VoiceoverError(f"Unsupported voice provider: {provider}")
        url = (
            f"{ELEVENLABS_API}/text-to-speech/"
            f"{urllib.parse.quote(voice, safe='')}?output_format={OUTPUT_FORMAT}"
        )
        payload = {
            "text": text,
            "model_id": model,
            "voice_settings": settings,
        }
        audio = _request(url, key, method="POST", payload=payload, accept="audio/mpeg")
        temporary = destination.with_suffix(".mp3.tmp")
        temporary.write_bytes(audio)
        temporary.replace(destination)
    return destination


def _gemini_tts_to_mp3(text, voice, model, key, destination):
    response = _gemini_request(
        model,
        key,
        {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice},
                    },
                },
            },
        },
    )
    try:
        audio_part = next(
            part for part in response["candidates"][0]["content"]["parts"]
            if isinstance(part.get("inlineData"), dict)
        )["inlineData"]
        audio = base64.b64decode(audio_part["data"], validate=True)
        mime = str(audio_part.get("mimeType") or "").casefold()
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise VoiceoverError("Gemini TTS response did not contain valid audio data.") from exc

    with tempfile.TemporaryDirectory(prefix="accessdesk-gemini-tts-") as temporary_dir:
        wav_path = Path(temporary_dir) / "clip.wav"
        if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
            wav_path.write_bytes(audio)
        else:
            rate = re.search(r"rate=(\d+)", mime)
            sample_rate = int(rate.group(1)) if rate else 24_000
            if len(audio) % 2:
                raise VoiceoverError("Gemini returned an odd-length 16-bit PCM payload.")
            if "l16" in mime:
                audio = b"".join(
                    audio[offset:offset + 2][::-1] for offset in range(0, len(audio), 2)
                )
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio)
        converted = Path(temporary_dir) / "clip.mp3"
        _run_ffmpeg([
            "-i", str(wav_path), "-vn", "-c:a", "libmp3lame",
            "-b:a", "128k", str(converted),
        ])
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".mp3.tmp")
        temporary.write_bytes(converted.read_bytes())
        temporary.replace(destination)


def tempo_for_slot(duration, slot, margin=0.3, max_speed=1.10):
    available = slot - margin
    if available <= 0:
        raise ValueError("slot must exceed the safety margin")
    if duration <= available:
        return 1.0
    factor = duration / available
    if factor > max_speed:
        raise ValueError(
            f"clip duration {duration:.2f}s needs {factor:.3f}x speed "
            f"(limit {max_speed:.2f}x); use shorter text"
        )
    return factor


def _parse_time(value):
    minutes, seconds = (int(part) for part in value.split(":"))
    return minutes * 60 + seconds


def _configured_key(name):
    value = os.environ.get(name, "").strip()
    if value:
        return value
    env_path = ROOT / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key_name, value = line.split("=", 1)
        if key_name.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            return value or None
    return None


def _api_key():
    return _configured_key("ELEVENLABS_API_KEY")


def _gemini_key():
    return _configured_key("GEMINI_API_KEY")


def _request(url, key, method="GET", payload=None, accept="application/json"):
    data = None
    headers = {"xi-api-key": key, "Accept": accept}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            permission = "Voices: Read" if method == "GET" else "Text to Speech: Access"
            raise VoiceoverError(
                f"ElevenLabs returned HTTP {exc.code}; enable the required key permission: {permission}."
            ) from None
        if exc.code == 429:
            raise VoiceoverError("ElevenLabs rate limit or quota reached (HTTP 429).") from None
        raise VoiceoverError(f"ElevenLabs request failed (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VoiceoverError(f"ElevenLabs request failed: {exc.reason if hasattr(exc, 'reason') else exc}") from None


def _retry_after_seconds(error):
    headers = error.headers or {}
    value = headers.get("Retry-After")
    if value:
        try:
            return min(60.0, max(0.0, float(value)))
        except ValueError:
            pass
    try:
        body = json.loads(error.read().decode("utf-8"))
        details = body.get("error", {}).get("details", [])
        for detail in details:
            retry = detail.get("retryDelay", "")
            match = re.fullmatch(r"([\d.]+)s", retry)
            if match:
                return min(60.0, max(0.0, float(match.group(1))))
    except (AttributeError, UnicodeDecodeError, ValueError, TypeError):
        pass
    return 7.0


def _gemini_request(
    model, key, payload, attempts=3, timeout=30, retry_timeout=False,
):
    global _gemini_last_request
    url = f"{GEMINI_API}/{urllib.parse.quote(model, safe='.-')}:generateContent"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    for attempt in range(attempts):
        wait = 7.0 - (time.monotonic() - _gemini_last_request)
        if _gemini_last_request and wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                _gemini_last_request = time.monotonic()
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            _gemini_last_request = time.monotonic()
            if exc.code in (429, 503) and attempt + 1 < attempts:
                time.sleep(_retry_after_seconds(exc))
                continue
            if exc.code in (429, 503):
                raise VoiceoverError(
                    f"Gemini API returned HTTP {exc.code} after {attempts} attempts."
                ) from None
            if exc.code in (401, 403):
                raise VoiceoverError(f"Gemini API key was rejected (HTTP {exc.code}).") from None
            raise VoiceoverError(f"Gemini API request failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _gemini_last_request = time.monotonic()
            if retry_timeout and attempt + 1 < attempts:
                time.sleep(7.0)
                continue
            raise VoiceoverError(
                f"Gemini API request failed: {exc.reason if hasattr(exc, 'reason') else exc}"
            ) from None
        except json.JSONDecodeError:
            _gemini_last_request = time.monotonic()
            raise VoiceoverError("Gemini API returned invalid JSON.") from None
    raise VoiceoverError("Gemini API retry limit exceeded.")


def _ffprobe_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    except FileNotFoundError as exc:
        raise VoiceoverError("ffprobe is required to measure generated clips.") from exc
    except subprocess.CalledProcessError as exc:
        raise VoiceoverError(f"ffprobe failed: {exc.stderr.strip()}") from None
    return float(result.stdout.strip())


def _run_ffmpeg(args):
    try:
        subprocess.run(
            ["ffmpeg", "-y", *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    except FileNotFoundError as exc:
        raise VoiceoverError("ffmpeg is required for audio processing.") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip().splitlines()
        raise VoiceoverError(f"ffmpeg failed: {message[-1] if message else exc}") from None


def mix_audio(clips, destination, duration=TOTAL_SECONDS):
    if not clips:
        raise ValueError("at least one voice clip is required")
    command = [
        "-f", "lavfi", "-t", f"{duration:.3f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    ]
    for clip in clips:
        command.extend(["-i", str(clip.path)])
    filters = []
    labels = ["[0:a]"]
    for index, clip in enumerate(clips, 1):
        label = f"voice{index}"
        delay_ms = max(0, round(clip.start * 1000))
        filters.append(f"[{index}:a]adelay={delay_ms}:all=1[{label}]")
        labels.append(f"[{label}]")
    fade = min(0.4, duration / 2)
    fade_out_start = max(0.0, duration - fade)
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(clips) + 1}:duration=longest:dropout_transition=0:normalize=0,"
        + f"atrim=duration={duration:.3f},"
        + f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade:.3f},"
        + f"afade=t=out:st={fade_out_start:.3f}:d={fade:.3f},"
        + "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    )
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[out]", "-ar", "44100", "-c:a", "pcm_s16le", str(destination),
    ])
    _run_ffmpeg(command)


def _srt_to_ass(srt_path, ass_path):
    blocks = Path(srt_path).read_text(encoding="utf-8").strip().split("\n\n")
    events = []
    for block in blocks:
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
            + r"\N".join(lines[2:])
        )
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 972
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,1,0,2,40,40,12,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(ass_path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def _ass_time(value):
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    return f"{int(hours)}:{minutes}:{seconds}.{milliseconds[:2]}"


def _mix_into_video(video, audio, destination, subtitles=False):
    args = ["-i", str(video), "-i", str(audio)]
    filter_parts = ["tpad=stop_mode=clone:stop_duration=0.3"]
    ass_path = ROOT / "docs" / "demo" / "voiceover-captions.ass"
    try:
        if subtitles:
            _srt_to_ass(ROOT / "docs" / "demo" / "accessdesk2-demo.de.srt", ass_path)
            filter_parts.extend([
                "pad=iw:ih+72:0:0:color=white",
                "ass=docs/demo/voiceover-captions.ass",
            ])
        args.extend([
            "-vf", ",".join(filter_parts),
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(TOTAL_SECONDS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
            "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(destination),
        ])
        _run_ffmpeg(args)
    finally:
        ass_path.unlink(missing_ok=True)


def _print_dry_run(rows):
    total = sum(len(row.text) for row in rows)
    print(f"Rows: {len(rows)}")
    for index, row in enumerate(rows, 1):
        print(
            f"{index:02d} {_clock(row.start)}–{_clock(row.end)}"
            f"  {len(row.text)} chars  {row.slot_seconds:.0f}s"
        )
    print(f"Total characters: {total}")
    print(f"Estimated credits: {total} (1 credit per character)")


def _clock(seconds):
    return f"{seconds // 60}:{seconds % 60:02d}"


def _list_voices(key):
    data = json.loads(_request(f"{ELEVENLABS_API}/voices?page_size=100", key).decode("utf-8"))
    for voice in data.get("voices", []):
        labels = voice.get("labels") or {}
        parts = [f"{label}={labels[label]}" for label in ("accent", "language", "gender") if labels.get(label)]
        description = voice.get("description") or labels.get("description") or labels.get("descriptive")
        if description:
            parts.append(f"description={description}")
        print(f"{voice.get('voice_id', '')}\t{voice.get('name', '')}\t" + ", ".join(parts))


def _settings(args):
    values = {
        "stability": args.stability,
        "similarity_boost": args.similarity,
        "style": args.style,
        "use_speaker_boost": args.speaker_boost,
    }
    if any(not 0 <= values[name] <= 1 for name in ("stability", "similarity_boost", "style")):
        raise VoiceoverError("stability, similarity and style must be between 0 and 1.")
    return values


def _generate(rows, args, key, settings):
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    clips = []
    with tempfile.TemporaryDirectory(prefix="accessdesk-voiceover-") as temp:
        for index, row in enumerate(rows, 1):
            key_hash = cache_key(row.text, args.voice, args.model, settings)
            cached = cached_voice_clip(
                row.text, args.voice, args.model, settings, key, VOICE_DIR,
            )
            duration = _ffprobe_duration(cached)
            try:
                factor = tempo_for_slot(duration, row.slot_seconds)
            except ValueError as exc:
                raise VoiceoverError(f"Row {index} ({_clock(row.start)}): {exc}") from None
            clip_path = cached
            if factor > 1.0:
                clip_path = Path(temp) / f"{key_hash}-fast.mp3"
                _run_ffmpeg([
                    "-i", str(cached), "-filter:a", f"atempo={factor:.6f}",
                    "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(clip_path),
                ])
                fitted = _ffprobe_duration(clip_path)
                if fitted > row.slot_seconds - 0.3:
                    raise VoiceoverError(
                        f"Row {index} ({_clock(row.start)}) still takes {fitted:.2f}s "
                        "after 1.10x; use shorter text."
                    )
            clips.append(VoiceClip(clip_path, float(row.start)))
        mix_path = Path(temp) / "voiceover.wav"
        mix_audio(clips, mix_path)
        _mix_into_video(SILENT_VIDEO, mix_path, OUTPUT_VIDEO)
        _mix_into_video(SILENT_VIDEO, mix_path, OUTPUT_SUBTITLED_VIDEO, subtitles=True)


def _transcribe_gemini(path, expected_text, key):
    mime = "audio/mpeg" if Path(path).suffix.casefold() == ".mp3" else "audio/wav"
    payload = {
        "contents": [{
            "parts": [
                {"text": "Transcribe the spoken words verbatim. Return only the transcript field."},
                {
                    "inlineData": {
                        "mimeType": mime,
                        "data": base64.b64encode(Path(path).read_bytes()).decode("ascii"),
                    },
                },
            ],
        }],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "responseJsonSchema": {
                "type": "object",
                "properties": {"transcript": {"type": "string"}},
                "required": ["transcript"],
                "additionalProperties": False,
            },
        },
    }
    response = _gemini_request(
        GEMINI_TEXT_MODEL, key, payload, attempts=2, timeout=60, retry_timeout=True,
    )
    try:
        text = next(
            part["text"]
            for part in response["candidates"][0]["content"]["parts"]
            if isinstance(part.get("text"), str)
        )
        transcript = json.loads(text)["transcript"]
        if not isinstance(transcript, str):
            raise ValueError("transcript must be text")
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise VoiceoverError("Gemini transcription response was not valid structured JSON.") from exc
    score, boundaries_ok = transcript_score(expected_text, transcript)
    return transcript, score, boundaries_ok


def _words(text):
    normalized = re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE)
    tokens = normalized.split()
    return [
        token.replace(".", "").replace(",", "")
        for token in tokens
    ]


def transcript_score(expected, actual):
    expected_words, actual_words = _words(expected), _words(actual)
    score = difflib.SequenceMatcher(
        None, expected_words, actual_words, autojunk=False,
    ).ratio()
    boundaries_ok = bool(
        expected_words
        and actual_words
        and expected_words[0] == actual_words[0]
        and expected_words[-1] == actual_words[-1]
    )
    return score, boundaries_ok


def _generate_gemini(rows, args, key):
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    voice_settings = {"response_modalities": ["AUDIO"]}
    generated = []
    variants = [(row, args.voice, False) for row in rows]
    variants.append((rows[0], args.alternate_first_voice, True))

    with tempfile.TemporaryDirectory(prefix="accessdesk-gemini-voice-") as temp:
        temp_path = Path(temp)
        primary_clips = {}
        for row, voice, alternate in variants:
            cached = cached_voice_clip(
                row.text,
                voice,
                args.model,
                voice_settings,
                key,
                VOICE_DIR,
                provider="gemini",
            )
            duration = _ffprobe_duration(cached)
            transcript, score, boundaries_ok = _transcribe_gemini(cached, row.text, key)
            if score < 0.9 or not boundaries_ok:
                cached_voice_clip(
                    row.text,
                    voice,
                    args.model,
                    voice_settings,
                    key,
                    VOICE_DIR,
                    provider="gemini",
                    force=True,
                )
                duration = _ffprobe_duration(cached)
                transcript, score, boundaries_ok = _transcribe_gemini(cached, row.text, key)
            print(
                f"Transcript row {_clock(row.start)} voice={voice}: "
                f"overlap={score:.3f}, boundaries={'ok' if boundaries_ok else 'extra-edge-words'}"
            )
            if score < 0.9 or not boundaries_ok:
                raise VoiceoverError(
                    f"Transcript check failed for row {_clock(row.start)} voice {voice}: "
                    f"overlap {score:.3f}, boundary match {boundaries_ok}."
                )
            try:
                factor = tempo_for_slot(duration, row.slot_seconds)
            except ValueError as exc:
                raise VoiceoverError(
                    f"Row {_clock(row.start)} voice {voice} is too long ({duration:.2f}s): {exc}"
                ) from None

            clip_path = cached
            if factor > 1.0:
                clip_path = temp_path / f"{row.start}-{voice}-fast.mp3"
                _run_ffmpeg([
                    "-i", str(cached), "-filter:a", f"atempo={factor:.6f}",
                    "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(clip_path),
                ])
                fitted = _ffprobe_duration(clip_path)
                if fitted > row.slot_seconds - 0.3:
                    raise VoiceoverError(
                        f"Row {_clock(row.start)} still takes {fitted:.2f}s "
                        "after 1.10x; use shorter text."
                    )
            generated.append((row, voice, clip_path, duration, factor, score))
            if not alternate:
                primary_clips[row.start] = VoiceClip(clip_path, float(row.start))

        print("Gemini voice clips:")
        for row, voice, clip_path, duration, factor, score in generated:
            print(
                f"{_clock(row.start)} voice={voice} duration={duration:.2f}s "
                f"atempo={factor:.3f} transcript={score:.3f} cache={clip_path.name}"
            )
        mix_path = temp_path / "voiceover.wav"
        mix_audio(
            [primary_clips[row.start] for row in rows],
            mix_path,
        )
        _mix_into_video(SILENT_VIDEO, mix_path, OUTPUT_VIDEO)
        _mix_into_video(SILENT_VIDEO, mix_path, OUTPUT_SUBTITLED_VIDEO, subtitles=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("elevenlabs", "gemini"), default="elevenlabs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--voice")
    parser.add_argument("--alternate-first-voice", default=ALTERNATE_GEMINI_VOICE)
    parser.add_argument("--model")
    parser.add_argument("--stability", type=float, default=SPEAKER_SETTINGS["stability"])
    parser.add_argument("--similarity", type=float, default=SPEAKER_SETTINGS["similarity_boost"])
    parser.add_argument("--style", type=float, default=SPEAKER_SETTINGS["style"])
    parser.add_argument(
        "--speaker-boost",
        action=argparse.BooleanOptionalAction,
        default=SPEAKER_SETTINGS["use_speaker_boost"],
    )
    args = parser.parse_args(argv)

    try:
        rows = load_demo_rows()
        if args.dry_run:
            _print_dry_run(rows)
            return 0
        if args.provider == "gemini":
            key = _gemini_key()
        else:
            key = _api_key()
        if not key:
            key_name = "GEMINI_API_KEY" if args.provider == "gemini" else "ELEVENLABS_API_KEY"
            raise VoiceoverError(f"{key_name} is missing from the environment and accessdesk2/.env.")
        if args.list_voices:
            if args.provider != "elevenlabs":
                raise VoiceoverError("--list-voices is available for ElevenLabs; Gemini uses prebuilt voice names.")
            _list_voices(key)
            return 0
        if args.provider == "gemini":
            args.voice = args.voice or DEFAULT_GEMINI_VOICE
            args.model = args.model or GEMINI_TTS_MODEL
            _generate_gemini(rows, args, key)
        else:
            args.voice = args.voice or DEFAULT_VOICE_ID
            args.model = args.model or MODEL
            settings = _settings(args)
            _generate(rows, args, key, settings)
        return 0
    except VoiceoverError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Voiceover file error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
