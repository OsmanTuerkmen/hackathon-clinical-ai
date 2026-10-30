"""Regression checks for complete interpretation before statistical or SPE release.

All requests below are synthetic. Replacing full-clause validation with a partial match
must fail these tests; no external request expectations or patient rows are copied.
"""

import dataclasses

import duckdb
import pytest

from ehds_desk.models import AccessRequest, Applicant
from ehds_desk.parsing import parse_rules
from ehds_desk.pipeline import DeskService, MANUAL_REVIEW_NOTE
from ehds_desk.terminology import Terminology

SPE_PURPOSE = (
    "Scientific research trains a prediction model. Training needs individual-level histories; "
    "aggregates are not enough."
)
COHORT = ["Cohort = adults.", "Report the size of the cohort you would make available."]


def request(question, definitions=None, *, access=True):
    return AccessRequest(
        id="SYNTHETIC-FINAL-PARSER",
        applicant=Applicant(name="Synthetic researcher", organisation="Test University"),
        requested_as="health data access application" if access else "health data request",
        requested_format="pseudonymised records" if access else "statistics",
        purpose=SPE_PURPOSE if access else "Scientific research.",
        question=question,
        definitions=COHORT if definitions is None else definitions,
    )


EXCLUSIONS = [
    ("Provide only encounters. Do not provide observations or medications.", {"observations", "medications"}),
    ("Provide only encounters, without medications.", {"medications"}),
    ("Provide observations. Do not provide observations.", {"observations"}),
    ("Provide encounters, excluding lab results.", {"observations"}),
    ("Provide only encounters and not medications.", {"medications"}),
]
COHORT_TAILS = [
    "Report the size of the cohort excluding patients in Vienna.",
    "Report the size of the cohort aged under 65.",
    "Report the size of the cohort. Do not include patients in Vienna.",
]
BAD_DIMENSIONS = [
    "hospital department", "region by year", "region and year", "hospital except Vienna",
    "age band by year", "sex within hospital department",
]
BAD_MEASUREMENTS = [
    "Provide observations for quux only.",
    "Provide labs for quux only.",
    "Provide observations (HbA1c above 8 only).",
    "Provide observations for HbA1c only recorded after 2024.",
    "Provide HbA1c observations above 8.",
    "Provide HbA1c observations without diabetes.",
    "Provide lab results for HbA1c and quux only.",
    "Provide observations for marker only.",
]


@pytest.fixture(scope="module")
def terminology(db):
    return Terminology(db)


@pytest.mark.parametrize("question,excluded", EXCLUSIONS)
def test_record_exclusions_never_become_positive_provisioning_types(terminology, question, excluded):
    spec, report = parse_rules(request(question), terminology)
    assert not report.complete
    assert spec is None or not (set(spec.record_types) & excluded)


def test_contradictory_only_records_require_manual_review(terminology):
    _, report = parse_rules(request("Provide only encounters. Also provide medications."), terminology)
    assert not report.complete


@pytest.mark.parametrize("sentence", COHORT_TAILS)
def test_cohort_size_does_not_consume_uninterpreted_restrictions(terminology, sentence):
    _, report = parse_rules(request("Provide encounters.", ["Cohort = adults.", sentence]), terminology)
    assert not report.complete
    assert sentence in report.not_understood


@pytest.mark.parametrize("dimension", BAD_DIMENSIONS)
def test_grouping_expression_must_be_fully_understood(terminology, dimension):
    _, report = parse_rules(request(
        "Count patients per hospital department.", [f"Report per {dimension}: patients."], access=False,
    ), terminology)
    assert not report.complete


@pytest.mark.parametrize("question", BAD_MEASUREMENTS)
def test_measurement_qualifiers_cannot_silently_release_all_observations(terminology, question):
    _, report = parse_rules(request(question), terminology)
    assert not report.complete


@pytest.mark.parametrize("question,definitions,want", [
    ("Provide observations for HbA1c only.", COHORT, ["4548-4"]),
    ("Provide lab results for HbA1c only.", COHORT, ["4548-4"]),
    ("Provide labs for HbA1c only.", COHORT, ["4548-4"]),
    ("Provide observations (HbA1c only).", COHORT, ["4548-4"]),
    ("Provide HbA1c observations only.", COHORT, ["4548-4"]),
    ("Provide observations for marker only.", ["Marker = LOINC 4548-4.", *COHORT], ["4548-4"]),
    ("Provide HbA1c and eGFR observations only.", COHORT, ["4548-4", "62238-1"]),
    ("Provide observations for HbA1c and eGFR only.", COHORT, ["4548-4", "62238-1"]),
])
def test_complete_measurement_requests_preserve_exact_codes(terminology, question, definitions, want):
    spec, report = parse_rules(request(question, definitions), terminology)
    assert report.complete, report.not_understood
    assert spec is not None and spec.record_types == ["observations"]
    assert spec.observation_codes is not None
    assert spec.observation_codes.prefixes == want


@pytest.mark.parametrize("dimension,kind", [
    ("hospital", "data_holder"), ("data holder", "data_holder"), ("data_holder", "data_holder"),
    ("sex", "sex"), ("gender", "sex"), ("region", "region"), ("5-year age band", "age_band"),
])
def test_supported_dimensions_still_parse_completely(terminology, dimension, kind):
    spec, report = parse_rules(request(
        "Count patients.", [f"Report per {dimension}: patients."], access=False,
    ), terminology)
    assert report.complete, report.not_understood
    assert [d.kind for d in spec.group_by] == [kind]


UNSAFE_REQUESTS = (
    [request(q) for q, _ in EXCLUSIONS]
    + [request("Provide only encounters. Also provide medications.")]
    + [request("Provide encounters.", ["Cohort = adults.", s]) for s in COHORT_TAILS]
    + [request(q) for q in BAD_MEASUREMENTS]
    + [request("Count patients.", [f"Report per {d}: patients."], access=False) for d in BAD_DIMENSIONS]
)


@pytest.mark.parametrize("req", UNSAFE_REQUESTS, ids=lambda r: r.question + " / " + r.definitions[-1])
def test_incomplete_interpretation_blocks_real_service_data_release(settings, tmp_path, req):
    service = DeskService(dataclasses.replace(settings, var_dir=tmp_path, llm_mode="off", anthropic_api_key=None))
    result = service.process(req)
    assert not result.staff.parse_report.complete
    assert result.applicant.statistics is None
    assert result.applicant.spe is None
    assert result.staff.sql is None
    assert MANUAL_REVIEW_NOTE in result.applicant.notes
    assert not list((tmp_path / "spe").glob("*/spe.duckdb"))


@pytest.mark.parametrize("question,table,code", [
    ("Provide only encounters.", "encounters", None),
    ("Provide observations for HbA1c only.", "observations", "4548-4"),
])
def test_accepted_spe_request_copies_only_requested_records(settings, tmp_path, question, table, code):
    service = DeskService(dataclasses.replace(settings, var_dir=tmp_path, llm_mode="off", anthropic_api_key=None))
    result = service.process(request(question))
    assert result.staff.parse_report.complete
    spe = result.applicant.spe
    assert spe is not None
    assert set(spe.tables) == {"cohort", table}
    with duckdb.connect(str(tmp_path / "spe" / spe.permit_id / "spe.duckdb"), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert tables == {"cohort", table}
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
        assert conn.execute(
            f"SELECT count(*) FROM {table} WHERE patient_id NOT IN (SELECT patient_id FROM cohort)"
        ).fetchone()[0] == 0
        if code:
            assert conn.execute("SELECT count(*) FROM observations WHERE loinc <> ?", [code]).fetchone()[0] == 0


@pytest.mark.parametrize("req", [r for r in UNSAFE_REQUESTS if "access application" in r.requested_as],
                         ids=lambda r: r.question + " / " + r.definitions[-1])
def test_explicit_scope_uncertainty_cannot_be_overridden_by_broader_llm(settings, tmp_path, req, monkeypatch):
    from ehds_desk.models import QuerySpec, PurposeAssessment
    from ehds_desk.parsing import llm

    # A schema-valid translation can still ignore an exclusion or measurement restriction.
    # Only the external translation boundary is fake; parsing, decisions and provisioning are real.
    broad = QuerySpec(population=[{"kind": "age", "min": 18}], output="cohort_size",
                      record_types=["encounters", "observations", "medications"])
    monkeypatch.setattr(llm, "parse_with_llm", lambda *args: (broad, PurposeAssessment(prohibited=[], permitted=[], spe_justification=[]), False))
    service = DeskService(dataclasses.replace(settings, var_dir=tmp_path, llm_mode="auto",
                                             anthropic_api_key="fake-no-network"))
    result = service.process(req)
    assert not result.staff.parse_report.complete
    assert result.applicant.spe is None
    assert result.applicant.statistics is None
    assert MANUAL_REVIEW_NOTE in result.applicant.notes
    assert not list((tmp_path / "spe").glob("*/spe.duckdb"))


@pytest.mark.parametrize("dimension,partial_kind", [
    ("hospital department", "data_holder"),
    ("region by year", "region"),
    ("region and year", "region"),
])
@pytest.mark.parametrize("path", ["report", "question"])
def test_unknown_grouping_scope_cannot_be_dropped_by_llm(
    settings, tmp_path, monkeypatch, dimension, partial_kind, path,
):
    from ehds_desk.models import QuerySpec, PurposeAssessment
    from ehds_desk.parsing import llm

    # Dropping department/year is schema-valid but changes the requested grouping.
    broad = QuerySpec(group_by=[{"kind": partial_kind}],
                      metrics=[{"kind": "count", "name": "patients", "label": "Patients"}])
    monkeypatch.setattr(llm, "parse_with_llm", lambda *args: (broad, PurposeAssessment(prohibited=[], permitted=[], spe_justification=[]), False))
    req = request(
        "Count patients." if path == "report" else f"How many patients per {dimension}?",
        [f"Report per {dimension}: patients."] if path == "report" else [],
        access=False,
    )
    service = DeskService(dataclasses.replace(settings, var_dir=tmp_path, llm_mode="auto",
                                             anthropic_api_key="fake-no-network"))
    result = service.process(req)
    assert not result.staff.parse_report.complete
    assert result.applicant.statistics is None
    assert result.applicant.spe is None
    assert result.staff.sql is None
    assert MANUAL_REVIEW_NOTE in result.applicant.notes
