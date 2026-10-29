from decimal import Decimal

import pytest

from ehds_desk import compiler, engine
from ehds_desk.data import REGIONS
from ehds_desk.disclosure import disclose_table
from ehds_desk.models import RawCount, RawMean, RawPercent
import specs


def by_group(table, key):
    return {r.group[key]: r for r in table.rows}


def test_r01_raw_counts(db):
    table, _ = engine.run_statistics(specs.r01(), db)
    rows = by_group(table, "region")
    assert table.dimensions == ["region"]
    assert rows["Burgenland"].cells["adults"] == RawCount(n=532)
    assert rows["Burgenland"].cells["type2_diabetes"] == RawCount(n=33)
    assert rows["Wien"].cells["adults"] == RawCount(n=3247)
    assert rows["Wien"].cells["type2_diabetes"] == RawCount(n=263)
    assert rows["Wien"].cells["prevalence_pct"] == RawPercent(num=263, den=3247)
    assert [r.group["region"] for r in table.rows] == list(REGIONS)
    disclosed = disclose_table(table)
    assert {r.group["region"]: r.values["prevalence_pct"] for r in disclosed.rows}["Wien"] == 8.1


def test_r03_age_bands_and_negated_active_med(db):
    table, _ = engine.run_statistics(specs.r03(), db)
    assert [r.group["age_band"] for r in table.rows] == ["65-74", "75-84", "85+"]
    disclosed = {r.group["age_band"]: r.values for r in disclose_table(table).rows}
    assert disclosed["65-74"] == {"af_patients": 81, "without_oac": 30, "share_without_oac_pct": 37.0}
    assert disclosed["75-84"] == {"af_patients": 154, "without_oac": 37, "share_without_oac_pct": 24.0}
    assert disclosed["85+"] == {"af_patients": 78, "without_oac": 22, "share_without_oac_pct": 28.2}


def test_r07_counts_encounters_not_patients(db):
    table, _ = engine.run_statistics(specs.r07(), db)
    rows = by_group(table, "region")
    assert rows["Wien"].cells["inpatient_stays"] == RawCount(n=245)
    assert rows["Burgenland"].cells["inpatient_stays"] == RawCount(n=28)


def test_r08_latest_bmi_mean(db):
    table, _ = engine.run_statistics(specs.r08(), db)
    rows = by_group(table, "region")
    noe = rows["Niederösterreich"].cells
    assert noe["women_with_bmi"] == RawCount(n=15)
    assert isinstance(noe["mean_bmi"], RawMean)
    assert isinstance(noe["mean_bmi"].total, Decimal)
    assert noe["mean_bmi"].n == 15
    disclosed = {r.group["region"]: r.values for r in disclose_table(table).rows}
    assert disclosed["Niederösterreich"] == {"women_with_bmi": 15, "mean_bmi": 27.2}
    assert disclosed["Burgenland"] == {"women_with_bmi": "<10", "mean_bmi": "suppressed"}
    assert disclosed["Wien"] == {"women_with_bmi": 14, "mean_bmi": 26.6}


def test_r09_percent_of_active_meds(db):
    table, _ = engine.run_statistics(specs.r09(), db)
    disclosed = {r.group["age_band"]: r.values for r in disclose_table(table).rows}
    assert disclosed["18-49"] == {"adults_with_hypertension": 359, "ace_inhibitor_pct": 39.6, "arb_pct": 33.4}
    assert disclosed["50-64"]["adults_with_hypertension"] == 1057
    assert disclosed["65+"]["adults_with_hypertension"] == 2046


def test_r05_cohort(db):
    spec = specs.r05()
    ids = engine.cohort_patient_ids(spec, db)
    assert len(ids) == 1152
    assert ids == sorted(set(ids))
    assert engine.opt_out_exclusions(spec, db) == 55


def test_empty_groups_are_present(db):
    table, _ = engine.run_statistics(specs.r10(), db)
    assert table.dimensions == ["region", "age_band"]
    assert len(table.rows) == 90
    zero_band = [r for r in table.rows if r.group["age_band"] == "0-9"]
    assert len(zero_band) == 9
    assert all(r.cells["copd_patients"] == RawCount(n=0) for r in zero_band)
    assert table.rows[0].group == {"region": "Burgenland", "age_band": "0-9"}
    assert table.rows[1].group == {"region": "Burgenland", "age_band": "10-19"}


def test_group_by_data_holder(db):
    table, _ = engine.run_statistics(specs.heart_failure_by_holder(), db)
    assert [r.group["data_holder"] for r in table.rows] == list(db.data_holders)
    assert len(table.rows) == 3
    assert sum(r.cells["hf_patients"].n for r in table.rows) > 0


def test_no_group_by_yields_single_row(db):
    table, _ = engine.run_statistics(specs.hip_fracture_stays(), db)
    assert table.dimensions == []
    assert len(table.rows) == 1
    assert table.rows[0].group == {}


def test_primary_icd10_encounter_filter(db):
    table, _ = engine.run_statistics(specs.hip_fracture_stays(), db)
    total = table.rows[0].cells["stays"].n
    expected = (
        db.cursor()
        .execute("SELECT count(*) FROM enc WHERE type = 'inpatient' AND primary_icd10 LIKE 'S72%'")
        .fetchone()[0]
    )
    assert total > 0
    assert total == expected


def test_sql_uses_parameters(db):
    q = compiler.compile_statistics(specs.r01(), data_holders=db.data_holders)
    assert "E11" not in q.sql
    assert "E11" in q.params
    assert "Wien" not in q.sql and "Wien" in q.params
    assert q.dimensions == ["region"]
    q3 = compiler.compile_statistics(specs.r03(), data_holders=db.data_holders)
    assert "B01AA" not in q3.sql and "65-74" not in q3.sql
    cohort = compiler.compile_cohort(specs.r05())
    assert "4548-4" not in cohort.sql and "4548-4" in cohort.params


def test_scope_all_uses_all_views(db):
    q = compiler.compile_statistics(specs.r01(), data_holders=db.data_holders, scope="all")
    assert "pat_all" in q.sql and "cond_all" in q.sql
    q = compiler.compile_statistics(specs.r01(), data_holders=db.data_holders)
    assert "_all" not in q.sql


@pytest.mark.parametrize("name", ["r01", "r03", "r08", "r09", "r10"])
def test_compiles_and_runs(db, name):
    table, _ = engine.run_statistics(getattr(specs, name)(), db)
    assert table.rows
