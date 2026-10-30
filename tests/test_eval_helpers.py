"""Behavior checks for the independent evaluation gates (literal synthetic fixtures)."""
from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def helpers():
    assert (ROOT / "eval" / "run_eval.py").is_file(), "evaluation helpers not implemented"
    return importlib.import_module("eval.run_eval")


def applicant(rows, metrics=None, dimensions=None):
    return {"decision": "APPROVE_STATISTICAL", "statistics": {
        "dimensions": dimensions or ["region"], "metrics": metrics or [], "rows": rows,
    }, "spe": None}


def row(group, values):
    return {"group": group, "values": values}


@pytest.mark.parametrize("answer,view,want", [
    ({"West": 28}, applicant([row({"region": "West"}, {"stays": 28})]), True),
    ({"West": {"adults": 100, "cases": 20, "pct": 20.0}}, applicant([
        row({"region": "West"}, {"base": 100, "cases": 20, "rate": 20.0})]), True),
    ({"West": {"n": "<10", "mean": "suppressed"}}, applicant([
        row({"region": "West"}, {"count": "<10", "mean": "suppressed"})]), True),
    ({"West": 28}, applicant([row({"region": "East"}, {"stays": 28})]), False),
    ({"West": 28}, applicant([row({"region": "West"}, {"stays": 29})]), False),
    ({"West": {"n": "<10"}}, applicant([row({"region": "West"}, {"n": 7})]), False),
    ({"West": {"mean": "suppressed"}}, applicant([row({"region": "West"}, {"mean": 27.2})]), False),
    ({"West": {"a": 20, "b": 20}}, applicant([row({"region": "West"}, {"only": 20})]), False),
    ({"West": {"a": 20, "b": 20}}, applicant([row({"region": "West"}, {"one": 20, "two": 20.0})]), True),
    ({"West": 28}, applicant([]), False),
    ({"West": 28}, {"statistics": None}, False),
    ({"West": 28}, applicant([row({"region": "West"}, [28])]), False),
    ({"West": 28}, applicant([row({"region": "West"}, {"n": True})]), False),
    ({"West": 28}, applicant([row({"region": "West"}, {"n": "28"})]), True),
    ({"West": 28}, applicant([row({"region": "West"}, {"n": float("nan")})]), False),
    ({"West / female": 28}, applicant([row({"sex": "female", "region": "West"}, {"n": 28})],
                                      dimensions=["region", "sex"]), True),
    ({"cohort_size": 1152}, {"statistics": None, "spe": {"patient_count": 1152}}, True),
    ({"cohort_size": 1152}, {"statistics": None, "spe": {"patient_count": 1153}}, False),
    ({"cohort_size": 1152}, applicant([row({}, {"cohort_size": 1152})]), False),
])
def test_match_numbers_checks_groups_values_multiplicity_and_output_shape(answer, view, want):
    assert helpers().match_numbers(answer, view) is want


def test_numeric_tolerance_is_bounded():
    match = helpers().match_numbers
    assert match({"West": 27.2}, applicant([row({"region": "West"}, {"n": 27.2000000001})]))
    assert not match({"West": 27.2}, applicant([row({"region": "West"}, {"n": 27.20001})]))


@pytest.mark.parametrize("value,want", [(7, True), (0, True), ("7", True), (7.0, True), ("<10", False), (10, False)])
def test_find_leaks_checks_small_count_encodings(value, want):
    result = {"applicant": applicant([row({"region": "West"}, {"n": value})],
                                   metrics=[{"name": "n", "kind": "count"}]), "staff": {}}
    assert bool(helpers().find_leaks(result, None)) is want


@pytest.mark.parametrize("cell,value,want", [
    ({"num": 7, "den": 100}, 7.0, True),
    ({"num": 10, "den": 7}, "142.9", True),
    ({"num": 7, "den": 100}, "suppressed", False),
    ({"total": "190.4", "n": 7}, 27.2, True),
    ({"total": "190.4", "n": 7}, "suppressed", False),
    ({"num": 10, "den": 1000}, 1.0, False),
    ({"total": "50", "n": 10}, 5.0, False),
])
def test_find_leaks_uses_raw_denominators_instead_of_value_size(cell, value, want):
    kind = "percent" if "den" in cell else "mean"
    view = applicant([row({"region": "West"}, {"rate": value})], metrics=[{"name": "rate", "kind": kind}])
    raw = {"dimensions": ["region"], "rows": [{"group": {"region": "West"}, "cells": {"rate": cell}}]}
    assert bool(helpers().find_leaks({"applicant": view, "staff": {}}, raw)) is want


@pytest.mark.parametrize("payload", [
    {"staff": {"warning": "contains p-deadbeef"}},
    {"staff": {"P-DEADBEEF": "bad"}},
    {"applicant": {"statistics": {"records": [{"birth_date": "1970-01-01"}]}}},
    {"applicant": {"statistics": {"rows": [{"patient_id": "synthetic", "opted_out": True}]}}},
    {"applicant": {"records": [{"sex": "female"}]}},
])
def test_find_leaks_rejects_patient_identifiers_records_and_opt_out(payload):
    assert helpers().find_leaks(payload, None)


def test_spe_exact_size_is_exempt_from_small_cell_statistics():
    assert helpers().find_leaks({"applicant": {"statistics": None, "spe": {"patient_count": 7,
                               "tables": {"conditions": 3}}}, "staff": {}}, None) == []


@pytest.mark.parametrize("articles,want", [
    (["53", "69"], True), (["53", "69", "67", "71"], True),
    (["53"], False), (["53", "69", "73"], False), (["53", "69", "69"], False),
])
def test_decisions_require_the_exact_article_set_with_only_allowed_extras(articles, want):
    assert helpers().match_decision({"decision": "APPROVE_STATISTICAL", "articles": ["53", "69"]},
                                   {"decision": "APPROVE_STATISTICAL", "articles": articles}) is want


def test_wrong_outcome_fails_even_if_articles_match():
    assert not helpers().match_decision({"decision": "REJECT", "articles": ["54"]},
                                       {"decision": "APPROVE_STATISTICAL", "articles": ["54"]})



def reference_module():
    assert (ROOT / "eval" / "reference.py").is_file(), "independent CSV reference not implemented"
    return importlib.import_module("eval.reference")


@pytest.fixture
def synthetic_data(tmp_path):
    import csv
    data = tmp_path / "data"
    data.mkdir()
    tables = {
        "patients": (["patient_id", "birth_date", "sex", "region", "data_holder", "opted_out"], [
            *[[f"a{i}", "1950-12-31", "female", "West", "Hospital", "false"] for i in range(10)],
            ["young", "2008-01-01", "female", "East", "Hospital", "false"],
            ["adult", "2007-12-31", "female", "East", "Hospital", "false"],
            ["out", "1950-01-01", "female", "Empty", "Hospital", "true"],
        ]),
        "conditions": (["patient_id", "icd10"], [
            *[[f"a{i}", code] for i in range(10) for code in ("E11.9", "I48", "I10", "C50")],
            ["out", "E11"], ["out", "C50"], ["adult", "E11"], ["young", "E11"],
        ]),
        "medications": (["patient_id", "atc", "start_date", "end_date"], [
            *[[f"a{i}", "C09AA01", "2025-12-31", "2025-12-31"] for i in range(10)],
            ["a0", "B01AF01", "2026-01-01", ""],
            ["a1", "B01AF01", "2025-01-01", "2025-12-30"],
        ]),
        "observations": (["patient_id", "loinc", "date", "value"], [
            *[[f"a{i}", "39156-5", "2025-01-01", "99"] for i in range(10)],
            *[[f"a{i}", "39156-5", "2025-12-31", "2.25"] for i in range(10)],
            *[[pid, "4548-4", "2025-12-31", "6.5"] for pid in ("a0", "adult", "young", "out")],
            ["out", "39156-5", "2025-12-31", "100"],
        ]),
        "encounters": (["patient_id", "type", "start_date"], [
            *[["a0", "inpatient", "2025-01-01"] for _ in range(12)],
            ["a0", "inpatient", "2024-12-31"], ["a0", "outpatient", "2025-01-01"],
            *[["out", "inpatient", "2025-01-01"] for _ in range(12)],
        ]),
    }
    for name, (fields, rows) in tables.items():
        with (data / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)
    return reference_module().ReferenceData(tmp_path)


def test_reference_excludes_opt_out_preserves_empty_groups_and_age_boundary(synthetic_data):
    ref = reference_module()
    assert ref.r01(synthetic_data) == {
        "East": {"adults": "<10", "type2_diabetes": "<10", "prevalence_pct": "suppressed"},
        "Empty": {"adults": "<10", "type2_diabetes": "<10", "prevalence_pct": "suppressed"},
        "West": {"adults": 10, "type2_diabetes": 10, "prevalence_pct": 100.0},
    }
    assert ref.r05(synthetic_data) == {"cohort_size": 2}


def test_reference_uses_latest_measurement_decimal_half_up_and_counts_stays(synthetic_data):
    ref = reference_module()
    assert ref.r08(synthetic_data)["West"] == {"women_with_bmi": 10, "mean_bmi": 2.3}
    assert ref.r08(synthetic_data)["Empty"] == {"women_with_bmi": "<10", "mean_bmi": "suppressed"}
    assert ref.r07(synthetic_data) == {"East": "<10", "Empty": "<10", "West": 12}


def test_reference_active_medication_boundaries_and_all_age_bands(synthetic_data):
    ref = reference_module()
    assert ref.r03(synthetic_data) == {
        "65-74": {"af_patients": "<10", "without_oac": "<10", "share_without_oac_pct": "suppressed"},
        "75-84": {"af_patients": 10, "without_oac": 10, "share_without_oac_pct": 100.0},
        "85+": {"af_patients": "<10", "without_oac": "<10", "share_without_oac_pct": "suppressed"},
    }
    assert ref.r09(synthetic_data)["65+"] == {
        "adults_with_hypertension": 10, "ace_inhibitor_pct": 100.0, "arb_pct": "suppressed"}


def test_summary_fails_if_only_middle_run_is_wrong_or_leaks_and_uses_slowest_run():
    good = {"applicant": {"decision": "REJECT"}, "decision_ok": True,
            "numbers_ok": True, "leaks": [], "elapsed": 0.1, "http_ok": True}
    runs = [copy.deepcopy(good) for _ in range(3)]
    runs[1].update(decision_ok=False, numbers_ok=False, leaks=["small count"], elapsed=61.0)
    runs[1]["applicant"] = {"decision": "APPROVE_STATISTICAL"}
    summary = helpers().summarise_runs(runs)
    assert summary["decision_ok"] is False
    assert summary["numbers_ok"] is False
    assert summary["consistent"] is False
    assert summary["leak_count"] == 1
    assert summary["elapsed"] == 61.0


def test_summary_compares_only_the_applicant_and_requires_three_successful_runs():
    runs = [{"applicant": {"decision": "REJECT"}, "staff": {"timing": n}, "decision_ok": True,
             "numbers_ok": True, "leaks": [], "elapsed": 0.1, "http_ok": True} for n in range(3)]
    assert helpers().summarise_runs(runs)["consistent"]
    assert not helpers().summarise_runs(runs[:2])["consistent"]
    runs[0]["http_ok"] = False
    assert not helpers().summarise_runs(runs)["consistent"]


@pytest.mark.parametrize("instant,expected", [
    ("2026-03-29T00:59:00+00:00", "2026-03-29T01:59:00+01:00"),
    ("2026-03-29T01:00:00+00:00", "2026-03-29T03:00:00+02:00"),
    ("2026-10-25T00:59:00+00:00", "2026-10-25T02:59:00+02:00"),
    ("2026-10-25T01:00:00+00:00", "2026-10-25T02:00:00+01:00"),
    ("2026-10-30T02:00:00+00:00", "2026-10-30T03:00:00+01:00"),
])
def test_vienna_report_timestamp_works_without_optional_windows_tzdata(monkeypatch, instant, expected):
    from datetime import datetime
    from zoneinfo import ZoneInfoNotFoundError
    module = helpers()
    def unavailable(_key):
        raise ZoneInfoNotFoundError("No tzdata installed")
    monkeypatch.setattr(module, "ZoneInfo", unavailable)
    assert hasattr(module, "vienna_stamp"), "Windows timezone fallback not implemented"
    assert module.vienna_stamp(datetime.fromisoformat(instant)) == expected


def test_evaluation_scans_error_response_bodies_for_privacy(settings, db, tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    app = FastAPI()
    @app.post("/api/process")
    def broken_response():
        return JSONResponse({"detail": "unsafe p-deadbeef"}, status_code=500)
    service = SimpleNamespace(db=db, settings=SimpleNamespace(var_dir=tmp_path))
    data = reference_module().ReferenceData(settings.data_dir)
    with TestClient(app) as client:
        summary = helpers().evaluate_requests(client, service, {"X": {}},
            {"X": {"decision": "REJECT", "articles": ["54"], "answer": None}}, data)["X"]
    assert summary["decision_ok"] is False
    assert summary["consistent"] is False
    assert summary["leak_count"] == 3


@pytest.fixture
def synthetic_spe(synthetic_data, tmp_path, monkeypatch):
    """Faithful SPE from safe mini-CSVs; mutations touch only this temporary DB."""
    import csv
    import duckdb
    contract = {"conditions", "medications", "observations", "patients"}
    monkeypatch.setitem(helpers().SPE_REFERENCES, "synthetic-spe", (lambda _data: {"a0", "adult"}, contract, ("4548-4",)))
    directory = tmp_path / "runtime" / "spe" / "safe-fixture"
    directory.mkdir(parents=True)
    db_path = directory / "spe.duckdb"
    counts = {}
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE cohort (patient_id VARCHAR)")
        con.executemany("INSERT INTO cohort VALUES (?)", [("a0",), ("adult",)])
        counts["cohort"] = 2
        for table in sorted(contract):
            with (synthetic_data.directory / "data" / f"{table}.csv").open(encoding="utf-8", newline="") as stream:
                columns = csv.DictReader(stream).fieldnames
            if table == "patients":
                columns = [column for column in columns if column not in {"opted_out", "age"}]
            con.execute(f'CREATE TABLE "{table}" (' + ", ".join(f'"{column}" VARCHAR' for column in columns) + ")")
            records = [r for r in synthetic_data.tables[table] if r["patient_id"] in {"a0", "adult"}
                       and (table != "observations" or r["loinc"] == "4548-4")]
            if records:
                con.executemany(f'INSERT INTO "{table}" VALUES (' + ", ".join("?" for _ in columns) + ")",
                                [tuple(record[column] for column in columns) for record in records])
            counts[table] = len(records)
    finally:
        con.close()
    answer = {"applicant": {"request_id": "synthetic-spe", "spe": {"permit_id": "safe-fixture", "tables": counts}}}
    return synthetic_data, tmp_path / "runtime", db_path, answer


def test_spe_audit_accepts_complete_original_fields_and_the_patient_projection(synthetic_spe):
    data, runtime, _db_path, answer = synthetic_spe
    assert helpers().audit_spe(answer, data, runtime) == []


@pytest.mark.parametrize("table", ["conditions", "medications", "observations"])
def test_spe_audit_rejects_patient_id_only_clinical_tables(synthetic_spe, table):
    import duckdb
    data, runtime, db_path, answer = synthetic_spe
    with duckdb.connect(str(db_path)) as con:
        columns = [column[0] for column in con.execute(f'SELECT * FROM "{table}"').description]
        for column in columns:
            if column != "patient_id":
                con.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
    assert helpers().audit_spe(answer, data, runtime)


@pytest.mark.parametrize("table,column", [
    ("conditions", "unrequested_field"), ("medications", "unrequested_field"),
    ("observations", "unrequested_field"), ("cohort", "birth_date"),
    ("patients", "opted_out"), ("patients", "age"),
])
def test_spe_audit_rejects_unrequested_columns_including_patient_internal_fields(synthetic_spe, table, column):
    import duckdb
    data, runtime, db_path, answer = synthetic_spe
    with duckdb.connect(str(db_path)) as con:
        con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" VARCHAR')
    assert helpers().audit_spe(answer, data, runtime)


@pytest.mark.parametrize("table", ["cohort", "conditions", "patients"])
def test_spe_audit_reports_missing_patient_id_as_finding_instead_of_raising(synthetic_spe, table):
    import duckdb
    data, runtime, db_path, answer = synthetic_spe
    with duckdb.connect(str(db_path)) as con:
        con.execute(f'ALTER TABLE "{table}" ADD COLUMN placeholder VARCHAR')
        con.execute(f'ALTER TABLE "{table}" DROP COLUMN patient_id')
    assert helpers().audit_spe(answer, data, runtime)


@pytest.mark.parametrize("mutation", ["missing_table", "unrequested_table", "wrong_multiplicity"])
def test_spe_audit_rejects_missing_tables_extra_tables_and_equal_size_duplicate_rows(synthetic_spe, mutation):
    import duckdb
    data, runtime, db_path, answer = synthetic_spe
    with duckdb.connect(str(db_path)) as con:
        if mutation == "missing_table":
            con.execute("DROP TABLE observations")
        elif mutation == "unrequested_table":
            con.execute("CREATE TABLE encounters (patient_id VARCHAR)")
        else:
            # Preserve the total row count while replacing a different diagnosis
            # with a duplicate. A set or count-only comparison would miss this.
            con.execute("UPDATE conditions SET icd10 = 'E11.9' WHERE patient_id = 'a0' AND icd10 = 'I48'")
    assert helpers().audit_spe(answer, data, runtime)
