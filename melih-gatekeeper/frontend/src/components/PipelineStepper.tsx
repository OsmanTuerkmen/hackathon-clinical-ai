import { AnimatePresence, motion } from "framer-motion";
import { Check, DatabaseZap, Minus, X } from "lucide-react";
import { Fragment } from "react";
import { cn, fmtMs } from "@/lib/utils";
import type { Decision, Step } from "@/types";

const DEFAULT_STEPS: Step[] = [
  { key: "received", label: "Received", state: "pending" },
  { key: "purpose", label: "Purpose check", state: "pending" },
  { key: "plan", label: "Query plan", state: "pending" },
  { key: "query", label: "Query", state: "pending" },
  { key: "privacy", label: "Privacy", state: "pending" },
  { key: "decision", label: "Decision", state: "pending" },
];

const OUTCOME_FILL: Record<Decision, string> = {
  REJECT: "bg-reject border-reject text-white",
  APPROVE_STATISTICAL: "bg-stat border-stat text-white",
  APPROVE_SPE: "bg-spe border-spe text-white",
  NEEDS_REVIEW: "bg-warn border-warn text-white",
};

export function PipelineStepper({
  steps, outcome, compact = false, className, showSkipNote = true,
}: { steps?: Step[]; outcome?: Decision | null; compact?: boolean; className?: string; showSkipNote?: boolean }) {
  const s = steps && steps.length ? steps : DEFAULT_STEPS;
  const skippedData = ["plan", "query", "privacy"].every((k) => s.find((x) => x.key === k)?.state === "skipped");
  const node = compact ? "h-6 w-6" : "h-9 w-9";
  const icon = compact ? 12 : 16;

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-start">
        {s.map((step, i) => {
          const isLast = i === s.length - 1;
          const next = s[i + 1];
          const terminal = step.state === "done" || step.state === "failed" || step.state === "skipped";
          const decisionColored = step.key === "decision" && (step.state === "done" || step.state === "failed") && outcome;
          const failed = step.state === "failed" || (step.key === "decision" && step.state === "done" && outcome === "REJECT");
          return (
            <Fragment key={step.key}>
              <div className={cn("flex flex-col items-center shrink-0", compact ? "w-[58px]" : "w-[92px]")}>
                <div className="relative">
                  {step.state === "running" && <span className={cn("absolute inset-0 rounded-full animate-pulse-ring")} />}
                  <motion.div
                    layout={false}
                    initial={false}
                    animate={{ scale: step.state === "running" ? 1.06 : 1 }}
                    transition={{ duration: 0.25 }}
                    className={cn(
                      "relative flex items-center justify-center rounded-full border-2 transition-colors duration-300",
                      node,
                      step.state === "pending" && "border-line bg-surface text-muted",
                      step.state === "running" && "border-accent bg-surface text-accent",
                      step.state === "done" && !decisionColored && "border-ink bg-ink text-ink-fg",
                      step.state === "skipped" && "border-dashed border-muted/40 bg-sunken text-muted/70",
                      failed && "border-reject bg-reject text-white",
                      decisionColored && !failed && OUTCOME_FILL[outcome!],
                    )}
                  >
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.span
                        key={step.state}
                        initial={{ scale: 0.4, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0.4, opacity: 0 }}
                        transition={{ duration: 0.18 }}
                        className="flex"
                      >
                        {step.state === "pending" && <span className={cn("font-mono font-medium", compact ? "text-[10px]" : "text-xs")}>{i + 1}</span>}
                        {step.state === "running" && <span className={cn("rounded-full bg-accent", compact ? "h-1.5 w-1.5" : "h-2 w-2")} />}
                        {step.state === "done" && !failed && <Check size={icon} strokeWidth={3} />}
                        {failed && <X size={icon} strokeWidth={3} />}
                        {step.state === "skipped" && <Minus size={icon} strokeWidth={2.5} />}
                      </motion.span>
                    </AnimatePresence>
                  </motion.div>
                </div>
                <div
                  className={cn(
                    "text-center leading-tight",
                    compact ? "mt-1 text-[11px]" : "mt-2 text-sm",
                    step.state === "pending" && "text-muted",
                    step.state === "running" && "text-accent font-medium",
                    step.state === "skipped" && "text-muted/70 line-through decoration-muted/40",
                    (step.state === "done" || step.state === "failed") && "text-ink font-medium",
                  )}
                >
                  {step.label}
                </div>
                {!compact && (
                  <div className="mt-0.5 h-4 font-mono text-[11px] tabular text-muted">
                    {step.state === "skipped" ? "skipped" : step.state === "running" ? "…" : terminal && step.ms != null ? fmtMs(step.ms) : ""}
                  </div>
                )}
              </div>
              {!isLast && (
                <div className={cn("relative flex-1 min-w-[12px]", compact ? "mt-3" : "mt-[18px]")}>
                  <div className={cn("h-[2px] w-full", next?.state === "skipped" || step.state === "skipped" ? "border-t-2 border-dashed border-line bg-transparent" : "bg-line")} />
                  {next?.state !== "skipped" && step.state !== "skipped" && (
                    <motion.div
                      className="absolute left-0 top-0 h-[2px] w-full origin-left bg-ink"
                      initial={false}
                      animate={{ scaleX: terminal && step.state !== "failed" ? 1 : step.state === "running" ? 0.35 : 0 }}
                      transition={{ duration: 0.35, ease: "easeOut" }}
                    />
                  )}
                </div>
              )}
            </Fragment>
          );
        })}
      </div>
      <AnimatePresence>
        {showSkipNote && skippedData && !compact && outcome && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-3 flex justify-center"
          >
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-sunken px-3 py-1 text-xs font-medium text-muted">
              <DatabaseZap size={13} /> {outcome && outcome !== "REJECT" ? "Held for human review before any data was touched" : "Rejected before any data was touched"} · plan, query and privacy skipped
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
