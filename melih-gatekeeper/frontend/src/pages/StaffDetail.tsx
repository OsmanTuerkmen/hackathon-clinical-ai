import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BadgeCheck, CheckCircle2, Clock, DatabaseZap, ExternalLink, FileText, Loader2, LockKeyhole, MessageSquare, Pencil, ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api";
import { ArticleChips, FieldRow, OutcomeBadges, PendingBadge } from "@/components/decision";
import { Page } from "@/components/Layout";
import {
  AuditTimeline, DataFlowPanel, FiveSafesRecord, PrivacyChecklist, PurposeSummary, QueryPlanView, ReviewReasons, RuleTrace, SignalsPanel,
} from "@/components/panels";
import { PipelineStepper } from "@/components/PipelineStepper";
import { countProtected, ResultsTable } from "@/components/ResultsTable";
import {
  Button, Callout, Card, CardHeader, Dialog, DialogContent, DialogTrigger, SectionLabel, Select, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, Textarea,
} from "@/components/ui";
import { useDisplaySteps, useRequest } from "@/hooks";
import { cn, fmtMs, shortOrg, speIdOf } from "@/lib/utils";
import type { Decision, RequestDetail } from "@/types";
import NotFound from "./NotFound";

const ACTOR = "staff:anna";
const ALL_ARTICLES = ["53", "54", "66", "67", "68", "69", "71", "73"];
const DEFAULT_ARTS: Record<Decision, string[]> = {
  REJECT: ["54"],
  APPROVE_STATISTICAL: ["53", "69"],
  APPROVE_SPE: ["53", "66", "68", "73"],
  NEEDS_REVIEW: [],
};

export default function StaffDetail() {
  const { id } = useParams();
  const { data, error, isLoading } = useRequest(id);
  const { steps, finished } = useDisplaySteps(data?.steps);
  const [tab, setTab] = useState("decision");

  if (error && (error as { status?: number }).status === 404) return <NotFound message={`No request ${id}`} />;
  const d = data?.decision;
  const decided = !!d && finished;
  const r = data?.request;
  const isReject = d?.outcome === "REJECT";
  const protectedCells = data?.result?.kind === "table" ? countProtected(data.result) : 0;

  return (
    <Page wide>
      <Link to="/staff" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft size={14} /> Queue
      </Link>

      <Card className="mb-6 px-6 pb-5 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm text-muted">
              <span className="font-mono font-medium text-ink">{id}</span>
              {r && (
                <>
                  · <span>{/access/i.test(r.requested_as) ? "Data access application" : "Health data request"}</span> · {r.requested_format}
                </>
              )}
            </div>
            <h1 className="mt-1 truncate text-xl font-semibold tracking-tight">
              {r ? (
                <>
                  {r.applicant.name} <span className="font-normal text-muted">· {shortOrg(r.applicant.organisation)} ({r.applicant.country})</span>
                </>
              ) : (
                <Skeleton className="h-7 w-96" />
              )}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {decided && d ? <OutcomeBadges outcome={d.outcome} needsReview={d.needs_review} downgradedFrom={d.downgraded_from} reveal size="lg" /> : <PendingBadge />}
            {data?.status === "released" && (
              <span className="inline-flex h-7 items-center gap-1 rounded-md bg-stat-bg px-2 text-sm font-medium text-stat">
                <BadgeCheck size={14} /> Released
              </span>
            )}
            <span className="inline-flex items-center gap-1 font-mono text-sm tabular text-muted">
              <Clock size={13} /> {fmtMs(data?.elapsed_ms)}
            </span>
          </div>
        </div>
        <div className="mt-6">
          <PipelineStepper steps={steps} outcome={decided ? d?.outcome : null} />
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="decision">Decision</TabsTrigger>
              <TabsTrigger value="plan">Query plan</TabsTrigger>
              <TabsTrigger value="results">
                Results
                {protectedCells > 0 && <span className="hatch rounded px-1 font-mono text-[11px] text-muted">{protectedCells}</span>}
              </TabsTrigger>
              <TabsTrigger value="privacy">Privacy</TabsTrigger>
              <TabsTrigger value="audit">
                Audit {data && <span className="font-mono text-[11px] text-muted">{data.audit.length}</span>}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="decision">
              {isLoading || !data ? <Skeleton className="h-64 w-full" /> : !d ? <Processing /> : <DecisionTab data={data} />}
            </TabsContent>

            <TabsContent value="plan">
              {data?.plan ? (
                <QueryPlanView plan={data.plan} definitions={data.request.definitions ?? []} />
              ) : isReject ? (
                <NoData />
              ) : (
                <Processing what="query plan" />
              )}
            </TabsContent>

            <TabsContent value="results">
              {data?.result?.kind === "table" ? (
                <div>
                  <ResultsTable result={data.result} />
                  <p className="mt-3 flex items-center gap-1.5 text-sm text-muted">
                    <LockKeyhole size={13} /> Even staff never see small cells: suppressed values are not sent to the browser (value: null).
                  </p>
                </div>
              ) : data?.result?.kind === "cohort" ? (
                <Card className="flex flex-wrap items-center justify-between gap-6 p-6">
                  <div>
                    <SectionLabel>Cohort copied to secure processing environment</SectionLabel>
                    <div className="mt-2 font-mono text-[40px] font-medium leading-none tabular">{data.result.cohort_size.toLocaleString("en-US")}</div>
                    <div className="mt-1 text-sm text-muted">patients · exact count (inside SPE only)</div>
                  </div>
                  <Link to={`/spe/${speIdOf(data.spe, data.id)}`}>
                    <Button>
                      <LockKeyhole size={15} /> Open workspace
                    </Button>
                  </Link>
                </Card>
              ) : isReject ? (
                <NoData />
              ) : (
                <Processing what="results" />
              )}
            </TabsContent>

            <TabsContent value="privacy">
              {data?.privacy ? (
                <div className="space-y-4">
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-[28px] font-medium tabular">{data.privacy.opted_out_excluded.toLocaleString("en-US")}</span>
                    <span className="text-muted">opted-out patients excluded before any query (Art. 71)</span>
                  </div>
                  <PrivacyChecklist privacy={data.privacy} />
                </div>
              ) : isReject ? (
                <NoData />
              ) : (
                <Processing what="privacy checks" />
              )}
            </TabsContent>

            <TabsContent value="audit">
              {data ? (
                <Card className="p-5">
                  <AuditTimeline entries={data.audit} />
                </Card>
              ) : (
                <Skeleton className="h-40 w-full" />
              )}
            </TabsContent>
          </Tabs>
        </div>

        <aside className="space-y-4">
          {data && <StaffActions data={data} decided={decided} />}
          {data && <DataFlowPanel inference={data.inference} />}
        </aside>
      </div>
    </Page>
  );
}

function Processing({ what = "decision" }: { what?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-dashed border-line px-5 py-10 text-muted">
      <Loader2 size={16} className="animate-spin text-accent" /> Waiting for the {what}…
    </div>
  );
}

function NoData() {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line px-5 py-12 text-center">
      <DatabaseZap size={26} className="text-muted" />
      <div className="mt-3 font-medium">Rejected before any data was touched</div>
      <p className="mt-1 max-w-md text-sm text-muted">The purpose is prohibited (Art. 54), so no plan was made, no query ran and no privacy check was needed.</p>
    </div>
  );
}

function DecisionTab({ data }: { data: RequestDetail }) {
  const d = data.decision!;
  return (
    <div className="space-y-6">
      {d.review_reasons && d.review_reasons.length > 0 && <ReviewReasons reasons={d.review_reasons} />}

      <Card className="px-5 py-2">
        <FieldRow label="Decision">
          <OutcomeBadges outcome={d.outcome} needsReview={d.needs_review} downgradedFrom={d.downgraded_from} />
        </FieldRow>
        {(d.purpose || d.purpose_category) && (
          <FieldRow label="Purpose class">
            <PurposeSummary
              category={d.purpose?.category ?? d.purpose_category ?? ""}
              confidence={d.purpose?.confidence}
              source={d.purpose?.source ?? d.purpose_source}
              ruleHits={d.purpose?.rule_hits}
              allowed={d.purpose?.allowed ?? d.outcome !== "REJECT"}
            />
          </FieldRow>
        )}
        <FieldRow label="Articles">
          <ArticleChips ids={d.articles} />
        </FieldRow>
        {d.reason_staff && <FieldRow label="Reasoning">{d.reason_staff}</FieldRow>}
        {d.downgraded_from && (
          <FieldRow label="Downgrade">
            Asked for <span className="font-medium">{d.downgraded_from}</span>; statistics answer the question, so data minimisation applies (Art. 66).
          </FieldRow>
        )}
      </Card>

      {d.signals && <SignalsPanel signals={d.signals} />}

      {d.rule_trace && d.rule_trace.length > 0 && (
        <div>
          <SectionLabel className="mb-3">Rule trace</SectionLabel>
          <Card className="p-5">
            <RuleTrace items={d.rule_trace} />
          </Card>
        </div>
      )}

      {d.five_safes && (
        <div>
          <SectionLabel className="mb-3">Five Safes record</SectionLabel>
          <FiveSafesRecord safes={d.five_safes} />
        </div>
      )}
    </div>
  );
}

function StaffActions({ data, decided }: { data: RequestDetail; decided: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"release" | "override" | null>(null);
  const [note, setNote] = useState("");
  const released = data.status === "released";
  const d = data.decision;

  const release = async () => {
    setBusy("release");
    try {
      const updated = await api.release(data.id, ACTOR);
      qc.setQueryData(["request", data.id], updated);
      qc.invalidateQueries({ queryKey: ["queue"] });
      toast.success("Decision released to applicant", { description: "Audit entry decision.released added." });
    } catch (e) {
      toast.error("Release failed", { description: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader title="Staff actions" subtitle="Decision support with a human in the loop" icon={<ShieldCheck size={16} />} />
      <div className="space-y-2.5 px-5 pb-5">
        <Button className="w-full" onClick={release} disabled={!decided || released || busy !== null}>
          {busy === "release" ? <Loader2 size={15} className="animate-spin" /> : released ? <CheckCircle2 size={15} /> : <BadgeCheck size={15} />}
          {released ? "Released" : "Confirm & release"}
        </Button>
        <OverrideDialog data={data} disabled={!decided} />
        <Button
          variant="secondary"
          className="w-full"
          disabled={!decided}
          onClick={() => toast.message("Clarification requested", { description: `Message sent to ${data.request.applicant.name} (demo).` })}
        >
          <MessageSquare size={15} /> Request clarification
        </Button>
        <div className="pt-2">
          <SectionLabel className="mb-1.5">Internal note</SectionLabel>
          <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Visible to staff only" />
        </div>
        <div className="flex items-center justify-between border-t border-line pt-3 text-sm">
          <span className="text-muted">Applicant sees</span>
          <Link to={`/apply/${encodeURIComponent(data.id)}`} className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
            <FileText size={14} /> Preview letter <ExternalLink size={12} />
          </Link>
        </div>
        {d?.needs_review && <Callout tone="warn" title="Held for review">The letter is not final until a staff member confirms or overrides.</Callout>}
      </div>
    </Card>
  );
}

function OverrideDialog({ data, disabled }: { data: RequestDetail; disabled: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<Decision>(data.decision?.outcome ?? "APPROVE_STATISTICAL");
  const [arts, setArts] = useState<string[]>(data.decision?.articles ?? []);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    const key = ["request", data.id];
    const prev = qc.getQueryData<RequestDetail>(key);
    // optimistic audit entry
    if (prev)
      qc.setQueryData<RequestDetail>(key, {
        ...prev,
        audit: [...prev.audit, { ts: new Date().toISOString(), event: "decision.overridden", actor: ACTOR, detail: `→ ${decision} · Art. ${arts.join(", ")} · note="${note}"` }],
      });
    try {
      const updated = await api.override(data.id, { decision, articles: arts, note, actor: ACTOR });
      qc.setQueryData(key, updated);
      qc.invalidateQueries({ queryKey: ["queue"] });
      toast.success("Decision overridden", { description: "Logged to the audit trail. Suppressed cells stay suppressed." });
      setOpen(false);
      setNote("");
    } catch (e) {
      if (prev) qc.setQueryData(key, prev);
      toast.error("Override failed", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setDecision(data.decision?.outcome ?? "APPROVE_STATISTICAL");
          setArts(data.decision?.articles ?? []);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="secondary" className="w-full" disabled={disabled}>
          <Pencil size={15} /> Override decision
        </Button>
      </DialogTrigger>
      <DialogContent title="Override decision" description="Overrides are logged with your name and justification. They never reveal suppressed cells.">
        <div className="space-y-4">
          <div>
            <SectionLabel className="mb-1.5">New decision</SectionLabel>
            <Select
              value={decision}
              onChange={(e) => {
                const v = e.target.value as Decision;
                setDecision(v);
                setArts(DEFAULT_ARTS[v]);
              }}
            >
              <option value="REJECT">Reject (Art. 54)</option>
              <option value="APPROVE_STATISTICAL">Approve · Statistics</option>
              <option value="APPROVE_SPE">Approve · Secure environment</option>
            </Select>
          </div>
          <div>
            <SectionLabel className="mb-1.5">Articles</SectionLabel>
            <div className="flex flex-wrap gap-1.5">
              {ALL_ARTICLES.map((a) => {
                const on = arts.includes(a);
                return (
                  <button
                    key={a}
                    onClick={() => setArts(on ? arts.filter((x) => x !== a) : [...arts, a].sort())}
                    className={cn("h-7 rounded-md border px-2 font-mono text-xs font-medium transition-colors", on ? "border-gold bg-gold/15 text-ink" : "border-line text-muted hover:border-gold/50")}
                  >
                    Art. {a}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <SectionLabel className="mb-1.5">Justification (required)</SectionLabel>
            <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Clarified purpose with applicant by phone" />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={confirm} disabled={busy || note.trim().length < 3 || arts.length === 0}>
              {busy && <Loader2 size={15} className="animate-spin" />} Confirm override
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

