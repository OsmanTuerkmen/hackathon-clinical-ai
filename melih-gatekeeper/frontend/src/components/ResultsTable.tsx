import { motion } from "framer-motion";
import { GitCompare, Lock } from "lucide-react";
import { usePrefersReducedMotion } from "@/hooks";
import { cn } from "@/lib/utils";
import type { Cell, TableResult } from "@/types";
import { Tip } from "./ui";

const TIP = {
  small_count: "Fewer than 10 patients. Exact number hidden to prevent re-identification.",
  small_n: "Based on fewer than 10 patients, so not reliable or safe to show.",
  secondary: "Hidden because combined with your earlier query it could reveal a small group.",
};

function isCell(v: unknown): v is Cell {
  return !!v && typeof v === "object" && "display" in (v as object);
}

export function countProtected(r: TableResult) {
  let n = 0;
  r.rows.forEach((row) => Object.values(row).forEach((c) => isCell(c) && c.value === null && n++));
  return n;
}

export function SuppressedCell({ cell, delay = 0 }: { cell: Cell; delay?: number }) {
  const reduced = usePrefersReducedMotion();
  const secondary = cell.suppressed === "secondary";
  const isCount = cell.suppressed === "small_count" || cell.display.startsWith("<");
  const tip = secondary ? TIP.secondary : isCount ? TIP.small_count : TIP.small_n;
  return (
    <Tip content={tip}>
      <motion.span
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay, duration: 0.3 }}
        className={cn(
          "inline-flex h-7 min-w-[84px] cursor-help items-center justify-end gap-1.5 rounded-md px-2 text-muted",
          secondary ? "hatch-warn text-warn" : "hatch",
        )}
      >
        <motion.span
          initial={reduced ? false : { rotate: -18, scale: 0.8 }}
          animate={{ rotate: 0, scale: 1 }}
          transition={{ delay: delay + 0.15, type: "spring", stiffness: 500, damping: 14 }}
          className="flex"
        >
          {secondary ? <GitCompare size={12} /> : <Lock size={12} strokeWidth={2.2} />}
        </motion.span>
        {isCount && !secondary ? (
          <span className="font-mono text-sm">{cell.display}</span>
        ) : (
          <span className="small-caps italic text-sm">{secondary ? "suppressed" : cell.display || "suppressed"}</span>
        )}
      </motion.span>
    </Tip>
  );
}

export function ProtectedLegend({ count, className }: { count: number; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted", className)}>
      <span className="inline-flex items-center gap-2">
        <span className="hatch inline-flex h-5 w-9 items-center justify-center rounded border border-line">
          <Lock size={10} />
        </span>
        Protected by small-cell rule · <span className="font-medium text-ink">{count} {count === 1 ? "cell" : "cells"} protected</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="font-mono text-xs">&lt;10</span> fewer than 10 people
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="small-caps italic">suppressed</span> based on fewer than 10
      </span>
    </div>
  );
}

export function ResultsTable({ result, className, animate = true }: { result: TableResult; className?: string; animate?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const stagger = animate && !reduced;
  const protectedCount = countProtected(result);
  return (
    <div className={cn("space-y-3", className)}>
      <ProtectedLegend count={protectedCount} />
      <div className="overflow-x-auto rounded-xl border border-line bg-surface scrollbar-thin">
        <table className="w-full border-collapse text-base">
          <thead className="sticky top-0 z-[1] bg-sunken/80 backdrop-blur">
            <tr className="border-b border-line">
              {result.columns.map((c) => (
                <th
                  key={c.key}
                  className={cn("h-10 px-4 text-xs font-semibold uppercase tracking-[0.06em] text-muted", c.type === "group" ? "text-left" : "text-right")}
                >
                  {c.label}
                  {c.unit && <span className="ml-1 normal-case tracking-normal font-normal text-muted/80">({c.unit})</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <motion.tr
                key={String(row[result.columns[0]?.key] ?? i)}
                initial={stagger ? { opacity: 0, y: 6 } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03, duration: 0.25 }}
                className="h-11 border-b border-line last:border-0 hover:bg-sunken/50"
              >
                {result.columns.map((c) => {
                  const v = row[c.key];
                  if (c.type === "group") {
                    return (
                      <td key={c.key} className="px-4 font-medium">
                        {isCell(v) ? v.display : String(v ?? "")}
                      </td>
                    );
                  }
                  if (!isCell(v)) {
                    return (
                      <td key={c.key} className="px-4 text-right font-mono tabular">
                        {v === undefined || v === null ? "–" : String(v)}
                      </td>
                    );
                  }
                  return (
                    <td key={c.key} className="px-4 text-right">
                      {v.value === null ? (
                        <SuppressedCell cell={v} delay={stagger ? result.rows.length * 0.03 + 0.1 : 0} />
                      ) : (
                        <span className="font-mono tabular text-[14px]">
                          {v.display}
                          {c.type === "pct" && !c.unit && !v.display.endsWith("%") && <span className="ml-0.5 text-muted">%</span>}
                        </span>
                      )}
                    </td>
                  );
                })}
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
