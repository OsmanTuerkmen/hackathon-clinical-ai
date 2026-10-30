import * as DialogPrimitive from "@radix-ui/react-dialog";
import { motion } from "framer-motion";
import { ArrowDownRight, BarChart3, ExternalLink, Loader2, LockKeyhole, ShieldX, UserCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useApiMode, useArticles } from "@/hooks";
import { cn } from "@/lib/utils";
import type { Decision } from "@/types";
import { SheetContent, Tip } from "./ui";

export const DECISION_META: Record<Decision, { label: string; short: string; icon: typeof ShieldX; cls: string; ring: string }> = {
  REJECT: { label: "Rejected · Art. 54", short: "Rejected", icon: ShieldX, cls: "bg-reject-bg text-reject border-reject/30", ring: "rgb(var(--reject) / 0.35)" },
  APPROVE_STATISTICAL: { label: "Approved · Statistics", short: "Approved · Stats", icon: BarChart3, cls: "bg-stat-bg text-stat border-stat/30", ring: "rgb(var(--stat) / 0.35)" },
  APPROVE_SPE: { label: "Approved · Secure environment", short: "Approved · SPE", icon: LockKeyhole, cls: "bg-spe-bg text-spe border-spe/30", ring: "rgb(var(--spe) / 0.35)" },
  NEEDS_REVIEW: { label: "Needs human review", short: "Needs review", icon: UserCheck, cls: "bg-warn-bg text-warn border-warn/30", ring: "rgb(var(--warn) / 0.35)" },
};

export function DecisionBadge({
  decision, size = "md", reveal = false, compact = false, className,
}: { decision: Decision; size?: "sm" | "md" | "lg"; reveal?: boolean; compact?: boolean; className?: string }) {
  const m = DECISION_META[decision] ?? DECISION_META.NEEDS_REVIEW;
  const Icon = m.icon;
  const sz = size === "lg" ? "h-9 px-3.5 text-md gap-2" : size === "sm" ? "h-6 px-2 text-xs gap-1" : "h-7 px-2.5 text-sm gap-1.5";
  const inner = (
    <span className={cn("inline-flex items-center rounded-md border font-semibold whitespace-nowrap", sz, m.cls, className)}>
      <Icon size={size === "lg" ? 17 : size === "sm" ? 12 : 14} strokeWidth={2.2} />
      {compact ? m.short : m.label}
    </span>
  );
  if (!reveal) return inner;
  return (
    <motion.span
      className="inline-flex rounded-md"
      initial={{ scale: 0.9, opacity: 0, boxShadow: `0 0 0 0 ${m.ring}` }}
      animate={{ scale: 1, opacity: 1, boxShadow: [`0 0 0 0 ${m.ring}`, `0 0 0 8px ${m.ring}`, `0 0 0 14px rgba(0,0,0,0)`] }}
      transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
    >
      {inner}
    </motion.span>
  );
}

/** Combined badge: recommended outcome + needs-review flag + downgrade chip. */
export function OutcomeBadges({
  outcome, needsReview, downgradedFrom, reveal, size = "md", compact,
}: { outcome: Decision; needsReview?: boolean; downgradedFrom?: string | null; reveal?: boolean; size?: "sm" | "md" | "lg"; compact?: boolean }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {needsReview && outcome !== "NEEDS_REVIEW" ? (
        <>
          <DecisionBadge decision="NEEDS_REVIEW" size={size} reveal={reveal} compact={compact} />
          <span className={cn("inline-flex items-center gap-1 text-muted", size === "sm" ? "text-xs" : "text-sm")}>
            Recommended: <DecisionBadge decision={outcome} size="sm" compact />
          </span>
        </>
      ) : (
        <DecisionBadge decision={outcome} size={size} reveal={reveal} compact={compact} />
      )}
      {downgradedFrom && <DowngradeChip from={downgradedFrom} size={size} />}
    </span>
  );
}

export function DowngradeChip({ from, size = "md" }: { from: string; size?: "sm" | "md" | "lg" }) {
  return (
    <Tip content={`Applicant asked for ${from}. Statistics answer the question, so data minimisation (Art. 66) applies.`}>
      <span className={cn("inline-flex items-center gap-1 rounded-md border border-warn/30 bg-warn-bg font-medium text-warn", size === "sm" ? "h-6 px-1.5 text-xs" : "h-7 px-2 text-sm")}>
        <ArrowDownRight size={13} strokeWidth={2.4} /> from records
      </span>
    </Tip>
  );
}

export function PendingBadge({ label = "Processing" }: { label?: string }) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-accent/25 bg-accent/5 px-2.5 text-sm font-medium text-accent">
      <Loader2 size={13} className="animate-spin" /> {label}
    </span>
  );
}

// ---------------------------------------------------------------- Articles
export function ArticleChip({ id, size = "md" }: { id: string; size?: "sm" | "md" }) {
  const { data } = useArticles();
  const art = data?.[id];
  return (
    <DialogPrimitive.Root>
      <Tip content={art?.title ?? `Article ${id}, Reg. (EU) 2025/327`}>
        <DialogPrimitive.Trigger asChild>
          <button
            className={cn(
              "inline-flex items-center rounded-md border border-gold/60 bg-gold/[0.06] font-mono font-medium text-ink transition-colors hover:bg-gold/15 hover:border-gold",
              size === "sm" ? "h-6 px-1.5 text-[11px]" : "h-7 px-2 text-xs",
            )}
          >
            Art. {id}
          </button>
        </DialogPrimitive.Trigger>
      </Tip>
      <ArticleSheet id={id} />
    </DialogPrimitive.Root>
  );
}

function ArticleSheet({ id }: { id: string }) {
  const { data, isLoading } = useArticles();
  const mode = useApiMode();
  const art = data?.[id];
  return (
    <SheetContent title={<span><span className="font-mono text-gold">Art. {id}</span> · {art?.title ?? "Regulation (EU) 2025/327"}</span>} description="European Health Data Space Regulation, Chapter IV">
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {art ? (
        <div className="space-y-6">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">In plain language</div>
            <p className="mt-2 text-md leading-relaxed">{art.summary}</p>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">The law</div>
            <blockquote className="mt-2 border-l-[3px] border-gold pl-4 font-serif text-[17px] leading-[1.65] text-ink/90">{art.quote}</blockquote>
            {mode === "mock" && <p className="mt-2 text-xs text-muted">Mock mode: excerpt for demo only. The backend serves the verified EUR-Lex text.</p>}
          </div>
          {art.url && (
            <a href={art.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline">
              Read on EUR-Lex <ExternalLink size={13} />
            </a>
          )}
        </div>
      ) : (
        !isLoading && <p className="text-sm text-muted">No text available for this article.</p>
      )}
    </SheetContent>
  );
}

export function ArticleChips({ ids, size }: { ids: string[]; size?: "sm" | "md" }) {
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {ids.map((a) => (
        <ArticleChip key={a} id={a} size={size} />
      ))}
    </span>
  );
}

export function FieldRow({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-[150px_1fr] gap-4 py-2.5 border-b border-line last:border-0", className)}>
      <div className="text-sm text-muted">{label}</div>
      <div className="min-w-0 text-base">{children}</div>
    </div>
  );
}
