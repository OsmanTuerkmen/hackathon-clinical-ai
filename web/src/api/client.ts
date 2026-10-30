import type {
  AuditEntry,
  AIStatus,
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
    ai: AIStatus;
    mode: string;
    version: string;
    counts: Record<string, number>;
    identities: Array<Pick<Identity, "name" | "organisation" | "country">>;
  }>("/api/info"),
  identities: () => json<Identity[]>("/api/identities"),
  templates: () => json<Array<{
    id: string;
    title_de: string;
    title_en: string;
    request: Record<string, unknown>;
  }>>("/api/templates"),
  cases: (filters: { status?: string; decision?: string; q?: string; group?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    return json<CaseSummary[]>(`/api/cases?${query.toString()}`);
  },
  case: (id: string) => json<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`),
  aiOpinion: (id: string) => json<CaseDetail>(
    `/api/cases/${encodeURIComponent(id)}/ai-opinion`,
    { method: "POST" },
  ),
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
  submit: (request: Record<string, unknown>, login?: string) => post<{
    id: string;
    summary: CaseSummary;
  }>("/api/submit", { request, login }),
  aiDraft: (body: { text: string; lang: Language; purpose?: string; login?: string }) =>
    post<{
      draft: Record<string, unknown>;
      precheck: PrecheckResult;
      model: string;
      provider: "claude" | "gemini";
      cached: boolean;
    }>("/api/ai/draft", body),
  aiExplain: (id: string, login: string) => json<{
    explanation_de: string;
    explanation_en: string;
    model: string;
    provider: "claude" | "gemini";
    cached: boolean;
  }>(`/api/ai/explain/${encodeURIComponent(id)}?login=${encodeURIComponent(login)}`),
  spe: (permit: string, login: string) => json<{
    manifest: Record<string, unknown>;
    tables: Record<string, { columns: string[]; rows: unknown[][] }>;
  }>(`/api/spe/${encodeURIComponent(permit)}?login=${encodeURIComponent(login)}`),
  speQuery: (permit: string, login: string, sql: string) =>
    post<Record<string, unknown>>(`/api/spe/${encodeURIComponent(permit)}/query`, { login, sql }),
  speExports: (permit: string, login: string) =>
    json<Array<Record<string, unknown>>>(
      `/api/spe/${encodeURIComponent(permit)}/exports?login=${encodeURIComponent(login)}`,
    ),
  createExport: (permit: string, body: { login: string; sql: string; title: string; note: string }) =>
    post<Record<string, unknown>>(`/api/spe/${encodeURIComponent(permit)}/exports`, body),
  exports: (status?: string) => json<Array<Record<string, unknown>>>(
    `/api/exports${status ? `?status=${encodeURIComponent(status)}` : ""}`,
  ),
  export: (id: string) => json<Record<string, unknown>>(`/api/exports/${encodeURIComponent(id)}`),
  reviewExport: (id: string, body: { action: "approve" | "reject"; reason: string; reviewer: string }) =>
    post<Record<string, unknown>>(`/api/exports/${encodeURIComponent(id)}/review`, body),
  exportCsv: async (id: string, login: string) => {
    const response = await fetch(
      `/api/exports/${encodeURIComponent(id)}/download?login=${encodeURIComponent(login)}`,
    );
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body?.detail?.en ?? body?.detail ?? response.statusText);
    }
    return response.blob();
  },
  speCsv: async (permit: string, login: string, language: Language) => {
    const response = await fetch(
      `/api/spe/${encodeURIComponent(permit)}/download?login=${encodeURIComponent(login)}`,
    );
    if (!response.ok) {
      const body = await response.json();
      const detail = body?.detail;
      const message = detail && typeof detail === "object"
        ? detail[language] ?? detail.en ?? detail.de
        : detail;
      throw new Error(message ?? response.statusText);
    }
    return response.blob();
  },
  auditEntries: (limit = 300) => json<AuditEntry[]>(`/api/audit?limit=${limit}`),
  verifyAudit: () => json<Record<string, unknown>>("/api/audit/verify"),
  evaluation: (suite: "official" | "all" = "all") =>
    json<Record<string, unknown>>(`/api/eval?suite=${suite}`),
  register: () => json<{ legal_basis: string; entries: RegisterEntry[] }>("/api/register"),
};
