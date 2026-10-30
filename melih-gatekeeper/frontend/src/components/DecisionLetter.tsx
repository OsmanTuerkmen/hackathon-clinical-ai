import { AnimatePresence, motion } from "framer-motion";
import { ArrowDownRight, ArrowRight, ChevronDown, KeyRound, LockKeyhole, Scale, UserCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useArticles, useSpe } from "@/hooks";
import { cn, fmtDate, speIdOf } from "@/lib/utils";
import type { RequestDetail } from "@/types";
import { ArticleChip, DecisionBadge, OutcomeBadges } from "./decision";
import { FiveSafesRecord } from "./panels";
import { ResultsTable } from "./ResultsTable";
import { Button } from "./ui";

export function Seal({ size = 56 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden className="text-gold">
      <circle cx="32" cy="32" r="30" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="32" cy="32" r="25" fill="none" stroke="currentColor" strokeWidth="0.75" strokeDasharray="2 2.5" />
      {Array.from({ length: 12 }).map((_, i) => {
        const a = (i / 12) * Math.PI * 2;
        return <circle key={i} cx={32 + Math.cos(a) * 19} cy={32 + Math.sin(a) * 19} r="1.4" fill="currentColor" />;
      })}
      <path d="M32 21l8 3v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10v-6l8-3z" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M28.5 30.5l2.5 2.5 4.5-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArticleQuote({ id }: { id: string }) {
  const { data } = useArticles();
  const [open, setOpen] = useState(false);
  const art = data?.[id];
  return (
    <div className="border-b border-line last:border-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 py-3 text-left">
        <span className="font-mono text-sm font-medium text-gold">Art. {id}</span>
        <span className="flex-1 font-sans text-base font-medium text-ink">{art?.title ?? "Regulation (EU) 2025/327"}</span>
        <ChevronDown size={16} className={cn("text-muted transition-transform", open && "rotate-180")} />
      </button>
      {art && <p className="-mt-1 pb-3 pl-[52px] font-sans text-sm text-muted">{art.summary}</p>}
      <AnimatePresence initial={false}>
        {open && art && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <blockquote className="mb-4 ml-[52px] border-l-[3px] border-gold pl-4 text-[16px] leading-[1.65] text-ink/85">{art.quote}</blockquote>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function PermitCard({ detail }: { detail: RequestDetail }) {
  const size = detail.result?.kind === "cohort" ? detail.result.cohort_size : null;
  const wid = speIdOf(detail.spe, detail.id);
  const { data: spe } = useSpe(wid);
  const types = spe ? spe.tables.filter((t) => t.copied && t.name !== "patients").map((t) => (t.note ? `${t.name} (${t.note})` : t.name)).join(" · ") : "as requested";
  return (
    <div className="relative overflow-hidden rounded-xl border border-spe/30 bg-spe-bg/50 p-5 font-sans">
      <div className="absolute -right-6 -top-6 opacity-[0.15]">
        <Seal size={140} />
      </div>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-spe">
        <KeyRound size={14} /> Your data permit · {spe?.permit.number ?? `HDAB-2026-${detail.id}`}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-x-10 gap-y-3">
        <div>
          <div className="text-sm text-muted">Cohort</div>
          <div className="font-mono text-[40px] font-medium leading-none tabular text-ink">{(size ?? spe?.cohort_size)?.toLocaleString("en-US") ?? "–"}</div>
          <div className="mt-1 text-sm text-muted">patients, pseudonymised</div>
        </div>
        <div className="text-sm">
          <div className="text-muted">Record types</div>
          <div className="mt-1 max-w-sm font-medium">{types}</div>
          <div className="mt-2 text-muted">Valid until</div>
          <div className="font-medium">{spe ? fmtDate(spe.permit.valid_until) : "12 months"}</div>
        </div>
      </div>
      <ul className="mt-4 space-y-1 text-sm text-ink/80">
        <li className="flex items-center gap-2"><LockKeyhole size={13} className="text-spe" /> Data stays inside the secure processing environment. No download.</li>
        <li className="flex items-center gap-2"><LockKeyhole size={13} className="text-spe" /> Only aggregate outputs and model weights may leave, after HDAB output review (Art. 73).</li>
      </ul>
      <Link to={`/spe/${wid}`}>
        <Button className="mt-5" variant="primary">
          <LockKeyhole size={15} /> Open secure workspace <ArrowRight size={15} />
        </Button>
      </Link>
    </div>
  );
}

export function DecisionLetter({ detail, revealed = true }: { detail: RequestDetail; revealed?: boolean }) {
  const d = detail.decision;
  if (!d) return null;
  const letter = d.letter;
  const r = detail.request;
  const needsReview = !!d.needs_review;
  const isReject = d.outcome === "REJECT";
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={revealed ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
      transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
      className="paper relative overflow-hidden rounded-xl border border-line shadow-sm"
    >
      <div className="h-1.5 w-full bg-ink" />
      <div className="px-8 py-8 sm:px-14 sm:py-12">
        {/* Letterhead */}
        <header className="flex items-start justify-between gap-6 border-b border-line pb-6">
          <div className="flex items-center gap-4">
            <Seal />
            <div>
              <div className="font-sans text-xs font-semibold uppercase tracking-[0.14em] text-muted">Health Data Access Body · Austria (demo)</div>
              <div className="mt-1 font-serif text-lg font-semibold">Decision on your {/access application/i.test(r.requested_as) ? "data access application" : "health data request"}</div>
            </div>
          </div>
          <div className="shrink-0 text-right font-sans text-sm text-muted">
            <div className="font-mono text-ink">HDAB-2026-{detail.id}</div>
            <div>{fmtDate(detail.submitted ?? r.submitted ?? new Date().toISOString())}</div>
          </div>
        </header>

        <div className="mt-8 font-serif text-[17px] leading-[1.65] text-ink">
          <p>{letter?.greeting ?? `Dear ${r.applicant.name},`}</p>
          <p className="mt-4 text-[22px] font-semibold leading-snug">{letter?.headline}</p>
          <div className="mt-4 font-sans">
            <OutcomeBadges outcome={d.outcome} needsReview={needsReview} downgradedFrom={d.downgraded_from} reveal size="lg" />
          </div>

          {needsReview && (
            <div className="mt-6 flex gap-3 rounded-lg border border-warn/30 bg-warn-bg px-4 py-3 font-sans text-sm text-ink/85">
              <UserCheck size={16} className="mt-0.5 shrink-0 text-warn" />
              <div>
                <div className="font-semibold text-warn">A person will check this decision</div>
                Our automated review recommends <span className="font-medium">{d.outcome.replace("_", " ").toLowerCase()}</span>, but some checks need a human. You will hear from us; nothing is released until then.
              </div>
            </div>
          )}

          {d.downgraded_from && !needsReview && (
            <div className="mt-6 flex gap-3 rounded-lg border border-warn/30 bg-warn-bg px-4 py-3 font-sans text-sm text-ink/85">
              <ArrowDownRight size={16} className="mt-0.5 shrink-0 text-warn" />
              <div>
                <div className="font-semibold text-warn">You asked for patient-level records. We approved statistics instead.</div>
                Your question can be fully answered with statistics, so under the data-minimisation principle (Art. 66) we approved statistics instead. Here they are. If you need records, explain why aggregates are not enough.
              </div>
            </div>
          )}

          <h4 className="mt-8 font-sans text-xs font-semibold uppercase tracking-[0.1em] text-muted">Why</h4>
          <div className="mt-2 space-y-3 whitespace-pre-line">{letter?.why ?? d.reason_staff}</div>

          {/* Results / permit */}
          {!needsReview && detail.result?.kind === "table" && (
            <div className="mt-8 font-sans">
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.1em] text-muted">Your statistics</h4>
              <ResultsTable result={detail.result} />
              <p className="mt-2 text-sm text-muted">Small numbers are hidden to protect privacy. Numbers are computed by code from the data; no AI touched them.</p>
            </div>
          )}
          {!needsReview && d.outcome === "APPROVE_SPE" && (
            <div className="mt-8">
              <PermitCard detail={detail} />
            </div>
          )}

          <h4 className="mt-8 font-sans text-xs font-semibold uppercase tracking-[0.1em] text-muted">The law</h4>
          <div className="mt-1 font-serif">
            {d.articles.map((a) => (
              <ArticleQuote key={a} id={a} />
            ))}
          </div>

          {letter?.alternatives && letter.alternatives.length > 0 && (
            <>
              <h4 className="mt-8 font-sans text-xs font-semibold uppercase tracking-[0.1em] text-muted">What you can do instead</h4>
              <ul className="mt-2 space-y-2">
                {letter.alternatives.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-gold" />
                    {a}
                  </li>
                ))}
              </ul>
            </>
          )}
          {letter?.next_steps && letter.next_steps.length > 0 && (
            <>
              <h4 className="mt-8 font-sans text-xs font-semibold uppercase tracking-[0.1em] text-muted">Next steps</h4>
              <ol className="mt-2 space-y-2">
                {letter.next_steps.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="font-mono text-sm leading-[28px] text-gold">{i + 1}.</span>
                    {a}
                  </li>
                ))}
              </ol>
            </>
          )}

          {d.five_safes && (
            <>
              <h4 className="mt-8 font-sans text-xs font-semibold uppercase tracking-[0.1em] text-muted">Decision record · Five Safes</h4>
              <div className="mt-3">
                <FiveSafesRecord safes={d.five_safes} variant="letter" />
              </div>
            </>
          )}

          <div className="mt-10 flex gap-3 rounded-lg bg-sunken/70 px-4 py-3 font-sans text-sm text-muted">
            <Scale size={16} className="mt-0.5 shrink-0" />
            <div>
              <span className="font-medium text-ink">Your right to appeal.</span> If you disagree with this decision you can ask the Health Data Access Body to review it, and you may lodge a complaint under national law. Contact: appeals@hdab.example (demo).
            </div>
          </div>

          <footer className="mt-8 flex flex-wrap items-end justify-between gap-4 border-t border-line pt-5 font-sans text-xs text-muted">
            <div>
              Reference <span className="font-mono text-ink">HDAB-2026-{detail.id}</span> · decided automatically · reviewed by:{" "}
              {detail.status === "released" ? <span className="text-stat font-medium">staff (released)</span> : "pending"}
            </div>
            <div className="flex items-center gap-1.5">
              {d.articles.map((a) => (
                <ArticleChip key={a} id={a} size="sm" />
              ))}
              {isReject && <DecisionBadge decision="REJECT" size="sm" compact />}
            </div>
          </footer>
        </div>
      </div>
    </motion.article>
  );
}
