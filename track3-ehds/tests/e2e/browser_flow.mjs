// End-to-end browser test of the demo flow (headless Chrome via the DevTools protocol, no npm packages).
// Usage: node tests/e2e/browser_flow.mjs [http://127.0.0.1:8000] [screenshot-dir]
// Requires Node >= 22 (global WebSocket) and Google Chrome / Chromium.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const SHOTS = process.argv[3] || "reports/screenshots";
const CHROME = process.env.CHROME_BIN || [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].find(p => existsSync(p));
if (!CHROME) { console.error("Chrome not found; set CHROME_BIN"); process.exit(2); }
mkdirSync(SHOTS, { recursive: true });

const port = 9300 + Math.floor(Math.random() * 500);
const profile = join(tmpdir(), `desk-e2e-${process.pid}`);
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--window-size=1440,1100", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let ws, msgId = 0;
const pending = new Map();
const consoleErrors = [];
const results = [];

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = targets.find(t => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch (e) { /* not up yet */ }
    await sleep(200);
  }
  throw new Error("Chrome DevTools endpoint did not come up");
}

function send(method, params = {}) {
  const id = ++msgId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`JS error: ${r.exceptionDetails.text} ${JSON.stringify(r.exceptionDetails.exception?.description || "")}`);
  return r.result.value;
}

async function waitFor(expression, timeout = 15000, what = expression) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { if (await evaluate(expression)) return Date.now() - t0; } catch (e) { /* retry */ }
    await sleep(100);
  }
  throw new Error(`timeout waiting for ${what}`);
}

async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(join(SHOTS, `${name}.png`), Buffer.from(r.data, "base64"));
}

async function step(name, fn) {
  try {
    const detail = await fn();
    results.push({ name, ok: true, detail });
    console.log(`  PASS  ${name}${detail ? ` — ${detail}` : ""}`);
  } catch (e) {
    results.push({ name, ok: false, detail: String(e.message || e) });
    console.log(`  FAIL  ${name} — ${e.message || e}`);
  }
}

const text = sel => `(document.querySelector(${JSON.stringify(sel)})?.innerText || "")`;

async function submit(id) {
  await evaluate(`document.querySelector('[data-id="${id}"]').click()`);
  await waitFor(`document.querySelector('#request-json').value.includes('"${id}"')`, 5000, `${id} loaded`);
  await evaluate(`window.__prevCase = ${text("#meta")}; document.querySelector('#submit-btn').click()`);
  const ms = await waitFor(`${text("#meta")} !== window.__prevCase && ${text("#meta")}.includes("Request ${id}")`, 30000, `${id} answer`);
  return ms;
}

try {
  ws = new WebSocket(await connect());
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id); pending.delete(msg.id);
      msg.error ? p.reject(new Error(msg.error.message)) : p.resolve(msg.result);
    } else if (msg.method === "Runtime.exceptionThrown") {
      consoleErrors.push(msg.params.exceptionDetails.text);
    } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      consoleErrors.push(msg.params.args.map(a => a.value || a.description).join(" "));
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      const e = msg.params.entry;
      // Intended HTTP errors: the blocked SPE download (403) and the deliberately invalid request (400).
      const expected = (e.url || "").match(/\/api\/spe\/[^/]+\/download/) && e.text.includes("403")
        || (e.url || "").endsWith("/api/submit") && e.text.includes("400");
      if (!expected) consoleErrors.push(`${e.source}: ${e.text} ${e.url || ""}`);
    }
  };
  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: BASE });
  console.log(`E2E browser test against ${BASE}`);

  await step("App loads with request list", async () => {
    await waitFor(`document.querySelectorAll('#request-list .req').length >= 10`, 15000, "request list");
    return `${await evaluate(`document.querySelectorAll('#request-list .req').length`)} requests listed`;
  });
  await step("Simulation label is visible", async () => {
    const t = await evaluate(text("#sim-banner"));
    if (!/hackathon simulation/i.test(t) || !/not a real government approval system/i.test(t)) throw new Error(t);
    return t.trim().slice(0, 60) + "…";
  });
  await step("R10 nicotine pouches -> REJECT, Art. 54, no data queried", async () => {
    const ms = await submit("R10");
    const code = await evaluate(text("#decision-code"));
    const arts = await evaluate(text("#articles"));
    const meta = await evaluate(text("#meta"));
    if (code !== "REJECT" || !arts.includes("Art. 54") || !/Patient data queried: no/.test(meta)) throw new Error(`${code} ${arts} ${meta}`);
    await shot("01-r10-reject");
    return `answered in ${ms} ms`;
  });
  await step("R08 statistics -> APPROVE_STATISTICAL with <10 and suppressed cells", async () => {
    await submit("R08");
    const code = await evaluate(text("#decision-code"));
    const rows = await evaluate(`[...document.querySelectorAll('#stat-table tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()))`);
    const by = Object.fromEntries(rows.map(r => [r[0], r.slice(1)]));
    if (code !== "APPROVE_STATISTICAL") throw new Error(code);
    if (rows.length !== 9) throw new Error(`${rows.length} rows`);
    if (by["Burgenland"].join("|") !== "<10|suppressed") throw new Error(JSON.stringify(by["Burgenland"]));
    if (by["Niederösterreich"].join("|") !== "15|27.2" || by["Wien"].join("|") !== "14|26.6") throw new Error(JSON.stringify(by));
    await shot("02-r08-statistics");
    return "9 regions, small cells masked, NÖ 15 / 27.2";
  });
  await step("R01 statistics -> prevalence table", async () => {
    await submit("R01");
    const rows = await evaluate(`[...document.querySelectorAll('#stat-table tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()))`);
    const wien = rows.find(r => r[0] === "Wien");
    if (!wien || wien.slice(1).join("|") !== "3 247|263|8.1") throw new Error(JSON.stringify(wien));
    return "Wien 3 247 adults, 263 with T2D, 8.1 %";
  });
  await step("R05 -> APPROVE_SPE, exact cohort 1152, record types listed", async () => {
    await submit("R05");
    const code = await evaluate(text("#decision-code"));
    const n = await evaluate(text("#cohort-size"));
    const types = await evaluate(`[...document.querySelectorAll('#spe-table tbody tr')].map(tr => tr.cells[0].innerText + ':' + tr.cells[4].innerText)`);
    if (code !== "APPROVE_SPE" || n.replace(/\s/g, "") !== "1152") throw new Error(`${code} ${n}`);
    if (types.length !== 3 || !types.some(t => t.includes("LOINC 4548-4"))) throw new Error(JSON.stringify(types));
    return `cohort ${n}; ${types.join(" | ")}`;
  });
  await step("R05 download attempt is blocked (HTTP 403)", async () => {
    await evaluate(`document.querySelector('#download-btn').click()`);
    await waitFor(`${text("#download-result")}.includes("403")`, 10000, "blocked banner");
    const t = await evaluate(text("#download-result"));
    if (!/Download blocked/.test(t)) throw new Error(t);
    await shot("03-r05-spe-download-blocked");
    return t.split("\n")[0];
  });
  await step("N01 new request: primary_icd10 + hospital grouping", async () => {
    await submit("N01");
    const rows = await evaluate(`[...document.querySelectorAll('#stat-table tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()))`);
    const s = rows.map(r => r.join(":")).join(", ");
    if (s !== "Klinikum Nord:66, Klinikum Süd:60, Klinikum West:31") throw new Error(s);
    await shot("04-n01-new-request");
    return s;
  });
  await step("Pasted custom request (edited JSON) is processed", async () => {
    const custom = {
      id: "PASTE-1", applicant: { name: "Demo", organisation: "Jury test", country: "AT" },
      requested_as: "health data request", requested_format: "anonymised statistics",
      purpose: "Research on asthma care quality in children to improve treatment guidelines.",
      question: "How many children have asthma, by sex?",
      definitions: ["Children = aged under 18 on 31 December 2025.", "Asthma = any condition with an ICD-10 code starting with J45.",
        "Report per sex: children with asthma."],
    };
    await evaluate(`document.querySelector('#request-json').value = ${JSON.stringify(JSON.stringify(custom, null, 2))}; window.__prevCase = ${text("#meta")}; document.querySelector('#submit-btn').click()`);
    await waitFor(`${text("#meta")} !== window.__prevCase && ${text("#meta")}.includes("PASTE-1")`, 30000, "custom answer");
    const rows = await evaluate(`[...document.querySelectorAll('#stat-table tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()).join(':'))`);
    if (rows.length !== 2) throw new Error(JSON.stringify(rows));
    return rows.join(", ");
  });
  await step("Invalid JSON gives a clear error", async () => {
    await evaluate(`document.querySelector('#request-json').value = '{"requested_as": "health data request"'; document.querySelector('#submit-btn').click()`);
    await waitFor(`${text("#decision-code")} === "INVALID_REQUEST"`, 10000, "invalid request");
    return (await evaluate(text("#result"))).split("\n").slice(0, 2).join(" ");
  });
  await step("Staff view shows decision trace, privacy checks, plan and SQL", async () => {
    await submit("R08");
    await evaluate(`[...document.querySelectorAll('#meta a')].find(a => a.innerText.includes('staff')).click()`);
    await waitFor(`${text("#case-detail")}.includes("Privacy checks")`, 10000, "case detail");
    const t = await evaluate(text("#case-detail"));
    for (const must of ["Decision trace", "Privacy checks", "Interpretation", "Query plan", "Generated parameterized SQL", "Opted-out patients excluded"]) {
      if (!t.includes(must)) throw new Error(`missing '${must}'`);
    }
    await evaluate(`document.querySelectorAll('#case-detail details').forEach(d => d.open = true)`);
    await shot("05-staff-view");
    return "all sections present";
  });
  await step("Evaluation tab shows the five metrics", async () => {
    await evaluate(`document.querySelector('#tab-evaluation').click(); document.querySelector('#run-eval').click()`);
    await waitFor(`document.querySelectorAll('#eval-cards .card').length === 5`, 120000, "metrics");
    const cards = await evaluate(`[...document.querySelectorAll('#eval-cards .card')].map(c => c.innerText.replace(/\\n/g, ' '))`);
    if (!cards[0].startsWith("10/10") || !cards[1].startsWith("6/6") || !cards[2].startsWith("0") || !cards[3].startsWith("10/10")) throw new Error(JSON.stringify(cards));
    await shot("06-evaluation");
    return cards.join(" | ");
  });
  await step("No browser console errors (incl. CSP violations)", async () => {
    if (consoleErrors.length) throw new Error(consoleErrors.join(" || "));
    return "0 errors";
  });
} catch (e) {
  results.push({ name: "harness", ok: false, detail: String(e) });
  console.log("  FAIL  harness —", e);
} finally {
  try { ws && ws.close(); } catch (e) { /* ignore */ }
  chrome.kill("SIGKILL");
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) { /* ignore */ }
}
const failed = results.filter(r => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} browser checks passed; screenshots in ${SHOTS}`);
writeFileSync(join(SHOTS, "e2e-results.json"), JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);
