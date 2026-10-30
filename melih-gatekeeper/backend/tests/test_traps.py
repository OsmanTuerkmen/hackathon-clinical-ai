"""One test per data trap (T1-T12), through the real compiler."""
from app import compiler, db
from app.plan import Criterion, EncounterFilter, GroupBy, Measure, Population, QueryPlan


def total(plan):
    raw = compiler.run(plan)
    return raw.values[()][plan.measures[0].name]["value"]


def count(pop=None, unit="patients", ef=None):
    return total(QueryPlan(unit=unit, population=pop or Population(), encounter_filter=ef, measures=[Measure(name="n", kind="count")]))


def test_t1_opt_outs_excluded_everywhere():
    assert count() == 20000 - 839
    n_raw = int(db.query("select count(*) n from raw.medications")["n"][0])
    n_view = int(db.query("select count(*) n from hdab.medications")["n"][0])
    assert n_view < n_raw


def test_t2_age_boundary():
    assert count(Population(age_min=18)) == 14716


def test_t3_empty_end_date_is_active():
    statin = Criterion(source="medication", codes=["C10AA"], active_on="2025-12-31")
    assert count(Population(criteria=[statin])) == 1684


def test_t4_latest_not_any():
    t2d = Criterion(source="condition", codes=["E11"])
    latest = Criterion(source="observation", codes=["4548-4"], pick="latest", value_op=">", value=8)
    anyv = Criterion(source="observation", codes=["4548-4"], pick="any", value_op=">", value=8)
    assert count(Population(age_min=18, criteria=[t2d, latest])) == 251
    assert count(Population(age_min=18, criteria=[t2d, anyv])) == 509


def test_t5_started_vs_ended():
    assert count(unit="encounters", ef=EncounterFilter(types=["inpatient"], start_from="2025-01-01", start_to="2025-12-31")) == 1079
    assert count(unit="encounters", ef=EncounterFilter(types=["inpatient"], end_from="2025-01-01", end_to="2025-12-31")) == 1106


def test_t7_t8_main_diagnosis():
    assert count(unit="encounters", ef=EncounterFilter(types=["inpatient"], start_from="2025-01-01", start_to="2025-12-31", primary_icd10=["J18"])) == 91


def test_t10_empty_groups_present():
    plan = QueryPlan(population=Population(criteria=[Criterion(source="condition", codes=["J44"])]),
                     group_by=[GroupBy(dim="age_band", bands=["0-9", "10-19", "90+"])], measures=[Measure(name="n", kind="count")])
    raw = compiler.run(plan)
    assert [g[0] for g in raw.groups] == ["0-9", "10-19", "90+"]


def test_t11_other_active_date():
    statin = Criterion(source="medication", codes=["C10AA"], active_on="2025-06-30")
    assert count(Population(criteria=[statin])) == 1567


def test_sql_injection_rejected():
    import pytest
    with pytest.raises(ValueError):
        compiler.compile_sql(QueryPlan(population=Population(criteria=[Criterion(source="condition", codes=["E11'; drop table x; --"])]),
                                       measures=[Measure(name="n", kind="count")]))
    with pytest.raises(ValueError):
        compiler.compile_sql(QueryPlan(population=Population(regions=["Wien' or 1=1 --"]), measures=[Measure(name="n", kind="count")]))
