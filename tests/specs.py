"""Hand-built QuerySpecs for the hackathon requests (test fixtures, independent of the NL parser)."""

from __future__ import annotations

from ehds_desk.models import (
    AgeBand,
    AgeCriterion,
    CodeSet,
    ConditionCriterion,
    CountMetric,
    Dimension,
    EncounterScope,
    MeanMetric,
    MedicationCriterion,
    ObservationCriterion,
    PercentMetric,
    QuerySpec,
    SexCriterion,
)


def codes(system: str, *prefixes: str, label: str = "") -> CodeSet:
    return CodeSet(system=system, prefixes=list(prefixes), label=label or ",".join(prefixes), source="explicit")


ADULT = AgeCriterion(kind="age", min=18)


def r01() -> QuerySpec:
    return QuerySpec(
        population=[ADULT],
        group_by=[Dimension(kind="region")],
        metrics=[
            CountMetric(kind="count", name="adults", label="Adults"),
            CountMetric(
                kind="count",
                name="type2_diabetes",
                label="Adults with type 2 diabetes",
                where=[ConditionCriterion(kind="condition", codes=codes("icd10", "E11"))],
            ),
            PercentMetric(
                kind="percent",
                name="prevalence_pct",
                label="Prevalence (%)",
                numerator="type2_diabetes",
                denominator="adults",
            ),
        ],
    )


def r03() -> QuerySpec:
    oac = codes("atc", "B01AA", "B01AF")
    return QuerySpec(
        population=[
            AgeCriterion(kind="age", min=65),
            ConditionCriterion(kind="condition", codes=codes("icd10", "I48")),
        ],
        group_by=[
            Dimension(
                kind="age_band",
                bands=[
                    AgeBand(label="65-74", min=65, max=74),
                    AgeBand(label="75-84", min=75, max=84),
                    AgeBand(label="85+", min=85),
                ],
            )
        ],
        metrics=[
            CountMetric(kind="count", name="af_patients", label="Patients with atrial fibrillation"),
            CountMetric(
                kind="count",
                name="without_oac",
                label="Without active oral anticoagulant",
                where=[MedicationCriterion(kind="medication", codes=oac, active_only=True, negate=True)],
            ),
            PercentMetric(
                kind="percent",
                name="share_without_oac_pct",
                label="Share without OAC (%)",
                numerator="without_oac",
                denominator="af_patients",
            ),
        ],
    )


def r05() -> QuerySpec:
    return QuerySpec(
        population=[
            ADULT,
            ConditionCriterion(kind="condition", codes=codes("icd10", "E11")),
            ObservationCriterion(kind="observation", codes=codes("loinc", "4548-4")),
        ],
        output="cohort_size",
        record_types=["conditions", "medications", "observations"],
        observation_codes=codes("loinc", "4548-4"),
    )


def r07() -> QuerySpec:
    from datetime import date

    return QuerySpec(
        unit="encounter",
        encounter_scope=EncounterScope(types=["inpatient"], start_from=date(2025, 1, 1), start_to=date(2025, 12, 31)),
        group_by=[Dimension(kind="region")],
        metrics=[CountMetric(kind="count", name="inpatient_stays", label="Inpatient stays")],
    )


def r08() -> QuerySpec:
    bmi = codes("loinc", "39156-5")
    return QuerySpec(
        population=[
            ConditionCriterion(kind="condition", codes=codes("icd10", "C50")),
            SexCriterion(kind="sex", value="female"),
        ],
        group_by=[Dimension(kind="region")],
        metrics=[
            CountMetric(
                kind="count",
                name="women_with_bmi",
                label="Women with a BMI",
                where=[ObservationCriterion(kind="observation", codes=bmi)],
            ),
            MeanMetric(kind="mean", name="mean_bmi", label="Mean BMI", codes=bmi),
        ],
    )


def r09() -> QuerySpec:
    return QuerySpec(
        population=[ADULT, ConditionCriterion(kind="condition", codes=codes("icd10", "I10"))],
        group_by=[
            Dimension(
                kind="age_band",
                bands=[
                    AgeBand(label="18-49", min=18, max=49),
                    AgeBand(label="50-64", min=50, max=64),
                    AgeBand(label="65+", min=65),
                ],
            )
        ],
        metrics=[
            CountMetric(kind="count", name="adults_with_hypertension", label="Adults with hypertension"),
            CountMetric(
                kind="count",
                name="ace_count",
                label="With active ACE inhibitor",
                display=False,
                where=[MedicationCriterion(kind="medication", codes=codes("atc", "C09AA"), active_only=True)],
            ),
            CountMetric(
                kind="count",
                name="arb_count",
                label="With active ARB",
                display=False,
                where=[MedicationCriterion(kind="medication", codes=codes("atc", "C09CA"), active_only=True)],
            ),
            PercentMetric(
                kind="percent",
                name="ace_inhibitor_pct",
                label="ACE inhibitor (%)",
                numerator="ace_count",
                denominator="adults_with_hypertension",
            ),
            PercentMetric(
                kind="percent",
                name="arb_pct",
                label="ARB (%)",
                numerator="arb_count",
                denominator="adults_with_hypertension",
            ),
        ],
    )


def r10() -> QuerySpec:
    bands = [AgeBand(label=f"{lo}-{lo + 9}", min=lo, max=lo + 9) for lo in range(0, 90, 10)]
    bands.append(AgeBand(label="90+", min=90))
    return QuerySpec(
        population=[ConditionCriterion(kind="condition", codes=codes("icd10", "J44"))],
        group_by=[Dimension(kind="region"), Dimension(kind="age_band", bands=bands)],
        metrics=[CountMetric(kind="count", name="copd_patients", label="Patients with COPD")],
    )


def heart_failure_by_holder() -> QuerySpec:
    return QuerySpec(
        population=[ConditionCriterion(kind="condition", codes=codes("icd10", "I50"))],
        group_by=[Dimension(kind="data_holder")],
        metrics=[CountMetric(kind="count", name="hf_patients", label="Patients with heart failure")],
    )


def hip_fracture_stays() -> QuerySpec:
    return QuerySpec(
        unit="encounter",
        encounter_scope=EncounterScope(types=["inpatient"], primary_icd10=codes("icd10", "S72")),
        metrics=[CountMetric(kind="count", name="stays", label="Inpatient stays with S72 primary diagnosis")],
    )

