import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowDownRight, ChevronRight, GitCompare, Inbox, Loader2, Lock, Pencil, Play, Sparkles, UserCheck } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, TRACK_IDS } from "@/api";
import { OutcomeBadges } from "@/components/decision";
import { Page, PageHeader } from "@/components/Layout";
import { Button, Card, Select, Skeleton, Tip } from "@/components/ui";
import { useCountUp, useQueue } from "@/hooks";
import { cn, fmtMs, shortOrg } from "@/lib/utils";
import type { QueueItem, StepKey } from "@/types";

const STEP_NAME: Record<StepKey, string> = {
  received: "Received",
  purpose: "Purpose check",
  plan: "Query plan",
  query: "Query",
  privacy: "Privacy",
  decision: "Decision",
};

type Filter = "all" | "REJECT" | "APPROVE_STATISTICAL" | "APPROVE_SPE" | "processing";

const needsReview = (r: QueueItem) => !!(r.needs_review || r.flags?.needs_review || r.decision === "NEEDS_REVIEW");

function Kpi({ label, value, tone, suffix }: { label: string; value: number; tone?: string; suffix?: string }) {
  const v = useCountUp(value, 500);
  return (
    <div className="min-w-[110px] flex-1 px-5 py-3.5">
      <div className={cn("font-mono text-[26px] font-medium leading-none tabular", tone)}>
        {suffix ? v.toFixed(1) : Math.round(v)}
        {suffix && <span className="ml-1 text-base text-muted">{suffix}</span>}
      </div>
      <div className="mt-1.5 text-sm text-muted">{label}</div>
    </div>
  );
}

function Flag({ tip, children, tone }: { tip: string; children: ReactNode; tone: string }) {
  return (
    <Tip content={tip}>
      <span className={cn("inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-xs font-medium", tone)}>{children}</span>
    </Tip>
  );
}

export default function StaffQueue() {
  const { data, isLoading } = useQueue();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [filter, setFilter] = useState<Filter>("all");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [running, setRunning] = useState(false);

  const rows = useMemo(() => {
    const all = [...(data ?? [])].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
    return all.filter((r) => {
      if (reviewOnly && !needsReview(r)) return false;
      if (filter === "all") return true;
      if (filter === "processing") return r.status === "processing" || r.status === "received";
      return r.decision === filter;
    });
  }, [data, filter, reviewOnly]);

  const kpi = useMemo(() => {
    const d = data ?? [];
    const decided = d.filter((r) => r.decision);
    const times = decided.map((r) => r.elapsed_ms ?? 0).filter(Boolean);
    return {
      total: d.length,
      rejected: decided.filter((r) => r.decision === "REJECT").length,
      stats: decided.filter((r) => r.decision === "APPROVE_STATISTICAL").length,
      spe: decided.filter((r) => r.decision === "APPROVE_SPE").length,
      review: d.filter(needsReview).length,
      avg: times.length ? times.reduce((a, b) => a + b, 0) / times.length / 1000 : 0,
    };
  }, [data]);

  const runAll = async () => {
    setRunning(true);
    try {
      const r = await api.batch(TRACK_IDS);
      toast.success(`Submitted ${r.ids.length} sample requests`, { description: "Watch them run through the pipeline." });
      qc.invalidateQueries({ queryKey: ["queue"] });
    } catch (e) {
      toast.error("Batch run failed", { description: (e as Error).message });
    } finally {
      setRunning(false);
    }
  };

  return (
    <Page wide>
      <PageHeader
        eyebrow="HDAB staff console"
        title="Request queue"
        subtitle="Every request is decided automatically and explained. Staff review the hard cases, confirm and release."
        right={
          <Button size="lg" onClick={runAll} disabled={running}>
            {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />} Run all 10 samples
          </Button>
        }
      />

      <Card className="mb-5 flex flex-wrap divide-x divide-line">
        <Kpi label="requests" value={kpi.total} />
        <Kpi label="rejected" value={kpi.rejected} tone="text-reject" />
        <Kpi label="statistics" value={kpi.stats} tone="text-stat" />
        <Kpi label="secure environment" value={kpi.spe} tone="text-spe" />
        <Kpi label="need review" value={kpi.review} tone={kpi.review ? "text-warn" : undefined} />
        <Kpi label="avg time to decision" value={kpi.avg} suffix="s" />
      </Card>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="w-56">
          <Select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
            <option value="all">All decisions</option>
            <option value="REJECT">Rejected</option>
            <option value="APPROVE_STATISTICAL">Approved · Statistics</option>
            <option value="APPROVE_SPE">Approved · SPE</option>
            <option value="processing">In progress</option>
          </Select>
        </div>
        <button
          onClick={() => setReviewOnly(!reviewOnly)}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-base font-medium transition-colors",
            reviewOnly ? "border-warn/40 bg-warn-bg text-warn" : "border-line bg-surface text-muted hover:text-ink",
          )}
        >
          <UserCheck size={15} /> Needs review
          {kpi.review > 0 && <span className="rounded-full bg-warn px-1.5 font-mono text-[11px] text-white">{kpi.review}</span>}
        </button>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-base">
          <thead className="bg-sunken/70">
            <tr className="border-b border-line text-left text-xs font-semibold uppercase tracking-[0.06em] text-muted">
              <th className="h-10 w-[84px] pl-5">ID</th>
              <th className="h-10">Applicant</th>
              <th className="h-10">Purpose</th>
              <th className="h-10 w-[120px]">Type</th>
              <th className="h-10">Decision</th>
              <th className="h-10 w-[150px]">Flags</th>
              <th className="h-10 w-[80px] pr-3 text-right">Time</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="h-12 border-b border-line">
                  <td colSpan={8} className="px-5">
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              ))}
            <AnimatePresence initial={false}>
              {rows.map((r) => {
                const inFlight = r.status === "processing" || r.status === "received";
                const sup = r.flags?.suppressed_cells ?? 0;
                return (
                  <motion.tr
                    key={r.id}
                    layout="position"
                    initial={{ opacity: 0, backgroundColor: "rgb(var(--accent) / 0.08)" }}
                    animate={{ opacity: 1, backgroundColor: "rgb(var(--accent) / 0)" }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.5 }}
                    onClick={() => nav(`/staff/requests/${encodeURIComponent(r.id)}`)}
                    className="group h-[52px] cursor-pointer border-b border-line last:border-0 hover:!bg-sunken/60"
                  >
                    <td className="pl-5 font-mono text-sm font-medium">{r.id}</td>
                    <td className="max-w-[240px] pr-4">
                      <div className="truncate font-medium">{shortOrg(r.applicant.organisation)}</div>
                      <div className="truncate text-xs text-muted">
                        {r.applicant.name} · {r.applicant.country}
                      </div>
                    </td>
                    <td className="max-w-[240px] truncate pr-4 text-muted">{r.purpose_short ?? "–"}</td>
                    <td className="text-sm text-muted">{/access/i.test(r.requested_as) ? "Access appl." : "Statistics"}</td>
                    <td className="pr-3">
                      {inFlight || !r.decision ? (
                        <span className="inline-flex items-center gap-2 text-sm font-medium text-accent">
                          <Loader2 size={14} className="animate-spin" />
                          <AnimatePresence mode="wait">
                            <motion.span key={r.current_step ?? "x"} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
                              {r.current_step ? STEP_NAME[r.current_step] : "Queued"}…
                            </motion.span>
                          </AnimatePresence>
                        </span>
                      ) : (
                        <motion.span initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.35 }} className="inline-flex">
                          <OutcomeBadges outcome={r.decision} needsReview={needsReview(r)} size="sm" compact />
                        </motion.span>
                      )}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {r.flags?.downgraded && (
                          <Flag tip="Downgraded: asked for records, statistics approved (Art. 66)" tone="bg-warn-bg text-warn">
                            <ArrowDownRight size={12} /> stats
                          </Flag>
                        )}
                        {sup > 0 && (
                          <Flag tip={`${sup} cells protected by the small-cell rule`} tone="hatch bg-sunken text-muted">
                            <Lock size={11} /> {sup}
                          </Flag>
                        )}
                        {r.flags?.differencing_risk && (
                          <Flag tip="Differencing risk: overlaps an earlier query" tone="bg-warn-bg text-warn">
                            <GitCompare size={12} />
                          </Flag>
                        )}
                        {r.flags?.overridden && (
                          <Flag tip="Decision overridden by staff" tone="bg-gold/10 text-gold">
                            <Pencil size={11} />
                          </Flag>
                        )}
                        {r.flags?.low_confidence && (
                          <Flag tip="LLM low confidence" tone="bg-warn-bg text-warn">
                            <Sparkles size={11} /> low
                          </Flag>
                        )}
                        {needsReview(r) && (
                          <Flag tip="Needs human review" tone="bg-warn-bg text-warn">
                            <AlertTriangle size={11} /> review
                          </Flag>
                        )}
                      </div>
                    </td>
                    <td className="pr-3 text-right font-mono text-sm tabular text-muted">{fmtMs(r.elapsed_ms)}</td>
                    <td className="pr-3 text-muted/50 group-hover:text-ink">
                      <ChevronRight size={16} />
                    </td>
                  </motion.tr>
                );
              })}
            </AnimatePresence>
          </tbody>
        </table>
        {!isLoading && rows.length === 0 && (
          <div className="flex flex-col items-center py-16 text-center">
            <Inbox size={28} className="text-muted/60" />
            <div className="mt-3 font-medium">{data?.length ? "No requests match this filter" : "The queue is empty"}</div>
            <p className="mt-1 text-sm text-muted">{data?.length ? "Change the filter to see more." : "Run the 10 sample requests or submit one from the applicant portal."}</p>
            {!data?.length && (
              <Button className="mt-5" onClick={runAll} disabled={running}>
                <Play size={15} /> Run all 10 samples
              </Button>
            )}
          </div>
        )}
      </Card>
    </Page>
  );
}
