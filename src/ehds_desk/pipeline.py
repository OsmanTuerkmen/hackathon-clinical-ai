"""End-to-end processing: request -> decision -> statistics / SPE -> applicant view and staff view.

The decision is made first and never depends on the computation. The request is always parsed (staff see the
generated query even for a rejection), but statistics or an SPE are only computed for approvals. Every result
passes a privacy guard before it is returned.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel

from .compiler import compile_cohort
from .config import REPO_ROOT, Settings, load_settings
from .data import get_database
from .decision import assess_purpose, decide, request_kind
from .disclosure import (
    PATIENT_ID_PATTERN,
    DisclosedTable,
    LeakError,
    SuppressionNote,
    assert_no_leak,
    disclose_cell,
    disclose_table,
)
from .engine import opt_out_exclusions, run_statistics
from .law import ARTICLES
from .models import (
    AccessRequest,
    AgeCriterion,
    CodeSet,
    ConditionCriterion,
    CountMetric,
    Criterion,
    DataHolderCriterion,
    Dimension,
    EncounterCriterion,
    EncounterScope,
    MeanMetric,
    MedicationCriterion,
    ObservationCriterion,
    Outcome,
    PercentMetric,
    PurposeAssessment,
    QuerySpec,
    RawCount,
    RegionCriterion,
    RuleStep,
    SexCriterion,
)
from .parsing import ParseReport, parse_request
from .spe import provision_spe
from .terminology import Terminology

EXTRA_REQUESTS_DIR = REPO_ROOT / "requests" / "extra"

MANUAL_REVIEW_NOTE = (
    "Part of this request could not be interpreted automatically and was referred to staff for manual review."
)
_STATISTICS_REVIEW_WARNING = (
    "Statistics not computed – needs manual review: the request could not be interpreted completely "
    "or contains no statistics to compute."
)
_SPE_REVIEW_WARNING = (
    "Secure processing environment not provisioned – needs manual review: the cohort or the requested "
    "record types could not be interpreted completely."
)


# --- Result models ------------------------------------------------------------------------------


class SpeAnswer(BaseModel):
    permit_id: str
    patient_count: int
    tables: dict[str, int]
    workspace_url: str


class ApplicantView(BaseModel):
    request_id: str
    decision: Outcome
    articles: list[str]
    article_titles: dict[str, str]
    headline: str
    reasons: list[str]
    statistics: DisclosedTable | None
    spe: SpeAnswer | None
    notes: list[str]


class StaffView(BaseModel):
    trace: list[RuleStep]
    purpose: PurposeAssessment
    request_kind: str
    spec: QuerySpec | None
    spec_summary: list[str]
    parse_report: ParseReport
    parser_source: str
    sql: str | None
    opt_out_excluded: int | str | None
    disclosure_notes: list[SuppressionNote]
    timings_ms: dict[str, int]
    warnings: list[str]


class ProcessResult(BaseModel):
    applicant: ApplicantView
    staff: StaffView


# --- Readable spec summary ----------------------------------------------------------------------


def _codes(codes: CodeSet) -> str:
    system = {"icd10": "ICD-10", "atc": "ATC", "loinc": "LOINC"}[codes.system]
    shown = ", ".join(p if codes.system == "loinc" else f"{p}*" for p in codes.prefixes)
    label = codes.label.strip()
    return f"{system} {shown}" + (f" ({label})" if label and label != ",".join(codes.prefixes) else "")


def _age(min_: int | None, max_: int | None) -> str:
    if min_ is not None and max_ is not None:
        return f"{min_}–{max_}"
    if min_ is not None:
        return f"≥ {min_}"
    if max_ is not None:
        return f"≤ {max_}"
    return "any"


def _period(start_from, start_to) -> str | None:
    if start_from is None and start_to is None:
        return None
    return f"{start_from or '…'}..{start_to or '…'}"


def _encounter_parts(types, start_from, start_to, primary_icd10) -> list[str]:
    parts = []
    if types:
        parts.append("/".join(types))
    if period := _period(start_from, start_to):
        parts.append(period)
    if primary_icd10 is not None:
        parts.append(f"main diagnosis {_codes(primary_icd10)}")
    return parts


def _criterion(c: Criterion) -> str:
    if isinstance(c, AgeCriterion):
        return f"age {_age(c.min, c.max)}"
    if isinstance(c, SexCriterion):
        return f"sex {c.value}"
    if isinstance(c, RegionCriterion):
        return f"region in {', '.join(c.values)}"
    if isinstance(c, DataHolderCriterion):
        return f"data holder in {', '.join(c.values)}"
    if isinstance(c, ConditionCriterion):
        text = f"condition {_codes(c.codes)}"
    elif isinstance(c, MedicationCriterion):
        text = f"medication {_codes(c.codes)}" + (" (active)" if c.active_only else "")
    elif isinstance(c, ObservationCriterion):
        text = f"observation {_codes(c.codes)}"
    elif isinstance(c, EncounterCriterion):
        text = "encounter " + (", ".join(_encounter_parts(c.types, c.start_from, c.start_to, c.primary_icd10)) or "any")
    else:  # pragma: no cover - exhaustive over the Criterion union
        raise TypeError(type(c).__name__)
    return f"NOT ({text})" if c.negate else text


def _dimension(d: Dimension) -> str:
    if d.kind == "age_band":
        return "age band (" + ", ".join(b.label for b in d.bands) + ")"
    return d.kind.replace("_", " ")


def _metric(m) -> str:
    if isinstance(m, CountMetric):
        text = f"{m.label} (count" + ("" if m.display else ", not shown")
        if m.where:
            text += ": " + " AND ".join(_criterion(c) for c in m.where)
        return text + ")"
    if isinstance(m, PercentMetric):
        return f"{m.label} (percent: {m.numerator} / {m.denominator})"
    if isinstance(m, MeanMetric):
        return f"{m.label} (mean of the {m.method} value, {_codes(m.codes)})"
    raise TypeError(type(m).__name__)  # pragma: no cover


def _summarise(spec: QuerySpec | None) -> list[str]:
    if spec is None:
        return []
    lines = [f"Unit: {'patients' if spec.unit == 'patient' else 'encounters'}"]
    if spec.population:
        lines.append("Population: " + " AND ".join(_criterion(c) for c in spec.population))
    scope: EncounterScope | None = spec.encounter_scope
    if scope is not None:
        parts = _encounter_parts(scope.types, scope.start_from, scope.start_to, scope.primary_icd10)
        if scope.data_holders:
            parts.append("data holder in " + ", ".join(scope.data_holders))
        lines.append("Encounter scope: " + (", ".join(parts) or "all encounters"))
    if spec.group_by:
        lines.append("Group by: " + ", ".join(_dimension(d) for d in spec.group_by))
    if spec.metrics:
        lines.append("Metrics: " + "; ".join(_metric(m) for m in spec.metrics))
    if spec.output == "cohort_size":
        lines.append("Output: cohort size")
    if spec.record_types:
        text = "Records: " + ", ".join(spec.record_types)
        if spec.observation_codes is not None:
            text += f" (observations limited to {_codes(spec.observation_codes)})"
        lines.append(text)
    return lines


# --- Service ------------------------------------------------------------------------------------


def _article_titles(articles: list[str]) -> dict[str, str]:
    return {a: ARTICLES[a].title for a in articles if a in ARTICLES}


def _spe_possible(spec: QuerySpec | None, complete: bool) -> bool:
    return spec is not None and complete and bool(spec.record_types) and (spec.output == "cohort_size" or bool(spec.population))


class DeskService:
    def __init__(self, settings: Settings | None = None, extra_dir: Path | None = None):
        self.settings = settings or load_settings()
        self.db = get_database(self.settings)
        self.terminology = Terminology(self.db)
        self._extra_dir = EXTRA_REQUESTS_DIR if extra_dir is None else Path(extra_dir)

    # --- processing ---

    def process(self, request: AccessRequest) -> ProcessResult:
        started = time.perf_counter()
        parse = parse_request(request, self.terminology, self.settings)
        parsed = time.perf_counter()
        assessment = assess_purpose(request, parse.llm_purpose)
        decision = decide(request, assessment)
        decided = time.perf_counter()

        spec = parse.spec
        complete = spec is not None and parse.report.complete
        notes: list[str] = []
        warnings = [*decision.warnings, *parse.report.notes]
        statistics: DisclosedTable | None = None
        spe: SpeAnswer | None = None
        sql: str | None = None
        opt_out: int | str | None = None

        if decision.outcome == "APPROVE_STATISTICAL":
            if complete and spec is not None and spec.metrics:
                raw, query = run_statistics(spec, self.db)
                statistics = disclose_table(raw)
                sql = query.sql
                opt_out = disclose_cell(RawCount(n=opt_out_exclusions(spec, self.db)))
            else:
                notes.append(MANUAL_REVIEW_NOTE)
                warnings.append(_STATISTICS_REVIEW_WARNING)
        elif decision.outcome == "APPROVE_SPE":
            if spec is not None and _spe_possible(spec, complete):
                manifest = provision_spe(request, spec, self.db, self.settings.var_dir)
                # Exact cohort and table sizes are shown on purpose: the SPE holds the records themselves, so
                # the small-cell rule for statistics does not apply to them (controller ruling R13).
                spe = SpeAnswer(
                    permit_id=manifest.permit_id,
                    patient_count=manifest.patient_count,
                    tables=dict(manifest.tables),
                    workspace_url=f"/spe/{manifest.permit_id}",
                )
                sql = compile_cohort(spec).sql
                opt_out = disclose_cell(RawCount(n=opt_out_exclusions(spec, self.db)))
            else:
                notes.append(MANUAL_REVIEW_NOTE)
                warnings.append(_SPE_REVIEW_WARNING)
        computed = time.perf_counter()

        result = ProcessResult(
            applicant=ApplicantView(
                request_id=request.id,
                decision=decision.outcome,
                articles=list(decision.articles),
                article_titles=_article_titles(decision.articles),
                headline=decision.headline,
                reasons=list(decision.reasons),
                statistics=statistics,
                spe=spe,
                notes=notes,
            ),
            staff=StaffView(
                trace=decision.trace,
                purpose=assessment,
                request_kind=request_kind(request),
                spec=spec,
                spec_summary=_summarise(spec),
                parse_report=parse.report,
                parser_source=parse.source,
                sql=sql,
                opt_out_excluded=opt_out,
                disclosure_notes=list(statistics.notes) if statistics else [],
                timings_ms={
                    "parse": round((parsed - started) * 1000),
                    "decide": round((decided - parsed) * 1000),
                    "compute": round((computed - decided) * 1000),
                    "total": round((time.perf_counter() - started) * 1000),
                },
                warnings=warnings,
            ),
        )
        self._guard(result)
        return result

    @staticmethod
    def _guard(result: ProcessResult) -> None:
        """Last line of defence: no small count in the statistics, no patient identifier anywhere."""
        assert_no_leak(result.applicant.statistics)
        if PATIENT_ID_PATTERN.search(result.model_dump_json()):
            raise LeakError("result contains a patient identifier")

    # --- stored requests ---

    def _sources(self) -> list[tuple[str, Path]]:
        found: list[tuple[str, Path]] = []
        for source, directory in (("track3", self.settings.data_dir / "requests"), ("extra", self._extra_dir)):
            if directory.is_dir():
                found.extend((source, p) for p in sorted(directory.glob("*.json")) if p.name != "expected.json")
        return found

    @staticmethod
    def _load(path: Path) -> AccessRequest | None:
        try:
            return AccessRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):  # unreadable, invalid JSON or not an access request
            return None

    def list_requests(self) -> list[dict]:
        listed = []
        for source, path in self._sources():
            request = self._load(path)
            if request is not None:
                listed.append(
                    {
                        "id": request.id,
                        "source": source,
                        "organisation": request.applicant.organisation,
                        "purpose": request.purpose,
                        "requested_as": request.requested_as,
                    }
                )
        return listed

    def get_request(self, request_id: str) -> AccessRequest:
        for _source, path in self._sources():
            request = self._load(path)
            if request is not None and request.id == request_id:
                return request
        raise KeyError(request_id)
