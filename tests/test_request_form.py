"""Pure form logic behind the new-request page, exercised in Node, plus its templates against the real parser."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ehds_desk.models import AccessRequest
from ehds_desk.parsing.rules import parse_rules
from ehds_desk.terminology import Terminology

SCRIPT = (Path(__file__).resolve().parents[1] / "web" / "request-form.js").as_posix()
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")

FIELDS = {
    "name": " Dr. Sophie Lechner ",
    "organisation": "Danube Institute",
    "country": "at",
    "kind": "statistics",
    "purpose": " We study regional differences. ",
    "question": "How many adults have diabetes?",
    "definitions": ["Adult = aged 18 or older on 31 December 2025", "  ", "Report per region: adults."],
}
META = {"id": "NEW-1", "submitted": "2026-10-30T12:00:00+00:00"}


def run(expression, **values):
    script = f"const m = require({json.dumps(SCRIPT)}); const v = {json.dumps(values)}; process.stdout.write(JSON.stringify({expression}));"
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(done.stdout)


def test_statistics_answers_become_a_health_data_request():
    built = run("m.buildRequest(v.fields, v.meta)", fields=FIELDS, meta=META)
    assert built == {
        "id": "NEW-1",
        "submitted": "2026-10-30T12:00:00+00:00",
        "applicant": {"name": "Dr. Sophie Lechner", "organisation": "Danube Institute", "country": "AT"},
        "requested_as": "health data request",
        "requested_format": "anonymised statistics",
        "purpose": "We study regional differences.",
        "question": "How many adults have diabetes?",
        "definitions": ["Adult = aged 18 or older on 31 December 2025.", "Report per region: adults."],
    }


def test_records_answers_become_an_access_application():
    built = run("m.buildRequest({...v.fields, kind: 'records'}, v.meta)", fields=FIELDS, meta=META)
    assert built["requested_as"] == "health data access application"
    assert built["requested_format"] == "pseudonymised records"


def test_blank_country_is_left_out():
    assert "country" not in run("m.buildRequest({...v.fields, country: ' '}, v.meta).applicant", fields=FIELDS, meta=META)


def test_built_request_passes_the_api_model():
    AccessRequest.model_validate(run("m.buildRequest(v.fields, v.meta)", fields=FIELDS, meta=META))


def test_lines_keep_their_own_closing_punctuation():
    built = run("m.buildRequest({...v.fields, definitions: ['What counts as adult?', 'Report per region: adults.']}, v.meta)", fields=FIELDS, meta=META)
    assert built["definitions"] == ["What counts as adult?", "Report per region: adults."]


def test_complete_answers_have_no_errors():
    assert run("m.validateFields(v.fields)", fields=FIELDS) == {}


def test_missing_answers_are_named():
    errors = run("m.validateFields({name: '', organisation: ' ', country: '', kind: 'statistics', purpose: '', question: '', definitions: ['  ']})")
    assert set(errors) == {"name", "organisation", "purpose", "question", "definitions"}


def test_records_require_a_stated_reason_only_through_the_purpose_hint():
    assert run("m.purposeHint('records')").startswith("Explain why anonymised statistics are not enough")
    assert run("m.purposeHint('statistics')") != run("m.purposeHint('records')")


def test_a_stored_request_fills_the_form():
    request = run("m.buildRequest({...v.fields, kind: 'records'}, v.meta)", fields=FIELDS, meta=META)
    fields = run("m.fieldsFromRequest(v.request)", request=request)
    assert fields == {
        "name": "Dr. Sophie Lechner",
        "organisation": "Danube Institute",
        "country": "AT",
        "kind": "records",
        "purpose": "We study regional differences.",
        "question": "How many adults have diabetes?",
        "definitions": ["Adult = aged 18 or older on 31 December 2025.", "Report per region: adults."],
    }


def test_a_partial_request_still_fills_the_form():
    fields = run("m.fieldsFromRequest({id: 'X'})")
    assert fields["name"] == "" and fields["kind"] == "statistics" and fields["definitions"] == [""]


def test_a_pasted_request_keeps_its_other_fields_through_the_form():
    base = {"id": "MY-ID", "submitted": "2026-01-01", "note": "keep", "applicant": {"name": "A", "organisation": "B", "email": "a@b.example"}, "requested_as": "health data request", "purpose": "P", "question": "Q", "definitions": ["Report per region: adults."]}
    built = run("m.buildRequest(m.fieldsFromRequest(v.base), {id: 'MY-ID', submitted: '2026-01-01'}, v.base)", base=base)
    assert built["note"] == "keep" and built["id"] == "MY-ID" and built["applicant"]["email"] == "a@b.example"


def test_form_answers_win_over_the_pasted_values():
    base = {"purpose": "old", "applicant": {"name": "old", "organisation": "old"}}
    built = run("m.buildRequest(v.fields, v.meta, v.base)", fields=FIELDS, meta=META, base=base)
    assert built["purpose"] == "We study regional differences." and built["applicant"]["name"] == "Dr. Sophie Lechner"


@pytest.mark.parametrize("request_json,expected", [
    ({"applicant": "someone"}, ["applicant"]),
    ({"definitions": "Report per region: adults."}, ["definitions"]),
    ({"definitions": [None, 5]}, ["definitions"]),
    ({"purpose": 7}, ["purpose"]),
    ({"applicant": {"name": 3}}, ["applicant"]),
])
def test_values_the_form_cannot_show_are_named(request_json, expected):
    assert run("m.formProblems(v.request)", request=request_json) == expected


def test_a_regular_request_has_no_form_problems():
    assert run("m.formProblems(m.buildRequest(v.fields, v.meta))", fields=FIELDS, meta=META) == []


@pytest.mark.parametrize("request_json,kind", [
    ({"requested_as": "Health  Data  Access  Application"}, "records"),
    ({"requested_as": "something else", "requested_format": "pseudonymised records"}, "records"),
    ({"requested_as": "something else", "requested_format": "anonymised statistics"}, "statistics"),
    ({"requested_as": "health data request", "requested_format": "pseudonymised records"}, "statistics"),
    ({}, "statistics"),
])
def test_kind_matches_the_server_classification(request_json, kind):
    assert run("m.fieldsFromRequest(v.request).kind", request=request_json) == kind


@pytest.mark.parametrize("country,valid", [("AT", True), ("at", True), ("", True), ("A", False), ("Austria", False), ("A1", False)])
def test_country_is_a_two_letter_code_or_empty(country, valid):
    errors = run("m.validateFields({...v.fields, country: v.country})", fields=FIELDS, country=country)
    assert ("country" not in errors) is valid


def test_new_ids_are_safe_and_prefixed():
    assert run("/^NEW-[A-Z0-9]+$/.test(m.newRequestId(1798000000000))") is True


def test_every_template_parses_completely(db):
    templates = run("m.TEMPLATES")
    assert {entry["label"] for entry in templates} >= {"Age", "Diagnosis", "Medication", "Age bands", "Latest measurement", "Hospital stays", "Report"}
    by_label = {entry["label"]: entry["text"] for entry in templates} | {
        "Report medication": "Report per region: patients with type 2 diabetes, % with an active statin.",
        "Report by age band": "Report per age band: patients with type 2 diabetes.",
        "Report measurement": "Report per region: patients with a HbA1c, mean HbA1c.",
        "Report stays": "Report per hospital: inpatient stays.",
    }
    terminology = Terminology(db)
    combinations = [
        ["Age", "Diagnosis", "Report"],
        ["Diagnosis", "Medication", "Report medication"],
        ["Diagnosis", "Age bands", "Report by age band"],
        ["Latest measurement", "Report measurement"],
        ["Hospital stays", "Report stays"],
    ]
    for names in combinations:
        definitions = [by_label[name] for name in names]
        request = AccessRequest(id="T", applicant={"name": "A", "organisation": "B"}, requested_as="health data request", purpose="Research on care.", question="How many?", definitions=definitions)
        _, report = parse_rules(request, terminology)
        assert report.complete, (names, report.not_understood)
