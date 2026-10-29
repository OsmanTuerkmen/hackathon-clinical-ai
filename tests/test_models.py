import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ehds_desk.models import (
    AccessRequest,
    AgeBand,
    AgeCriterion,
    CodeSet,
    ConditionCriterion,
    CountMetric,
    Decision,
    Dimension,
    EncounterCriterion,
    EncounterScope,
    MeanMetric,
    MedicationCriterion,
    PercentMetric,
    QuerySpec,
    RawCount,
    RawMean,
    RawPercent,
    RawRow,
    RawTable,
    SexCriterion,
)

E11 = CodeSet(system="icd10", prefixes=["E11"], label="type 2 diabetes", source="explicit")
HBA1C = CodeSet(system="loinc", prefixes=["4548-4"], label="HbA1c", source="explicit")


def count(name: str, **kw) -> CountMetric:
    return CountMetric(name=name, label=name, **kw)


def test_spec_rejects_percent_with_unknown_metric():
    with pytest.raises(ValidationError):
        QuerySpec(
            metrics=[
                count("a"),
                PercentMetric(name="p", label="p", numerator="a", denominator="missing"),
            ]
        )


def test_spec_rejects_percent_on_mean():
    with pytest.raises(ValidationError):
        QuerySpec(
            metrics=[
                count("a"),
                MeanMetric(name="m", label="m", codes=HBA1C),
                PercentMetric(name="p", label="p", numerator="m", denominator="a"),
            ]
        )


def test_percent_with_valid_counts_is_accepted():
    spec = QuerySpec(
        metrics=[
            count("a"),
            count("b"),
            PercentMetric(name="p", label="p", numerator="a", denominator="b"),
        ]
    )
    assert len(spec.metrics) == 3


def test_encounter_unit_requires_scope():
    with pytest.raises(ValidationError):
        QuerySpec(unit="encounter", metrics=[count("a")])
    spec = QuerySpec(unit="encounter", encounter_scope=EncounterScope(), metrics=[count("a")])
    assert spec.encounter_scope is not None


def test_statistics_output_requires_metric():
    with pytest.raises(ValidationError):
        QuerySpec(output="statistics", metrics=[])
    assert QuerySpec(output="cohort_size", metrics=[]).metrics == []


def test_age_band_dimension_requires_bands():
    with pytest.raises(ValidationError):
        Dimension(kind="age_band")
    with pytest.raises(ValidationError):
        Dimension(kind="region", bands=[AgeBand(label="0-17", min=0, max=17)])
    dim = Dimension(kind="age_band", bands=[AgeBand(label="85+", min=85, max=None)])
    assert dim.bands[0].max is None


def test_mean_only_for_patient_unit():
    with pytest.raises(ValidationError):
        QuerySpec(
            unit="encounter",
            encounter_scope=EncounterScope(),
            metrics=[MeanMetric(name="m", label="m", codes=HBA1C)],
        )
    spec = QuerySpec(metrics=[MeanMetric(name="m", label="m", codes=HBA1C)])
    assert spec.metrics[0].method == "latest"


def _build() -> QuerySpec:
    return QuerySpec(
        population=[AgeCriterion(min=18, max=None), SexCriterion(value="female")],
        group_by=[Dimension(kind="region")],
        metrics=[count("adults", where=[ConditionCriterion(codes=E11)])],
    )


def test_canonical_json_is_order_stable():
    a, b = _build(), _build()
    assert a.canonical_json() == b.canonical_json()
    parsed = json.loads(a.canonical_json())
    assert list(parsed) == sorted(parsed)
    assert ": " not in a.canonical_json() and ", " not in a.canonical_json()


def test_access_request_allows_extra_and_missing_optional_fields():
    req = AccessRequest.model_validate(
        {
            "id": "X1",
            "applicant": {"name": "A", "organisation": "O"},
            "requested_as": "health data request",
            "purpose": "P",
            "question": "Q",
            "definitions": ["D1", "D2"],
            "unexpected": 42,
        }
    )
    assert req.submitted is None and req.requested_format is None
    assert req.applicant.country is None
    assert req.full_text() == "P\nQ\nD1\nD2"
    assert req.model_dump()["unexpected"] == 42


def test_access_request_loads_example_file(settings):
    path = settings.data_dir / "requests" / "R01.json"
    req = AccessRequest.model_validate_json(path.read_text(encoding="utf-8"))
    assert req.id == "R01" and req.applicant.country == "AT"
    assert len(req.definitions) == 4


def test_criterion_discriminator_roundtrip():
    spec = QuerySpec(
        population=[
            AgeCriterion(min=18, max=None),
            MedicationCriterion(
                codes=CodeSet(system="atc", prefixes=["A10"], label="antidiabetics", source="lexicon"),
                negate=True,
            ),
            EncounterCriterion(
                types=["inpatient"],
                start_from=date(2025, 1, 1),
                start_to=date(2025, 12, 31),
                primary_icd10=E11,
            ),
        ],
        group_by=[Dimension(kind="age_band", bands=[AgeBand(label="18-64", min=18, max=64)])],
        metrics=[count("a"), count("b"), PercentMetric(name="p", label="p", numerator="a", denominator="b")],
    )
    again = QuerySpec.model_validate(json.loads(json.dumps(spec.model_dump(mode="json"))))
    assert again == spec
    assert [c.kind for c in again.population] == ["age", "medication", "encounter"]
    assert again.population[1].active_only is True
    assert [m.kind for m in again.metrics] == ["count", "count", "percent"]


def test_models_are_frozen():
    with pytest.raises(ValidationError):
        E11.label = "x"


def test_raw_table_and_decision_models():
    table = RawTable(
        dimensions=["region"],
        metrics=[count("a")],
        rows=[
            RawRow(
                group={"region": "Wien"},
                cells={
                    "a": RawCount(n=12),
                    "p": RawPercent(num=3, den=12),
                    "m": RawMean(total=Decimal("12.5"), n=2),
                },
            )
        ],
    )
    cell = table.rows[0].cells["m"]
    assert isinstance(cell, RawMean) and cell.total == Decimal("12.5")
    d = Decision(outcome="REJECT", articles=["Art. 54"], headline="h", reasons=[], trace=[], warnings=[])
    assert d.outcome == "REJECT"
    with pytest.raises(ValidationError):
        Decision(outcome="MAYBE", articles=[], headline="h", reasons=[], trace=[], warnings=[])
