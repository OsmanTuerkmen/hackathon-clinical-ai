import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, CheckCircle2, Clock, Loader2, Minus, Play, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api";
import { DecisionBadge } from "@/components/decision";
import { Page, PageHeader } from "@/components/Layout";
import { Button, Card, Dialog, DialogContent, SectionLabel } from "@/components/ui";
import { useCountUp } from "@/hooks";
import { cn, fmtMs } from "@/lib/utils";
import type { MetricsRow, MetricsRun, MetricsRunCell } from "@/types";

function getStoredRun(): string | null {
  try {
    return sessionStorage.getItem("ehds.metricsRun");
  } catch {
    return null;
  }
}

function Tile({
  label, value, total, target, done, leak, format, sub,
}: { label: string; value: number | null; total?: number; target: boolean; done: boolean; leak?: boolean; format?: (n: number) => string; sub?: string }) {
  const v = useCountUp(value ?? 0, 700);
  const tone = value === null ? "neutral" : leak ? "red" : done && target ? "green" : done ? "amber" : "neutral";
  return (
    <motion.div
      layout
      className={cn(
        "relative overflow-hidden rounded-xl border bg-surface px-5 py-4 transition-colors duration-500",
        tone === "green" && "border-stat/30 bg-stat-bg/50",
        tone === "amber" && "border-warn/30 bg-warn-bg/60",
        tone === "red" && "border-reject/40 bg-reject-bg",
        tone === "neutral" && "border-line",
      )}
    >
      <div className="flex items-center justify-between">
        <SectionLabel>{label}</SectionLabel>
        <AnimatePresence>
          {tone === "green" && (
            <motion.span initial={{ scale: 0, rotate: -40 }} animate={{ scale: 1, rotate: 0 }} className="flex h-5 w-5 items-center justify-center rounded-full bg-stat text-white">
              <Check size={12} strokeWidth={3} />
            </motion.span>
          )}
          {(tone === "amber" || tone === "red") && <AlertTriangle size={15} className={tone === "red" ? "text-reject" : "text-warn"} />}
        </AnimatePresence>
      </div>
      <div className={cn("mt-2 font-mono text-[40px] font-medium leading-none tracking-tight tabular", tone === "red" && "text-reject")}>
        {value === null ? <span className="text-muted/50">–</span> : format ? format(v) : Math.round(v)}
        {total !== undefined && value !== null && <span className="text-[22px] text-muted"> / {total}</span>}
      </div>
      {sub && <div className="mt-1.5 text-sm text-muted">{sub}</div>}
    </motion.div>
  );
}

function RunCell({ cell, expected, onClick }: { cell: MetricsRunCell | null | undefined; expected: string; onClick: () => void }) {
  if (!cell)
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-dashed border-line text-muted/50">
        <Minus size={12} />
      </span>
    );
  const ok = cell.decision === expected && cell.articles_ok !== false && cell.numbers_ok !== false && !cell.leaks;
  return (
    <motion.button
      initial={{ scale: 0.5, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 20 }}
      onClick={ok ? undefined : onClick}
      title={`${cell.decision} · ${fmtMs(cell.ms)}`}
      className={cn("inline-flex h-7 w-7 items-center justify-center rounded-md", ok ? "bg-stat-bg text-stat" : "cursor-pointer bg-reject-bg text-reject ring-1 ring-reject/30")}
    >
      {ok ? <Check size={14} strokeWidth={3} /> : <X size={14} strokeWidth={3} />}
    </motion.button>
  );
}

function TimingChart({ rows, threshold }: { rows: MetricsRow[]; threshold: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = rows.map((r) => ({ id: r.id, ms: Math.max(0, ...r.runs.map((c) => c?.ms ?? 0)) }));
  const maxMs = Math.max(threshold, ...data.map((d) => d.ms));
  const W = 720, H = 210, PL = 44, PB = 26, PT = 22;
  const iw = W - PL - 8, ih = H - PB - PT;
  const bw = Math.min(30, iw / data.length - 14);
  const y = (ms: number) => PT + ih - (ms / maxMs) * ih;
  const ticks = [0, 15000, 30000, 45000, 60000].filter((t) => t <= maxMs);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Slowest of three runs per request, seconds, with 60 second threshold">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PL} x2={W - 8} y1={y(t)} y2={y(t)} stroke="rgb(var(--line))" strokeWidth={1} />
            <text x={PL - 8} y={y(t) + 4} textAnchor="end" className="fill-muted font-mono" fontSize={10}>
              {t / 1000}s
            </text>
          </g>
        ))}
        <line x1={PL} x2={W - 8} y1={y(threshold)} y2={y(threshold)} stroke="rgb(var(--reject))" strokeWidth={1.5} strokeDasharray="5 4" />
        <text x={W - 10} y={y(threshold) - 6} textAnchor="end" className="fill-reject" fontSize={11} fontWeight={600}>
          60 s limit
        </text>
        {data.map((d, i) => {
          const cx = PL + (iw / data.length) * (i + 0.5);
          const h = Math.max(0, PT + ih - y(d.ms));
          return (
            <g key={d.id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={cx - iw / data.length / 2} y={PT} width={iw / data.length} height={ih} fill="transparent" />
              <motion.path
                initial={false}
                animate={{ d: barPath(cx - bw / 2, PT + ih, bw, h) }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                fill="rgb(var(--accent))"
                opacity={hover === null || hover === i ? 1 : 0.45}
              />
              <text x={cx} y={H - 8} textAnchor="middle" className="fill-muted font-mono" fontSize={10.5}>
                {d.id}
              </text>
            </g>
          );
        })}
      </svg>
      {hover !== null && data[hover] && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded-md bg-ink px-2.5 py-1.5 text-xs text-ink-fg shadow-lg"
          style={{ left: `${((PL + (iw / data.length) * (hover + 0.5)) / W) * 100}%`, top: `${(y(data[hover].ms) / H) * 100 - 18}%` }}
        >
          <span className="font-mono">{data[hover].id}</span> · slowest run <span className="font-mono font-medium">{fmtMs(data[hover].ms || null)}</span>
        </div>
      )}
    </div>
  );
}

function barPath(x: number, base: number, w: number, h: number) {
  const r = Math.min(4, h, w / 2);
  if (h <= 0) return `M${x},${base} h${w} v0 h${-w} Z`;
  return `M${x},${base} V${base - h + r} Q${x},${base - h} ${x + r},${base - h} H${x + w - r} Q${x + w},${base - h} ${x + w},${base - h + r} V${base} Z`;
}

export default function Metrics() {
  const [runId, setRunId] = useState<string | null>(getStoredRun);
  const [starting, setStarting] = useState(false);
  const [diff, setDiff] = useState<MetricsRow | null>(null);
  const { data, error } = useQuery<MetricsRun>({
    queryKey: ["metrics", runId],
    queryFn: () => api.metrics(runId!),
    enabled: !!runId,
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === "running" || !q.state.data ? 500 : false),
  });

  useEffect(() => {
    if (error) {
      setRunId(null);
      try {
        sessionStorage.removeItem("ehds.metricsRun");
      } catch {
        /* ignore */
      }
    }
  }, [error]);

  const start = async () => {
    setStarting(true);
    try {
      const r = await api.metricsRun(3, true);
      setRunId(r.run_id);
      try {
        sessionStorage.setItem("ehds.metricsRun", r.run_id);
      } catch {
        /* ignore */
      }
    } catch (e) {
      toast.error("Could not start evaluation", { description: (e as Error).message });
    } finally {
      setStarting(false);
    }
  };

  const s = data?.summary;
  const done = data?.status === "done";
  const running = data?.status === "running" || starting;
  const runsN = data?.runs_total ?? Math.max(3, ...(data?.rows ?? []).map((r) => r.runs.length));
  const custom = (data?.custom ?? []).map((c) => {
    const runs = c.runs ?? [];
    const decision = c.decision ?? runs.find((x) => x?.decision)?.decision ?? null;
    const ok = runs.length ? runs.every((x) => x && (!c.expected || x.decision === c.expected) && x.articles_ok !== false && x.numbers_ok !== false && !x.leaks) : !!decision;
    return { id: c.id, title: c.title, decision, ms: c.ms ?? (runs.length ? Math.max(0, ...runs.map((x) => x?.ms ?? 0)) : undefined), ok, expected: c.expected };
  });
  const customDone = s?.custom_correct ?? custom.filter((c) => c.decision && c.ok).length;
  const customTotal = s?.custom_total ?? custom.length;

  return (
    <Page wide>
      <PageHeader
        eyebrow="Evaluation"
        title="Metrics scoreboard"
        subtitle={<>Evaluated against <span className="font-mono text-ink">requests/expected.json</span>: decisions, articles, numbers, privacy leaks, consistency across runs and time to answer.</>}
        right={
          <Button size="lg" onClick={start} disabled={running}>
            {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />} Run all 10 × 3
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Tile label="Decisions" value={s ? s.decisions_correct : null} total={s?.decisions_total ?? 10} target={!!s && s.decisions_correct === s.decisions_total} done={done} sub="decision + articles" />
        <Tile label="Numbers" value={s ? s.numbers_correct : null} total={s?.numbers_total ?? 6} target={!!s && s.numbers_correct === s.numbers_total} done={done} sub="every expected value" />
        <Tile label="Privacy" value={s ? s.privacy_leaks : null} target={!!s && s.privacy_leaks === 0} done={done} leak={!!s && s.privacy_leaks > 0} sub="leaks" />
        <Tile label="Consistency" value={s ? s.consistent : null} total={s?.consistent_total ?? 10} target={!!s && s.consistent === s.consistent_total} done={done} sub={`identical over ${runsN} runs`} />
        <Tile label="Slowest" value={s ? s.slowest_ms / 1000 : null} target={!!s && s.slowest_ms < s.threshold_ms} done={done} format={(n) => `${n.toFixed(1)}s`} sub="target < 60 s" />
        <Tile label="Custom tests" value={data?.custom ? customDone : null} total={customTotal || 2} target={!!data?.custom && customDone === customTotal} done={done} sub="new + adversarial requests" />
      </div>

      {!runId && !starting && (
        <Card className="mt-6 flex flex-col items-center py-14 text-center">
          <ShieldCheck size={28} className="text-muted/60" />
          <div className="mt-3 font-medium">No evaluation run yet</div>
          <p className="mt-1 max-w-md text-sm text-muted">Runs all 10 track requests three times plus the custom requests, and compares every decision, article and number with expected.json.</p>
          <Button className="mt-5" onClick={start}>
            <Play size={15} /> Run all 10 × 3
          </Button>
        </Card>
      )}

      {data && (
        <div className="mt-6 grid gap-6 xl:grid-cols-[1.3fr_1fr]">
          <Card className="overflow-hidden">
            <table className="w-full text-base">
              <thead className="bg-sunken/70">
                <tr className="border-b border-line text-left text-xs font-semibold uppercase tracking-[0.06em] text-muted">
                  <th className="h-10 pl-5">Req</th>
                  <th>Expected</th>
                  {Array.from({ length: runsN }).map((_, i) => (
                    <th key={i} className="text-center">Run {i + 1}</th>
                  ))}
                  <th>Articles</th>
                  <th>Numbers</th>
                  <th className="pr-5 text-right">Max t</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => {
                  const maxMs = Math.max(0, ...r.runs.map((c) => c?.ms ?? 0));
                  const allIn = r.runs.length >= runsN && r.runs.every(Boolean);
                  const artsOk = r.runs.filter(Boolean).every((c) => c!.articles_ok !== false);
                  const arts = r.expected_articles ?? r.runs.find((c) => c?.articles)?.articles ?? [];
                  const numsOk = r.runs.filter(Boolean).every((c) => c!.numbers_ok !== false);
                  const matched = r.values_matched ?? (allIn && r.values_total != null ? (numsOk ? r.values_total : null) : null);
                  return (
                    <tr key={r.id} className="h-12 border-b border-line last:border-0">
                      <td className="pl-5 font-mono text-sm font-medium">{r.id}</td>
                      <td>
                        <DecisionBadge decision={r.expected} size="sm" compact />
                      </td>
                      {Array.from({ length: runsN }).map((_, i) => (
                        <td key={i} className="text-center">
                          <RunCell cell={r.runs[i]} expected={r.expected} onClick={() => setDiff(r)} />
                        </td>
                      ))}
                      <td className="font-mono text-sm">
                        {allIn ? (
                          <span className={artsOk ? "text-stat" : "text-reject"}>
                            {arts.join(",")} {artsOk ? "✓" : "✗"}
                          </span>
                        ) : (
                          <span className="text-muted/50">…</span>
                        )}
                      </td>
                      <td className="font-mono text-sm">
                        {r.values_total == null || r.expected === "REJECT" ? (
                          <span className="text-muted">n/a</span>
                        ) : !allIn ? (
                          <span className="text-muted/50">…</span>
                        ) : matched == null ? (
                          <span className="text-reject">✗ mismatch</span>
                        ) : (
                          <span className={matched === r.values_total ? "text-stat" : "text-reject"}>
                            {matched}/{r.values_total} {matched === r.values_total ? "✓" : "✗"}
                          </span>
                        )}
                      </td>
                      <td className="pr-5 text-right font-mono text-sm tabular text-muted">{maxMs ? fmtMs(maxMs) : "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <div className="space-y-6">
            <Card className="p-5">
              <div className="mb-2 flex items-center justify-between">
                <SectionLabel>Time to answer · slowest of {runsN} runs</SectionLabel>
                <Clock size={14} className="text-muted" />
              </div>
              <TimingChart rows={data.rows} threshold={s?.threshold_ms ?? 60000} />
            </Card>
            {custom.length > 0 && (
              <Card className="p-5">
                <div className="flex items-center justify-between">
                  <SectionLabel>Custom requests (not in the track set)</SectionLabel>
                  <span className="font-mono text-xs text-muted">{custom.length}</span>
                </div>
                <div className="mt-3 max-h-[340px] space-y-1.5 overflow-y-auto pr-1 scrollbar-thin">
                  {custom.map((c) => (
                    <div key={c.id} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2">
                      <span className="w-9 font-mono text-sm font-medium">{c.id}</span>
                      <span className="min-w-0 flex-1 truncate text-sm text-muted">
                        {c.title ?? (c.id === "C01" ? "Inpatient stays by hospital" : c.id === "C02" ? "Stays by primary diagnosis (S72)" : "Custom request")}
                      </span>
                      {c.decision ? <DecisionBadge decision={c.decision} size="sm" compact /> : <Loader2 size={14} className="animate-spin text-accent" />}
                      {c.decision && (c.ok ? <Check size={14} className="text-stat" strokeWidth={3} /> : <X size={14} className="text-reject" strokeWidth={3} />)}
                      <span className="w-12 text-right font-mono text-xs text-muted">{c.ms != null ? fmtMs(c.ms) : ""}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
            {done && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-2 text-sm text-stat">
                <CheckCircle2 size={15} /> Run <span className="font-mono">{runId}</span> complete
              </motion.div>
            )}
          </div>
        </div>
      )}

      <Dialog open={!!diff} onOpenChange={(o) => !o && setDiff(null)}>
        <DialogContent title={`Mismatch · ${diff?.id ?? ""}`} description="Expected (expected.json) vs what the pipeline returned.">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <SectionLabel className="mb-1">Expected</SectionLabel>
              <div className="rounded-lg bg-sunken p-3 font-mono text-xs">{diff?.expected} · Art. {(diff?.expected_articles ?? []).join(", ")}</div>
            </div>
            <div>
              <SectionLabel className="mb-1">Got</SectionLabel>
              <div className="space-y-1 rounded-lg bg-reject-bg/60 p-3 font-mono text-xs">
                {diff?.runs.map((c, i) => (
                  <div key={i}>
                    run {i + 1}: {c?.decision ?? "–"} {c?.articles_ok === false && "· articles ✗"} {c?.numbers_ok === false && "· numbers ✗"}
                  </div>
                ))}
              </div>
            </div>
          </div>
          {diff?.diff && diff.diff.length > 0 && (
            <pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-[#0f1724] p-3 font-mono text-[11px] text-[#d7e0ea]">{JSON.stringify(diff.diff, null, 2)}</pre>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}
