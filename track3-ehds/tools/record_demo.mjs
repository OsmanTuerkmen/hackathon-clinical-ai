// Records a silent demo video of Doccess (headless Chrome screencast -> MP4 via ffmpeg). No narration, no intro.
// Usage: node tools/record_demo.mjs [http://127.0.0.1:8000] [output.mp4]
// Requires Node >= 22, Google Chrome and ffmpeg. The desk must be running.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const OUT = resolve(process.argv[3] || "doccess-demo.mp4");
const CHROME = process.env.CHROME_BIN || ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/chromium"].find(p => existsSync(p));
const W = 1440, H = 810, DPR = 4 / 3;  // 16:9, frames come out as 1920x1080
const sleep = ms => new Promise(r => setTimeout(r, ms));

const port = 9800 + Math.floor(Math.random() * 150);
const profile = join(tmpdir(), `doccess-rec-${process.pid}`);
const frameDir = join(tmpdir(), `doccess-frames-${process.pid}`);
mkdirSync(frameDir, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", `--window-size=${W},${H}`,
  `--force-device-scale-factor=${DPR}`, "about:blank"], { stdio: "ignore" });
const MOVE_MS = 450;  // cursor travel time; the whole demo stays under one minute

let ws, msgId = 0;
const pending = new Map();
const frames = [];
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++msgId;
  pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params }));
});
async function evaluate(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
async function waitFor(expression, timeout = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { if (await evaluate(expression)) return; } catch (e) { /* page navigating */ }
    await sleep(100);
  }
  throw new Error(`timeout: ${expression}`);
}

// ---------------------------------------------------------------- fake cursor, clicks, typing, scrolling
let cursor = { x: W / 2, y: H / 2 };
async function ensureCursor() {
  await evaluate(`(() => {
    if (document.getElementById('demo-cursor')) return;
    const c = document.createElement('div');
    c.id = 'demo-cursor';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28"><path d="M3 2l7 19 2.6-7.4L20 11z" fill="#111827" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: '2147483647', pointerEvents: 'none',
      transition: 'transform ${MOVE_MS}ms cubic-bezier(.45,0,.2,1)', transform: 'translate(${cursor.x - 3}px, ${cursor.y - 2}px)',
      filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))' });
    document.body.append(c);
  })()`);
}
async function pointAt(selector, { scroll = true } = {}) {
  await ensureCursor();
  if (scroll) {
    await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); const r = e.getBoundingClientRect();
      if (r.top < 90 || r.bottom > innerHeight - 40) { e.scrollIntoView({ block: 'center', behavior: 'smooth' }); return true; }
      return false; })()`) && await sleep(500);
  }
  const p = await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
    return { x: Math.round(r.left + Math.min(r.width / 2, 120)), y: Math.round(r.top + r.height / 2) }; })()`);
  cursor = p;
  await evaluate(`document.getElementById('demo-cursor').style.transform = 'translate(${p.x - 3}px, ${p.y - 2}px)'`);
  await sleep(MOVE_MS + 50);
}
async function click(selector, opts) {
  await pointAt(selector, opts);
  await evaluate(`(() => {
    const d = document.createElement('div');
    Object.assign(d.style, { position: 'fixed', left: '${cursor.x - 18}px', top: '${cursor.y - 18}px', width: '36px',
      height: '36px', borderRadius: '50%', border: '3px solid #0284c7', zIndex: '2147483646', pointerEvents: 'none' });
    document.body.append(d);
    d.animate([{ transform: 'scale(.3)', opacity: .9 }, { transform: 'scale(1.5)', opacity: 0 }], { duration: 480 })
      .onfinish = () => d.remove();
    document.querySelector(${JSON.stringify(selector)}).click();
  })()`);
  await sleep(300);
}
async function type(selector, text) {  // fast typing effect, three characters per step
  await pointAt(selector);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  for (let i = 3; i < text.length + 3; i += 3) {
    await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)});
      e.value = ${JSON.stringify(text)}.slice(0, ${i}); e.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(20);
  }
  await sleep(150);
}
async function scrollTo(selector, block = "start") {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({ block: '${block}', behavior: 'smooth' })`);
  await sleep(650);
}
async function scrollBy(dy, ms = 1200) {
  await evaluate(`window.scrollBy({ top: ${dy}, behavior: 'smooth' })`);
  await sleep(ms);
}
async function loadExample(id) {
  if (!(await evaluate(`document.querySelector('#examples').open`))) await click("#examples > summary");
  await click(`[data-id="${id}"]`);
  await waitFor(`document.querySelector('#request-json').value.includes('"${id}"')`);
  await sleep(250);
}
async function submitAndWait(requestText) {
  await evaluate(`window.__prev = document.querySelector('#meta')?.innerText || ''`);
  await click("#submit-btn");
  await waitFor(`(document.querySelector('#meta')?.innerText || '') !== window.__prev &&
    document.querySelector('#meta').innerText.includes(${JSON.stringify(requestText)})`, 30000);
  await sleep(200);
  await scrollTo("#answer-panel");
}

// ---------------------------------------------------------------- the demo (under one minute)
async function demo() {
  await sleep(900);
  // 1. Sign in with ID Austria (simulated)
  await click("#idaustria-btn");
  await waitFor(`location.pathname === '/idp-sim/authorize' && document.querySelectorAll('.idp-person').length === 3`);
  cursor = { x: W / 2, y: H / 2 };
  await sleep(400);
  await click(".idp-person:first-child", { scroll: false });
  await click("#idp-confirm", { scroll: false });
  await waitFor(`location.pathname === '/' && !document.querySelector('#identity-in').classList.contains('hidden')`);
  await pointAt("#identity-in");
  await sleep(700);

  // 2. Prohibited purpose -> rejected before any data is touched
  await loadExample("R10");
  await submitAndWait("Request R10");
  await pointAt("#decision");
  await sleep(1200);
  await pointAt("#meta");
  await sleep(900);

  // 3. Anonymised statistics with small-cell suppression
  await scrollTo("#request-panel");
  await loadExample("R08");
  await submitAndWait("Request R08");
  await pointAt("#stat-table tbody tr:first-child td:nth-child(2)");
  await sleep(700);
  await pointAt("#stat-table tbody tr:nth-child(3) td:nth-child(3)");
  await sleep(900);

  // 4. Secure processing environment: exact cohort, blocked download
  await scrollTo("#request-panel");
  await loadExample("R05");
  await submitAndWait("Request R05");
  await pointAt("#cohort-size");
  await sleep(1000);
  await click("#download-btn");
  await waitFor(`document.querySelectorAll('#download-result tbody tr').length > 0`);
  await pointAt("#download-result");
  await sleep(1300);

  // 5. A new request written in the form (derived value: length of stay)
  await scrollTo("#request-panel");
  await evaluate(`document.querySelector('#examples').open = false; document.querySelector('#clear-btn').click()`);
  await sleep(300);
  await type("#f-purpose", "Research on hospital efficiency to plan beds.");
  await type("#f-question", "Mean length of inpatient stays in 2025 by hospital?");
  await type("#f-defs .def-row:last-child .def-input", "Inpatient stay = encounter with type 'inpatient'.");
  await click("#add-def");
  await type("#f-defs .def-row:last-child .def-input", "Count stays whose start_date is in 2025.");
  await click("#add-def");
  await type("#f-defs .def-row:last-child .def-input", "Report per hospital: inpatient stays and mean length of stay.");
  await submitAndWait("Request WEB-");
  await pointAt("#stat-table");
  await sleep(1300);

  // 6. Staff view and the evaluation metrics
  await click("#meta a");
  await waitFor(`document.querySelector('#view-staff').classList.contains('active') && document.querySelector('#case-detail .facts')`);
  await sleep(700);
  await scrollBy(500, 1100);
  await scrollBy(600, 1100);
  await evaluate(`window.scrollTo({ top: 0 })`);
  await click("#tab-evaluation");
  await waitFor(`document.querySelectorAll('#eval-cards .card').length === 5`, 5000).catch(() => {});
  await pointAt("#eval-cards");
  await sleep(1500);
}

try {
  if (!CHROME) throw new Error("Chrome not found (set CHROME_BIN)");
  for (let i = 0; i < 50 && !ws; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === "page");
      if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
    } catch (e) { await sleep(200); }
  }
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id); pending.delete(msg.id);
      msg.error ? p.rej(new Error(msg.error.message)) : p.res(msg.result);
    } else if (msg.method === "Page.screencastFrame") {
      const file = join(frameDir, `${String(frames.length).padStart(6, "0")}.jpg`);
      writeFileSync(file, Buffer.from(msg.params.data, "base64"));
      frames.push({ file, t: msg.params.metadata.timestamp });
      send("Page.screencastFrameAck", { sessionId: msg.params.sessionId });
    }
  };
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DPR, mobile: false });
  await send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: W * DPR, maxHeight: H * DPR });
  await send("Page.navigate", { url: BASE });  // recording from the first paint captures the opening animation
  await waitFor(`document.querySelectorAll('#request-list .req').length >= 10`);
  console.log("recording ...");
  await demo();
  await send("Page.stopScreencast");
  await sleep(300);

  // constant-frame-rate MP4 from the variable-rate screencast frames: macOS AVFoundation, else ffmpeg
  console.log(`${frames.length} frames, ${(frames[frames.length - 1].t - frames[0].t).toFixed(1)} s`);
  const tsv = join(frameDir, "frames.tsv");
  writeFileSync(tsv, frames.map(f => `${f.file}\t${f.t}`).join("\n"));
  const swift = join(dirname(fileURLToPath(import.meta.url)), "encode_frames.swift");
  let enc = spawnSync("swift", [swift, tsv, OUT, "30"], { stdio: "inherit" });
  if (enc.error || enc.status !== 0) {
    const lines = [];
    frames.forEach((f, i) => {
      const next = frames[i + 1];
      lines.push(`file '${f.file}'`, `duration ${next ? Math.max(0.001, next.t - f.t).toFixed(4) : "1.5"}`);
    });
    lines.push(`file '${frames[frames.length - 1].file}'`);
    writeFileSync(join(frameDir, "frames.txt"), lines.join("\n"));
    enc = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", join(frameDir, "frames.txt"),
      "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", OUT], { stdio: "inherit" });
  }
  if (enc.error || enc.status !== 0) throw new Error("no encoder worked (needs macOS swift or ffmpeg)");
  console.log(`video written to ${OUT}`);
} catch (e) {
  console.error(`recording failed: ${e.message}`);
  process.exitCode = 1;
} finally {
  try { ws?.close(); } catch (e) { /* ignore */ }
  chrome.kill();
  rmSync(frameDir, { recursive: true, force: true });
  setTimeout(() => rmSync(profile, { recursive: true, force: true }), 500);
}
