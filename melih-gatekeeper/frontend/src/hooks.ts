import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, getMode, onModeChange, resolveMode, type ApiMode } from "@/api";
import type { Step, StepState } from "@/types";

export const useSamples = () => useQuery({ queryKey: ["samples"], queryFn: api.samples, staleTime: Infinity });
export const useArticles = () => useQuery({ queryKey: ["articles"], queryFn: api.articles, staleTime: Infinity, retry: 1 });

export const useQueue = () =>
  useQuery({
    queryKey: ["queue"],
    queryFn: api.queue,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "processing" || r.status === "received") ? 500 : 4000),
  });

export const useRequest = (id: string | undefined) =>
  useQuery({
    queryKey: ["request", id],
    queryFn: () => api.request(id!),
    enabled: !!id,
    retry: (n, e) => n < 2 && !(e as { status?: number }).status,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "processing" || s === "received" ? 500 : false;
    },
  });

export const useSpe = (wid: string | undefined) =>
  useQuery({ queryKey: ["spe", wid], queryFn: () => api.spe(wid!), enabled: !!wid, retry: 1 });

export function useApiMode(): ApiMode | null {
  const [m, setM] = useState<ApiMode | null>(getMode());
  useEffect(() => {
    resolveMode().then(setM);
    const off = onModeChange(setM);
    return () => {
      off();
    };
  }, []);
  return m;
}

// ---------------------------------------------------------------------------
// Persona (Applicant / Staff), purely presentational
// ---------------------------------------------------------------------------
export type Persona = "applicant" | "staff";
export const PersonaContext = createContext<{ persona: Persona; setPersona: (p: Persona) => void }>({
  persona: "staff",
  setPersona: () => {},
});
export const usePersona = () => useContext(PersonaContext);

export function usePrefersReducedMotion() {
  const [r, setR] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const fn = () => setR(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return r;
}

// ---------------------------------------------------------------------------
// Pipeline display: replays step progress with a minimum visual hold per step,
// so fast backend steps don't flash by invisibly (spec §3.2).
// ---------------------------------------------------------------------------
const TERMINAL: StepState[] = ["done", "failed", "skipped"];
const HOLD_MS = 340;
const SKIP_HOLD_MS = 160;

export function useDisplaySteps(steps: Step[] | undefined, animate = true) {
  const reduced = usePrefersReducedMotion();
  const instant = reduced || !animate;
  const target = steps ?? [];
  // number of leading terminal steps in the real data
  const realTerminal = useMemo(() => {
    let n = 0;
    for (const s of target) {
      if (TERMINAL.includes(s.state)) n++;
      else break;
    }
    return n;
  }, [target]);
  const [shown, setShown] = useState(instant ? realTerminal : 0);
  const targetRef = useRef(target);
  targetRef.current = target;

  useEffect(() => {
    if (instant) {
      setShown(realTerminal);
      return;
    }
    if (shown > realTerminal) {
      setShown(realTerminal); // request was re-run
      return;
    }
    if (shown >= realTerminal) return;
    const next = targetRef.current[shown];
    const hold = next?.state === "skipped" ? SKIP_HOLD_MS : HOLD_MS;
    const t = setTimeout(() => setShown((s) => Math.min(s + 1, realTerminal)), hold);
    return () => clearTimeout(t);
  }, [shown, realTerminal, instant]);

  const display: Step[] = target.map((s, i) => {
    if (i < shown) return s;
    if (i === shown) {
      // the step we are "on": show running if real is running/terminal
      if (s.state === "pending") return s;
      return { ...s, state: "running", ms: null };
    }
    return { ...s, state: "pending", ms: null };
  });
  const finished = target.length > 0 && shown >= target.length;
  const activeIndex = finished ? -1 : shown;
  return { steps: display, finished, activeIndex };
}

/** Animated count-up for scoreboard numbers. */
export function useCountUp(value: number, duration = 600) {
  const reduced = usePrefersReducedMotion();
  const [v, setV] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduced) {
      setV(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      const e = 1 - Math.pow(1 - k, 3);
      setV(a + (value - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduced]);
  return v;
}
