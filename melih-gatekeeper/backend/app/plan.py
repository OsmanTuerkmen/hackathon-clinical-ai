"""Query plan: the structured, validated form of a request's plain-English definitions.

The LLM (or a human) produces a QueryPlan; everything after that is deterministic code.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Source = Literal["condition", "medication", "observation", "encounter"]
Dim = Literal["region", "data_holder", "sex", "age_band"]


class Criterion(BaseModel):
    """One patient-level condition, e.g. 'has an ICD-10 code starting with E11'."""

    source: Source
    codes: list[str] = Field(default_factory=list, description="Code prefixes (ICD-10/ATC/primary_icd10) or exact LOINC codes")
    active_on: Optional[str] = Field(None, description="medication only: active on this date (YYYY-MM-DD)")
    pick: Literal["any", "latest"] = Field("any", description="observation only: test against any value or only the latest")
    value_op: Optional[Literal[">", ">=", "<", "<=", "="]] = None
    value: Optional[float] = None
    encounter_types: list[Literal["inpatient", "outpatient", "emergency"]] = Field(default_factory=list)
    start_from: Optional[str] = None
    start_to: Optional[str] = None
    negate: bool = False
    label: str = ""


class Population(BaseModel):
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    sex: Optional[Literal["female", "male"]] = None
    regions: list[str] = Field(default_factory=list)
    data_holders: list[str] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list, description="All must hold (AND)")


class EncounterFilter(BaseModel):
    types: list[Literal["inpatient", "outpatient", "emergency"]] = Field(default_factory=list)
    start_from: Optional[str] = None
    start_to: Optional[str] = None
    end_from: Optional[str] = None
    end_to: Optional[str] = None
    primary_icd10: list[str] = Field(default_factory=list, description="Main-diagnosis code prefixes")
    data_holders: list[str] = Field(default_factory=list)


class GroupBy(BaseModel):
    dim: Dim
    bands: list[str] = Field(default_factory=list, description="age_band only, e.g. ['18-29', '80+']")


class Measure(BaseModel):
    name: str
    kind: Literal["count", "pct", "mean"]
    criteria: list[Criterion] = Field(default_factory=list, description="count: extra filter on top of the population")
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    loinc: Optional[str] = None
    pick: Literal["latest"] = "latest"
    hidden: bool = Field(False, description="Helper measure (e.g. a numerator) not shown in the answer")

    @model_validator(mode="after")
    def _check(self):
        if self.kind == "pct" and not (self.numerator and self.denominator):
            raise ValueError(f"pct measure {self.name} needs numerator and denominator")
        if self.kind == "mean" and not self.loinc:
            raise ValueError(f"mean measure {self.name} needs loinc")
        return self


class SpeRecordType(BaseModel):
    table: Literal["patients", "conditions", "medications", "observations", "encounters"]
    codes: list[str] = Field(default_factory=list, description="Restrict rows to these code prefixes; empty = all rows")


class QueryPlan(BaseModel):
    patient_level_requested: bool = Field(False, description="The request asks for individual records; statistics never return them")
    unit: Literal["patients", "encounters"] = "patients"
    population: Population = Field(default_factory=Population)
    encounter_filter: Optional[EncounterFilter] = None
    group_by: list[GroupBy] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    spe_records: list[SpeRecordType] = Field(default_factory=list, description="Record types to copy into an SPE")

    @model_validator(mode="after")
    def _check(self):
        names = {m.name for m in self.measures}
        for m in self.measures:
            for ref in (m.numerator, m.denominator):
                if ref and ref not in names:
                    raise ValueError(f"measure {m.name} references unknown measure {ref}")
        for g in self.group_by:
            if g.dim == "age_band" and not g.bands:
                raise ValueError("age_band grouping needs bands")
        return self
