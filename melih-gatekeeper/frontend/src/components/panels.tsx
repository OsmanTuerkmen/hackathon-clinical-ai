import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, ArrowRight, Bot, CheckCircle2, ChevronDown, CircleDashed, Cloud, Code2, Cpu, Database, FileText, Gavel,
  HardDrive, Quote, ScanSearch, ShieldAlert, ShieldCheck, Swords, XCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn, fmtTime, humanize } from "@/lib/utils";
import type { AuditEntry, FiveSafes, Inference, Plan, Privacy, ReviewReason, RuleTraceItem, Signals } from "@/types";
import { ArticleChip } from "./decision";
import { Callout, SectionLabel, Tip } from "./ui";

// ---------------------------------------------------------------- Query plan
const STOP = new Set(["with", "that", "from", "each", "have", "their", "patients", "patient", "number", "per", "report", "code", "codes", "starting", "start", "any", "condition", "value", "values", "one", "decimal", "the", "and", "all"]);
function tokens(t: string) {
  const codes = t.match(/\b[A-Z]\d{2}[A-Z0-9]*|\b\d{4,5}-\d\b/g) ?? [];
  const words = (t.toLowerCase().match(/[a-zäöüß]{4,}/g) ?? []).filter((w) => !STOP.has(w));
  return { codes: new Set(codes.map((c) => c.toUpperCase())), words: new Set(words) };
}
/** Fallback when the backend omits source_definition: best token overlap (codes weigh most). */
function inferSource(text: string, defs: string[]): number | null {
  const a = tokens(text);
  let best = -1, score = 0;
  defs.forEach((d, i) => {
    const b = tokens(d);
    let sc = 0;
    a.codes.forEach((c) => [...b.codes].some((x) => x.startsWith(c) || c.startsWith(x)) && (sc += 3));
    a.words.forEach((w) => b.words.has(w) && (sc += 1));
    if (sc > score) {
      score = sc;
      best = i;
    }
  });
  return score >= 1 ? best : null;
}

export function QueryPlanView({ plan, definitions }: { plan: Plan; definitions: string[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [raw, setRaw] = useState<"none" | "json" | "sql">("none");
  return (
    <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
      <div>
        <SectionLabel>Query plan · in plain English</SectionLabel>
        <div className="mt-2 overflow-hidden rounded-xl border border-line bg-surface">
          {plan.readable.map((item, i) => {
            const explicit = item.source_definition !== undefined;
            const src = explicit ? item.source_definition : inferSource(item.text, definitions);
            const linked = src !== null && src !== undefined && src < definitions.length;
            return (
              <div
                key={i}
                onMouseEnter={() => linked && setHover(src!)}
                onMouseLeave={() => setHover(null)}
                className={cn(
                  "grid grid-cols-[96px_1fr_auto] items-center gap-3 border-b border-line px-4 py-2.5 last:border-0 transition-colors",
                  linked && "cursor-default",
                  linked && hover === src && "bg-gold/[0.07]",
                )}
              >
                <div className="text-sm font-medium text-muted">{item.label}</div>
                <div className="font-mono text-[13px] leading-relaxed">{item.text}</div>
                <div className="text-xs text-muted">
                  {linked ? (
                    <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono transition-colors", hover === src ? "border-gold bg-gold/10 text-ink" : "border-line")}>
                      {explicit ? "" : "≈ "}def {src! + 1}
                    </span>
                  ) : explicit ? (
                    <span className="font-mono text-muted/60">rule</span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
        {plan.catalog_matches && plan.catalog_matches.length > 0 && (
          <div className="mt-4">
            <SectionLabel>Catalogue matches · closed code list</SectionLabel>
            <div className="mt-2 flex flex-wrap gap-2">
              {plan.catalog_matches.map((c) => (
                <span
                  key={c.system + c.code}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm",
                    c.ok ? "border-stat/25 bg-stat-bg text-stat" : "border-warn/30 bg-warn-bg text-warn",
                  )}
                >
                  {c.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                  <span className="text-xs opacity-80">{c.system}</span>
                  <span className="font-mono font-medium">{c.code}</span>
                  <span className="text-ink/70">{c.label}</span>
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="mt-5 flex gap-2">
          <RawButton active={raw === "json"} onClick={() => setRaw(raw === "json" ? "none" : "json")} icon={<Code2 size={14} />}>
            Raw plan JSON
          </RawButton>
          <RawButton active={raw === "sql"} onClick={() => setRaw(raw === "sql" ? "none" : "sql")} icon={<Database size={14} />}>
            Compiled SQL
          </RawButton>
        </div>
        <AnimatePresence initial={false}>
          {raw !== "none" && (
            <motion.pre
              key={raw}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 max-h-[420px] overflow-auto rounded-xl border border-line bg-[#0f1724] p-4 font-mono text-[12px] leading-relaxed text-[#d7e0ea] scrollbar-thin"
            >
              {raw === "json" ? JSON.stringify(plan.raw ?? {}, null, 2) : plan.sql ?? "-- no SQL"}
            </motion.pre>
          )}
        </AnimatePresence>
      </div>
      <div>
        <SectionLabel>Applicant's definitions · source</SectionLabel>
        <ol className="mt-2 space-y-1.5">
          {definitions.map((d, i) => (
            <li
              key={i}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              className="flex gap-3 rounded-lg px-3 py-2 text-base leading-relaxed"
            >
              <span className={cn("mt-0.5 font-mono text-xs transition-colors", hover === i ? "text-gold" : "text-muted")}>{i + 1}</span>
              <span className={cn("marker rounded-sm px-0.5", hover === i && "marker-on")}>{d}</span>
            </li>
          ))}
        </ol>
        <p className="mt-4 flex items-start gap-2 rounded-lg bg-sunken px-3 py-2.5 text-sm text-muted">
          <Bot size={15} className="mt-0.5 shrink-0" />
          The AI only translates these sentences into a plan using codes from a closed catalogue. A deterministic compiler turns the plan into SQL; the AI never sees patient data.
        </p>
      </div>
    </div>
  );
}

function RawButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: ReactNode; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-sm font-medium transition-colors",
        active ? "border-ink bg-ink text-ink-fg" : "border-line bg-surface hover:bg-sunken",
      )}
    >
      {icon}
      {active ? "Hide" : "Show"} {children}
      <ChevronDown size={13} className={cn("transition-transform", active && "rotate-180")} />
    </button>
  );
}

// ---------------------------------------------------------------- Privacy
export function PrivacyChecklist({ privacy }: { privacy: Privacy }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      {privacy.checks.map((c, i) => {
        const warn = c.warning || (!c.passed && c.key === "differencing");
        return (
          <motion.div
            key={c.key}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="grid grid-cols-[28px_minmax(180px,260px)_1fr] items-center gap-3 border-b border-line px-4 py-3 last:border-0"
          >
            {c.passed && !warn ? <CheckCircle2 size={18} className="text-stat" /> : warn ? <AlertTriangle size={18} className="text-warn" /> : <XCircle size={18} className="text-reject" />}
            <div className="font-medium">{c.label}</div>
            <div className="font-mono text-[13px] text-muted">{c.detail ?? (c.passed ? "passed" : "failed")}</div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- Audit
const EVENT_TONE: Record<string, string> = {
  "decision.made": "bg-ink",
  "decision.overridden": "bg-gold",
  "decision.released": "bg-stat",
  "spe.download_blocked": "bg-reject",
  "guard.injection_flagged": "bg-warn",
};

export function AuditTimeline({ entries, dense = false }: { entries: AuditEntry[]; dense?: boolean }) {
  return (
    <ol className="relative">
      <div className="absolute left-[7px] top-2 bottom-2 w-px bg-line" />
      <AnimatePresence initial={false}>
        {entries.map((e, i) => (
          <motion.li
            key={`${e.ts}-${e.event}-${i}`}
            layout
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className={cn("relative grid gap-x-4 pl-6", dense ? "grid-cols-1 py-1.5" : "grid-cols-[110px_200px_1fr] py-2.5 items-baseline")}
          >
            <span className={cn("absolute left-[3px] h-[9px] w-[9px] rounded-full ring-4 ring-surface", dense ? "top-3" : "top-[15px]", EVENT_TONE[e.event] ?? "bg-muted/60")} />
            <span className="font-mono text-[12px] tabular text-muted">{fmtTime(e.ts, true)}</span>
            <span className={cn("font-mono text-[13px] font-medium", e.event.includes("blocked") && "text-reject", e.event.includes("overridden") && "text-gold")}>{e.event}</span>
            <span className="text-sm text-muted">
              {e.detail}
              <span className="ml-2 font-mono text-[11px] text-muted/80">actor={e.actor}</span>
              {e.hash && !dense && (
                <Tip content={`Tamper-evident hash chain · prev ${e.prev ?? "–"}`}>
                  <span className="ml-2 cursor-help rounded bg-sunken px-1 font-mono text-[10px] text-muted/80">#{e.hash.slice(0, 8)}</span>
                </Tip>
              )}
            </span>
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  );
}

// ---------------------------------------------------------------- Rule trace
export function RuleTrace({ items }: { items: RuleTraceItem[] }) {
  return (
    <ol className="space-y-2">
      {items.map((r) => (
        <li key={r.step} className="flex items-start gap-3">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sunken font-mono text-[11px] text-muted">{r.step}</span>
          <div className="min-w-0 flex-1">
            <div className="text-base">{r.question}</div>
            <div className="mt-0.5 flex items-center gap-2 text-sm">
              <ArrowRight size={12} className="text-muted" />
              <span className="font-mono font-medium">{r.answer}</span>
            </div>
          </div>
          {r.article && (
            <div className="flex shrink-0 gap-1">
              {r.article.split(/[,\s]+/).filter(Boolean).map((a) => (
                <ArticleChip key={a} id={a} size="sm" />
              ))}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------- Review reasons
export function ReviewReasons({ reasons }: { reasons: ReviewReason[] }) {
  if (!reasons.length) return null;
  return (
    <div className="space-y-2">
      {reasons.map((r) => (
        <Callout key={r.code} tone="warn" title={<span className="font-mono text-xs tracking-wide">{r.code}</span>}>
          {r.message}
        </Callout>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Signals
type Row = {
  key: string; label: string; icon: ReactNode; flag: boolean | null; flagLabel: string; okLabel: string; category?: string;
  quote?: string | null; verified?: boolean; extra?: ReactNode; unavailable?: string | null;
};

export function SignalsPanel({ signals }: { signals: Signals }) {
  const rows: Row[] = [];
  const prohibitedRow = (key: keyof Signals, label: string, icon: ReactNode) => {
    const s = signals[key] as import("@/types").SignalVerdict | undefined;
    if (!s) return;
    const unavailable = s.available === false ? s.note || "not available" : null;
    const cat = s.prohibited ? s.category : s.allowed_purpose && s.allowed_purpose !== "none" ? s.allowed_purpose : s.category !== "none" ? s.category : undefined;
    rows.push({
      key, label, icon, flag: unavailable ? null : s.prohibited, flagLabel: "Prohibited", okLabel: "Allowed", category: cat,
      quote: s.quote, verified: s.quote_verified, unavailable,
    });
  };
  prohibitedRow("rules", "Rules", <Gavel size={15} />);
  prohibitedRow("classifier", "AI classifier", <Bot size={15} />);
  prohibitedRow("redteam", "AI red-team", <Swords size={15} />);
  // majority among purpose signals defines "agree"
  const votes = rows.filter((r) => r.flag !== null).map((r) => r.flag);
  const majority = votes.filter(Boolean).length * 2 > votes.length;
  const purposeDisagree = votes.some((v) => v !== majority);

  const j = signals.justification;
  if (j)
    rows.push({
      key: "justification",
      label: "Justification",
      icon: <ScanSearch size={15} />,
      flag: null,
      flagLabel: "",
      okLabel: "",
      category: j.source,
      quote: j.quote,
      verified: j.quote_verified,
      extra: (
        <span className={cn("inline-flex items-center gap-1 text-sm font-medium", j.justified ? "text-stat" : "text-muted")}>
          {j.justified ? <CheckCircle2 size={14} /> : <CircleDashed size={14} />}
          {j.justified ? "Records justified" : "No justification for records"}
        </span>
      ),
    });
  const inj = signals.injection;
  if (inj)
    rows.push({
      key: "injection",
      label: "Injection guard",
      icon: inj.flagged ? <ShieldAlert size={15} /> : <ShieldCheck size={15} />,
      flag: null,
      flagLabel: "",
      okLabel: "",
      extra: (
        <span className={cn("inline-flex flex-wrap items-center gap-1.5 text-sm font-medium", inj.flagged ? "text-reject" : "text-stat")}>
          {inj.flagged ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
          {inj.flagged ? "Instruction-like text found" : "Clean"}
          {inj.hits.map((h) => (
            <span key={h} className="rounded bg-reject-bg px-1.5 py-0.5 font-mono text-[11px] text-reject">
              {h}
            </span>
          ))}
        </span>
      ),
    });

  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <div className="flex items-center justify-between border-b border-line bg-sunken/60 px-4 py-2">
        <SectionLabel>Signals</SectionLabel>
        <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", purposeDisagree ? "text-warn" : "text-stat")}>
          {purposeDisagree ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
          {purposeDisagree ? "Purpose signals disagree: fail closed" : "Purpose signals agree"}
        </span>
      </div>
      {rows.map((r) => {
        const disagrees = r.flag !== null && r.flag !== majority;
        return (
          <div key={r.key} className={cn("border-b border-line px-4 py-2.5 last:border-0", disagrees && "bg-warn-bg/60")}>
            <div className="grid grid-cols-[150px_1fr_auto] items-center gap-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span className="text-muted">{r.icon}</span>
                {r.label}
              </div>
              <div className="min-w-0">
                {r.unavailable ? (
                  <span className="inline-flex items-center gap-1.5 text-sm text-muted">
                    <CircleDashed size={14} /> Not run <span className="font-mono text-xs">· {r.unavailable}</span>
                  </span>
                ) : r.extra ?? (
                  <span className="inline-flex items-center gap-2 text-sm">
                    <span className={cn("inline-flex items-center gap-1 font-medium", r.flag ? "text-reject" : "text-stat")}>
                      {r.flag ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
                      {r.flag ? r.flagLabel : r.okLabel}
                    </span>
                    {r.category && <span className="truncate font-mono text-xs text-muted">{r.category}</span>}
                  </span>
                )}
              </div>
              <div className="text-xs">
                {r.flag !== null &&
                  (disagrees ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-warn-bg px-2 py-0.5 font-medium text-warn">disagrees</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-stat-bg px-2 py-0.5 font-medium text-stat">agrees</span>
                  ))}
                {r.key === "justification" && r.category && <span className="font-mono text-muted">{r.category}</span>}
              </div>
            </div>
            {r.quote && <EvidenceQuote quote={r.quote} verified={r.verified} source={r.key === "rules" ? "Rule match" : undefined} />}
          </div>
        );
      })}
    </div>
  );
}

export function EvidenceQuote({ quote, verified, source }: { quote: string; verified?: boolean; source?: string }) {
  const label = source
    ? `${source} · quoted from the request${verified ? " (verified verbatim)" : ""}`
    : verified === false
      ? "AI-extracted evidence (not verified, treat with caution)"
      : "AI-extracted evidence (verified verbatim)";
  return (
    <div className={cn("mt-2 ml-[162px] rounded-md border-l-2 px-3 py-2", verified === false && !source ? "border-warn/60 bg-warn-bg/50" : "border-accent/50 bg-accent/[0.04]")}>
      <div className={cn("flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em]", verified === false && !source ? "text-warn" : "text-accent")}>
        <Quote size={11} /> {label}
      </div>
      <p className="mt-1 font-serif text-[15px] italic leading-snug text-ink/85">“{quote}”</p>
    </div>
  );
}

// ---------------------------------------------------------------- Five Safes
const SAFES: { key: keyof FiveSafes; label: string }[] = [
  { key: "project", label: "Safe project" },
  { key: "people", label: "Safe people" },
  { key: "setting", label: "Safe setting" },
  { key: "data", label: "Safe data" },
  { key: "outputs", label: "Safe outputs" },
];

export function FiveSafesRecord({ safes, variant = "staff" }: { safes: FiveSafes; variant?: "staff" | "letter" }) {
  if (variant === "letter")
    return (
      <dl className="overflow-hidden rounded-xl border border-line">
        {SAFES.map((s) => (
          <div key={s.key} className="grid grid-cols-[130px_1fr] gap-4 border-b border-line px-4 py-2.5 last:border-0">
            <dt className="pt-0.5 font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-gold">{s.label}</dt>
            <dd className="font-serif text-[15px] leading-snug">{safes[s.key] || "–"}</dd>
          </div>
        ))}
      </dl>
    );
  return (
    <div
      className="grid overflow-hidden rounded-xl border border-line bg-surface sm:grid-cols-5"
    >
      {SAFES.map((s, i) => (
        <div key={s.key} className={cn("px-3.5 py-3", i > 0 && "border-t border-line sm:border-t-0 sm:border-l")}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{s.label}</div>
          <div className="mt-1 text-sm leading-snug">{safes[s.key] || "–"}</div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Data flow (sovereignty)
export function DataFlowPanel({ inference }: { inference?: Inference | null }) {
  const off = !inference || inference.profile === "off";
  const leaked = inference?.patient_data_sent === true;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Data flow</SectionLabel>
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold", leaked ? "bg-reject-bg text-reject" : "bg-stat-bg text-stat")}>
          {leaked ? <AlertTriangle size={12} /> : <ShieldCheck size={12} />} Patient data sent to AI: {leaked ? "YES" : "none"}
        </span>
      </div>
      <div className="mt-4 space-y-1.5">
        <FlowNode icon={<HardDrive size={16} />} title="Local database" sub="20,000 synthetic patients · never leaves" tone="ok" />
        <FlowLink blocked label="patient data: never" />
        <FlowNode icon={off ? <Cpu size={16} /> : <Cloud size={16} />} title={off ? "No AI model (profile off)" : inference?.model ?? "LLM"} sub={off ? "rules + deterministic code only" : inference?.endpoint_host ?? "unknown host"} />
        <FlowLink label={off ? "request text: not sent" : "request text only: purpose, question, definitions"} />
        <FlowNode icon={<FileText size={16} />} title="Applicant's request text" sub={off ? "processed locally" : <>sent to <span className="font-mono">{inference?.endpoint_host ?? "the model"}</span></>} />
      </div>
    </div>
  );
}

function FlowLink({ label, blocked }: { label: string; blocked?: boolean }) {
  return (
    <div className="flex items-center gap-2 pl-5">
      <div className={cn("h-5 w-px", blocked ? "border-l border-dashed border-reject/60" : "bg-accent/50")} />
      <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium", blocked ? "text-reject" : "text-accent")}>
        {blocked ? <XCircle size={11} /> : <ArrowRight size={11} className="rotate-90" />} {label}
      </span>
    </div>
  );
}

function FlowNode({ icon, title, sub, tone }: { icon: ReactNode; title: ReactNode; sub: ReactNode; tone?: "ok" }) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-lg border px-3 py-2", tone === "ok" ? "border-stat/25 bg-stat-bg/50" : "border-line bg-sunken/50")}>
      <span className={cn(tone === "ok" ? "text-stat" : "text-muted")}>{icon}</span>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{title}</div>
        <div className="truncate text-xs text-muted">{sub}</div>
      </div>
    </div>
  );
}

export function PurposeSummary({ category, confidence, source, ruleHits, allowed }: { category: string; confidence?: number | null; source?: string; ruleHits?: string[]; allowed?: boolean }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="font-medium">{humanize(category)}</span>
      {confidence != null && (
        <Tip content="Classifier confidence. Below threshold sends the request to human review.">
          <span className="rounded bg-sunken px-1.5 py-0.5 font-mono text-xs text-muted">conf {confidence.toFixed(2)}</span>
        </Tip>
      )}
      {source && <span className="font-mono text-xs text-muted">{source}</span>}
      {ruleHits?.map((h) => (
        <span key={h} className={cn("rounded px-1.5 py-0.5 font-mono text-xs", allowed === false ? "bg-reject-bg text-reject" : "bg-sunken text-muted")}>
          {allowed === false ? `"${h}"` : h}
        </span>
      ))}
    </span>
  );
}
