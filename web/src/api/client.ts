import type {
  AuditEntry,
  CaseDetail,
  CaseSummary,
  DecisionLetter,
  Identity,
  Language,
  PipelineResult,
  PrecheckResult,
  RegisterEntry,
  SPEManifest,
} from "./types";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json; charset=utf-8" } : {}),
      ...init?.headers,
    },
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.en ?? detail?.de ?? response.statusText;
    throw new Error(message);
  }
  return body as T;
}

function post<T>(url: string, body: unknown): Promise<T> {
  return json<T>(url, { method: "POST", body: JSON.stringify(body) });
}

export const api = {
  health: () => json<{ ok: boolean }>("/api/health"),
  info: () => json<{
    patients: number;
    opted_out: number;
    load_seconds: number;
    ai: { enabled: boolean; reason?: string; model?: string };
    mode: string;
    version: string;
    counts: Record<string, number>;
    identities: Array<Pick<Identity, "name" | "organisation" | "country">>;
  }>("/api/info"),
  identities: () => json<Identity[]>("/api/identities"),
  cases: (filters: { status?: string; decision?: string; q?: string; group?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    return json<CaseSummary[]>(`/api/cases?${query.toString()}`);
  },
  case: (id: string) => json<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`),
  review: (id: string, body: {
    action: "release" | "hold" | "reject";
    reason: string;
    reviewer: string;
  }) => post<CaseSummary>(`/api/cases/${encodeURIComponent(id)}/review`, body),
  caseAudit: (id: string) => json<AuditEntry[]>(`/api/cases/${encodeURIComponent(id)}/audit`),
  letter: (id: string, language: Language) => json<DecisionLetter>(
    `/api/cases/${encodeURIComponent(id)}/letter?lang=${language}`,
  ),
  applicantCases: (login: string) => json<CaseSummary[]>(
    `/api/applicant/cases?login=${encodeURIComponent(login)}`,
  ),
  applicantCase: (id: string, login: string) => json<{
    summary: CaseSummary;
    decision: CaseDetail["result"]["decision"];
    delivery: CaseDetail["result"]["delivery"];
    visible: boolean;
    notes: CaseDetail["result"]["notes"];
    released?: CaseDetail["result"]["released"];
    funnel?: CaseDetail["result"]["funnel"];
    spe?: {
      permit_id: string;
      expires: string;
      cohort_size: number;
      tables_copied: SPEManifest["tables_copied"];
      tables_not_copied: SPEManifest["tables_not_copied"];
    } | null;
  }>(`/api/applicant/cases/${encodeURIComponent(id)}?login=${encodeURIComponent(login)}`),
  precheck: (request: Record<string, unknown>, login?: string) => post<PrecheckResult>(
    "/api/precheck",
    { request, ...(login ? { login } : {}) },
  ),
  register: () => json<{ legal_basis: string; entries: RegisterEntry[] }>("/api/register"),
};
