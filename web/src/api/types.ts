export type Language = "de" | "en";
export interface AIStatus {
  enabled: boolean;
  provider?: "claude" | "gemini";
  model?: string;
  reason?: string;
}

export type CaseGroup = "test" | "demo" | "custom";
export type InboxStatus =
  | "auto_decided"
  | "review_needed"
  | "held_identity"
  | "released"
  | "rejected_after_review";
export type Decision =
  | "REJECT"
  | "APPROVE_STATISTICAL"
  | "APPROVE_SPE";
export type SafeStatus = "pass" | "warn" | "fail" | "na";
export type SafeName = "people" | "projects" | "data" | "settings" | "outputs";
export type CellValue = number | string;

export interface Applicant {
  name: string;
  organisation: string;
  country: string;
}

export interface SafeSummary {
  people: SafeStatus;
  projects: SafeStatus;
  data: SafeStatus;
  settings: SafeStatus;
  outputs: SafeStatus;
}

export interface CaseSummary {
  id: string;
  group: CaseGroup;
  submitted: string | null;
  received_at: string;
  applicant: Applicant;
  requested_as: string;
  kind: "request" | "application";
  question: string;
  decision: Decision;
  articles: string[];
  status: InboxStatus;
  delivery_status: string;
  five_safes: SafeSummary;
  flags_count: number;
  ai_involved: boolean;
  permit_id: string | null;
  reviewed: boolean;
}

export interface Evidence {
  phrase: string;
  field: string;
  start: number;
  end: number;
}

export interface ProhibitedPurpose {
  category: string;
  label_en: string;
  label_de: string;
  evidence: Evidence[];
}

export interface AllowedPurpose {
  category: string;
  en: string;
  de: string;
  evidence: Evidence[];
}

export interface DecisionTrace {
  step: number;
  rule: string;
  result: boolean;
  evidence: string[];
}

export interface CaseDecision {
  decision: Decision;
  articles: string[];
  reason_en: string;
  reason_de: string;
  kind: string;
  trace: DecisionTrace[];
  articles_detail: Array<{ n: string; title_en: string; title_de: string }>;
}

export interface PersonCheck {
  id: string;
  ok: boolean;
  issuer: string | null;
  detail_en: string;
  detail_de: string;
  info?: boolean;
}

export interface PersonFlag {
  id: string;
  en: string;
  de: string;
}

export interface PersonResult {
  status: "verified" | "unverified" | "failed";
  checks: PersonCheck[];
  flags: PersonFlag[];
  persons_with_access: string[];
}

export interface PlanMeasure {
  key: string;
  label: string;
  type: "count" | "pct" | "mean";
}

export interface QueryPlanSummary {
  unit: "patient" | "encounter";
  groups: Array<{
    dim: "region" | "data_holder" | "sex" | "age_band" | "year";
    bands?: Array<{ label: string; min: number; max: number | null }>;
    years?: number[] | null;
  }>;
  measures: PlanMeasure[];
  warnings: string[];
}

export interface MappingCode {
  system: string;
  prefix: string;
  code: string;
  label: string | null;
  rows: number | string | null;
}

export interface Mapping {
  name: string;
  kind: string;
  source: string;
  ai?: boolean;
  codes: MappingCode[];
}

export interface ReleasedRow {
  group: string[];
  values: Record<string, CellValue>;
}

export interface ReleasedTable {
  group_dims: string[];
  measures: PlanMeasure[];
  rows: ReleasedRow[];
  answer: Record<string, unknown>;
  gate: {
    cells: number;
    counts_hidden: number;
    pct_suppressed: number;
    means_suppressed: number;
  };
  differencing?: {
    checked_cells: number;
    compared_entries: number;
    suppressed: Array<{
      group: string[];
      measure: string;
      part: string;
      difference: number;
      against: {
        request_id: string;
        group: string[];
        measure: string;
        part: string;
      };
    }>;
  };
}

export interface FunnelStep {
  key: string;
  label_en: string;
  label_de: string;
  count: number | string;
}

export interface SPEManifest {
  permit_id: string;
  request_id: string;
  created: string;
  expires: string;
  cohort_size: number;
  persons_with_access: string[];
  tables_copied: Array<{ table: string; rows: number; note: string | null }>;
  tables_not_copied: string[];
  cohort_sql: string;
  egress_rule: string;
  location: string;
  request_hash: string;
}

export interface PipelineResult {
  id: string;
  request: Record<string, unknown> & {
    applicant?: Applicant;
    purpose?: string;
    question?: string;
    definitions?: string[];
  };
  who: PersonResult;
  features: {
    prohibited: ProhibitedPurpose[];
    allowed: AllowedPurpose[];
    justifies_records: Evidence[];
    reidentification: Evidence[];
    org_type: string;
  };
  decision: CaseDecision;
  ai: {
    status: AIStatus;
    opinion: Record<string, unknown> | null;
    agrees: boolean | null;
  };
  plan: QueryPlanSummary;
  mappings: Mapping[];
  sql: string | null;
  released: ReleasedTable | null;
  spe: SPEManifest | null;
  notes: Array<{ de: string; en: string }>;
  delivery: { status: string; de: string; en: string };
  opted_out_excluded: number;
  expected_check: Record<string, unknown> | null;
  warnings: string[];
  funnel: FunnelStep[];
  five_safes: Record<SafeName, {
    status: SafeStatus;
    summary_de: string;
    summary_en: string;
  }>;
  data_minimisation: {
    summary_de: string;
    summary_en: string;
    requested_record_types: string[];
    copied_record_types: string[];
    not_copied_record_types: string[];
  };
  status: InboxStatus;
}

export interface Review {
  action: "release" | "hold" | "reject";
  reason: string;
  reviewer: string;
  reviewed_at: string;
}

export interface CaseDetail {
  summary: CaseSummary;
  result: PipelineResult;
  reviews: Review[];
  visible_to_applicant: boolean;
}

export interface Identity {
  name: string;
  organisation: string;
  country: string;
  credential_types: string[];
}

export interface RegisterPermit {
  expires: string;
  record_types: Array<{
    table: string;
    label_de: string;
    label_en: string;
  }>;
}

export interface RegisterEntry {
  reference: string;
  id: string;
  received: string;
  organisation: string;
  kind: "request" | "application";
  purpose: string;
  purpose_categories: string[];
  publication_status: "received" | "decided" | "in_review";
  decision?: Decision;
  articles?: string[];
  justification_de?: string;
  justification_en?: string;
  decided?: string;
  permit?: RegisterPermit | null;
}

export interface DecisionLetter {
  header: {
    lang: Language;
    reference: string;
    date: string;
    authority: string;
    authority_address: string;
    demo_notice: string;
    draft: boolean;
    draft_notice: string | null;
    title: string;
    labels: Record<string, string>;
  };
  applicant: Applicant;
  subject: string;
  operative: string;
  reasoning: string[];
  conditions: string[];
  annex: null | {
    type: "statistics";
    group_dims: string[];
    measures: PlanMeasure[];
    rows: ReleasedRow[];
  } | {
    type: "permit";
    permit_id: string;
    cohort_size: string;
    tables: string[];
    not_tables: string[];
    persons: string[];
    expires: string;
  };
  remedy: string;
  signature: string[];
  articles: Array<{ n: string; title: string }>;
}

export interface PrecheckResult {
  decision: {
    decision: Decision;
    articles: string[];
    reason_de: string;
    reason_en: string;
    trace: DecisionTrace[];
    kind: string;
  };
  art54: ProhibitedPurpose[];
  allowed: AllowedPurpose[];
  justification: Evidence[];
  mappings: Array<Mapping & { ai: boolean }>;
  plan: null | {
    unit: "patient" | "encounter";
    groups: Array<{ dim: string; labels: string[] }>;
    measures: PlanMeasure[];
  };
  result_shape: null | { group_dims: string[]; cells: number };
  cohort_estimate: number | string | null;
  funnel: FunnelStep[];
  warnings: string[];
  identity: { status: string };
  flags: PersonFlag[];
}

export interface AuditEntry {
  seq: number;
  time: string;
  actor: string;
  action: string;
  request_id: string | null;
  details: Record<string, unknown>;
  prev: string;
  hash: string;
}
