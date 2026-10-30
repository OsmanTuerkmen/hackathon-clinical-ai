// In-browser mock of the §3 backend. Time-based: each submitted request has a
// script of step durations; GET /requests/:id derives step states from Date.now().
import type {
  AuditEntry, Cell, Column, Decision, DecisionDetail, DownloadBlocked, FiveSafes, MetricsRow, MetricsRun,
  OverrideBody, Privacy, QueueItem, RawRequest, RequestDetail, Result, Sample, Signals, SpeWorkspace, Step,
  StepKey, StepState, TableResult,
} from "@/types";
import { CUSTOM_ANSWERS, CUSTOM_REQUESTS, KNOWLEDGE, MOCK_ARTICLES, type MockKnowledge } from "./content";
import expectedJson from "./data/expected.json";
import R01 from "./data/R01.json";
import R02 from "./data/R02.json";
import R03 from "./data/R03.json";
import R04 from "./data/R04.json";
import R05 from "./data/R05.json";
import R06 from "./data/R06.json";
import R07 from "./data/R07.json";
import R08 from "./data/R08.json";
import R09 from "./data/R09.json";
import R10 from "./data/R10.json";
import P01 from "./data/plans/R01.json";
import P03 from "./data/plans/R03.json";
import P05 from "./data/plans/R05.json";
import P07 from "./data/plans/R07.json";
import P08 from "./data/plans/R08.json";
import P09 from "./data/plans/R09.json";

type Expected = { decision: Decision; articles: string[]; reason: string; answer: unknown };
const EXPECTED = expectedJson as unknown as Record<string, Expected>;

const SAMPLE_REQUESTS: RawRequest[] = [
  R01, R02, R03, R04, R05, R06, R07, R08, R09, R10,
  CUSTOM_REQUESTS.C01, CUSTOM_REQUESTS.C02, CUSTOM_REQUESTS.C03,
] as unknown as RawRequest[];

const RAW_PLANS: Record<string, unknown> = { R01: P01, R03: P03, R05: P05, R07: P07, R08: P08, R09: P09 };

const OPTED_OUT = 839;
const REGIONS = ["Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien"];

export class MockHttpError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`HTTP ${status}`);
  }
}

// ---------------------------------------------------------------------------
// Outcome resolution
// ---------------------------------------------------------------------------

interface Outcome {
  decision: Decision;
  articles: string[];
  needsReview: boolean;
  reviewReasons: { code: string; message: string }[];
  downgradedFrom: string | null;
  answer: unknown;
  knowledge: MockKnowledge;
  reasonStaff: string;
  signals: Signals;
  injectionHits: string[];
}

const PROHIBITED_RULES: { re: RegExp; category: string; article: string }[] = [
  { re: /\b(insurance|premium|underwrit)/i, category: "insurance_pricing", article: "54(1)(b)" },
  { re: /\b(advertis|marketing|market research|campaign|promot)/i, category: "advertising_marketing", article: "54(1)(c)" },
  { re: /\b(employee|employer|hiring|job offer|contracts?\b)/i, category: "employment_decisions", article: "54(1)(b)" },
  { re: /\b(nicotine|tobacco|alcohol|weapon|gambling)/i, category: "harmful_products", article: "54(1)(d)" },
];
const INJECTION = /(ignore (all |any )?(previous|prior|above) instructions|system (note|prompt)|you are now|classify this (purpose )?as)/gi;

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return Math.abs(h);
}

function findQuote(text: string, re: RegExp): string | null {
  const m = text.match(new RegExp(`[^.]*${re.source}[^.]*`, "i"));
  return m ? m[0].trim() : null;
}

function resolveOutcome(raw: RawRequest, baseId: string): Outcome {
  const exp = EXPECTED[baseId];
  const isAccess = /access application/i.test(raw.requested_as);
  const purposeText = `${raw.purpose} ${raw.question}`;
  const injectionHits = Array.from(new Set((purposeText.match(INJECTION) ?? []).map((s) => s.toLowerCase())));

  const knowledge: MockKnowledge = KNOWLEDGE[baseId] ?? {
    purpose_short: raw.purpose.split(/[.,;]/)[0].slice(0, 42),
    category: "unclassified",
    why: "",
  };

  if (exp) {
    const rejected = exp.decision === "REJECT";
    const verdict = { prohibited: rejected, category: knowledge.category };
    return {
      decision: exp.decision,
      articles: exp.articles,
      needsReview: false,
      reviewReasons: [],
      downgradedFrom: baseId === "R09" ? "pseudonymised records" : null,
      answer: exp.answer,
      knowledge,
      reasonStaff: exp.reason,
      injectionHits: [],
      signals: {
        rules: { ...verdict },
        classifier: { ...verdict, quote: knowledge.evidence && rejected ? knowledge.evidence : null },
        redteam: { ...verdict },
        justification: knowledge.justification ?? { justified: false, quote: null, source: isAccess ? "llm" : "n/a (statistics request)" },
        injection: { flagged: false, hits: [] },
      },
    };
  }

  // Unknown / custom request: rule-based heuristic.
  const hit = PROHIBITED_RULES.find((r) => r.re.test(raw.purpose));
  const custom = CUSTOM_ANSWERS[baseId];
  if (injectionHits.length) {
    const cat = hit?.category ?? "unclear";
    return {
      decision: hit ? "REJECT" : "APPROVE_STATISTICAL",
      articles: hit ? ["54"] : ["53", "69"],
      needsReview: true,
      reviewReasons: [
        { code: "INJECTION_SUSPECTED", message: `The request text contains instruction-like phrases (${injectionHits.map((h) => `"${h}"`).join(", ")}). The AI signals cannot be trusted for this request.` },
        { code: "SIGNALS_DISAGREE", message: "Rules flag a prohibited purpose (market research / marketing) while the AI classifier reports scientific research." },
      ],
      downgradedFrom: null,
      answer: null,
      knowledge: { ...knowledge, purpose_short: "Diabetes 'market research'", category: cat,
        why: "Your request contains text that tries to instruct our automated review. It has been passed to a human reviewer at the Health Data Access Body, who will contact you." },
      reasonStaff: "Rule engine detected a marketing purpose; the AI classifier was steered by an embedded instruction. Fail closed: human review required.",
      injectionHits,
      signals: {
        rules: { prohibited: !!hit, category: cat },
        classifier: { prohibited: false, category: "scientific_research", quote: null },
        redteam: { prohibited: true, category: "advertising_marketing", quote: findQuote(raw.purpose, /market research/) },
        justification: { justified: false, quote: null, source: "n/a (statistics request)" },
        injection: { flagged: true, hits: injectionHits },
      },
    };
  }
  if (hit) {
    return {
      decision: "REJECT",
      articles: ["54"],
      needsReview: false,
      reviewReasons: [],
      downgradedFrom: null,
      answer: null,
      knowledge: {
        ...knowledge,
        category: hit.category,
        rule_hits: [raw.purpose.match(hit.re)?.[0] ?? ""],
        why: `Your stated purpose falls under a prohibited use of health data (Art. ${hit.article}). We rejected the request before any data was touched.`,
        alternatives: ["Research for prevention, public health or care quality may be allowed (Art. 53). You can submit a new request with such a purpose."],
      },
      reasonStaff: `Rule hit on prohibited category ${hit.category} (Art. ${hit.article}).`,
      injectionHits: [],
      signals: {
        rules: { prohibited: true, category: hit.category },
        classifier: { prohibited: true, category: hit.category, quote: findQuote(raw.purpose, hit.re) },
        redteam: { prohibited: true, category: hit.category },
        justification: { justified: false, quote: null, source: "n/a" },
        injection: { flagged: false, hits: [] },
      },
    };
  }
  const known = !!custom;
  const justQuote = findQuote(raw.purpose, /(aggregates?|statistics) (are|is) not enough|individual[- ]level/);
  const spe = isAccess && !!justQuote;
  return {
    decision: spe ? "APPROVE_SPE" : "APPROVE_STATISTICAL",
    articles: spe ? ["53", "66", "68", "73"] : isAccess ? ["53", "66", "69"] : ["53", "69"],
    needsReview: !known,
    reviewReasons: known
      ? []
      : [{ code: "MOCK_NO_ENGINE", message: "Mock mode cannot compile new definitions into a query. Connect the backend to compute this request." }],
    downgradedFrom: isAccess && !spe ? "pseudonymised records" : null,
    answer: custom ?? null,
    knowledge: {
      ...knowledge,
      why:
        knowledge.why ||
        "Your purpose is allowed (Art. 53). Your request will be answered with anonymised statistics (Art. 69). A staff member will review the query plan before results are released.",
      plan:
        knowledge.plan ??
        raw.definitions.map((d, i) => ({ label: `Definition ${i + 1}`, text: `pending translation: ${d}`, source_definition: i })),
    },
    reasonStaff: known ? "Allowed purpose (Art. 53); statistics answer the question (Art. 69)." : "Allowed purpose by rules; plan could not be compiled in mock mode.",
    injectionHits: [],
    signals: {
      rules: { prohibited: false, category: knowledge.category },
      classifier: { prohibited: false, category: knowledge.category, quote: null },
      redteam: { prohibited: false, category: knowledge.category },
      justification: { justified: spe, quote: justQuote, source: isAccess ? "llm" : "n/a (statistics request)" },
      injection: { flagged: false, hits: [] },
    },
  };
}

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------

interface Rec {
  id: string;
  baseId: string;
  raw: RawRequest;
  t0: number; // submit time (ms epoch)
  script: { key: StepKey; label: string; start: number; dur: number; skipped: boolean }[];
  total: number;
  outcome: Outcome;
  override: { decision: Decision; articles: string[]; note: string; actor: string; ts: number } | null;
  released: { actor: string; ts: number } | null;
  extraAudit: AuditEntry[];
}

const STEP_LABELS: Record<StepKey, string> = {
  received: "Received",
  purpose: "Purpose check",
  plan: "Query plan",
  query: "Query",
  privacy: "Privacy",
  decision: "Decision",
};

const store = new Map<string, Rec>();
const spes = new Map<string, { attempts: number; audit: AuditEntry[] }>();
let seq = 1;

function makeScript(outcome: Outcome, seed: number) {
  const j = (base: number, spread: number) => base + (seed % spread);
  const reject = outcome.decision === "REJECT" && !outcome.needsReview;
  const durs: Record<StepKey, number> = {
    received: 40,
    purpose: j(1500, 900),
    plan: reject || outcome.needsReview ? 0 : j(2200, 1400),
    query: reject || outcome.needsReview ? 0 : j(180, 220),
    privacy: reject || outcome.needsReview ? 0 : 60,
    decision: 30,
  };
  let t = 0;
  const keys: StepKey[] = ["received", "purpose", "plan", "query", "privacy", "decision"];
  const script = keys.map((key) => {
    const skipped = durs[key] === 0;
    const s = { key, label: STEP_LABELS[key], start: t, dur: durs[key], skipped };
    t += durs[key];
    return s;
  });
  return { script, total: t };
}

function submit(raw: RawRequest, delay = 0): Rec {
  // Re-submitting an id replaces the previous run (same as the backend).
  const id = (raw.id && String(raw.id)) || `X${String(100 + seq++).padStart(3, "0")}`;
  const baseId = id;
  spes.delete(`spe_${id}`);
  const outcome = resolveOutcome(raw, baseId);
  const { script, total } = makeScript(outcome, hash(id + Date.now()));
  const rec: Rec = {
    id,
    baseId,
    raw: { ...raw, id },
    t0: Date.now() + delay,
    script,
    total,
    outcome,
    override: null,
    released: null,
    extraAudit: [],
  };
  store.set(id, rec);
  return rec;
}

function stepStates(rec: Rec, now: number): Step[] {
  const el = now - rec.t0;
  return rec.script.map((s) => {
    let state: StepState;
    if (el < s.start) state = "pending";
    else if (s.skipped) state = "skipped";
    else if (el < s.start + s.dur) state = "running";
    else state = rec.outcome.decision === "REJECT" && s.key === "decision" ? "failed" : "done";
    const detail =
      s.key === "purpose" && (state === "done" || state === "failed")
        ? rec.outcome.knowledge.category
        : s.key === "decision" && state !== "pending" && state !== "running"
          ? rec.outcome.decision
          : null;
    return { key: s.key, label: s.label, state, ms: state === "done" || state === "failed" ? s.dur : null, detail };
  });
}

function isDone(rec: Rec, now: number) {
  return now - rec.t0 >= rec.total;
}

function stepDone(rec: Rec, key: StepKey, now: number) {
  const s = rec.script.find((x) => x.key === key)!;
  return !s.skipped && now - rec.t0 >= s.start + s.dur;
}

// ---------------------------------------------------------------------------
// Result building
// ---------------------------------------------------------------------------

const PCT_LIKE = (k: string) => /_pct$|share/.test(k);
const MEAN_LIKE = (k: string) => /^mean_/.test(k);

function cellOf(key: string, v: unknown): Cell {
  if (v === "<10") return { value: null, display: "<10", suppressed: "small_count" };
  if (v === "suppressed") return { value: null, display: "suppressed", suppressed: "small_n" };
  const n = Number(v);
  const display = PCT_LIKE(key) || MEAN_LIKE(key) ? n.toFixed(1) : n.toLocaleString("en-US");
  return { value: n, display };
}

function buildResult(rec: Rec): Result | null {
  const { answer, knowledge, decision } = rec.outcome;
  if (!answer) return null;
  if (decision === "APPROVE_SPE") return { kind: "cohort", cohort_size: (answer as { cohort_size: number }).cohort_size };
  const groups = Object.keys(answer as object);
  const first = (answer as Record<string, unknown>)[groups[0]];
  const flat = typeof first !== "object" || first === null;
  const measureKeys = flat ? [Object.keys(knowledge.labels ?? { value: "Value" })[0]] : Object.keys(first as object);
  const gk = knowledge.group_key ?? "group";
  const columns: Column[] = [
    { key: gk, label: knowledge.group_label ?? "Group", type: "group" },
    ...measureKeys.map((k) => ({
      key: k,
      label: knowledge.labels?.[k] ?? k.replace(/_/g, " "),
      type: PCT_LIKE(k) ? "pct" : MEAN_LIKE(k) ? "mean" : "count",
      unit: knowledge.units?.[k],
    })),
  ];
  const rows = groups.map((g) => {
    const src = (answer as Record<string, unknown>)[g];
    const row: Record<string, Cell | string> = { [gk]: g };
    measureKeys.forEach((k) => {
      row[k] = cellOf(k, flat ? src : (src as Record<string, unknown>)[k]);
    });
    return row;
  });
  return { kind: "table", group_by: [gk], columns, rows, answer } satisfies TableResult;
}

function countSuppressed(r: Result | null) {
  if (!r || r.kind !== "table") return { counts: 0, others: 0 };
  let counts = 0, others = 0;
  r.rows.forEach((row) =>
    Object.values(row).forEach((c) => {
      if (typeof c === "object" && c.value === null) c.suppressed === "small_count" ? counts++ : others++;
    }),
  );
  return { counts, others };
}

function buildPrivacy(rec: Rec, result: Result | null): Privacy {
  const sup = countSuppressed(result);
  const groups = result?.kind === "table" ? result.rows.length : 0;
  const cols = result?.kind === "table" ? result.columns.map((c) => c.key).join(", ") : "";
  const checks = [
    { key: "opt_out", label: "Opted-out patients excluded", passed: true, detail: `${OPTED_OUT} removed before any query (Art. 71)` },
  ];
  if (rec.outcome.decision === "APPROVE_SPE") {
    checks.push(
      { key: "spe_only", label: "Records only inside the SPE", passed: true, detail: "separate schema, download blocked (Art. 73)" },
      { key: "record_types", label: "Only requested record types copied", passed: true, detail: "patients, conditions, medications, observations (HbA1c)" },
      { key: "pseudonymised", label: "Pseudonymised identifiers", passed: true, detail: "no names, addresses or exact birth dates" },
    );
  } else {
    checks.push(
      { key: "small_cell", label: "Small-cell rule", passed: true, detail: sup.counts + sup.others ? `${sup.counts} counts shown as <10, ${sup.others} values suppressed` : "no cells below 10" },
      { key: "no_patient_level", label: "No patient-level fields in output", passed: true, detail: `columns: ${cols}` },
      { key: "all_groups", label: "All requested groups present", passed: true, detail: `${groups} / ${groups} groups, empty groups shown` },
      { key: "rounding", label: "Rounding", passed: true, detail: "half-up, 1 decimal" },
      { key: "differencing", label: "Differencing guard", passed: true, detail: "no overlapping prior queries by this applicant" },
    );
  }
  return { opted_out_excluded: OPTED_OUT, checks };
}

function fiveSafes(rec: Rec, outcome: Decision): FiveSafes {
  const k = rec.outcome.knowledge;
  const a = rec.raw.applicant;
  return {
    project: k.five_safes_project ?? rec.raw.purpose,
    people: `${a.name}, ${a.organisation} (${a.country}); identity not yet verified (no eIDAS in demo)`,
    setting:
      outcome === "APPROVE_SPE" ? `Secure processing environment spe_${rec.id}, no download (Art. 73)` : outcome === "REJECT" ? "None: no access granted" : "None needed: anonymised statistics only (Art. 69)",
    data:
      outcome === "APPROVE_SPE"
        ? "Pseudonymised patients, conditions, medications, HbA1c observations of the cohort"
        : outcome === "REJECT"
          ? "None: data never queried"
          : "Aggregates computed from 19,161 non-opted-out synthetic patients",
    outputs:
      outcome === "APPROVE_SPE" ? "Model weights and metrics only, after HDAB output review" : outcome === "REJECT" ? "Decision letter only" : "Small-cell rule (<10), suppressed means/shares, 1 dp half-up",
  };
}

function iso(ms: number) {
  return new Date(ms).toISOString();
}

function buildAudit(rec: Rec, now: number): AuditEntry[] {
  const a: AuditEntry[] = [];
  const at = (k: StepKey) => {
    const s = rec.script.find((x) => x.key === k)!;
    return rec.t0 + s.start + s.dur;
  };
  const el = now - rec.t0;
  if (el >= 0) a.push({ ts: iso(rec.t0), event: "request.received", actor: "applicant", detail: `applicant=${rec.raw.applicant.name} · ${rec.raw.requested_as}` });
  const o = rec.outcome;
  if (now >= at("purpose")) {
    a.push({ ts: iso(at("purpose") - 3), event: "purpose.rules", actor: "system", detail: o.knowledge.rule_hits?.length ? `rule hits: ${o.knowledge.rule_hits.map((h) => `"${h}"`).join(", ")}` : "no Art. 54 rule hit" });
    a.push({ ts: iso(at("purpose")), event: "purpose.classified", actor: "system:llm", detail: `${o.knowledge.category} · request text only, no patient data` });
    if (o.injectionHits.length) a.push({ ts: iso(at("purpose") + 1), event: "guard.injection_flagged", actor: "system", detail: o.injectionHits.join(", ") });
  }
  if (stepDone(rec, "plan", now)) a.push({ ts: iso(at("plan")), event: "plan.validated", actor: "system", detail: `${o.knowledge.catalog?.length ?? 0} codes matched in closed catalogue` });
  if (stepDone(rec, "query", now)) a.push({ ts: iso(at("query")), event: o.decision === "APPROVE_SPE" ? "spe.provisioned" : "query.executed", actor: "system", detail: o.decision === "APPROVE_SPE" ? `schema spe_${rec.id.toLowerCase()} · cohort copied` : "deterministic SQL on local DuckDB" });
  if (stepDone(rec, "privacy", now)) {
    const sup = countSuppressed(buildResult(rec));
    a.push({ ts: iso(at("privacy")), event: "privacy.checked", actor: "system", detail: `opt-out ${OPTED_OUT} excluded · ${sup.counts + sup.others} cells protected` });
  }
  if (isDone(rec, now)) {
    a.push({ ts: iso(rec.t0 + rec.total), event: "decision.made", actor: "system", detail: `${o.decision} · Art. ${o.articles.join(", ")}${o.needsReview ? " · needs human review" : ""}` });
  }
  if (rec.override) a.push({ ts: iso(rec.override.ts), event: "decision.overridden", actor: rec.override.actor, detail: `→ ${rec.override.decision} · Art. ${rec.override.articles.join(", ")} · note="${rec.override.note}"` });
  if (rec.released) a.push({ ts: iso(rec.released.ts), event: "decision.released", actor: rec.released.actor, detail: "letter released to applicant" });
  a.push(...rec.extraAudit);
  const spe = spes.get(`spe_${rec.id}`);
  if (spe) a.push(...spe.audit);
  return a.sort((x, y) => x.ts.localeCompare(y.ts));
}

function letterFor(rec: Rec, outcome: Decision) {
  const k = rec.outcome.knowledge;
  const name = rec.raw.applicant.name;
  const headline =
    rec.outcome.needsReview && !rec.override
      ? "Your request needs a review by our staff."
      : outcome === "REJECT"
        ? "Your request has been rejected."
        : outcome === "APPROVE_SPE"
          ? "Your application has been approved for a secure processing environment."
          : rec.outcome.downgradedFrom
            ? "Your request has been approved as statistics."
            : "Your request has been approved. Here are your statistics.";
  return {
    greeting: `Dear ${name},`,
    headline,
    why: rec.override ? `${k.why}\n\nAfter review, a staff member changed the decision: ${rec.override.note}` : k.why,
    alternatives: k.alternatives ?? [],
    next_steps: k.next_steps ?? [],
  };
}

function buildDetail(rec: Rec, now = Date.now()): RequestDetail {
  const done = isDone(rec, now);
  const o = rec.outcome;
  const outcome = rec.override?.decision ?? o.decision;
  const articles = rec.override?.articles ?? o.articles;
  const result = stepDone(rec, "query", now) ? buildResult(rec) : null;
  const rejectNoData = o.decision === "REJECT";
  let decision: DecisionDetail | null = null;
  if (done) {
    const isAccess = /access application/i.test(rec.raw.requested_as);
    decision = {
      outcome,
      articles,
      downgraded_from: o.downgradedFrom,
      purpose: {
        category: o.knowledge.category,
        allowed: o.decision !== "REJECT",
        confidence: o.needsReview ? 0.62 : 0.9 + (hash(rec.id) % 9) / 100,
        source: "llm+rules",
        rule_hits: o.knowledge.rule_hits ?? [],
      },
      rule_trace: [
        { step: 1, question: "Is the purpose prohibited (Art. 54)?", answer: o.decision === "REJECT" ? `Yes → ${o.knowledge.category}` : "No", article: "54" },
        ...(o.decision === "REJECT"
          ? [{ step: 2, question: "Stop: reject before any data is queried", answer: "REJECT", article: "54" }]
          : isAccess
            ? [
                { step: 2, question: "Is this a health data request (statistics only)?", answer: "No → access application", article: "67" },
                {
                  step: 3,
                  question: "Does the applicant explain why statistics are not enough?",
                  answer: o.decision === "APPROVE_SPE" ? "Yes → secure processing environment" : "No → downgrade to statistics",
                  article: "66",
                },
                o.decision === "APPROVE_SPE"
                  ? { step: 4, question: "Grant data permit, provision SPE", answer: "APPROVE_SPE", article: "68, 73" }
                  : { step: 4, question: "Answer with anonymised statistics", answer: "APPROVE_STATISTICAL", article: "69" },
              ]
            : [{ step: 2, question: "Is this a health data request?", answer: "Yes → statistics", article: "69" }]),
      ],
      reason_staff: o.reasonStaff,
      letter: letterFor(rec, outcome),
      needs_review: o.needsReview && !rec.override,
      review_reasons: rec.override ? [] : o.reviewReasons,
      signals: o.signals,
      five_safes: fiveSafes(rec, outcome),
    };
  }
  const planReady = stepDone(rec, "plan", now) || (done && o.needsReview && !rejectNoData);
  return {
    id: rec.id,
    request: rec.raw,
    submitted: iso(rec.t0),
    status: !done ? "processing" : rec.released ? "released" : "decided",
    elapsed_ms: done ? rec.total : Math.max(0, now - rec.t0),
    steps: stepStates(rec, now),
    decision,
    plan:
      planReady && o.knowledge.plan
        ? {
            readable: o.knowledge.plan,
            catalog_matches: o.knowledge.catalog ?? [],
            raw: RAW_PLANS[rec.baseId] ?? { note: "plan JSON produced by the backend" },
            sql: o.knowledge.sql ?? "-- compiled SQL is produced by the backend compiler (mock mode)",
          }
        : null,
    result,
    privacy: stepDone(rec, "privacy", now) ? buildPrivacy(rec, result) : null,
    spe: done && outcome === "APPROVE_SPE" ? { workspace_id: `spe_${rec.id}` } : null,
    audit: buildAudit(rec, now),
    inference: { profile: "llm", model: "mock-llm (no network call)", endpoint_host: "localhost (mock)", patient_data_sent: false },
  };
}

function queueItem(rec: Rec, now = Date.now()): QueueItem {
  const d = buildDetail(rec, now);
  const running = d.steps.find((s) => s.state === "running");
  const sup = countSuppressed(d.result);
  return {
    id: rec.id,
    submitted: iso(rec.t0),
    status: d.status,
    applicant: rec.raw.applicant,
    requested_as: rec.raw.requested_as,
    purpose_short: rec.outcome.knowledge.purpose_short,
    decision: d.decision?.outcome ?? null,
    articles: d.decision?.articles ?? [],
    flags: {
      downgraded: !!d.decision?.downgraded_from,
      suppressed_cells: sup.counts + sup.others,
      differencing_risk: false,
      overridden: !!rec.override,
      low_confidence: false,
      needs_review: !!d.decision?.needs_review,
    },
    needs_review: !!d.decision?.needs_review,
    current_step: running?.key ?? (d.status === "processing" ? "received" : "decision"),
    elapsed_ms: d.elapsed_ms,
  };
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

const metricRuns = new Map<string, { t0: number; runs: number; includeCustom: boolean }>();
const TRACK_IDS = ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10"];
const CELL_MS = 320;

function valueCount(ans: unknown): number {
  if (!ans || typeof ans !== "object") return 0;
  return Object.values(ans as object).reduce((n: number, v) => n + (typeof v === "object" && v ? Object.keys(v).length : 1), 0);
}

function metricsRun(id: string): MetricsRun {
  const m = metricRuns.get(id);
  if (!m) throw new MockHttpError(404, { detail: "run not found" });
  const filled = Math.floor((Date.now() - m.t0) / CELL_MS);
  const total = TRACK_IDS.length * m.runs;
  let slowest = 0;
  const rows: MetricsRow[] = TRACK_IDS.map((rid, i) => {
    const exp = EXPECTED[rid];
    const runs = Array.from({ length: m.runs }, (_, r) => {
      const idx = r * TRACK_IDS.length + i;
      if (idx >= filled) return null;
      const ms = (exp.decision === "REJECT" ? 1800 : 4200) + (hash(`${rid}-${r}`) % 2600);
      slowest = Math.max(slowest, ms);
      return { decision: exp.decision, articles_ok: true, numbers_ok: exp.answer && exp.decision !== "REJECT" ? true : null, leaks: 0, ms };
    });
    const complete = runs.every(Boolean);
    const vt = exp.decision === "REJECT" ? null : valueCount(exp.answer);
    return {
      id: rid,
      expected: exp.decision,
      expected_articles: exp.articles,
      runs,
      consistent: complete ? true : null,
      values_matched: complete ? vt : null,
      values_total: vt,
      diff: [],
    };
  });
  const finishedRows = rows.filter((r) => r.runs.every(Boolean));
  const done = filled >= total + (m.includeCustom ? 2 : 0);
  return {
    status: done ? "done" : "running",
    runs_total: m.runs,
    summary: {
      decisions_correct: finishedRows.length,
      decisions_total: 10,
      numbers_correct: finishedRows.filter((r) => r.expected !== "REJECT").length,
      numbers_total: 6,
      privacy_leaks: 0,
      consistent: finishedRows.length,
      consistent_total: 10,
      slowest_ms: slowest,
      threshold_ms: 60000,
    },
    rows,
    custom: m.includeCustom
      ? ["C01", "C02"].map((cid, k) => (filled >= total + k + 1 ? { id: cid, decision: "APPROVE_STATISTICAL" as Decision, ms: 5200 + k * 900, answer: CUSTOM_ANSWERS[cid] } : { id: cid, decision: null }))
      : [],
  };
}

// ---------------------------------------------------------------------------
// Seed + router
// ---------------------------------------------------------------------------

/** Deep links like /apply/R02 work standalone: unknown sample ids are created as already decided. */
function ensureSample(id: string): Rec | undefined {
  const existing = store.get(id);
  if (existing) return existing;
  const raw = SAMPLE_REQUESTS.find((r) => r.id === id);
  if (!raw) return undefined;
  const rec = submit(raw);
  rec.t0 = Date.now() - rec.total - 1500;
  return rec;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function mockFetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  await delay(60 + Math.random() * 80);
  const out = route(method, path, body);
  return structuredClone(out) as T;
}

function route(method: string, path: string, body: unknown): unknown {
  const p = path.replace(/^\/+/, "").replace(/\?.*$/, "").split("/");
  const get = method === "GET";
  if (get && p[0] === "samples") {
    return SAMPLE_REQUESTS.map<Sample>((r) => ({ id: String(r.id), organisation: r.applicant.organisation, requested_as: r.requested_as, json: r }));
  }
  if (get && p[0] === "articles") return MOCK_ARTICLES;
  if (p[0] === "requests") {
    if (get && p.length === 1) return Array.from(store.values()).sort((a, b) => b.t0 - a.t0).map((r) => queueItem(r));
    if (method === "POST" && p[1] === "batch") {
      const ids: string[] = (body as { ids?: string[] })?.ids ?? TRACK_IDS;
      const recs = ids.map((id, i) => {
        const raw = SAMPLE_REQUESTS.find((r) => r.id === id);
        if (!raw) throw new MockHttpError(404, { detail: `unknown sample ${id}` });
        return submit(raw, i * 450);
      });
      return { ids: recs.map((r) => r.id) };
    }
    if (method === "POST" && p.length === 1) {
      const raw = body as RawRequest;
      if (!raw || typeof raw !== "object" || !raw.applicant || !raw.purpose)
        throw new MockHttpError(422, { detail: "request must contain applicant, purpose, question and definitions" });
      if (!/^health data (request|access application)$/i.test(String(raw.requested_as ?? "")))
        throw new MockHttpError(422, { detail: "requested_as must be 'health data request' or 'health data access application'" });
      if (!Array.isArray(raw.definitions)) throw new MockHttpError(422, { detail: "definitions must be a list of strings" });
      const rec = submit(raw);
      return { id: rec.id, status: "processing" };
    }
    const rec = ensureSample(decodeURIComponent(p[1] ?? ""));
    if (!rec) throw new MockHttpError(404, { detail: "request not found" });
    if (get && p.length === 2) return buildDetail(rec);
    if (method === "POST" && p[2] === "override") {
      const b = body as OverrideBody;
      rec.override = { ...b, ts: Date.now() };
      return buildDetail(rec);
    }
    if (method === "POST" && p[2] === "release") {
      rec.released = { actor: (body as { actor?: string })?.actor ?? "staff", ts: Date.now() };
      return buildDetail(rec);
    }
  }
  if (p[0] === "spe") {
    const wid = decodeURIComponent(p[1] ?? "");
    const rec = ensureSample(wid.replace(/^spe_/, ""));
    if (!rec || (rec.override?.decision ?? rec.outcome.decision) !== "APPROVE_SPE") throw new MockHttpError(404, { detail: "workspace not found" });
    const st = spes.get(wid) ?? { attempts: 0, audit: [] };
    spes.set(wid, st);
    if (get && p.length === 2) return speWorkspace(rec, wid, st.attempts);
    if (get && p[2] === "download") {
      st.attempts++;
      const audit_id = `aud_${(hash(wid + st.attempts) % 100000).toString().padStart(5, "0")}`;
      st.audit.push({ ts: iso(Date.now()), event: "spe.download_blocked", actor: rec.raw.applicant.organisation.split(",")[0], detail: `${audit_id} · ip=10.20.0.14 · attempt ${st.attempts} · Art. 73` });
      throw new MockHttpError(403, {
        error: "download_blocked",
        article: "73",
        message: "Data in a secure processing environment cannot be downloaded.",
        audit_id,
        blocked_attempts: st.attempts,
      } satisfies DownloadBlocked);
    }
    if (method === "POST" && p[2] === "export-request") {
      st.audit.push({ ts: iso(Date.now()), event: "spe.export_requested", actor: rec.raw.applicant.organisation.split(",")[0], detail: "artifact=model_weights · pending HDAB output review" });
      return { status: "pending_review" };
    }
  }
  if (p[0] === "metrics") {
    if (method === "POST" && p[1] === "run") {
      const id = `m_${String(metricRuns.size + 1).padStart(3, "0")}`;
      const b = (body ?? {}) as { runs?: number; include_custom?: boolean };
      metricRuns.set(id, { t0: Date.now(), runs: b.runs ?? 3, includeCustom: b.include_custom ?? true });
      return { run_id: id };
    }
    if (get && p[1] === "runs") return metricsRun(p[2]);
  }
  throw new MockHttpError(404, { detail: `mock: no route for ${method} /${p.join("/")}` });
}

function speWorkspace(rec: Rec, wid: string, attempts: number): SpeWorkspace {
  const size = (rec.outcome.answer as { cohort_size?: number })?.cohort_size ?? 1152;
  const h = hash(wid);
  const sexes = ["female", "male"];
  return {
    id: wid,
    request_id: rec.id,
    schema: wid.toLowerCase(),
    permit: {
      number: `HDAB-2026-${rec.id}`,
      holder: rec.raw.applicant.organisation.split(",")[0],
      valid_until: "2027-10-29",
      articles: ["68", "73"],
    },
    cohort_size: size,
    cohort_definition: "Adults (≥18 on 2025-12-31) with ICD-10 E11* and ≥1 HbA1c (LOINC 4548-4)",
    tables: [
      { name: "patients", rows: size, copied: true, note: "pseudonymised IDs" },
      { name: "conditions", rows: size * 4 + (h % 400), copied: true },
      { name: "medications", rows: size * 6 + (h % 700), copied: true },
      { name: "observations", rows: size * 3 + (h % 300), copied: true, note: "LOINC 4548-4 (HbA1c) only" },
      { name: "encounters", rows: 0, copied: false, note: "not requested, not copied" },
    ],
    preview: {
      table: "patients",
      columns: ["patient_id", "sex", "birth_year", "region"],
      rows: Array.from({ length: 5 }, (_, i) => {
        const x = hash(`${wid}${i}`);
        return [`p-${x.toString(16).slice(0, 8).padStart(8, "0")}`, sexes[x % 2], 1940 + (x % 60), REGIONS[x % REGIONS.length]];
      }),
    },
    blocked_attempts: attempts,
  };
}
