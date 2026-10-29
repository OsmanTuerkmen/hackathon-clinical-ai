"""Typed interfaces: access request, query spec, raw cells and decision.

Pure data models with validation only; no business logic.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

_ICD_ATC_PREFIX = re.compile(r"[A-Z][0-9A-Z.]*")
_LOINC_PREFIX = re.compile(r"[0-9]+(-[0-9]?)?")

EncounterType = Literal["inpatient", "outpatient", "emergency"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# --- Request ---------------------------------------------------------------


class Applicant(_Frozen):
    name: str
    organisation: str
    country: str | None = None


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    submitted: str | None = None
    applicant: Applicant
    requested_as: str
    requested_format: str | None = None
    purpose: str
    question: str
    definitions: list[str]

    def full_text(self) -> str:
        return "\n".join([self.purpose, self.question, *self.definitions])


# --- Query spec ------------------------------------------------------------


class CodeSet(_Frozen):
    system: Literal["icd10", "atc", "loinc"]
    prefixes: list[str] = Field(min_length=1)
    label: str
    source: Literal["explicit", "lexicon", "data_match", "llm"]

    @field_validator("prefixes")
    @classmethod
    def _normalise_prefixes(cls, prefixes: list[str], info: ValidationInfo) -> list[str]:
        """Strip blanks, reject empty prefixes (they would match every code) and check the code shape."""
        system = info.data.get("system")
        out: list[str] = []
        for raw in prefixes:
            prefix = raw.strip()
            if not prefix:
                raise ValueError("code prefix must not be empty")
            if system == "loinc":
                if not _LOINC_PREFIX.fullmatch(prefix):
                    raise ValueError(f"'{prefix}' is not a LOINC code prefix (digits, optional hyphen and check digit)")
            elif system in ("icd10", "atc"):
                prefix = prefix.upper()
                if not _ICD_ATC_PREFIX.fullmatch(prefix):
                    raise ValueError(f"'{prefix}' is not a valid {system} code prefix")
            out.append(prefix)
        return out


class AgeCriterion(_Frozen):
    kind: Literal["age"]
    min: int | None = None
    max: int | None = None


class SexCriterion(_Frozen):
    kind: Literal["sex"]
    value: Literal["female", "male"]


class RegionCriterion(_Frozen):
    kind: Literal["region"]
    values: list[str]


class DataHolderCriterion(_Frozen):
    kind: Literal["data_holder"]
    values: list[str]


class ConditionCriterion(_Frozen):
    kind: Literal["condition"]
    codes: CodeSet
    negate: bool = False


class MedicationCriterion(_Frozen):
    kind: Literal["medication"]
    codes: CodeSet
    active_only: bool = True
    negate: bool = False


class ObservationCriterion(_Frozen):
    kind: Literal["observation"]
    codes: CodeSet
    negate: bool = False


class EncounterCriterion(_Frozen):
    kind: Literal["encounter"]
    types: list[EncounterType] = []
    start_from: date | None = None
    start_to: date | None = None
    primary_icd10: CodeSet | None = None
    negate: bool = False


Criterion = Annotated[
    Union[
        AgeCriterion,
        SexCriterion,
        RegionCriterion,
        DataHolderCriterion,
        ConditionCriterion,
        MedicationCriterion,
        ObservationCriterion,
        EncounterCriterion,
    ],
    Field(discriminator="kind"),
]


class AgeBand(_Frozen):
    label: str
    min: int
    max: int | None = None


class Dimension(_Frozen):
    kind: Literal["region", "data_holder", "sex", "age_band"]
    bands: list[AgeBand] = []

    @model_validator(mode="after")
    def _bands_match_kind(self) -> Dimension:
        if self.kind == "age_band" and not self.bands:
            raise ValueError("age_band dimension requires at least one band")
        if self.kind != "age_band" and self.bands:
            raise ValueError(f"bands are only allowed for age_band dimensions, not {self.kind}")
        return self


class EncounterScope(_Frozen):
    types: list[EncounterType] = []
    start_from: date | None = None
    start_to: date | None = None
    primary_icd10: CodeSet | None = None
    data_holders: list[str] = []


class CountMetric(_Frozen):
    kind: Literal["count"]
    name: str
    label: str
    where: list[Criterion] = []
    display: bool = True


class PercentMetric(_Frozen):
    kind: Literal["percent"]
    name: str
    label: str
    numerator: str
    denominator: str


class MeanMetric(_Frozen):
    kind: Literal["mean"]
    name: str
    label: str
    codes: CodeSet
    method: Literal["latest"] = "latest"


Metric = Annotated[
    Union[CountMetric, PercentMetric, MeanMetric],
    Field(discriminator="kind"),
]


class QuerySpec(_Frozen):
    unit: Literal["patient", "encounter"] = "patient"
    population: list[Criterion] = []
    encounter_scope: EncounterScope | None = None
    group_by: list[Dimension] = []
    metrics: list[Metric] = []
    output: Literal["statistics", "cohort_size"] = "statistics"
    record_types: list[Literal["patients", "conditions", "medications", "observations", "encounters"]] = []
    observation_codes: CodeSet | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> QuerySpec:
        if self.unit == "encounter" and self.encounter_scope is None:
            raise ValueError("unit 'encounter' requires encounter_scope")
        if self.output == "statistics" and not self.metrics:
            raise ValueError("output 'statistics' requires at least one metric")
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("metric names must be unique")
        dim_kinds = [d.kind for d in self.group_by]
        if len(dim_kinds) != len(set(dim_kinds)):
            raise ValueError("group_by must not contain the same dimension kind twice")
        count_names = {m.name for m in self.metrics if isinstance(m, CountMetric)}
        for m in self.metrics:
            if isinstance(m, MeanMetric) and self.unit != "patient":
                raise ValueError(f"mean metric '{m.name}' is only allowed for unit 'patient'")
            if isinstance(m, PercentMetric):
                for ref in (m.numerator, m.denominator):
                    if ref not in count_names:
                        raise ValueError(
                            f"percent metric '{m.name}' refers to '{ref}', which is not a count metric in this spec"
                        )
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- Raw (unsuppressed) result cells ----------------------------------------


class RawCount(_Frozen):
    n: int


class RawPercent(_Frozen):
    num: int
    den: int


class RawMean(_Frozen):
    total: Decimal
    n: int


class RawRow(_Frozen):
    group: dict[str, str]
    cells: dict[str, Union[RawCount, RawPercent, RawMean]]


class RawTable(_Frozen):
    dimensions: list[str]
    metrics: list[Metric]
    rows: list[RawRow]


# --- Decision ---------------------------------------------------------------


class Evidence(_Frozen):
    source: Literal["rules", "llm"]
    category: str
    quote: str


class PurposeAssessment(_Frozen):
    prohibited: list[Evidence]
    permitted: list[Evidence]
    spe_justification: list[Evidence]


class RuleStep(_Frozen):
    step: int
    title: str
    condition: str
    status: Literal["matched", "not_matched", "not_evaluated"]
    evidence: list[Evidence]


Outcome = Literal["REJECT", "APPROVE_STATISTICAL", "APPROVE_SPE"]


class Decision(_Frozen):
    outcome: Outcome
    articles: list[str]
    headline: str
    reasons: list[str]
    trace: list[RuleStep]
    warnings: list[str]
