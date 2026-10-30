"""Decision engine: a fixed decision table over independent signals. The LLM never outputs a decision.

Strictness order: REJECT > REVIEW > APPROVE_STATISTICAL > APPROVE_SPE.
LLM signals can only make the outcome stricter; APPROVE_SPE needs a verified justification.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import policy

ProhibitedCategory = Literal[
    "none", "decisions_detrimental_to_persons", "insurance_exclusion_or_premiums", "advertising_or_marketing", "harmful_products", "ethics_violation",
]
AllowedPurpose = Literal[
    "none", "public_interest_public_health", "policy_making_and_regulation", "official_statistics", "education_and_teaching",
    "scientific_research", "algorithm_training_and_testing", "improving_healthcare",
]
Decision = Literal["REJECT", "APPROVE_STATISTICAL", "APPROVE_SPE"]
REQUEST_TYPES = {"health data request", "health data access application"}


class Signal(BaseModel):
    """One independent opinion on the purpose."""

    source: Literal["rules", "classifier", "redteam"]
    available: bool = True
    prohibited: bool = False
    category: str = "none"
    allowed_purpose: str = "none"
    evidence: Optional[str] = None
    evidence_verified: bool = False
    note: str = ""
    negated_hits: list[str] = Field(default_factory=list)


class Justification(BaseModel):
    justified: bool = False
    rules: bool = False
    llm: Optional[bool] = None
    quote: Optional[str] = None
    quote_verified: bool = False
    source: str = "none"


class ReviewReason(BaseModel):
    code: str
    message: str


class DecisionResult(BaseModel):
    outcome: Decision
    articles: list[str]
    reason_staff: str
    downgraded_from: Optional[str] = None
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    purpose_category: str = "none"
    purpose_source: str = "rules"
    applicant_type: Literal["public", "private", "unknown"] = "unknown"
    signals: dict = Field(default_factory=dict)
    rule_trace: list[dict] = Field(default_factory=list)


PURPOSE_TEXT = {
    "public_interest_public_health": "Public health is an allowed purpose",
    "policy_making_and_regulation": "Policy-making and improving the quality of care are allowed purposes",
    "official_statistics": "Official statistics are an allowed purpose",
    "education_and_teaching": "Teaching and education are allowed purposes",
    "scientific_research": "Scientific research is an allowed purpose",
    "algorithm_training_and_testing": "Training and testing algorithms is an allowed purpose",
    "improving_healthcare": "Improving healthcare is an allowed purpose",
    "none": "The purpose falls under the allowed purposes",
}
PROHIBITED_TEXT = {
    "decisions_detrimental_to_persons": "Using health data for decisions that harm individuals, such as employment or credit decisions, is prohibited",
    "insurance_exclusion_or_premiums": "Using health data to exclude people from insurance or to set their premiums is prohibited",
    "advertising_or_marketing": "Advertising and marketing are prohibited",
    "harmful_products": "Developing or marketing products that harm health, such as tobacco, nicotine or alcohol products, is prohibited",
    "ethics_violation": "This use conflicts with ethical rules, for example passing data on or re-identifying people, and is prohibited",
    "none": "This use is prohibited",
}


def _text(request: dict) -> str:
    a = request.get("applicant") or {}
    return " ".join([request.get("purpose", ""), request.get("question", ""), str(a.get("organisation", ""))])


def rules_signal(request: dict) -> Signal:
    text = _text(request)
    low = text.lower()
    negated = []
    for cat, spec in policy.PROHIBITED.items():
        for pat in spec["keywords"]:
            for m in re.finditer(pat, low):
                before = low[max(0, m.start() - 45):m.start()]
                if re.search(r"\b(not|never|no|nor|without|nicht|kein\w*|niemals)\b[^.;]*$", before):
                    negated.append(f"{cat}: '{text[m.start():m.end()]}' (negated)")
                    continue
                s, e = max(0, m.start() - 40), min(len(text), m.end() + 40)
                return Signal(source="rules", prohibited=True, category=cat, evidence=text[s:e].strip(), evidence_verified=True,
                              note=f"keyword /{pat}/", negated_hits=negated)
    purpose = request.get("purpose", "").lower() + " " + request.get("question", "").lower() + " " + str((request.get("applicant") or {}).get("organisation", "")).lower()
    order = ["algorithm_training_and_testing", "official_statistics", "education_and_teaching", "policy_making_and_regulation",
             "scientific_research", "public_interest_public_health", "improving_healthcare"]
    allowed = next((cat for cat in order if any(re.search(p, purpose) for p in policy.ALLOWED[cat]["keywords"])), "none")
    return Signal(source="rules", allowed_purpose=allowed, note="keyword rules", negated_hits=negated)


def rules_justification(request: dict) -> bool:
    text = (request.get("purpose", "") + " " + request.get("question", "")).lower()
    return any(re.search(p, text) for p in policy.JUSTIFICATION_PATTERNS)


def applicant_type(request: dict) -> str:
    org = str((request.get("applicant") or {}).get("organisation", "")).lower()
    if any(re.search(p, org) for p in policy.PRIVATE_SIGNALS):
        return "private"
    if any(re.search(p, org) for p in policy.PUBLIC_BODY_SIGNALS):
        return "public"
    return "unknown"


def decide(request: dict, signals: list[Signal], just: Justification, injection_hits: list[str], llm_available: bool) -> DecisionResult:
    review: list[ReviewReason] = []
    trace: list[dict] = []
    requested_as = request.get("requested_as", "").strip().lower()
    a_type = applicant_type(request)
    live = [s for s in signals if s.available]
    votes = [s for s in live if s.prohibited]
    needed = 2 if llm_available else 1
    purpose_votes = [s.allowed_purpose for s in live if s.allowed_purpose != "none"]
    # prefer the LLM classifier's purpose when available, else rules
    purpose = next((s.allowed_purpose for s in live if s.source == "classifier" and s.allowed_purpose != "none"), None) or \
        (purpose_votes[0] if purpose_votes else "none")
    purpose_source = "classifier" if any(s.source == "classifier" and s.allowed_purpose == purpose for s in live) else "rules"

    for s in live:
        if s.negated_hits:
            review.append(ReviewReason(code="negated_red_flag", message="The request mentions a prohibited use but says it is not intended: "
                                       + "; ".join(s.negated_hits[:3]) + ". A person should confirm."))
    if injection_hits:
        review.append(ReviewReason(code="injection_suspected", message="Possible instructions hidden in the request: " + "; ".join(injection_hits[:5])))

    trace.append({"step": 1, "question": "Is the purpose prohibited (Art. 54)?",
                  "answer": f"Yes, {len(votes)} of {len(live)} checks" if votes else f"No, 0 of {len(live)} checks", "article": "54"})
    if votes:
        cat = max({v.category for v in votes}, key=lambda c: sum(v.category == c for v in votes))
        if len(votes) < needed:
            review.append(ReviewReason(code="single_red_flag", message=f"Only one check flagged a prohibited use ({votes[0].source}); a person should confirm."))
        if llm_available and len(votes) < len(live):
            dissent = [s.source for s in live if not s.prohibited]
            review.append(ReviewReason(code="signals_disagree", message=f"Not all checks agree ({', '.join(dissent)} found no prohibited use)."))
        return DecisionResult(
            outcome="REJECT", articles=["54"], reason_staff=f"{PROHIBITED_TEXT.get(cat, PROHIBITED_TEXT['none'])} (Art. 54).",
            needs_review=bool(review), review_reasons=review, purpose_category=cat, purpose_source=votes[0].source,
            applicant_type=a_type, signals=_signals_dict(signals, just, injection_hits), rule_trace=trace,
        )

    allowed = f"{PURPOSE_TEXT.get(purpose, PURPOSE_TEXT['none'])} (Art. 53)."
    if purpose == "none":
        review.append(ReviewReason(code="purpose_unclear", message="No allowed purpose (Art. 53) could be identified with confidence."))
    reserved = [p for p in dict.fromkeys([purpose] + purpose_votes) if p in policy.ALLOWED and policy.ALLOWED[p]["public_body_only"]]
    if reserved and a_type == "private":
        review.append(ReviewReason(code="art_53_2", message=f"Purpose {policy.ALLOWED[reserved[0]]['article']} ({reserved[0].replace('_', ' ')}) is reserved for "
                                                            "public-sector bodies (Art. 53(2)); the applicant appears to be private."))
    if requested_as == "health data request":
        trace.append({"step": 2, "question": "Is this a health data request?", "answer": "Yes, so statistics", "article": "69"})
        return DecisionResult(
            outcome="APPROVE_STATISTICAL", articles=["53", "69"], reason_staff=f"{allowed} Statistics answer the question (Art. 69).",
            needs_review=bool(review), review_reasons=review, purpose_category=purpose, purpose_source=purpose_source,
            applicant_type=a_type, signals=_signals_dict(signals, just, injection_hits), rule_trace=trace,
        )
    trace.append({"step": 2, "question": "Is this a health data request?", "answer": "No, an access application", "article": "67"})
    eligible = purpose in policy.SPE_ELIGIBLE
    spe_ok = just.justified and eligible and not injection_hits
    trace.append({"step": 3, "question": "Does the applicant explain why statistics are not enough (Art. 66)?",
                  "answer": ("Yes" if just.justified else "No") + (f" ({just.source})" if just.justified else ""), "article": "66"})
    if spe_ok:
        if just.source in ("rules", "llm") and llm_available:
            review.append(ReviewReason(code="justification_single_source", message=f"The justification for patient-level data was found only by {just.source}."))
        trace.append({"step": 4, "question": "Grant pseudonymised records in a secure processing environment?", "answer": "Yes", "article": "73"})
        return DecisionResult(
            outcome="APPROVE_SPE", articles=["53", "66", "68", "73"],
            reason_staff=f"{allowed} Patient-level data is needed, so pseudonymised data is justified (Art. 66). "
                         "Access only under a data permit inside a secure processing environment (Art. 68, 73).",
            needs_review=bool(review), review_reasons=review, purpose_category=purpose, purpose_source=purpose_source,
            applicant_type=a_type, signals=_signals_dict(signals, just, injection_hits), rule_trace=trace,
        )
    if just.justified and injection_hits:
        review.append(ReviewReason(code="spe_blocked_by_injection", message="Patient-level access was not granted because the request contains suspected injected instructions."))
    if just.justified and not eligible:
        review.append(ReviewReason(code="spe_purpose_not_eligible", message="A justification was given, but the purpose does not support patient-level access."))
    trace.append({"step": 4, "question": "Grant pseudonymised records?", "answer": "No, approved as statistics instead", "article": "69"})
    return DecisionResult(
        outcome="APPROVE_STATISTICAL", articles=["53", "66", "69"],
        reason_staff=f"{allowed} Statistics answer the question, so pseudonymised records are not justified (Art. 66). Approved as statistics instead (Art. 69).",
        downgraded_from="APPROVE_SPE", needs_review=bool(review), review_reasons=review, purpose_category=purpose,
        purpose_source=purpose_source, applicant_type=a_type, signals=_signals_dict(signals, just, injection_hits), rule_trace=trace,
    )


def _signals_dict(signals: list[Signal], just: Justification, injection_hits: list[str]) -> dict:
    out = {}
    for s in signals:
        out[s.source] = {"available": s.available, "prohibited": s.prohibited, "category": s.category,
                         "allowed_purpose": s.allowed_purpose, "quote": s.evidence, "quote_verified": s.evidence_verified, "note": s.note}
    out["justification"] = just.model_dump()
    out["injection"] = {"flagged": bool(injection_hits), "hits": injection_hits}
    return out


def strictness(outcome: str, needs_review: bool) -> int:
    """Higher = stricter. Used by the property test."""
    return {"APPROVE_SPE": 0, "APPROVE_STATISTICAL": 1, "REJECT": 3}[outcome] + (1 if needs_review and outcome != "REJECT" else 0)
