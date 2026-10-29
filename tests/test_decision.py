import json

import pytest

from ehds_desk.decision import assess_purpose, decide, request_kind
from ehds_desk.law import ART53_POINTS, ART54_POINTS, ARTICLES
from ehds_desk.models import AccessRequest, Evidence, PurposeAssessment

REQUEST_IDS = [f"R{i:02d}" for i in range(1, 11)]


def load_request(settings, rid: str) -> AccessRequest:
    path = settings.data_dir / "requests" / f"{rid}.json"
    return AccessRequest.model_validate_json(path.read_text(encoding="utf-8"))


def make_request(
    purpose: str = "We carry out research on diabetes.",
    question: str = "How many adults have type 2 diabetes?",
    requested_as: str = "health data request",
    requested_format: str | None = None,
    definitions: list[str] | None = None,
    organisation: str = "Test Institute",
) -> AccessRequest:
    return AccessRequest(
        id="T01",
        applicant={"name": "A. Tester", "organisation": organisation, "country": "AT"},
        requested_as=requested_as,
        requested_format=requested_format,
        purpose=purpose,
        question=question,
        definitions=definitions if definitions is not None else ["Adult = aged 18 or older."],
    )


def categories(evidence: list[Evidence]) -> set[str]:
    return {e.category for e in evidence}


# --- law catalogue ----------------------------------------------------------


def test_law_catalogue_is_complete():
    assert set(ARTICLES) == {"53", "54", "66", "67", "68", "69", "71", "73"}
    for number, art in ARTICLES.items():
        assert art.number == number
        assert art.title and art.summary
    assert set(ART53_POINTS) == {f"53(1)({c})" for c in "abcdef"}
    assert set(ART54_POINTS) == {f"54({c})" for c in "abcde"}


# --- the ten real requests --------------------------------------------------


@pytest.mark.parametrize("rid", REQUEST_IDS)
def test_track3_requests_decide_as_expected(settings, rid):
    expected = json.loads((settings.data_dir / "requests" / "expected.json").read_text(encoding="utf-8"))[rid]
    request = load_request(settings, rid)
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == expected["decision"]
    assert set(decision.articles) - {"67", "71"} == set(expected["articles"])


def test_r06_hits_employment_and_reidentification(settings):
    assessment = assess_purpose(load_request(settings, "R06"))
    assert {"54(b)", "54(a)"} <= categories(assessment.prohibited)


def test_evidence_quote_is_the_sentence_with_the_match(settings):
    assessment = assess_purpose(load_request(settings, "R02"))
    quotes = [e.quote for e in assessment.prohibited if e.category == "54(b)"]
    assert quotes[0] == (
        "We want to align private health insurance premiums for customers with diabetes with their actual risk"
    )
    assert all(e.source == "rules" for e in assessment.prohibited)


def test_organisation_name_is_not_scanned():
    request = make_request(
        purpose="We study regional variation of diabetes.",
        organisation="Brightline Health Marketing and Advertising GmbH",
    )
    assert assess_purpose(request).prohibited == []


# --- prohibited-purpose rules -----------------------------------------------


def test_smoking_cessation_research_is_not_prohibited():
    request = make_request(
        purpose="We evaluate a nicotine replacement therapy programme that helps patients with COPD quit smoking."
    )
    assert assess_purpose(request).prohibited == []


def test_sales_rep_targeting_is_marketing():
    request = make_request(
        purpose="We want to plan visits of our sales representatives to high-prescribing physicians."
    )
    assert "54(c)" in categories(assess_purpose(request).prohibited)


def test_credit_scoring_is_prohibited():
    request = make_request(purpose="We want to improve our credit scoring for loan applicants using diagnoses.")
    assert "54(b)" in categories(assess_purpose(request).prohibited)


def test_neutral_research_has_no_prohibited_hit():
    assessment = assess_purpose(make_request(purpose="Research on diabetes to plan prevention."))
    assert assessment.prohibited == []
    assert categories(assessment.permitted) >= {"53(1)(a)", "53(1)(e)"}


# --- ladder steps -----------------------------------------------------------


def test_access_without_justification_is_step4():
    request = make_request(
        purpose="Research on hypertension treatment in general practice.",
        question="Provide pseudonymised records of adults with hypertension.",
        requested_as="health data access application",
        requested_format="pseudonymised records",
    )
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == "APPROVE_STATISTICAL"
    assert decision.articles == ["53", "66", "69", "71"]
    assert [s.status for s in decision.trace] == ["not_matched", "not_matched", "not_matched", "matched"]
    joined = " ".join(decision.reasons)
    assert "Art. 66(2)" in joined and "Art. 68(3)" in joined and "Art. 69" in joined
    assert "Art. 71" in joined
    assert "anonymised statistics" in joined


def test_access_with_justification_is_spe():
    request = make_request(
        purpose="We train a prediction model for research. Aggregates are not enough for this.",
        requested_as="health data access application",
        requested_format="pseudonymised records",
    )
    assessment = assess_purpose(request)
    assert categories(assessment.spe_justification) == {"66(3)"}
    decision = decide(request, assessment)
    assert decision.outcome == "APPROVE_SPE"
    assert decision.articles == ["53", "66", "68", "73", "71"]
    assert [s.status for s in decision.trace] == ["not_matched", "not_matched", "matched", "not_evaluated"]
    assert decision.trace[2].evidence == assessment.spe_justification


def test_health_data_request_is_step2():
    request = make_request(purpose="Official statistics for the annual health report.")
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == "APPROVE_STATISTICAL"
    assert decision.articles == ["53", "69", "71"]
    assert [s.status for s in decision.trace] == ["not_matched", "matched", "not_evaluated", "not_evaluated"]
    assert "Art. 71" in " ".join(decision.reasons)
    assert "small" in " ".join(decision.reasons).lower()


def test_spe_justification_ignored_for_data_request():
    request = make_request(purpose="Research. Statistics are not enough for us.")
    assert assess_purpose(request).spe_justification == []


def test_reject_trace_and_reason(settings):
    request = load_request(settings, "R10")
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == "REJECT"
    assert decision.articles == ["54"]
    assert [s.status for s in decision.trace] == ["matched", "not_evaluated", "not_evaluated", "not_evaluated"]
    assert [s.step for s in decision.trace] == [1, 2, 3, 4]
    assert decision.trace[0].evidence
    joined = " ".join(decision.reasons)
    assert "Art. 54" in joined and "nicotine pouch flavours" in joined


def test_no_permitted_purpose_adds_warning():
    request = make_request(purpose="We would like to see some numbers.")
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == "APPROVE_STATISTICAL"
    assert "No permitted purpose under Art. 53(1) recognised – manual check recommended." in decision.warnings


# --- request kind -----------------------------------------------------------


def test_request_kind_normalises_requested_as():
    assert request_kind(make_request(requested_as="  Health Data ACCESS Application ")) == "access_application"
    assert request_kind(make_request(requested_as="Health  data request")) == "statistics_request"


def test_unknown_requested_as_falls_back_to_format():
    request = make_request(requested_as="something else", requested_format="pseudonymised records")
    assert request_kind(request) == "access_application"
    decision = decide(request, assess_purpose(request))
    assert decision.outcome == "APPROVE_STATISTICAL" and decision.articles == ["53", "66", "69", "71"]
    assert any("requested_as" in w for w in decision.warnings)


def test_unknown_requested_as_and_format_defaults_to_statistics_with_warning():
    request = make_request(requested_as="???", requested_format=None)
    assert request_kind(request) == "statistics_request"
    assert any("requested_as" in w for w in decide(request, assess_purpose(request)).warnings)


# --- LLM evidence -----------------------------------------------------------


def test_llm_evidence_requires_verbatim_quote():
    request = make_request(
        purpose="We plan a loyalty scheme.   Customers with  asthma get a different offer.",
        requested_as="health data access application",
    )
    llm = PurposeAssessment(
        prohibited=[
            Evidence(source="llm", category="54(a)", quote="we exclude asthma patients from everything"),
            Evidence(source="llm", category="54(a)", quote="customers with asthma get a DIFFERENT offer"),
        ],
        permitted=[Evidence(source="llm", category="53(1)(e)", quote="invented research statement")],
        spe_justification=[],
    )
    assessment = assess_purpose(request, llm)
    assert [e.quote for e in assessment.prohibited] == ["customers with asthma get a DIFFERENT offer"]
    assert assessment.prohibited[0].source == "llm"
    assert assessment.permitted == []

    decision = decide(request, assessment)
    assert decision.outcome == "REJECT"
    assert [e.source for e in decision.trace[0].evidence] == ["llm"]


def test_llm_evidence_is_not_duplicated_when_rules_found_it():
    request = make_request(purpose="We want to set insurance premiums by diagnosis.")
    rules_only = assess_purpose(request)
    quote = rules_only.prohibited[0].quote
    llm = PurposeAssessment(
        prohibited=[Evidence(source="llm", category="54(b)", quote=quote.upper())],
        permitted=[],
        spe_justification=[],
    )
    assert len(assess_purpose(request, llm).prohibited) == len(rules_only.prohibited)


# --- determinism ------------------------------------------------------------


def test_decision_is_deterministic(settings):
    request = load_request(settings, "R06")
    a = decide(request, assess_purpose(request)).model_dump()
    b = decide(request, assess_purpose(request)).model_dump()
    assert a == b
