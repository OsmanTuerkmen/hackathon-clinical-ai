"use strict";

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const ICONS = {
  check: ["M5 12.5l4.5 4.5L19 7"],
  x: ["M6 6l12 12M18 6L6 18"],
  lock: ["M6 11h12v9H6z", "M8.5 11V8a3.5 3.5 0 0 1 7 0v3"],
  alert: ["M12 7v6", "M12 17h.01"],
  minus: ["M7 12h10"],
  shield: ["M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z", "M9 12l2 2 4-4"],
  download: ["M12 4v11", "M7 10l5 5 5-5", "M5 20h14"],
  info: ["M12 11v6", "M12 7h.01"],
};

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2.4",
    "stroke-linecap": "round", "stroke-linejoin": "round", class: "ico", "aria-hidden": "true" })) svg.setAttribute(k, v);
  for (const d of ICONS[name]) {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  return { status: res.status, ok: res.ok, body };
}

const OUTCOME_SHORT = {
  REJECT: "Rejected",
  APPROVE_STATISTICAL: "Approved · anonymised statistics",
  APPROVE_SPE: "Approved · secure processing environment",
  NO_DECISION: "No automated decision",
};
const OUTCOME_ICON = { REJECT: "x", APPROVE_STATISTICAL: "check", APPROVE_SPE: "lock", NO_DECISION: "alert" };
const ARTICLE_HELP = {
  53: "Art. 53 – purposes for which health data may be used for secondary use: public health, policy, official statistics, teaching, scientific research (incl. training algorithms), improving care.",
  54: "Art. 54 – prohibited uses: decisions detrimental to people, insurance/credit/job decisions, advertising or marketing, developing harmful products such as tobacco or nicotine.",
  66: "Art. 66 – data minimisation: anonymised data by default; pseudonymised data only if the applicant shows the purpose cannot be achieved with anonymised data.",
  67: "Art. 67 – health data access applications.",
  68: "Art. 68 – data permit: the conditions under which pseudonymised data is made available.",
  69: "Art. 69 – health data request: answered only in an anonymised statistical format.",
  71: "Art. 71 – right to opt out: opted-out patients are excluded from secondary use.",
  73: "Art. 73 – secure processing environment: access only inside the SPE; only non-personal results may leave it after review.",
};
const TABLE_TITLES = {
  patients: "Patients (demographics)", conditions: "Conditions (ICD-10)", medications: "Medications (ATC)",
  observations: "Observations (LOINC)", encounters: "Encounters",
};

function fmt(v) {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US").replace(/,/g, " ") : v.toFixed(1);
  return String(v);
}
const isMasked = v => v === "<10" || v === "suppressed";

function masked(v) {
  return el("span", { class: "masked", title: v === "<10" ? "Count below 10 (small-cell rule)" : "Suppressed: based on fewer than 10 patients", text: v });
}

// ------------------------------------------------------------------ tabs + header
function showTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `view-${name}`));
  if (name === "staff") loadCases();
}
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));

api("/api/health").then(({ body }) => {
  if (!body || !body.data) return;
  const s = body.data;
  $("#data-pill").replaceChildren("Synthetic data · ", el("b", { text: fmt(s.patients_eligible) }), " patients · ",
    el("b", { text: fmt(s.patients_opted_out) }), " opt-outs excluded · 3 hospitals");
});

// ------------------------------------------------------------------ applicant: requests
let selectedRequest = null;
let allRequests = [];

async function loadRequests() {
  const { body } = await api("/api/requests");
  allRequests = body || [];
  renderRequestList();
}

function renderRequestList() {
  const q = ($("#request-filter").value || "").trim().toLowerCase();
  const list = $("#request-list");
  list.replaceChildren();
  const groups = [["supplied", "Supplied requests (R01–R10)"], ["new", "New test requests (ours)"]];
  let shown = 0;
  for (const [g, title] of groups) {
    const items = allRequests.filter(r => r.group === g &&
      (!q || `${r.id} ${r.applicant} ${r.question} ${r.requested_as}`.toLowerCase().includes(q)));
    if (!items.length) continue;
    list.append(el("div", { class: "group-title", text: title }));
    for (const r of items) {
      shown++;
      const app = r.requested_as === "health data access application";
      list.append(el("button", { class: `req${r.id === selectedRequest ? " selected" : ""}`, "data-id": r.id, title: r.question,
        type: "button", onclick: () => pickRequest(r.id) },
        el("span", { class: "rid", text: r.id }),
        el("span", {},
          el("div", { class: "org", text: r.applicant || "(no organisation)" }),
          el("div", { class: "q", text: r.question }),
          el("span", { class: `type-badge ${app ? "t-application" : "t-request"}`, text: app ? "access application" : "health data request" }))));
    }
  }
  if (!shown) list.append(el("p", { class: "hint", text: "No request matches the filter." }));
}
$("#request-filter").addEventListener("input", renderRequestList);

async function pickRequest(id) {
  const res = await fetch(`/api/requests/${encodeURIComponent(id)}`);
  const text = await res.text();
  let pretty = text;
  try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* keep raw */ }
  $("#request-json").value = pretty;
  selectedRequest = id;
  document.querySelectorAll(".req").forEach(b => b.classList.toggle("selected", b.dataset.id === id));
  $("#editor-hint").textContent = `Loaded ${id}. Edit the JSON if you like, then submit (Ctrl/⌘ + Enter).`;
}

$("#file-input").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const text = await file.text();
  let pretty = text;
  try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* invalid JSON is reported on submit */ }
  $("#request-json").value = pretty;
  selectedRequest = null;
  document.querySelectorAll(".req").forEach(b => b.classList.remove("selected"));
  $("#editor-hint").textContent = `Loaded file ${file.name}.`;
  ev.target.value = "";
});

$("#format-btn").addEventListener("click", () => {
  try {
    $("#request-json").value = JSON.stringify(JSON.parse($("#request-json").value), null, 2);
    $("#editor-hint").textContent = "JSON formatted.";
  } catch (e) {
    $("#editor-hint").textContent = `Not valid JSON yet: ${e.message}`;
  }
});
$("#clear-btn").addEventListener("click", () => {
  $("#request-json").value = "";
  selectedRequest = null;
  document.querySelectorAll(".req").forEach(b => b.classList.remove("selected"));
  $("#request-json").focus();
});
$("#request-json").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); submitRequest(); }
});
$("#submit-btn").addEventListener("click", submitRequest);

async function submitRequest() {
  const btn = $("#submit-btn");
  const text = $("#request-json").value.trim();
  if (!text) { $("#editor-hint").textContent = "Paste or select a request first."; return; }
  if (btn.disabled) return;
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), "Processing…");
  $("#answer-empty").classList.add("hidden");
  $("#busy").classList.remove("hidden");
  const t0 = performance.now();
  try {
    const res = await fetch("/api/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: text });
    const view = await res.json();
    view._roundtrip_ms = Math.round(performance.now() - t0);
    renderAnswer(view);
  } catch (e) {
    renderAnswer({ status: "INVALID_REQUEST", errors: [`The desk could not be reached: ${e.message}`] });
  } finally {
    $("#busy").classList.add("hidden");
    btn.disabled = false;
    btn.textContent = "Submit request";
  }
}

// ------------------------------------------------------------------ applicant: answer
function steps(view) {
  const d = view.decision || {};
  const f = view.fulfilment || {};
  const res = view.result || {};
  const ps = view.privacy_summary || {};
  const S = (state, title, detail) => ({ state, title, detail });
  const skip = (title) => S("skip", title, "not needed");
  if (view.status === "INVALID_REQUEST") {
    return [S("stop", "Format", "invalid JSON or missing fields"), skip("Purpose"),
      skip("Route"), skip("Query plan"), skip("Data access"), skip("Privacy audit")];
  }
  const out = [S("ok", "Format", "valid request")];
  if (d.outcome === "REJECT") {
    return out.concat([S("stop", "Purpose", "prohibited use (Art. 54)"), skip("Route"), skip("Query plan"),
      S("skip", "Data access", "none – no patient data touched"), skip("Privacy audit")]);
  }
  if (d.outcome === "NO_DECISION") {
    return out.concat([S("warn", "Purpose", "no Art. 53 purpose recognised"), S("warn", "Route", "referred to staff"),
      skip("Query plan"), skip("Data access"), skip("Privacy audit")]);
  }
  out.push(S("ok", "Purpose", "allowed (Art. 53), not prohibited"));
  out.push(d.outcome === "APPROVE_SPE" ? S("lock", "Route", "secure processing environment")
    : S("ok", "Route", (d.articles || []).includes("66") ? "statistics instead of records" : "anonymised statistics"));
  if (f.status === "NOT_PRODUCED") {
    return out.concat([S("warn", "Query plan", "could not interpret safely"), skip("Data access"), skip("Privacy audit")]);
  }
  out.push(S("ok", "Query plan", "generated from the definitions"));
  out.push(res.kind === "spe" ? S("lock", "Data access", `${fmt(res.cohort_size)} patients copied, downloads blocked`)
    : S("ok", "Data access", "computed inside the desk, opt-outs excluded"));
  out.push(f.status === "WITHHELD" ? S("stop", "Privacy audit", "failed – nothing released")
    : S("ok", "Privacy audit", `${ps.passed}/${ps.total} checks passed`));
  return out;
}

function renderSteps(view) {
  const iconFor = { ok: "check", stop: "x", warn: "alert", skip: "minus", lock: "lock" };
  $("#stepper").replaceChildren(...steps(view).map((s, i) => el("li", { class: s.state },
    el("span", { class: "si" }, icon(iconFor[s.state])),
    el("span", {}, el("b", { text: `${i + 1}. ${s.title}` }), el("span", { class: "d", text: s.detail })))));
}

function renderAnswer(view) {
  $("#answer-empty").classList.add("hidden");
  $("#answer").classList.remove("hidden");
  const box = $("#decision");
  const result = $("#result");
  result.replaceChildren();
  $("#decision-notes").replaceChildren();
  $("#articles").replaceChildren();
  renderSteps(view);

  if (view.status === "INVALID_REQUEST") {
    box.className = "decision d-INVALID";
    $("#decision-icon").replaceChildren(icon("alert"));
    $("#decision-label").textContent = "Request not valid";
    $("#decision-code").textContent = "INVALID_REQUEST";
    $("#reason").textContent = "The request does not follow the expected JSON format, so it was not assessed.";
    result.append(el("div", { class: "callout amber" }, el("h3", {}, icon("alert"), "Problems found"),
      el("ul", {}, (view.errors || []).map(e => el("li", { text: e })))));
    $("#result-title").textContent = "No answer";
    $("#meta").replaceChildren();
    return;
  }

  const d = view.decision;
  box.className = `decision d-${d.outcome}`;
  $("#decision-icon").replaceChildren(icon(OUTCOME_ICON[d.outcome] || "info"));
  $("#decision-label").textContent = OUTCOME_SHORT[d.outcome] || d.label;
  $("#decision-code").textContent = d.outcome;
  for (const a of d.articles || []) {
    $("#articles").append(el("span", { class: "chip", title: ARTICLE_HELP[a] || "" },
      el("b", { text: `Art. ${a}` }), ` · ${d.article_titles[a] || ""}`));
  }
  $("#reason").textContent = d.reason;
  for (const n of d.notes || []) $("#decision-notes").append(el("li", { text: n }));

  const ps = view.privacy_summary || {};
  $("#meta").replaceChildren(...[
    el("span", {}, "Case ", el("b", { text: view.case_id })),
    el("span", { text: `Request ${view.request_id}` }),
    el("span", { text: `Answered in ${view.elapsed_ms} ms (round trip ${view._roundtrip_ms ?? "?"} ms)` }),
    el("span", {}, "Patient data queried: ",
      el("b", { class: view.patient_data_queried ? "" : "ok", text: view.patient_data_queried ? "yes" : "no" })),
    ps.total ? el("span", {}, "Privacy checks: ",
      el("b", { class: ps.failed ? "no" : "ok", text: `${ps.passed}/${ps.total} passed` })) : null,
    el("a", { href: "#", onclick: (e) => { e.preventDefault(); openCase(view.case_id); }, text: "Open staff view →" }),
  ].filter(Boolean));

  const f = view.fulfilment || {};
  if (d.outcome === "REJECT") {
    $("#result-title").textContent = "No data released";
    result.append(el("div", { class: "callout red" }, el("h3", {}, icon("x"), "Request rejected"),
      el("p", { text: "The purpose is prohibited under Art. 54, so the request was rejected before any patient data was queried. No statistics or records are released." })));
    return;
  }
  if (d.outcome === "NO_DECISION") {
    $("#result-title").textContent = "Referred to staff";
    result.append(el("div", { class: "callout amber" }, el("h3", {}, icon("alert"), "No automated decision"),
      el("p", { text: f.message || "" })));
    return;
  }
  if (f.status === "NOT_PRODUCED" || f.status === "WITHHELD") {
    $("#result-title").textContent = "No numbers produced";
    const err = f.error || {};
    result.append(el("div", { class: "callout amber" },
      el("h3", {}, icon("alert"), f.status === "WITHHELD" ? "Answer withheld" : "The request could not be interpreted safely"),
      el("p", { text: f.message }),
      err.message ? el("p", {}, el("b", { text: "Reason: " }), `${err.message}${err.where ? ` (${err.where})` : ""}`) : null,
      err.hint ? el("p", {}, el("b", { text: "How to fix: " }), err.hint) : null));
    return;
  }
  const res = view.result;
  if (res && res.kind === "statistics") renderStatistics(result, res, view);
  if (res && res.kind === "spe") renderSpe(result, res);
  if ((view.interpretation_notes || []).length) {
    result.append(el("div", { class: "callout blue" }, el("h3", {}, icon("info"), "How the desk interpreted your request"),
      el("ul", {}, view.interpretation_notes.map(n => el("li", { text: n })))));
  }
}

function renderStatistics(root, res, view) {
  $("#result-title").textContent = "Anonymised statistics (small-cell rule applied)";
  const maskedCells = res.rows.reduce((n, r) => n + res.columns.filter(c => isMasked(r.cells[c.id])).length, 0);
  root.append(el("div", { class: "summary" },
    el("span", { class: "s" }, el("b", { text: String(res.rows.length) }), " groups"),
    el("span", { class: "s" }, el("b", { text: String(res.columns.length) }), " statistics"),
    el("span", { class: "s" }, el("b", { text: String(maskedCells) }), " cells masked"),
    el("span", { class: "s", text: "opt-outs excluded" }),
    el("span", { class: "s", text: "no patient-level data" })));

  const max = {};
  for (const c of res.columns) {
    if (c.type === "count") max[c.id] = Math.max(1, ...res.rows.map(r => typeof r.cells[c.id] === "number" ? r.cells[c.id] : 0));
  }
  const cell = (c, v) => {
    if (isMasked(v)) return el("td", { class: "num" }, masked(v));
    if (c.type !== "count" && c.type !== "percent") return el("td", { class: "num", text: fmt(v) });
    const width = c.type === "percent" ? Math.min(100, v) : (100 * v) / max[c.id];
    const bar = el("span", { class: `bar${c.type === "percent" ? " pct" : ""}` });
    bar.style.width = `${Math.max(2, width)}%`;
    return el("td", { class: "num" }, el("div", { class: "cellbar" }, el("span", { class: "track" }, bar), el("span", { text: fmt(v) })));
  };
  const head = el("tr", {},
    (res.dimensions.length ? res.dimensions : [{ label: "Group" }]).map(d => el("th", { text: d.label })),
    res.columns.map(c => el("th", { class: "num" }, c.label,
      el("small", { text: c.type === "count" ? c.unit : (c.type === "percent" ? "%, one decimal" : `${c.type}, one decimal`) }))));
  const body = res.rows.map(r => el("tr", {},
    (r.group.length ? r.group : [r.label]).map(g => el("td", { class: "grp", text: g })),
    res.columns.map(c => cell(c, r.cells[c.id]))));
  root.append(el("div", { class: "table-wrap" },
    el("table", { class: "stat-table", id: "stat-table" }, el("thead", {}, head), el("tbody", {}, body))));
  root.append(el("div", { class: "legend" },
    el("span", {}, masked("<10"), " count below 10, including 0"),
    el("span", {}, masked("suppressed"), " percentage or mean based on fewer than 10"),
    el("span", { text: "Rounded to one decimal, halves up" })));
  root.append(el("div", { class: "result-actions" }, el("button", { class: "btn secondary small", id: "csv-btn", type: "button",
    onclick: () => downloadCsv(res, view) }, icon("download"), "Download table (CSV)")));
}

function downloadCsv(res, view) {
  const q = v => /[",\n;]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
  const dims = res.dimensions.length ? res.dimensions.map(d => d.label) : ["Group"];
  const lines = [[...dims, ...res.columns.map(c => c.label)].map(q).join(",")];
  for (const r of res.rows) {
    lines.push([...(r.group.length ? r.group : [r.label]), ...res.columns.map(c => r.cells[c.id])].map(q).join(","));
  }
  const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob), download: `${view.request_id || "request"}-anonymised-statistics.csv` });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

function renderSpe(root, res) {
  $("#result-title").textContent = "Secure processing environment prepared";
  root.append(el("div", { class: "spe-head" },
    el("div", { class: "big-number" },
      el("div", { class: "n", id: "cohort-size", text: fmt(res.cohort_size) }),
      el("div", { class: "l", text: "patients selected (exact count)" })),
    el("div", { class: "spe-info" },
      el("div", {}, "Workspace ", el("code", { text: res.workspace_id })),
      el("div", {}, "Storage ", el("code", { text: res.storage })),
      el("div", { text: "Only the selected patients and the requested record types were copied in. Pseudonymous patient IDs are kept so records can be linked inside the environment." }),
      el("div", {}, "Download policy: ", el("span", { class: "badge b-REJECT", text: "records cannot leave the SPE" })))));

  const rows = Object.entries(res.tables).map(([t, info]) => el("tr", {},
    el("td", {}, el("b", { text: TABLE_TITLES[t] || t })),
    el("td", { class: "num", text: fmt(info.rows) }),
    el("td", { class: "num", text: fmt(info.patients) }),
    el("td", { text: info.columns.join(", ") }),
    el("td", { text: info.filter && info.filter.loinc ? `LOINC ${info.filter.loinc.join(", ")} only` : "all of the cohort's rows" })));
  root.append(el("div", { class: "table-wrap" }, el("table", { id: "spe-table" },
    el("thead", {}, el("tr", {}, ["Record type copied", "Rows", "Patients", "Columns", "Filter"].map((h, i) =>
      el("th", { class: i === 1 || i === 2 ? "num" : "", text: h })))),
    el("tbody", {}, rows))));
  const missing = Object.keys(TABLE_TITLES).filter(t => !(t in res.tables));
  if (missing.length) {
    root.append(el("div", { class: "not-copied" }, "Not requested, so not copied (data minimisation, Art. 66):",
      missing.map(t => el("span", { class: "off", text: TABLE_TITLES[t] }))));
  }

  const out = el("div", { class: "blocked", id: "download-result" });
  const btn = el("button", { class: "btn danger", id: "download-btn", type: "button", onclick: async () => {
    btn.disabled = true;
    const r = await api(`/api/spe/${res.workspace_id}/download`, { method: "POST" });
    const log = await api(`/api/spe/${res.workspace_id}`);
    btn.disabled = false;
    const entries = ((log.body && log.body.access_log) || []).slice(-6).reverse();
    out.replaceChildren(el("div", { class: "callout red" },
      el("h3", {}, icon("lock"), `Download blocked · HTTP ${r.status}`),
      el("p", { text: (r.body && r.body.message) || "Blocked." }),
      entries.length ? el("table", {}, el("thead", {}, el("tr", {}, ["Time (UTC)", "Actor", "Action", "Result"].map(h => el("th", { text: h })))),
        el("tbody", {}, entries.map(e => el("tr", {}, el("td", { text: e.time }), el("td", { text: e.actor }),
          el("td", { text: e.action }), el("td", {}, el("b", { class: e.result === "BLOCKED" ? "bad-text" : "", text: e.result })))))) : null));
  } }, icon("download"), "Download records (CSV)");
  root.append(el("div", { class: "actions" }, btn,
    el("span", { class: "hint", text: "Try it: record downloads are refused and logged (Art. 73)." })), out);
}

// ------------------------------------------------------------------ staff
let selectedCase = null;

async function loadCases() {
  const { body } = await api("/api/cases");
  const tbody = $("#cases-table tbody");
  tbody.replaceChildren();
  for (const c of body || []) {
    const tr = el("tr", { "data-case": c.case_id, class: `row-${c.outcome}`, onclick: () => selectCase(c.case_id) },
      el("td", { text: c.case_id }),
      el("td", {}, el("b", { text: c.request_id || "—" }), el("div", { class: "hint", text: c.applicant || "" })),
      el("td", {}, el("span", { class: `badge b-${c.outcome}`, text: c.outcome }),
        el("div", { class: "hint", text: (c.articles || []).length ? `Art. ${c.articles.join(", ")}` : "" })),
      el("td", { class: "num" }, el("div", { text: c.privacy }), el("div", { class: "hint", text: `${c.elapsed_ms} ms` })));
    if (c.case_id === selectedCase) tr.classList.add("selected");
    tbody.append(tr);
  }
  if (!body || !body.length) tbody.append(el("tr", {}, el("td", { colspan: 4, class: "hint", text: "No cases yet. Submit a request in the applicant portal." })));
}
$("#refresh-cases").addEventListener("click", loadCases);

async function openCase(id) {
  showTab("staff");
  await selectCase(id);
}

function section(title, open, ...content) {
  return el("details", { class: "section", open: open || null }, el("summary", { text: title }),
    el("div", { class: "section-body" }, ...content));
}

async function selectCase(id) {
  selectedCase = id;
  document.querySelectorAll("#cases-table tbody tr").forEach(tr => tr.classList.toggle("selected", tr.dataset.case === id));
  const { body: v } = await api(`/api/cases/${id}`);
  const root = $("#case-detail");
  root.replaceChildren();
  if (!v) { root.append(el("div", { class: "empty", text: "Case not found." })); return; }
  const req = v.request || {};
  const d = v.decision_detail || {};
  root.append(el("div", { class: "panel-head" },
    el("h2", { text: `${v.case_id} · ${req.id || ""}` }),
    d.outcome ? el("span", { class: `badge b-${d.outcome}`, text: d.outcome }) : null));

  if (v.status === "INVALID_REQUEST") {
    root.append(el("div", { class: "callout amber" }, el("ul", {}, (v.errors || []).map(e => el("li", { text: e })))));
    return;
  }
  const ap = req.applicant || {};
  const checks = v.privacy_checks || [];
  const fact = (k, val) => el("div", { class: "fact" }, el("small", { text: k }), el("span", { text: val }));
  root.append(el("div", { class: "facts" },
    fact("Applicant", ap.organisation || ap.name || "—"),
    fact("Requested as", req.requested_as || "—"),
    fact("Articles", (d.articles || []).map(a => `Art. ${a}`).join(", ") || "—"),
    fact("Fulfilment", (v.fulfilment || {}).status || "—"),
    fact("Privacy checks", checks.length ? `${checks.filter(c => c.status === "pass").length}/${checks.length} passed` : "n/a"),
    fact("Answer time", `${v.elapsed_ms} ms`)));
  if (d.reason) root.append(el("p", { class: "reason", text: d.reason }));

  root.append(section("Request", true,
    el("dl", { class: "kv" },
      el("dt", { text: "Applicant" }), el("dd", { text: `${ap.name || "—"} · ${ap.organisation || "—"} (${ap.country || "—"})` }),
      el("dt", { text: "Requested as" }), el("dd", { text: `${req.requested_as} · ${req.requested_format}` }),
      el("dt", { text: "Purpose" }), el("dd", { text: req.purpose }),
      el("dt", { text: "Question" }), el("dd", { text: req.question }),
      el("dt", { text: "Definitions" }), el("dd", {}, el("ol", { class: "defs" }, (req.definitions || []).map(x => el("li", { text: x })))))));

  root.append(section("Decision trace (rule order from the challenge, Art. 53/54/66/68/69/73)", true,
    (d.trace || []).map(t => el("div", { class: "trace-step" },
      el("div", { class: "no", text: String(t.step) }),
      el("div", {}, el("div", { text: t.rule }), (t.evidence || []).map(e => el("div", { class: "ev", text: e }))),
      el("div", { class: t.result === "yes" ? "res-yes" : (t.result === "no" ? "res-no" : "res-skip"), text: t.result }))),
    (d.notes || []).length ? el("ul", { class: "notes" }, d.notes.map(n => el("li", { text: n }))) : null));

  root.append(section(`Privacy checks (${checks.filter(c => c.status === "pass").length}/${checks.length} passed)`, true,
    checks.length ? el("ul", { class: "checks" }, checks.map(c => el("li", { class: c.status },
      el("span", { class: "icon", text: c.status === "pass" ? "✓" : (c.status === "fail" ? "✗" : "!") }),
      el("div", {}, el("div", { text: c.check }), el("div", { class: "detail", text: c.detail })))))
      : el("p", { class: "hint", text: d.outcome === "REJECT" ? "Not applicable: rejected before any patient data was queried (0 queries)." : "No data released." })));

  const f = v.fulfilment || {};
  if (f.error) {
    root.append(section("Interpretation problem", true, el("div", { class: "callout amber" },
      el("p", { text: f.error.message }), f.error.where ? el("p", { class: "hint", text: f.error.where }) : null,
      f.error.hint ? el("p", { text: f.error.hint }) : null)));
  }
  const plan = v.plan;
  if (plan) {
    const concepts = Object.values(plan.concepts || {});
    const conceptRows = concepts.map(c => el("tr", {},
      el("td", { text: c.label }), el("td", { text: c.kind }), el("td", { class: "params", text: codesOf(c) }),
      el("td", { text: c.source })));
    root.append(section("Interpretation: definitions → codes", true,
      el("table", {}, el("thead", {}, el("tr", {}, ["Definition", "Interpreted as"].map(h => el("th", { text: h })))),
        el("tbody", {}, (plan.interpretation || []).map(i => el("tr", {}, el("td", { text: i.text }), el("td", { text: i.meaning }))))),
      el("h4", { text: "Concepts used by the query plan" }),
      el("table", {}, el("thead", {}, el("tr", {}, ["Concept", "Kind", "Codes / filter", "Source"].map(h => el("th", { text: h })))),
        el("tbody", {}, conceptRows)),
      v.planner ? el("p", { class: "hint", text: `Planner: ${v.planner.engine}${v.planner.llm_used ? " (LLM-assisted, validated)" : ""}` }) : null));
    const desc = plan.described || {};
    const why = [...(plan.population_reasons || []), ...(plan.notes || [])];
    root.append(section("Query plan (intermediate representation)", false,
      why.length ? el("ul", { class: "notes" }, why.map(n => el("li", { text: n }))) : null,
      el("dl", { class: "kv" },
        el("dt", { text: "Population" }), el("dd", { text: desc.population }),
        desc.cohort ? el("dt", { text: "SPE cohort" }) : null, desc.cohort ? el("dd", { text: desc.cohort }) : null,
        el("dt", { text: "Grouped by" }), el("dd", { text: (desc.groups || []).join(" × ") || "—" })),
      el("table", {}, el("thead", {}, el("tr", {}, ["Measure", "Released", "Computes"].map(h => el("th", { text: h })))),
        el("tbody", {}, (desc.measures || []).map(m => el("tr", {}, el("td", { text: m.label }),
          el("td", { text: m.visible ? "yes" : "internal" }), el("td", { text: m.computes }))))),
      el("details", {}, el("summary", { text: "Raw IR (JSON)" }), el("pre", { class: "code", text: JSON.stringify(stripIr(plan), null, 2) }))));
  }
  if ((v.sql || []).length) {
    root.append(section(`Generated parameterized SQL (${v.sql.length} statement${v.sql.length > 1 ? "s" : ""})`, false,
      v.sql.map(s => el("div", {}, el("p", { class: "hint", text: `${s.purpose} — ${s.rows} rows read inside the desk` }),
        el("pre", { class: "code", text: s.sql }), el("div", { class: "params", text: `params: ${JSON.stringify(s.params)}` })))));
  }
  if (v.spe_log) {
    root.append(section("Secure processing environment · access log", true,
      el("table", {}, el("thead", {}, el("tr", {}, ["Time (UTC)", "Actor", "Action", "Result"].map(h => el("th", { text: h })))),
        el("tbody", {}, v.spe_log.map(e => el("tr", {}, el("td", { text: e.time }), el("td", { text: e.actor }),
          el("td", { text: e.action }), el("td", {}, el("b", { class: e.result === "BLOCKED" ? "bad-text" : "", text: e.result }))))))));
  }
}

function codesOf(c) {
  if (c.kind === "condition") return "ICD-10 " + c.icd10.map(x => x.code + (x.match === "prefix" ? "*" : "")).join(", ");
  if (c.kind === "medication") return "ATC " + c.atc.map(a => a + "*").join(", ");
  if (c.kind === "observation") return `LOINC ${c.loinc}${c.pick ? ` (${c.pick} per patient)` : ""}`;
  if (c.kind === "encounter") {
    const bits = [`type ${c.types.join("/")}`];
    if (c.primary_icd10) bits.push(`primary_icd10 ${c.primary_icd10.map(x => x + "*").join(", ")}`);
    if (c.start_from || c.start_to) bits.push(`start ${c.start_from || "…"} – ${c.start_to || "…"}`);
    if (c.data_holders) bits.push(c.data_holders.join(", "));
    return bits.join("; ");
  }
  if (c.kind === "derived") return c.formula === "age" ? "age = 2025 − birth year" : `end_date − start_date${c.plus_one ? " + 1" : ""} (days)`;
  if (c.kind === "set") return "patient group";
  if (c.kind === "ratio") return "ratio × 100";
  return "";
}

function stripIr(plan) {
  const { described, interpretation, ...rest } = plan;
  return rest;
}

// ------------------------------------------------------------------ evaluation
$("#run-eval").addEventListener("click", async () => {
  const btn = $("#run-eval");
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), "Running 30 submissions…");
  try {
    const { body } = await api("/api/evaluate", { method: "POST" });
    renderEvaluation(body);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run evaluation (R01–R10 × 3 runs)";
  }
});

function renderEvaluation(rep) {
  if (!rep || !rep.metrics) return;
  const m = rep.metrics;
  const card = (v, t, good) => el("div", { class: `card ${good ? "good" : "bad"}` }, el("div", { class: "v", text: v }), el("div", { class: "t", text: t }));
  $("#eval-cards").replaceChildren(
    card(`${m.correct_decisions}/${m.decisions_total}`, "Correct decisions (decision + articles)", m.correct_decisions === m.decisions_total),
    card(`${m.correct_numbers}/${m.numbers_total}`, "Correct numbers (approved requests)", m.correct_numbers === m.numbers_total),
    card(String(m.privacy_leaks), "Privacy leaks", m.privacy_leaks === 0),
    card(`${m.consistent}/${m.decisions_total}`, `Consistent across ${m.runs} runs`, m.consistent === m.decisions_total),
    card(`${(m.slowest_ms / 1000).toFixed(2)} s`, `Slowest answer (${m.slowest_request}), target < 60 s`, m.slowest_ms < 60000));
  const rows = Object.entries(rep.requests).map(([rid, r]) => el("tr", {},
    el("td", {}, el("b", { text: rid })),
    el("td", {}, el("span", { class: `badge b-${r.decision}`, text: r.decision })),
    el("td", { text: r.articles.join(", ") }),
    el("td", { class: r.decision_ok ? "ok-text" : "bad-text", text: r.decision_ok ? "✓" : "✗" }),
    el("td", { class: r.numbers_ok === null ? "" : (r.numbers_ok ? "ok-text" : "bad-text"), text: r.numbers_ok === null ? "—" : (r.numbers_ok ? "✓" : "✗") }),
    el("td", { text: String(r.leaks.length) }),
    el("td", { class: r.consistent ? "ok-text" : "bad-text", text: r.consistent ? "✓" : "✗" }),
    el("td", { class: "num", text: r.ms_max.toFixed(1) })));
  $("#eval-table").replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ["Request", "Decision", "Articles", "Decision ok", "Numbers ok", "Leaks", "Consistent", "Max ms"].map(h => el("th", { text: h })))),
    el("tbody", {}, rows))), el("p", { class: "hint", text: `Mode: ${m.mode}` }));
}

// ------------------------------------------------------------------ start
loadRequests().then(() => pickRequest("R10"));
api("/api/evaluation").then(({ body }) => { if (body && body.metrics) renderEvaluation(body); });
