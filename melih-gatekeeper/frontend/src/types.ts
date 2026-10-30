// Types mirroring docs/UI_AND_PITCH_PLAN.md §3 plus the agreed additions
// (review_reasons, signals, five_safes, inference, needs_review).
// Everything beyond the core contract is optional so the UI tolerates absence.

export type Decision = "REJECT" | "APPROVE_STATISTICAL" | "APPROVE_SPE" | "NEEDS_REVIEW";
export type Status = "received" | "processing" | "decided" | "released" | "error";
export type StepKey = "received" | "purpose" | "plan" | "query" | "privacy" | "decision";
export type StepState = "pending" | "running" | "done" | "failed" | "skipped";

export interface Applicant {
  name: string;
  organisation: string;
  country: string;
}

export interface RawRequest {
  id?: string;
  submitted?: string;
  applicant: Applicant;
  requested_as: string;
  requested_format?: string;
  purpose: string;
  question: string;
  definitions: string[];
  [k: string]: unknown;
}

export interface Sample {
  id: string;
  group?: string;
  organisation: string;
  requested_as: string;
  json: RawRequest;
}

export interface Flags {
  downgraded?: boolean;
  suppressed_cells?: number;
  differencing_risk?: boolean;
  overridden?: boolean;
  low_confidence?: boolean;
  needs_review?: boolean;
}

export interface QueueItem {
  id: string;
  submitted: string;
  status: Status;
  applicant: Applicant;
  requested_as: string;
  purpose_short?: string | null;
  decision: Decision | null;
  articles: string[];
  flags: Flags;
  current_step?: StepKey | null;
  elapsed_ms?: number | null;
  needs_review?: boolean;
}

export interface Step {
  key: StepKey;
  label: string;
  state: StepState;
  ms?: number | null;
  detail?: string | null;
}

export interface RuleTraceItem {
  step: number;
  question: string;
  answer: string;
  article?: string | null;
}

export interface Letter {
  greeting: string;
  headline: string;
  why: string;
  alternatives?: string[];
  next_steps?: string[];
}

export interface ReviewReason {
  code: string;
  message: string;
}

export interface SignalVerdict {
  prohibited: boolean;
  category: string;
  quote?: string | null;
  quote_verified?: boolean;
  available?: boolean;
  allowed_purpose?: string;
  note?: string;
  [k: string]: unknown;
}

export interface Signals {
  rules?: SignalVerdict;
  classifier?: SignalVerdict;
  redteam?: SignalVerdict;
  justification?: { justified: boolean; quote?: string | null; quote_verified?: boolean; source: string; [k: string]: unknown };
  injection?: { flagged: boolean; hits: string[] };
}

export interface FiveSafes {
  project: string;
  people: string;
  setting: string;
  data: string;
  outputs: string;
}

export interface DecisionDetail {
  outcome: Decision;
  purpose_category?: string;
  purpose_source?: string;
  articles: string[];
  downgraded_from?: string | null;
  purpose?: {
    category: string;
    allowed: boolean;
    confidence?: number | null;
    source?: string;
    rule_hits?: string[];
  } | null;
  rule_trace?: RuleTraceItem[];
  reason_staff?: string;
  letter?: Letter | null;
  needs_review?: boolean;
  review_reasons?: ReviewReason[];
  signals?: Signals | null;
  five_safes?: FiveSafes | null;
}

export interface ReadablePlanItem {
  label: string;
  text: string;
  source_definition?: number | null;
}

export interface CatalogMatch {
  system: string;
  code: string;
  label: string;
  ok: boolean;
}

export interface Plan {
  readable: ReadablePlanItem[];
  catalog_matches?: CatalogMatch[];
  raw?: unknown;
  sql?: string | null;
}

export interface Cell {
  value: number | null;
  display: string;
  suppressed?: "small_count" | "small_n" | "secondary" | string | null;
}

export interface Column {
  key: string;
  label: string;
  type: "group" | "count" | "mean" | "pct" | string;
  unit?: string;
}

export interface TableResult {
  kind: "table";
  group_by: string[];
  columns: Column[];
  rows: Record<string, Cell | string>[];
  answer?: unknown;
}

export interface CohortResult {
  kind: "cohort";
  cohort_size: number;
}

export type Result = TableResult | CohortResult;

export interface PrivacyCheck {
  key: string;
  label: string;
  passed: boolean;
  detail?: string | null;
  warning?: boolean;
}

export interface Privacy {
  opted_out_excluded: number;
  checks: PrivacyCheck[];
}

export interface AuditEntry {
  id?: string;
  hash?: string;
  prev?: string;
  ts: string;
  event: string;
  actor: string;
  detail?: string | null;
}

export interface Inference {
  profile: "off" | "llm";
  model: string | null;
  endpoint_host: string | null;
  patient_data_sent: false | boolean;
}

export interface SpeTable {
  name: string;
  rows: number;
  copied: boolean;
  note?: string;
}

export interface SpeWorkspace {
  id: string;
  request_id: string;
  schema: string;
  permit: { number: string; holder: string; valid_until: string; articles: string[] };
  cohort_size: number;
  cohort_definition: string;
  tables: SpeTable[];
  preview?: { table: string; columns: string[]; rows: (string | number)[][] } | null;
  blocked_attempts: number;
}

export interface SpeRef {
  workspace_id?: string;
  id?: string;
  [k: string]: unknown;
}

export interface RequestDetail {
  id: string;
  request: RawRequest;
  status: Status;
  elapsed_ms?: number | null;
  steps: Step[];
  decision: DecisionDetail | null;
  plan: Plan | null;
  result: Result | null;
  privacy: Privacy | null;
  spe: SpeRef | SpeWorkspace | null;
  audit: AuditEntry[];
  inference?: Inference | null;
  submitted?: string;
}

export interface ArticleInfo {
  title: string;
  summary: string;
  quote: string;
  url?: string;
}
export type Articles = Record<string, ArticleInfo>;

export interface DownloadBlocked {
  error: string;
  article: string;
  message: string;
  audit_id?: string;
  blocked_attempts?: number;
}

export interface MetricsRunCell {
  decision: Decision | null;
  articles?: string[];
  articles_ok?: boolean;
  numbers_ok?: boolean | null;
  leaks?: number;
  ms?: number;
}

export interface MetricsRow {
  id: string;
  title?: string;
  expected: Decision;
  expected_articles?: string[];
  runs: (MetricsRunCell | null)[];
  consistent?: boolean | null;
  values_matched?: number | null;
  values_total?: number | null;
  diff?: unknown[];
}

export interface MetricsRun {
  status: "running" | "done" | "error" | string;
  summary: {
    decisions_correct: number;
    decisions_total: number;
    numbers_correct: number;
    numbers_total: number;
    privacy_leaks: number;
    consistent: number;
    consistent_total: number;
    slowest_ms: number;
    threshold_ms: number;
    custom_correct?: number;
    custom_total?: number;
  };
  rows: MetricsRow[];
  /** mock: flat {id, decision, ms}; backend: rows shaped like MetricsRow */
  custom?: ({ id: string; decision?: Decision | null; ms?: number; answer?: unknown; title?: string } & Partial<MetricsRow>)[];
  runs_total?: number;
}

export interface OverrideBody {
  decision: Decision;
  articles: string[];
  note: string;
  actor: string;
}
