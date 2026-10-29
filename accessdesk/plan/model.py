"""Validated, typed query plan DSL."""
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ICD_ATC_PREFIX = re.compile(r"^[A-Z][0-9A-Z.]{0,7}$")
LOINC_CODE = re.compile(r"^\d{1,6}-\d$")


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Concept(PlanModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    kind: Literal[
        "condition", "medication", "observation", "encounter", "age", "sex",
        "region", "los", "composite",
    ]
    source: str
    aliases: list[str] = Field(default_factory=list)
    prefixes: list[str] = Field(default_factory=list)
    loinc: str | None = None
    pick: str | None = None
    enc_type: Literal["inpatient", "outpatient", "emergency"] | None = None
    primary_prefixes: list[str] = Field(default_factory=list)
    min: int | None = None
    max: int | None = None
    value: str | None = None
    phrase: str | None = None

    @field_validator("prefixes", "primary_prefixes")
    @classmethod
    def validate_code_prefixes(cls, values):
        if any(not ICD_ATC_PREFIX.fullmatch(value) for value in values):
            raise ValueError("ICD-10/ATC prefixes must contain only valid code characters")
        return values

    @field_validator("loinc")
    @classmethod
    def validate_loinc(cls, value):
        if value is not None and not LOINC_CODE.fullmatch(value):
            raise ValueError("LOINC codes must match NNNNNN-N")
        return value


class Comparison(PlanModel):
    op: Literal[">", ">=", "<", "<="]
    value: float

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value):
        if not math.isfinite(value):
            raise ValueError("comparison value must be finite")
        return value


class Term(PlanModel):
    concept: str
    neg: bool = False
    active: bool | None = None
    cmp: Comparison | None = None
    years: list[int] | None = None


class AgeBand(PlanModel):
    label: str = Field(pattern=r"^<?\d{1,3}(?:-\d{1,3}|\+)?$")
    min: int
    max: int | None = None

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min < 0 or (self.max is not None and self.max < self.min):
            raise ValueError("age-band bounds are invalid")
        return self


class Group(PlanModel):
    dim: Literal["region", "data_holder", "sex", "age_band", "year"]
    bands: list[AgeBand] = Field(default_factory=list)
    years: list[int] | None = None


class ParentMeasure(PlanModel):
    label: str
    set: list[Term]


class Measure(PlanModel):
    key: str
    label: str
    type: Literal["count", "pct", "mean"]
    set: list[Term] = Field(default_factory=list)
    num_set: list[Term] = Field(default_factory=list)
    den_set: list[Term] = Field(default_factory=list)
    value: str | None = None
    cohort: bool = False
    parent: ParentMeasure | None = None
    source: str | None = None


class Ratio(PlanModel):
    name: str
    num: str
    den: str


class RecordType(PlanModel):
    table: Literal["conditions", "medications", "observations", "encounters", "patients"]
    loinc: list[str] | None = None

    @field_validator("loinc")
    @classmethod
    def validate_loinc_codes(cls, values):
        if values is not None and any(not LOINC_CODE.fullmatch(value) for value in values):
            raise ValueError("LOINC codes must match NNNNNN-N")
        return values


class QueryPlan(PlanModel):
    unit: Literal["patient", "encounter"]
    unit_years: list[int] | None = None
    encounter_concept: str | None = None
    concepts: dict[str, Concept]
    ratios: list[Ratio] = Field(default_factory=list)
    population: list[Term] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    cohort: list[Term] = Field(default_factory=list)
    patient_level_requested: bool = False
    record_types: list[RecordType] = Field(default_factory=list)
    active_rule: bool = False
    reference_date: str
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        concept_ids = set(self.concepts)
        for key, concept in self.concepts.items():
            if concept.id != key:
                raise ValueError("concept dictionary keys must match concept IDs")
        if self.encounter_concept and self.encounter_concept not in concept_ids:
            raise ValueError("encounter concept is not defined")
        terms = [
            *self.population,
            *self.cohort,
            *(term for measure in self.measures for term in measure.set),
            *(term for measure in self.measures for term in measure.num_set),
            *(term for measure in self.measures for term in measure.den_set),
        ]
        if any(term.concept not in concept_ids for term in terms):
            raise ValueError("query terms must reference defined concepts")
        if any(measure.value is not None and measure.value not in concept_ids for measure in self.measures):
            raise ValueError("measure values must reference defined concepts")
        return self
