import json

import pytest

from accessdesk.cases import CaseRegistry
from accessdesk.config import build_desk


@pytest.fixture
def cases(data_dir, tmp_path):
    desk = build_desk(data_dir, runtime_dir=tmp_path / "runtime")
    try:
        yield CaseRegistry(desk, data_dir)
    finally:
        desk.store.con.close()


def test_case_registry_loads_official_and_demo_cases(cases):
    summaries = cases.list()

    assert len(summaries) == 14
    by_id = {summary["id"]: summary for summary in summaries}
    assert by_id["R02"]["decision"] == "REJECT"
    assert by_id["R02"]["status"] == "auto_decided"
    assert by_id["R05"]["decision"] == "APPROVE_SPE"
    assert by_id["R05"]["status"] == "auto_decided"
    assert by_id["D03"]["status"] == "held_identity"
    assert by_id["D04"]["status"] == "review_needed"
    assert len(by_id["R01"]["five_safes"]) == 5


def test_case_registry_filters_and_searches(cases):
    assert {case["id"] for case in cases.list(decision="REJECT")} == {
        "R02", "R04", "R06", "R10",
    }
    assert {case["id"] for case in cases.list(group="demo")} == {
        "D01", "D02", "D03", "D04",
    }
    assert [case["id"] for case in cases.list(q="Sophie")] == ["R01"]
    assert {case["id"] for case in cases.list(status="review_needed")} == {"D04"}


def test_review_is_persisted_audited_and_last_action_wins(cases):
    with pytest.raises(ValueError, match="20"):
        cases.review("R01", "hold", "Too short", "Reviewer")

    cases.review("R01", "hold", "Needs an additional staff review.", "Reviewer")
    assert cases.get("R01")["summary"]["status"] == "review_needed"
    assert not cases.get("R01")["visible_to_applicant"]
    cases.review("R01", "release", "Review is complete and the release is approved.", "Reviewer")
    assert cases.get("R01")["summary"]["status"] == "released"
    assert cases.get("R01")["visible_to_applicant"]
    assert cases.desk.audit.verify()["ok"]

    restored = CaseRegistry(cases.desk, cases.data_dir)
    assert restored.get("R01")["summary"]["status"] == "released"
    assert len(restored.get("R01")["reviews"]) == 2


def test_custom_submission_ignores_client_id_and_survives_restart(cases):
    request = {
        "id": "client-chosen",
        "applicant": {"name": "Sarah Novak", "organisation": "Nordic Pouch Company", "country": "SE"},
        "requested_as": "health data request",
        "purpose": "We develop new nicotine pouch flavours and market the product.",
        "question": "How many patients have COPD?",
        "definitions": ["COPD = an ICD-10 code starting with J44."],
    }
    summary = cases.submit(request, login="Sarah Novak")

    assert summary["id"] == "U01"
    assert summary["group"] == "custom"
    assert summary["submitted"]
    persisted = json.loads((cases.root / "submissions" / "U01.json").read_text(encoding="utf-8"))
    assert persisted == {"request": {**request, "id": "U01", "submitted": summary["submitted"]}, "login": "Sarah Novak"}

    restored = CaseRegistry(cases.desk, cases.data_dir)
    assert restored.get("U01")["summary"]["group"] == "custom"
    assert restored.get("U01")["login"] == "Sarah Novak"


def test_staff_rejection_overrides_the_effective_decision(cases):
    cases.review("R01", "reject", "The requested purpose needs a separate legal review.", "Reviewer")
    case = cases.get("R01")

    assert case["summary"]["status"] == "rejected_after_review"
    assert case["result"]["decision"]["decision"] == "REJECT"
    assert case["result"]["decision"]["articles"] == ["54"]
    assert case["result"]["decision"]["reason_en"] == "The requested purpose needs a separate legal review."
    assert case["result"]["decision"]["articles_detail"][0]["n"] == "54"
    assert not case["visible_to_applicant"]
