"""Task 14: request contracts and independent CSV references, with safe synthetic data."""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from eval import reference
from eval.run_eval import SPE_REFERENCES, evaluate_requests, match_decision
from ehds_desk.decision import assess_purpose, decide
from ehds_desk.models import AccessRequest
from ehds_desk.parsing import parse_rules
from ehds_desk.terminology import Terminology

EXTRA = Path(__file__).resolve().parents[1] / "requests" / "extra"
APPROVED = ["N01", "N02", "N03", "N05", "N06", "N07", "N08", "N10"]


def requests_and_expected():
    assert (EXTRA / "expected.json").is_file(), "Task 14 requests and expectations missing"
    expected = json.loads((EXTRA / "expected.json").read_text(encoding="utf-8"))
    requests = {key: json.loads((EXTRA / f"{key}.json").read_text(encoding="utf-8")) for key in expected}
    return requests, expected


def test_ten_extra_requests_have_fixed_decisions_and_independent_answers():
    requests, expected = requests_and_expected()
    assert set(requests) == {f"N{i:02}" for i in range(1, 11)}
    assert set(reference.EXTRA_REFERENCES) == set(APPROVED)
    for key, body in requests.items():
        request = AccessRequest.model_validate(body)
        assert request.id == key
        outcome = decide(request, assess_purpose(request))
        assert match_decision(expected[key], outcome.model_dump(mode="json") | {"decision": outcome.outcome})
        assert (expected[key]["answer"] is not None) == (key in APPROVED)
    assert expected["N04"]["articles"] == ["54"]
    assert expected["N09"]["articles"] == ["54"]
    assert expected["N06"]["articles"] == ["53", "66", "68", "73"]
    assert expected["N08"]["articles"] == ["53", "66", "69"]
    assert "marketing" not in requests["N04"]["purpose"].lower()
    assert not any(code in " ".join(requests["N03"]["definitions"]) for code in ("J45", "R03", "ICD", "ATC"))


@pytest.mark.parametrize("request_id", APPROVED)
def test_extra_approved_requests_parse_completely_without_id_dependence(request_id, db):
    requests, _ = requests_and_expected()
    request = AccessRequest.model_validate(requests[request_id] | {"id": "independent-new-id"})
    spec, report = parse_rules(request, Terminology(db))
    assert report.complete, report.not_understood
    assert spec is not None
    if request_id == "N06":
        assert spec.record_types == ["encounters"]
        assert spec.output == "cohort_size"
    if request_id == "N10":
        assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]
        assert not spec.population


@pytest.fixture
def extra_csv(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    patients = [
        *[{"patient_id": f"safe{i}", "birth_date": "1950-01-01", "sex": "female",
           "region": "West", "data_holder": "Home", "opted_out": "false"} for i in range(12)],
        {"patient_id": "excluded", "birth_date": "1950-01-01", "sex": "male",
         "region": "Empty", "data_holder": "Empty", "opted_out": "true"},
        {"patient_id": "young", "birth_date": "2025-12-31", "sex": "male",
         "region": "East", "data_holder": "Home", "opted_out": "false"},
    ]
    conditions = [{"patient_id": p["patient_id"], "icd10": code} for p in patients
                  for code in ("I50.9", "I50.9", "J45.9", "J44.9", "N18.3", "I63.9")]
    observations = [{"patient_id": p["patient_id"], "loinc": "62238-1", "date": date, "value": value}
                    for p in patients for date, value in (("2024-01-01", "99"), ("2025-12-31", "2.25"))]
    medications = [{"patient_id": f"safe{i}", "atc": "R03AK06", "start_date": "2025-12-31", "end_date": "2025-12-31"} for i in range(10)]
    medications += [
        {"patient_id": "safe10", "atc": "R03AK06", "start_date": "2026-01-01", "end_date": ""},
        {"patient_id": "safe11", "atc": "R03AK06", "start_date": "2025-01-01", "end_date": "2025-12-30"},
    ]
    encounters = [{"patient_id": "safe0", "data_holder": "Away", "type": "inpatient",
                   "start_date": "2024-01-01", "primary_icd10": "J18.9"} for _ in range(10)]
    encounters += [{"patient_id": "safe0", "data_holder": "Away", "type": "inpatient",
                    "start_date": "2025-12-31", "primary_icd10": "S72.0"} for _ in range(10)]
    encounters += [{"patient_id": pid, "data_holder": "Away", "type": kind,
                    "start_date": date, "primary_icd10": code}
                   for pid, kind, date, code in [
                       ("excluded", "inpatient", "2025-01-01", "J18"),
                       ("safe0", "outpatient", "2025-01-01", "J18"),
                       ("safe0", "inpatient", "2023-12-31", "J18"),
                       ("safe0", "inpatient", "2026-01-01", "J18"),
                       ("safe0", "inpatient", "2025-01-01", "I50")]]
    for name, rows in {"patients": patients, "conditions": conditions, "medications": medications,
                       "observations": observations, "encounters": encounters}.items():
        with (directory / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return reference.ReferenceData(tmp_path)


def test_reference_counts_encounters_at_the_encounter_holder_not_the_patient_holder(extra_csv):
    assert hasattr(reference, "n01"), "Independent pneumonia reference missing"
    assert reference.n01(extra_csv) == {"Away": 10, "Empty": "<10", "Home": "<10"}


@pytest.mark.parametrize("name,group", [("n02", "Home"), ("n08", "West")])
def test_reference_latest_egfr_distinct_patients_and_decimal_half_up(extra_csv, name, group):
    assert hasattr(reference, name), "Independent eGFR reference missing"
    answer = getattr(reference, name)(extra_csv)
    assert sorted(answer[group].values()) == [2.3, 13 if name == "n02" else 12]
    assert answer["Empty"] == {"patients_with_egfr": "<10", "mean_egfr": "suppressed"}


def test_reference_plain_text_asthma_uses_exact_active_combination_and_suppression(extra_csv):
    assert hasattr(reference, "n03"), "Independent asthma reference missing"
    assert reference.n03(extra_csv)["West"] == {"asthma_patients": 12, "active_combination_pct": 83.3}
    assert reference.n03(extra_csv)["Empty"] == {"asthma_patients": "<10", "active_combination_pct": "suppressed"}


def test_reference_copd_and_heart_failure_spe_exclude_opt_out(extra_csv):
    assert hasattr(reference, "n05") and hasattr(reference, "n06")
    assert reference.n05(extra_csv) == {"East": "<10", "Empty": "<10", "West": 12}
    assert reference.n06(extra_csv) == {"cohort_size": 13}
    assert SPE_REFERENCES["N06"] == (reference.n06_patient_ids, {"encounters"}, ())


def test_reference_multi_dimension_domains_keep_empty_cells_and_age_boundaries(extra_csv):
    assert hasattr(reference, "n07") and hasattr(reference, "n10")
    stroke = reference.n07(extra_csv)
    assert len(stroke) == 3 * 2 * 19
    assert stroke["West / female / 75-79"] == 12
    assert stroke["East / male / 0-4"] == "<10"
    assert all(value == "<10" for key, value in stroke.items() if key.startswith("Empty / "))
    hip = reference.n10(extra_csv)
    assert len(hip) == 2 * 4
    assert hip["female / 65-79"] == 10
    assert hip["male / 80+"] == "<10"


def test_all_extra_answers_match_original_csv_independently(settings):
    _, expected = requests_and_expected()
    assert set(reference.EXTRA_REFERENCES) == set(APPROVED)
    checks = reference.compare_references(reference.ReferenceData(settings.data_dir), expected, reference.EXTRA_REFERENCES)
    assert checks and all(checks.values()), checks


def test_all_extra_requests_pass_three_real_http_runs_and_spe_audit(settings, tmp_path):
    from fastapi.testclient import TestClient
    from ehds_desk.api import create_app
    from ehds_desk.pipeline import DeskService

    requests, expected = requests_and_expected()
    service = DeskService(settings=replace(settings, var_dir=tmp_path / "runtime", llm_mode="off", anthropic_api_key=None))
    data = reference.ReferenceData(settings.data_dir)
    with TestClient(create_app(service)) as client:
        summaries = evaluate_requests(client, service, requests, expected, data)
    safe_summary = {key: {field: item[field] for field in ("decision_ok", "numbers_ok", "consistent", "leak_count", "http_ok", "elapsed")}
                    for key, item in summaries.items()}
    assert all(item["decision_ok"] and item["numbers_ok"] and item["consistent"] and item["http_ok"]
               and item["leak_count"] == 0 and item["elapsed"] < 60 for item in safe_summary.values()), safe_summary


def test_extra_reference_module_has_only_standard_library_imports_and_expected_is_anonymised():
    import ast
    import re
    import sys

    tree = ast.parse(Path(reference.__file__).read_text(encoding="utf-8"))
    imported = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported.update(alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert imported <= sys.stdlib_module_names | {"__future__"}
    _, expected = requests_and_expected()
    assert not re.search(r"p-[0-9a-f]{8}", json.dumps(expected), re.I)
    for key, target in expected.items():
        assert set(target) == {"decision", "articles", "answer"}
        assert set(target["articles"]) <= ({"54"} if key in {"N04", "N09"} else {"53", "66", "68", "69", "73"})
    stroke = expected["N07"]["answer"]
    assert len(stroke) == 9 * 2 * 19
    assert sum(value == "<10" for value in stroke.values()) > len(stroke) / 2


def test_extra_report_shows_all_five_metrics_and_each_reference():
    from eval import run_eval

    assert hasattr(run_eval, "extra_report"), "Extra report lacks its five-metric summary"
    expected = {"A": {"decision": "APPROVE_STATISTICAL", "articles": ["53", "69"], "answer": {"West": 12}}}
    summary = {"A": {"decision_ok": True, "numbers_ok": True, "consistent": True,
                     "leak_count": 0, "elapsed": 0.125,
                     "applicant": {"decision": "APPROVE_STATISTICAL", "articles": ["53", "69", "71"]}}}
    report = "\n".join(run_eval.extra_report(summary, expected, {"A": True}))
    for name, value in (("Correct decisions", "1/1"), ("Correct numbers", "1/1"),
                        ("Privacy leaks (all runs)", "0"), ("Consistency (applicant JSON)", "1/1"),
                        ("Time to answer (slowest HTTP run)", "0.125 s")):
        assert f"| {name} | {value} |" in report
    assert "| A | PASS |" in report


@pytest.mark.parametrize("mutation", ["none", "patient_id_only", "changed_record"])
def test_extra_spe_auditor_uses_independent_encounter_columns_and_values(extra_csv, tmp_path, mutation):
    import duckdb
    from eval.run_eval import audit_spe

    runtime = tmp_path / "audit-runtime"
    folder = runtime / "spe" / "synthetic-extra"
    folder.mkdir(parents=True)
    cohort = reference.n06_patient_ids(extra_csv)
    selected = [row for row in extra_csv.tables["encounters"] if row["patient_id"] in cohort]
    columns = list(selected[0])
    with duckdb.connect(str(folder / "spe.duckdb")) as con:
        con.execute("CREATE TABLE cohort (patient_id VARCHAR)")
        con.executemany("INSERT INTO cohort VALUES (?)", [(pid,) for pid in cohort])
        con.execute("CREATE TABLE encounters (" + ", ".join(f'"{column}" VARCHAR' for column in columns) + ")")
        con.executemany("INSERT INTO encounters VALUES (" + ", ".join("?" for _ in columns) + ")",
                        [tuple(row[column] for column in columns) for row in selected])
        if mutation == "patient_id_only":
            for column in columns:
                if column != "patient_id":
                    con.execute(f'ALTER TABLE encounters DROP COLUMN "{column}"')
        elif mutation == "changed_record":
            con.execute("UPDATE encounters SET primary_icd10 = 'J99' WHERE rowid = 0")
    result = {"applicant": {"request_id": "N06", "spe": {"permit_id": "synthetic-extra",
               "patient_count": len(cohort), "tables": {"cohort": len(cohort), "encounters": len(selected)}}}}
    findings = audit_spe(result, extra_csv, runtime)
    assert (not findings) == (mutation == "none")
