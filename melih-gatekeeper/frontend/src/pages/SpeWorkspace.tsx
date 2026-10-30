import { AnimatePresence, motion, useAnimationControls } from "framer-motion";
import {
  Ban, Check, ChevronRight, Cpu, Download, FileLock2, Loader2, LockKeyhole, ScrollText, Server, Table2, X,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, ApiError } from "@/api";
import { ArticleChips } from "@/components/decision";
import { Page } from "@/components/Layout";
import { AuditTimeline } from "@/components/panels";
import { Button, Card, Dialog, DialogContent, SectionLabel, Skeleton } from "@/components/ui";
import { useRequest, useSpe } from "@/hooks";
import { cn, fmtDate, shortOrg } from "@/lib/utils";
import type { AuditEntry, DownloadBlocked } from "@/types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function SpeWorkspacePage() {
  const { workspaceId } = useParams();
  const { data: ws, error, isLoading } = useSpe(workspaceId);
  const { data: req, refetch: refetchReq } = useRequest(ws?.request_id);
  const controls = useAnimationControls();
  const [downloading, setDownloading] = useState(false);
  const [blocked, setBlocked] = useState<DownloadBlocked | null>(null);
  const [attempts, setAttempts] = useState<number | null>(null);
  const [local, setLocal] = useState<AuditEntry[]>([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  const download = async () => {
    if (!workspaceId) return;
    setDownloading(true);
    let body: DownloadBlocked | null = null;
    try {
      await Promise.all([api.speDownload(workspaceId), wait(400)]);
      toast.error("Unexpected: download was not blocked");
    } catch (e) {
      await wait(0);
      if (e instanceof ApiError && e.status === 403) {
        const b = (e.body ?? {}) as Partial<DownloadBlocked>;
        body = {
          error: b.error ?? "download_blocked",
          article: b.article ?? "73",
          message: b.message ?? "Data in a secure processing environment cannot be downloaded.",
          audit_id: b.audit_id,
          blocked_attempts: b.blocked_attempts,
        };
      } else {
        toast.error("Download request failed", { description: (e as Error).message });
      }
    }
    setDownloading(false);
    if (!body) return;
    setBlocked(body);
    setAttempts((a) => body!.blocked_attempts ?? (a ?? ws?.blocked_attempts ?? 0) + 1);
    setLocal((l) => [
      ...l,
      {
        ts: new Date().toISOString(),
        event: "spe.download_blocked",
        actor: ws ? shortOrg(ws.permit.holder) : "applicant",
        detail: `${body!.audit_id ?? "audit"} · HTTP 403 · Art. ${body!.article}`,
      },
    ]);
    controls.start({ x: [0, -8, 8, -6, 6, 0], transition: { duration: 0.4 } });
    toast.error("Incident logged to HDAB audit trail", { description: body.audit_id ? `Audit ID ${body.audit_id}` : undefined });
    refetchReq();
  };

  const requestExport = async () => {
    if (!workspaceId) return;
    setExportOpen(true);
    setExportStatus(null);
    try {
      const r = await api.speExport(workspaceId, "model_weights");
      setExportStatus(r.status);
      refetchReq();
    } catch (e) {
      setExportStatus(`error: ${(e as Error).message}`);
    }
  };

  if (error) {
    return (
      <Page>
        <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
          <FileLock2 size={28} className="mx-auto text-muted" />
          <h1 className="mt-3 text-lg font-semibold">Workspace {workspaceId} is not available</h1>
          <p className="mt-1 text-muted">A secure processing environment exists only after an access application is approved (APPROVE_SPE). Run R05 first.</p>
          <Link to="/staff">
            <Button variant="secondary" className="mt-5">Go to the queue</Button>
          </Link>
        </Card>
      </Page>
    );
  }

  const speAudit = (req?.audit ?? []).filter((a) => a.event.startsWith("spe."));
  const known = new Set(speAudit.map((a) => a.detail ?? ""));
  const audit = [...speAudit, ...local.filter((l) => ![...known].some((k) => l.detail && k.includes(l.detail.split(" · ")[0])))].sort((a, b) =>
    a.ts.localeCompare(b.ts),
  );
  const shownAttempts = attempts ?? ws?.blocked_attempts ?? 0;

  return (
    <Page wide>
      {/* Environment banner */}
      <div className="mb-5 overflow-hidden rounded-xl bg-[#14213D] text-white shadow-sm dark:bg-[#0b1220]">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
              <LockKeyhole size={18} className="text-[#D6AE5A]" />
            </span>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#D6AE5A]">Secure Processing Environment</div>
              <div className="text-md font-semibold">
                Workspace <span className="font-mono">{workspaceId}</span>
                {ws && (
                  <>
                    {" "}· Permit <span className="font-mono">{ws.permit.number}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          {ws && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-white/75">
              <span>Holder: <span className="text-white">{shortOrg(ws.permit.holder)}</span></span>
              <span>Valid until <span className="text-white">{fmtDate(ws.permit.valid_until)}</span></span>
              <span className="font-mono">schema {ws.schema}</span>
            </div>
          )}
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-[#7ed3a6]" /> Session monitored
            </span>
            {ws && (
              <span className="[&_button]:border-[#D6AE5A]/60 [&_button]:bg-white/5 [&_button]:text-white">
                <ArticleChips ids={ws.permit.articles} size="sm" />
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Block banner */}
      <AnimatePresence>
        {blocked && (
          <motion.div
            key={shownAttempts}
            initial={{ opacity: 0, y: -24, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 28 }}
            className="mb-5 overflow-hidden"
          >
            <div className="flex items-center gap-4 rounded-xl border-2 border-reject bg-reject px-5 py-4 text-white shadow-[0_10px_30px_-10px_rgb(var(--reject)/0.6)]">
              <Ban size={26} strokeWidth={2.4} className="shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm font-semibold tracking-wide">DOWNLOAD BLOCKED · HTTP 403 · Art. {blocked.article}</div>
                <div className="mt-0.5 text-md">
                  {blocked.message} <span className="opacity-85">This attempt has been logged.</span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="font-mono text-[26px] font-medium leading-none tabular">{shownAttempts}</div>
                <div className="text-xs opacity-80">blocked attempts</div>
              </div>
              <button onClick={() => setBlocked(null)} className="rounded-md p-1 text-white/80 hover:bg-white/10 hover:text-white" aria-label="Dismiss">
                <X size={16} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <motion.div animate={controls}>
          <Card className={cn("overflow-hidden transition-[border-color,box-shadow] duration-300", blocked && "border-2 border-reject shadow-[0_0_0_4px_rgb(var(--reject)/0.12)]")}>
            {isLoading || !ws ? (
              <div className="space-y-3 p-6">
                <Skeleton className="h-10 w-1/3" />
                <Skeleton className="h-40 w-full" />
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-3 border-b border-line bg-sunken/40 px-6 py-3.5">
                  <Button variant="secondary" size="lg" onClick={download} disabled={downloading} className={cn(blocked && "border-reject/40 text-reject")}>
                    {downloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} Download dataset (CSV)
                  </Button>
                  <Button variant="secondary" size="lg" onClick={requestExport}>
                    <Cpu size={16} /> Export model weights <ChevronRight size={14} className="-ml-1" /> request review
                  </Button>
                  <span className="ml-auto text-sm text-muted">
                    Blocked attempts: <span className={cn("font-mono font-medium", shownAttempts > 0 ? "text-reject" : "text-ink")}>{shownAttempts}</span>
                  </span>
                </div>
                <div className="grid lg:grid-cols-[300px_1fr]">
                  <div className="border-b border-line p-6 lg:border-b-0 lg:border-r">
                    <SectionLabel>Cohort</SectionLabel>
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-2 font-mono text-[52px] font-medium leading-none tracking-tight tabular"
                    >
                      {ws.cohort_size.toLocaleString("en-US")}
                    </motion.div>
                    <div className="mt-1 text-muted">patients, pseudonymised</div>
                    <p className="mt-4 text-sm leading-relaxed">{ws.cohort_definition}</p>
                    <SectionLabel className="mt-6">Record types copied</SectionLabel>
                    <ul className="mt-2 space-y-1.5">
                      {ws.tables.map((t) => (
                        <li key={t.name} className={cn("flex items-center gap-2 text-sm", !t.copied && "text-muted")}>
                          {t.copied ? <Check size={14} className="text-stat" strokeWidth={2.6} /> : <X size={14} className="text-muted" />}
                          <span className={cn("font-mono", !t.copied && "line-through decoration-muted/50")}>{t.name}</span>
                          {t.note && <span className="truncate text-xs text-muted">· {t.note}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="min-w-0 p-6">
                    <SectionLabel>
                      Tables in this workspace · schema <span className="font-mono normal-case">{ws.schema}</span>
                    </SectionLabel>
                    <div className="mt-2 overflow-hidden rounded-lg border border-line">
                      {ws.tables.map((t) => (
                        <div key={t.name} className={cn("flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-0", !t.copied && "bg-sunken/50 text-muted")}>
                          {t.copied ? <Table2 size={15} className="text-spe" /> : <X size={15} />}
                          <span className="w-32 font-mono text-sm font-medium">{t.name}</span>
                          <span className="font-mono text-sm tabular">{t.copied ? `${t.rows.toLocaleString("en-US")} rows` : "–"}</span>
                          <span className="ml-auto truncate text-xs text-muted">{t.note ?? (t.copied ? "copied" : "not copied")}</span>
                        </div>
                      ))}
                    </div>
                    {ws.preview && (
                      <>
                        <SectionLabel className="mt-6">
                          Preview · first {ws.preview.rows.length} rows of <span className="font-mono normal-case">{ws.preview.table}</span> · inside SPE only
                        </SectionLabel>
                        <div className="mt-2 overflow-x-auto rounded-lg border border-line">
                          <table className="w-full text-sm">
                            <thead className="bg-sunken/70">
                              <tr>
                                {ws.preview.columns.map((c) => (
                                  <th key={c} className="h-9 px-4 text-left font-mono text-xs font-medium text-muted">
                                    {c}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {ws.preview.rows.map((row, i) => (
                                <tr key={i} className="h-9 border-t border-line">
                                  {row.map((v, j) => (
                                    <td key={j} className="px-4 font-mono text-[13px] tabular">
                                      {String(v)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </>
            )}
          </Card>
        </motion.div>

        <aside className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <SectionLabel>Workspace audit</SectionLabel>
              <ScrollText size={14} className="text-muted" />
            </div>
            <div className="mt-3">
              {audit.length ? (
                <AuditTimeline entries={audit} dense />
              ) : (
                <p className="text-sm text-muted">No events yet. Every action in this workspace is logged.</p>
              )}
            </div>
          </Card>
          <Card className="p-5 text-sm">
            <div className="flex items-center gap-2 font-semibold">
              <Server size={15} className="text-spe" /> Permit conditions
            </div>
            <ul className="mt-3 space-y-2 text-muted">
              <li>• Records stay in schema <span className="font-mono text-ink">{ws?.schema ?? "…"}</span>; there is no export path.</li>
              <li>• Only non-personal outputs (model weights, metrics) may leave, after HDAB output review (Art. 73).</li>
              <li>• Only the selected patients and requested record types were copied.</li>
              <li>• Access is personal to the permit holder and audited.</li>
            </ul>
            {ws?.request_id && (
              <Link to={`/staff/requests/${ws.request_id}`} className="mt-4 inline-flex items-center gap-1 font-medium text-accent hover:underline">
                View request {ws.request_id} <ChevronRight size={14} />
              </Link>
            )}
          </Card>
        </aside>
      </div>

      <Dialog open={exportOpen} onOpenChange={setExportOpen}>
        <DialogContent title="Export requires output review" description="Art. 73: only non-personal data may leave a secure processing environment.">
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-lg border border-line bg-sunken/60 p-4">
              <Cpu size={18} className="mt-0.5 text-spe" />
              <div className="text-sm">
                <div className="font-medium">Artifact: model weights + performance metrics</div>
                <div className="mt-0.5 text-muted">An HDAB reviewer checks that the export contains no personal data before it is released to you.</div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              {exportStatus === null ? (
                <>
                  <Loader2 size={14} className="animate-spin text-accent" /> Submitting request…
                </>
              ) : exportStatus.startsWith("error") ? (
                <span className="text-reject">{exportStatus}</span>
              ) : (
                <>
                  <Check size={15} className="text-stat" /> Request submitted · status <span className="rounded bg-warn-bg px-1.5 py-0.5 font-mono text-xs text-warn">{exportStatus}</span>
                </>
              )}
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setExportOpen(false)}>Done</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
