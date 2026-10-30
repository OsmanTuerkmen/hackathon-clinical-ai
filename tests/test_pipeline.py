import dataclasses
import json
import os
import subprocess
import sys

import pytest

from ehds_desk.disclosure import PATIENT_ID_PATTERN, LeakError, assert_no_leak
from ehds_desk.models import AccessRequest, Applicant
from ehds_desk.pipeline import DeskService, ProcessResult

IDS = [f"R{i:02d}" for i in range(1, 11)]


@pytest.fixture(scope="module")
def service(settings, tmp_path_factory):
    isolated = dataclasses.replace(settings, var_dir=tmp_path_factory.mktemp("var"))
    return DeskService(isolated)


@pytest.fixture(scope="module")
def expected(settings):
    return json.loads((settings.data_dir / "requests" / "expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def results(service):
    return {rid: service.process(service.get_request(rid)) for rid in IDS}


def test_process_all_track3_requests(results, expected):
    for rid in IDS:
        result = results[rid]
        assert result.applicant.request_id == rid
        assert result.applicant.decision == expected[rid]["decision"], rid
        if result.applicant.decision == "REJECT":
            assert result.applicant.statistics is None and result.applicant.spe is None, rid
        assert result.applicant.headline and result.applicant.reasons
        assert set(result.applicant.article_titles) == set(result.applicant.articles)
    r05 = results["R05"].applicant
    assert r05.spe is not None and r05.spe.patient_count == 1152
    assert r05.spe.workspace_url == f"/spe/{r05.spe.permit_id}"
    assert r05.statistics is None
    r01 = results["R01"].applicant
    assert r01.statistics is not None and r01.spe is None and len(r01.statistics.rows) == 9


def test_process_is_reproducible(service):
    for rid in ("R01", "R05"):
        request = service.get_request(rid)
        dumps = {service.process(request).applicant.model_dump_json() for _ in range(3)}
        assert len(dumps) == 1, rid


def test_no_patient_ids_in_result(results):
    for rid, result in results.items():
        assert not PATIENT_ID_PATTERN.search(result.model_dump_json()), rid


def test_staff_view_contents(results):
    staff = results["R03"].staff
    assert staff.sql and "SELECT" in staff.sql.upper()
    assert staff.parse_report.mappings
    assert staff.opt_out_excluded is not None
    assert len(staff.trace) == 4
    assert staff.parser_source == "rules"
    assert staff.request_kind in ("statistics_request", "access_application")
    assert staff.spec is not None and staff.spec_summary
    assert set(staff.timings_ms) == {"parse", "decide", "compute", "total"}
    assert all(isinstance(v, int) for v in staff.timings_ms.values())


def test_staff_view_of_rejection_still_shows_query(results):
    staff = results["R02"].staff
    assert staff.spec is not None and staff.spec_summary
    assert staff.sql is None and staff.opt_out_excluded is None
    assert results["R02"].applicant.statistics is None


def test_spec_summary_is_readable(results):
    summary = results["R01"].staff.spec_summary
    assert "Unit: patients" in summary
    assert "Population: age ≥ 18" in summary
    assert any(line.startswith("Group by:") and "region" in line for line in summary)
    assert any(line.startswith("Metrics:") and "condition ICD-10 E11*" in line for line in summary)
    encounters = results["R07"].staff.spec_summary
    assert "Unit: encounters" in encounters
    assert any(line.startswith("Encounter scope:") and "inpatient" in line for line in encounters)


def test_spe_summary_lists_records(results):
    assert any("Records:" in line for line in results["R05"].staff.spec_summary)


def test_opt_out_is_disclosed_not_raw(results):
    value = results["R01"].staff.opt_out_excluded
    assert value == "<10" or (isinstance(value, int) and value >= 10)


def _gout_request(**overrides) -> AccessRequest:
    fields = dict(
        id="T-GOUT",
        applicant=Applicant(name="Dr. Test", organisation="Test University"),
        requested_as="health data request",
        requested_format="anonymised statistics",
        purpose="We study gout to plan public health prevention programmes.",
        question="How many adults have gout in each region?",
        definitions=[
            "Adult = aged 18 or older on 31 December 2025.",
            "Gout patients = patients with a gout diagnosis.",
            "Report per region: adults and gout patients.",
        ],
    )
    fields.update(overrides)
    return AccessRequest(**fields)


def test_unmappable_term_needs_review(service):
    result = service.process(_gout_request())
    assert result.applicant.decision == "APPROVE_STATISTICAL"
    assert result.applicant.statistics is None
    assert any("referred to staff for manual review" in n for n in result.applicant.notes)
    assert any("manual review" in w for w in result.staff.warnings)
    assert result.staff.sql is None
    assert result.staff.parse_report.not_understood


def test_incomplete_spe_request_is_not_provisioned(service):
    request = _gout_request(
        id="T-GOUT-SPE",
        requested_as="data access application",
        requested_format="pseudonymised records",
        purpose="We develop a gout prediction algorithm for scientific research. Anonymised statistics are not "
        "enough because the model needs record-level data to be trained.",
    )
    result = service.process(request)
    assert result.applicant.decision == "APPROVE_SPE"
    assert result.applicant.spe is None
    assert any("referred to staff for manual review" in n for n in result.applicant.notes)
    assert result.staff.warnings
    spe_dir = service.settings.var_dir / "spe"
    assert not [p.name for p in spe_dir.glob("T-GOUT-SPE*")]  # permit dirs are named <id>-<8 hex>


def test_list_requests(service, tmp_path):
    listed = service.list_requests()
    assert [r["id"] for r in listed if r["source"] == "track3"] == IDS
    first = listed[0]
    assert set(first) == {"id", "source", "organisation", "purpose", "requested_as"}
    assert first["organisation"].startswith("Danube Institute")


def test_list_requests_reads_extra_directory(settings, tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    base = _gout_request(id="X01")
    (extra / "X01.json").write_text(base.model_dump_json(), encoding="utf-8")
    svc = DeskService(dataclasses.replace(settings, var_dir=tmp_path), extra_dir=extra)
    listed = svc.list_requests()
    assert [r["id"] for r in listed if r["source"] == "extra"] == ["X01"]
    assert svc.get_request("X01").id == "X01"


def test_get_request_unknown(service):
    with pytest.raises(KeyError):
        service.get_request("R99")
    with pytest.raises(KeyError):
        service.get_request("../expected")


def test_cli_decide(settings, tmp_path):
    env = {**os.environ, "EHDS_VAR_DIR": str(tmp_path), "EHDS_LLM": "off", "PYTHONIOENCODING": "utf-8"}
    path = settings.data_dir / "requests" / "R01.json"
    proc = subprocess.run(
        [sys.executable, "-m", "ehds_desk", "decide", str(path)], capture_output=True, env=env, timeout=180
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    assert "APPROVE_STATISTICAL" in out
    assert json.loads(out)["request_id"] == "R01"
    assert "timings_ms" not in out
    staff = subprocess.run(
        [sys.executable, "-m", "ehds_desk", "decide", str(path), "--staff"],
        capture_output=True,
        env=env,
        timeout=180,
    )
    assert staff.returncode == 0
    assert "timings_ms" in json.loads(staff.stdout.decode("utf-8"))["staff"]


def test_cli_decide_missing_file(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "ehds_desk", "decide", str(tmp_path / "nope.json")], capture_output=True, timeout=60
    )
    assert proc.returncode != 0
    assert b"nope.json" in proc.stderr


def test_applicant_statistics_pass_leak_guard(results):
    for rid, result in results.items():
        assert_no_leak(result.applicant.statistics)  # raises LeakError on a count < 10 or a patient id


def test_spe_staff_view_shows_cohort_query(results):
    sql = results["R05"].staff.sql
    assert sql and "patient_id" in sql and "SELECT" in sql.upper()


def test_guard_blocks_patient_id(results):
    tainted = results["R01"].model_copy(deep=True)
    tainted.applicant.reasons.append("Contact record p-0123abcd for details.")
    with pytest.raises(LeakError):
        DeskService._guard(tainted)
    DeskService._guard(results["R01"])  # the untouched result passes
    assert isinstance(tainted, ProcessResult)


def test_guard_blocks_small_count_in_statistics(results):
    tainted = results["R01"].model_copy(deep=True)
    tainted.applicant.statistics.rows[0].values["adults"] = 3
    with pytest.raises(LeakError):
        DeskService._guard(tainted)
