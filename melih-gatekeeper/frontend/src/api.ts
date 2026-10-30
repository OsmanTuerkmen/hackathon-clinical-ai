// Typed API client for the §3 contract, with automatic mock fallback.
//
// Mode resolution (once per page load):
//   1. VITE_MOCK=1, ?mock=1 or localStorage "ehds.mode"="mock"  -> mock
//   2. ?live=1 or localStorage "ehds.mode"="live"                -> live (no probe)
//   3. otherwise probe GET {base}/health; JSON answer (<500) -> live, else mock
import { MockHttpError, mockFetch } from "@/mock/engine";
import type {
  Articles, MetricsRun, OverrideBody, QueueItem, RawRequest, RequestDetail, Sample, SpeWorkspace,
} from "@/types";

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "/api";

export type ApiMode = "live" | "mock";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, message?: string) {
    super(message ?? (typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : `HTTP ${status}`));
  }
}

const listeners = new Set<(m: ApiMode) => void>();
let modePromise: Promise<ApiMode> | null = null;
let currentMode: ApiMode | null = null;

function forced(): ApiMode | null {
  if (import.meta.env.VITE_MOCK === "1" || import.meta.env.VITE_MOCK === "true") return "mock";
  try {
    const q = new URLSearchParams(window.location.search);
    if (q.get("mock") === "1") return "mock";
    if (q.get("live") === "1") return "live";
    const s = localStorage.getItem("ehds.mode");
    if (s === "mock" || s === "live") return s;
  } catch {
    /* storage blocked */
  }
  return null;
}

async function probe(): Promise<ApiMode> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 2000);
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: ctl.signal, headers: { Accept: "application/json" } });
    const json = (r.headers.get("content-type") ?? "").includes("json");
    return json && r.status < 500 ? "live" : "mock";
  } catch {
    return "mock";
  } finally {
    clearTimeout(t);
  }
}

export function resolveMode(): Promise<ApiMode> {
  if (!modePromise) {
    const f = forced();
    modePromise = (f ? Promise.resolve(f) : probe()).then((m) => {
      currentMode = m;
      listeners.forEach((l) => l(m));
      if (m === "mock") console.info("[ehds] backend unreachable or mock forced: using in-browser mock data");
      return m;
    });
  }
  return modePromise;
}

export function getMode() {
  return currentMode;
}
export function onModeChange(fn: (m: ApiMode) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
/** Persist a mode preference and reload. `null` = auto-detect. */
export function setModePreference(m: ApiMode | null) {
  try {
    if (m) localStorage.setItem("ehds.mode", m);
    else localStorage.removeItem("ehds.mode");
  } catch {
    /* ignore */
  }
  const url = new URL(window.location.href);
  url.searchParams.delete("mock");
  url.searchParams.delete("live");
  window.location.replace(url.toString());
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const mode = await resolveMode();
  if (mode === "mock") {
    try {
      return await mockFetch<T>(method, path, body);
    } catch (e) {
      if (e instanceof MockHttpError) throw new ApiError(e.status, e.body);
      throw e;
    }
  }
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!r.ok) {
    // FastAPI 422 sends detail as a list of {loc,msg}; flatten it for display.
    if (data && typeof data === "object" && Array.isArray((data as { detail?: unknown }).detail)) {
      const msgs = ((data as { detail: { msg?: string; loc?: unknown[] }[] }).detail).map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`);
      throw new ApiError(r.status, data, msgs.join("; "));
    }
    throw new ApiError(r.status, data);
  }
  return data as T;
}

export const api = {
  samples: () => call<Sample[]>("GET", "/samples"),
  articles: () => call<Articles>("GET", "/articles"),
  queue: () => call<QueueItem[]>("GET", "/requests"),
  request: (id: string) => call<RequestDetail>("GET", `/requests/${encodeURIComponent(id)}`),
  submit: (raw: RawRequest | Record<string, unknown>) => call<{ id: string; status: string }>("POST", "/requests", raw),
  batch: (ids: string[]) => call<{ ids: string[] }>("POST", "/requests/batch", { ids }),
  override: (id: string, body: OverrideBody) => call<RequestDetail>("POST", `/requests/${encodeURIComponent(id)}/override`, body),
  release: (id: string, actor: string) => call<RequestDetail>("POST", `/requests/${encodeURIComponent(id)}/release`, { actor }),
  spe: (wid: string) => call<SpeWorkspace>("GET", `/spe/${encodeURIComponent(wid)}`),
  speDownload: (wid: string) => call<unknown>("GET", `/spe/${encodeURIComponent(wid)}/download`),
  speExport: (wid: string, artifact = "model_weights") => call<{ status: string }>("POST", `/spe/${encodeURIComponent(wid)}/export-request`, { artifact }),
  metricsRun: (runs = 3, include_custom = true) => call<{ run_id: string }>("POST", "/metrics/run", { runs, include_custom }),
  metrics: (runId: string) => call<MetricsRun>("GET", `/metrics/runs/${encodeURIComponent(runId)}`),
};

export const TRACK_IDS = ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10"];
