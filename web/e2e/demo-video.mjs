import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const demoDir = path.join(root, "docs", "demo");
const port = 8091;
const baseUrl = `http://127.0.0.1:${port}`;
const totalSeconds = 120;
const py = process.env.PYTHON ?? path.join(root, ".venv", "Scripts", "python.exe");
const srtPath = path.join(demoDir, "accessdesk2-demo.de.srt");
const silentMp4 = path.join(demoDir, "accessdesk2-demo.mp4");
const captionedMp4 = path.join(demoDir, "accessdesk2-demo-untertitel.mp4");

await fs.mkdir(demoDir, { recursive: true });
await fs.writeFile(srtPath, await makeSrt(), "utf8");
if (process.argv.includes("--captions-only")) {
  await renderCaptions();
  process.exit(0);
}
await assertPortFree(port);

const runtime = await fs.mkdtemp(path.join(os.tmpdir(), "accessdesk-demo-runtime-"));
const videoDir = await fs.mkdtemp(path.join(os.tmpdir(), "accessdesk-demo-video-"));
const server = spawn(py, [
  path.join(root, "start.py"),
  "--no-browser",
  "--port",
  String(port),
  "--runtime",
  runtime,
], {
  cwd: root,
  env: { ...process.env, ACCESSDESK_AI: "off", PYTHONIOENCODING: "utf-8" },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverOutput = "";
server.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
server.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });

let browser;
let context;
let video;
try {
  await waitForServer(server);
  browser = await chromium.launch({ channel: "chrome", headless: true });
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
  });
  await context.addInitScript(() => {
    localStorage.setItem("accessdesk.theme", "white");
    localStorage.setItem("accessdesk.language", "de");
  });
  const recordingStartedAt = Date.now();
  const page = await context.newPage();
  await page.goto(`${baseUrl}/#/staff/inbox`, { waitUntil: "domcontentloaded" });
  await page.locator(".desktop-case-table tbody tr").first().waitFor();
  const recordingOffset = (Date.now() - recordingStartedAt) / 1000;
  const clock = Date.now();
  await holdUntil(clock, 12);

  await page.locator(".desktop-case-table tbody tr").filter({ hasText: "R02" }).dblclick();
  await page.locator("#page-title").waitFor();
  await holdUntil(clock, 24);

  await openApplicantCase(page, "Dr. Sophie Lechner", "R01");
  await holdUntil(clock, 38);

  await page.getByRole("button", { name: "Bescheid öffnen" }).click();
  await page.locator(".letter-page").waitFor();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.45));
  await holdUntil(clock, 44);

  await openApplicantCase(page, "Prof. Elena Rossi", "R08");
  await holdUntil(clock, 54);

  await openApplicantCase(page, "Dr. Sophie Lechner", "D05");
  await holdUntil(clock, 66);

  await openApplicantCase(page, "Dr. Amir Hadžić", "R05");
  await page.getByRole("button", { name: "Zum SPE-Arbeitsbereich" }).click();
  await page.locator("#spe-sql").waitFor();
  await holdUntil(clock, 76);

  await page.locator("#spe-sql").fill("SELECT * FROM cohort LIMIT 20");
  await page.getByRole("button", { name: "Abfrage ausführen" }).click();
  await page.locator(".spe-query-result").waitFor();
  await page.getByRole("button", { name: "Rohdaten herunterladen" }).click();
  await page.getByText(/Download blockiert/).waitFor();
  await holdUntil(clock, 88);

  await page.locator('a[href="#/apply/new"]').click();
  await page.locator("#builder-purpose").pressSequentially(
    "We are launching an advertising campaign to promote a new product.",
    { delay: 45 },
  );
  await page.getByText("REJECT [54]").waitFor();
  await holdUntil(clock, 100);

  await page.locator("#role-switch").selectOption("staff");
  await page.locator('a[href="#/staff/audit"]').click();
  await page.getByRole("button", { name: "Kette prüfen" }).click();
  await page.getByRole("status").waitFor();
  await holdUntil(clock, 103);
  await page.locator('a[href="#/staff/eval"]').click();
  await page.getByRole("button", { name: "Auswertung starten" }).click();
  await page.locator(".evaluation-results").waitFor();
  await holdUntil(clock, 106);
  await holdUntil(clock, 114);

  await page.locator("#role-switch").selectOption("public");
  await page.locator('a[href="#/register"]').click();
  await page.locator(".register-table").waitFor();
  await holdUntil(clock, totalSeconds);

  video = page.video();
  await page.close();
  await context.close();
  context = undefined;
  const webm = await video.path();

  runFfmpeg([
    "-y", "-i", webm, "-ss", recordingOffset.toFixed(3), "-t", String(totalSeconds), "-an",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
    "-preset", "medium", "-movflags", "+faststart", silentMp4,
  ]);
  await renderCaptions();
  const info = JSON.parse(spawnSync("ffprobe", [
    "-v", "error", "-show_entries", "format=duration,size",
    "-of", "json", silentMp4,
  ], { cwd: root, encoding: "utf8" }).stdout).format;
  console.log(JSON.stringify({
    silent: silentMp4,
    captioned: captionedMp4,
    subtitles: srtPath,
    duration_seconds: Number(info.duration),
    silent_bytes: Number(info.size),
  }, null, 2));
} finally {
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  server.kill();
  await new Promise((resolve) => {
    if (server.exitCode !== null) resolve();
    else server.once("exit", resolve);
  });
  await fs.rm(runtime, { recursive: true, force: true });
  await fs.rm(videoDir, { recursive: true, force: true });
  if (server.exitCode && !server.killed) {
    console.error(serverOutput);
  }
}

async function openApplicantCase(page, identity, caseId) {
  await page.locator("#role-switch").selectOption("applicant");
  await page.locator("#identity-switch").selectOption({ label: identity });
  await page.goto(`${baseUrl}/#/apply/cases`, { waitUntil: "networkidle" });
  await page.locator(".applicant-cases-table tbody tr").filter({ hasText: caseId })
    .getByRole("button", { name: "Öffnen" }).click();
  await page.locator("#page-title").waitFor();
}

async function holdUntil(start, seconds) {
  const remaining = start + seconds * 1000 - Date.now();
  if (remaining > 0) await new Promise((resolve) => setTimeout(resolve, remaining));
}

async function assertPortFree(requested) {
  await new Promise((resolve, reject) => {
    const socket = net.createServer();
    socket.once("error", reject);
    socket.listen(requested, "127.0.0.1", () => socket.close(resolve));
  });
}

async function waitForServer(process) {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) throw new Error(`AccessDesk stopped during startup:\n${serverOutput}`);
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`AccessDesk did not start:\n${serverOutput}`);
}

function runFfmpeg(args) {
  const result = spawnSync("ffmpeg", args, { cwd: root, stdio: "inherit" });
  if (result.status !== 0) throw new Error(`ffmpeg failed with exit code ${result.status}`);
}

async function renderCaptions() {
  const assPath = path.join(demoDir, "accessdesk2-demo.de.ass");
  const srt = await fs.readFile(srtPath, "utf8");
  await fs.writeFile(assPath, srtToAss(srt), "utf8");
  try {
    runFfmpeg([
      "-y", "-i", silentMp4, "-t", String(totalSeconds),
      "-vf", "pad=iw:ih+72:0:0:color=white,ass=docs/demo/accessdesk2-demo.de.ass",
      "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
      "-preset", "medium", "-movflags", "+faststart", captionedMp4,
    ]);
  } finally {
    await fs.rm(assPath, { force: true });
  }
}

function srtToAss(srt) {
  const blocks = srt.trim().split(/\r?\n\r?\n/u);
  const events = blocks.map((block) => {
    const lines = block.split(/\r?\n/u);
    const [start, end] = lines[1].split(" --> ");
    return `Dialogue: 0,${assTime(start)},${assTime(end)},Default,,0,0,0,,${lines.slice(2).join("\\N")}`;
  });
  return [
    "[Script Info]",
    "ScriptType: v4.00+",
    "PlayResX: 1440",
    "PlayResY: 972",
    "ScaledBorderAndShadow: yes",
    "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,1,0,2,40,40,12,1",
    "",
    "[Events]",
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ...events,
    "",
  ].join("\n");
}

function assTime(value) {
  const [hours, minutes, rest] = value.split(":");
  const [seconds, milliseconds] = rest.split(",");
  return `${Number(hours)}:${minutes}:${seconds}.${milliseconds.slice(0, 2)}`;
}

async function makeSrt() {
  const markdown = await fs.readFile(path.join(root, "DEMO.md"), "utf8");
  const rows = markdown.split(/\r?\n/u).filter((line) => /^\|\s*\d+:\d\d\s*\|/u.test(line))
    .map((line) => {
      const columns = line.split("|").slice(1, -1).map((column) => column.trim());
      return {
        start: parseTime(columns[0]),
        speech: columns[2].replace(/^„/u, "").replace(/“$/u, ""),
      };
    });
  return rows.flatMap((row, rowIndex) => {
    const end = rows[rowIndex + 1]?.start ?? totalSeconds;
    const chunks = cueChunks(row.speech);
    const slot = end - row.start;
    const totalWeight = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    let elapsed = row.start;
    return chunks.map((chunk, chunkIndex) => {
      const start = elapsed;
      const stop = chunkIndex === chunks.length - 1
        ? end
        : start + slot * chunk.length / totalWeight;
      elapsed = stop;
      return `${srtTime(start)} --> ${srtTime(stop)}\n${wrapLines(chunk).join("\n")}`;
    });
  }).map((cue, index) => `${index + 1}\n${cue}`).join("\n\n") + "\n";
}

function cueChunks(text) {
  const chunks = [];
  let current = "";
  for (const sentence of splitSentences(text)) {
    const parts = wrapLines(sentence).length <= 2
      ? [sentence]
      : splitLongSentence(sentence);
    for (const part of parts) {
      const candidate = current ? `${current} ${part}` : part;
      if (current && wrapLines(candidate).length > 2) {
        chunks.push(current);
        current = part;
      } else {
        current = candidate;
      }
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

function splitSentences(text) {
  const protectedText = text
    .replace(/\bArt\./gu, "Art\uE000")
    .replace(/\bz\.B\./giu, "z\uE001B\uE001")
    .replace(/\bd\.h\./giu, "d\uE002h\uE002");
  return protectedText
    .split(/(?:(?<=[.!?])|(?<=[.!?][“”»"']))\s+/u)
    .map((sentence) => sentence
      .replaceAll("\uE000", ".")
      .replaceAll("\uE001", ".")
      .replaceAll("\uE002", "."))
    .filter(Boolean);
}

function splitLongSentence(sentence) {
  const chunks = [];
  let current = "";
  for (const clause of sentence.split(/(?<=,)\s+/u)) {
    const candidate = current ? `${current} ${clause}` : clause;
    if (current && wrapLines(candidate).length > 2) {
      chunks.push(current);
      current = clause;
    } else {
      current = candidate;
    }
  }
  if (current) chunks.push(current);
  return chunks.flatMap((chunk) => splitLongClause(chunk));
}

function splitLongClause(clause) {
  if (wrapLines(clause).length <= 2) return [clause];
  const chunks = [];
  let current = "";
  for (const word of clause.split(/\s+/u)) {
    const candidate = current ? `${current} ${word}` : word;
    if (current && wrapLines(candidate).length > 2) {
      chunks.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

function wrapLines(text) {
  const lines = [];
  let line = "";
  for (const word of text.split(/\s+/u)) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > 42 && line) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function parseTime(value) {
  const [minutes, seconds] = value.split(":").map(Number);
  return minutes * 60 + seconds;
}

function srtTime(seconds) {
  const milliseconds = Math.round(seconds * 1000);
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const secs = Math.floor((milliseconds % 60_000) / 1000);
  const millis = milliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")},${String(millis).padStart(3, "0")}`;
}
