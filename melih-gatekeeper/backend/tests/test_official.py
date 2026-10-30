import pathlib

import pytest
from conftest import ROOT, load

from app import compiler, metrics, pipeline, privacy
from app.parser import parse
from app.plan import QueryPlan

EXP = load("track/requests/expected.json")
IDS = sorted(EXP)


@pytest.mark.parametrize("rid", IDS)
def test_golden_plan_matches_expected(rid):
    plan = QueryPlan.model_validate_json((ROOT / f"fixtures/plans/{rid}.json").read_text())
    pub = privacy.publish(compiler.run(plan), {m.name for m in plan.measures if m.hidden})
    if EXP[rid]["answer"] and rid != "R05":
        assert metrics.values_match(EXP[rid]["answer"], pub)


@pytest.mark.parametrize("rid", IDS)
def test_parser_equals_golden(rid):
    req = load(f"track/requests/{rid}.json")
    r = parse(req)
    assert r.plan is not None and not r.unparsed and not r.unknown_terms
    assert all(r.coverage.get(i) for i in range(len(req["definitions"]))), r.coverage
    golden = QueryPlan.model_validate_json((ROOT / f"fixtures/plans/{rid}.json").read_text())
    a = privacy.publish(compiler.run(r.plan), {m.name for m in r.plan.measures if m.hidden})
    b = privacy.publish(compiler.run(golden), {m.name for m in golden.measures if m.hidden})
    assert metrics.values_match(b, a)


@pytest.mark.parametrize("rid", IDS)
def test_pipeline_decision(rid):
    d = pipeline.run_sync({**load(f"track/requests/{rid}.json"), "id": f"t{rid}"})
    dec = d["decision"]
    assert dec["outcome"] == EXP[rid]["decision"]
    assert metrics.articles_ok(EXP[rid]["articles"], dec["articles"])
    assert not dec["needs_review"], dec["review_reasons"]
    if EXP[rid]["answer"]:
        assert metrics.values_match(EXP[rid]["answer"], d["result"]["answer"])
    if dec["outcome"] == "REJECT":
        assert d["result"] is None and d["plan"] is None  # rejected before any data access


def test_spe_r05_minimised_and_no_opt_outs():
    import duckdb
    from app import db, spe
    d = pipeline.run_sync({**load("track/requests/R05.json"), "id": "tspe05"})
    assert d["result"]["cohort_size"] == 1152
    con = duckdb.connect(str(spe.SPE_DIR / "tspe05.duckdb"), read_only=True)
    tables = {r[0] for r in con.execute("show tables").fetchall()}
    assert tables == {"patients", "conditions", "medications", "observations"}
    assert {r[0] for r in con.execute("select distinct loinc from observations").fetchall()} == {"4548-4"}
    ids = {r[0] for r in con.execute("select patient_id from patients").fetchall()}
    con.close()
    opted = set(db.query("select patient_id from raw.patients where opted_out = 'true'")["patient_id"])
    assert len(ids) == 1152 and not ids & opted


def test_consistency_three_runs():
    import json
    outs = {json.dumps(pipeline.run_sync({**load("track/requests/R08.json"), "id": f"tc{i}"})["result"]["answer"], sort_keys=True) for i in range(3)}
    assert len(outs) == 1
