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


# --- fix round 1: sentence-scoped rules and conservative LLM merge ------------


def test_hazard_ratio_hr_is_not_employment():
    request = make_request(purpose="Report the HR (hazard ratio) for patients selected by age band.")
    assert assess_purpose(request).prohibited == []


def test_matched_case_control_is_not_reidentification():
    request = make_request(purpose="Cases were matched with controls by age and sex.")
    assert assess_purpose(request).prohibited == []


def test_rule_patterns_must_co_occur_in_one_sentence():
    request = make_request(
        purpose="We study coverage under public insurance.",
        definitions=["Exclude patients under 18."],
    )
    assert assess_purpose(request).prohibited == []


def test_matching_with_employee_list_is_reidentification():
    request = make_request(purpose="We will match the records with our employee list")
    assert "54(a)" in categories(assess_purpose(request).prohibited)


def test_hr_department_renewing_contracts_is_employment():
    request = make_request(purpose="The HR department wants to know which team members to renew contracts for.")
    assert "54(b)" in categories(assess_purpose(request).prohibited)


def test_llm_spe_justification_needs_rule_pattern_in_quote():
    request = make_request(
        purpose="Research on hypertension treatment in general practice.",
        question="Provide pseudonymised records of adults with hypertension.",
        requested_as="health data access application",
        requested_format="pseudonymised records",
    )
    llm = PurposeAssessment(
        prohibited=[],
        permitted=[],
        spe_justification=[
            Evidence(source="llm", category="66(3)", quote="Provide pseudonymised records of adults with hypertension")
        ],
    )
    assessment = assess_purpose(request, llm)
    assert assessment.spe_justification == []
    decision = decide(request, assessment)
    assert decision.outcome == "APPROVE_STATISTICAL" and decision.articles == ["53", "66", "69", "71"]
    assert decision.trace[3].status == "matched"


def test_llm_spe_justification_not_duplicated_when_rules_found_it():
    request = make_request(
        purpose="Research on rare outcomes. We need patient-level data for this.",
        requested_as="health data access application",
    )
    llm = PurposeAssessment(
        prohibited=[],
        permitted=[],
        spe_justification=[Evidence(source="llm", category="66(3)", quote="We need patient-level data for this")],
    )
    assessment = assess_purpose(request, llm)
    assert len(assessment.spe_justification) == 1
    assert assessment.spe_justification[0].source == "rules"


def test_llm_quote_with_two_words_is_discarded():
    request = make_request(purpose="We plan a loyalty scheme. Customers with asthma get a different offer.")
    llm = PurposeAssessment(
        prohibited=[Evidence(source="llm", category="54(a)", quote="loyalty scheme")],
        permitted=[Evidence(source="llm", category="53(1)(e)", quote="loyalty scheme")],
        spe_justification=[],
    )
    assessment = assess_purpose(request, llm)
    assert assessment.prohibited == [] and assessment.permitted == []


def test_llm_evidence_with_unknown_category_is_discarded():
    quote = "Customers with asthma get a different offer"
    request = make_request(purpose=f"We plan a loyalty scheme. {quote}.", requested_as="health data access application")
    llm = PurposeAssessment(
        prohibited=[Evidence(source="llm", category="99(z)", quote=quote)],
        permitted=[Evidence(source="llm", category="53(1)(z)", quote=quote)],
        spe_justification=[Evidence(source="llm", category="66(9)", quote=quote)],
    )
    assessment = assess_purpose(request, llm)
    assert assessment.prohibited == [] and assessment.permitted == [] and assessment.spe_justification == []


def test_statistics_request_with_pseudonymised_format_stays_step2():
    request = make_request(
        purpose="Research on diabetes prevention.",
        requested_as="health data request",
        requested_format="pseudonymised records",
    )
    assert request_kind(request) == "statistics_request"
    decision = decide(request, assess_purpose(request))
    assert decision.articles == ["53", "69", "71"]
    assert [s.status for s in decision.trace] == ["not_matched", "matched", "not_evaluated", "not_evaluated"]


# --- fix wave M1: prohibited-rule false positives ---------------------------


@pytest.mark.parametrize(
    "purpose",
    [
        "The data will be pseudonymised and no attempt at re-identification will be made.",
        "We will not use the data for marketing or advertising.",
        "Post-marketing safety study of SGLT2 inhibitors in older adults.",
        "Research on stroke after the marketing authorisation of DOACs.",
        "We evaluate a workplace health promotion programme for employees.",
        "We compare outcomes of patients with private insurance, excluding children.",
        "We study non-alcoholic fatty liver disease and consumer behaviour.",
        "We will not use the data for marketing, advertising or sales.",
        "We will not use the data for marketing, or for advertising.",
        "We will not use the data for marketing, nor for advertising.",
        "We will not, under any circumstances, use the data for advertising.",
    ],
)
def test_legitimate_wording_is_not_prohibited(purpose):
    assert assess_purpose(make_request(purpose=purpose)).prohibited == []


@pytest.mark.parametrize(
    ("purpose", "category"),
    [
        ("Our HR department will use the results to decide on contract renewals.", "54(b)"),
        ("We will match the records with our employee list.", "54(a)"),
        ("We plan an advertising campaign for physicians.", "54(c)"),
        ("We use the data to set insurance premiums.", "54(b)"),
        ("We develop new e-cigarette flavours for young consumers.", "54(d)"),
        ("We exclude customers from insurance cover based on their diagnoses.", "54(b)"),
        ("We decide on the promotion of employees by diagnosis.", "54(b)"),
        ("Not for research, only for advertising.", "54(c)"),
        ("We will not share the data but we use it for advertising.", "54(c)"),
        ("We study alcohol; the data is not used for marketing, but for our advertising campaign.", "54(c)"),
        ("Not only research: we also run an advertising campaign for physicians.", "54(c)"),
        ("There is no doubt we will use the data for marketing to physicians.", "54(c)"),
        ("We will use the data without delay for advertising.", "54(c)"),
        ("We will use the data without hesitation for advertising.", "54(c)"),
        ("However, we will use the data for advertising.", "54(c)"),
        ("We will not use it for research, instead we plan an advertising campaign.", "54(c)"),
    ],
)
def test_prohibited_wording_stays_prohibited(purpose, category):
    assert category in categories(assess_purpose(make_request(purpose=purpose)).prohibited)


# Known limitation (deliberately not asserted either way): a comma is not a clause boundary, so a comma splice such as
# "We will not use it for research, we plan an advertising campaign." may slip through the negation guard.
def test_negation_only_guards_the_hit_in_the_same_sentence():
    request = make_request(purpose="We do not do research. We will use the data for advertising.")
    assert "54(c)" in categories(assess_purpose(request).prohibited)


def test_step4_reason_names_what_was_actually_requested():
    with_format = make_request(
        purpose="Research on hypertension treatment in general practice.",
        requested_as="health data access application",
        requested_format="pseudonymised records",
    )
    joined = " ".join(decide(with_format, assess_purpose(with_format)).reasons)
    assert "You asked for pseudonymised records" in joined

    without_format = make_request(
        purpose="Research on hypertension treatment in general practice.",
        requested_as="health data access application",
        requested_format="aggregated tables",
    )
    decision = decide(without_format, assess_purpose(without_format))
    joined = " ".join(decision.reasons)
    assert decision.trace[3].status == "matched"
    assert "You asked for pseudonymised records" not in joined
    assert "You submitted a data access application" in joined

    no_format = make_request(
        purpose="Research on hypertension treatment in general practice.",
        requested_as="health data access application",
        requested_format=None,
    )
    assert "You asked for pseudonymised records" not in " ".join(decide(no_format, assess_purpose(no_format)).reasons)
