"""Deterministic decision ladder: purpose assessment and the REJECT / APPROVE_STATISTICAL / APPROVE_SPE decision.

Pure functions, no I/O. The assessment (rules, optionally merged with verified LLM evidence) is the only input
the ladder looks at besides the request itself, so the same inputs always give the same decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from .law import ART53_POINTS, ART54_POINTS
from .models import AccessRequest, Decision, Evidence, PurposeAssessment, RuleStep

RequestKind = Literal["statistics_request", "access_application"]

NO_PERMITTED_PURPOSE_WARNING = "No permitted purpose under Art. 53(1) recognised – manual check recommended."
SPE_CATEGORY = "66(3)"

# --- Rules ------------------------------------------------------------------


@dataclass(frozen=True)
class _Rule:
    category: str
    all_of: tuple[re.Pattern[str], ...]
    none_of: tuple[re.Pattern[str], ...] = ()
    negatable: bool = False  # a negation cue shortly before the first all_of hit discards the hit


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in patterns)


# A hit that a negation cue precedes within this many characters ("no attempt at re-identification",
# "will not use the data for marketing") states the opposite of a prohibited purpose.
NEGATION_WINDOW = 40
_NEGATION_CUE = re.compile(
    r"\b(no|not|never|without|will not|won't|do not|does not|must not|prohibit\w*|prevent\w*|avoid\w*"
    r"|exclud\w* any)\b",
    re.I,
)


PROHIBITED_RULES: tuple[_Rule, ...] = (
    _Rule(
        "54(b)",  # insurance
        _rx(
            r"\binsur(ance|er)\b|\bpremium",
            r"premium|pricing|risk[- ]based|underwrit|tariff|contribution"
            r"|exclu\w* (them |customers |persons |people |patients )?from "
            r"(cover|coverage|insurance|policy|policies|contracts?)",
        ),
    ),
    _Rule(
        "54(b)",  # credit
        _rx(
            r"\b(credit|loan|mortgage)",
            r"scor|decision|approv|condition|terms|worth|eligib",
        ),
    ),
    _Rule(
        "54(b)",  # employment
        _rx(
            r"(?-i:\bHR\b)\s*(department|team|manager)|human resources|\bemployees?\b|\bstaff list"
            r"|job (offer|applicant|candidate)s?",
            r"contract|hir(e|ing)|dismiss|recruit|selection of (staff|employees|applicants|candidates)"
            r"|promot(e|ion|ions) (of|to) (staff|employees|workers)|promotion decisions"
            r"|sick leave|absenteeism",
        ),
        _rx(r"health promotion"),
    ),
    _Rule(
        "54(a)",  # re-identification / disadvantage
        _rx(
            r"match\w* (the |our |these |their )?(records|data|patients)?\s*(with|against) "
            r"(our|their|the|an?|a list of)\s+[\w ]{0,25}"
            r"(employee|staff|customer|client|member|applicant|policyholder)s?"
            r"|re-?identif"
            r"|identify (which|individual|specific) (patients|persons|people|employees|customers)"
            r"|who has been diagnosed",
        ),
    ),
    _Rule(
        "54(c)",  # advertising / marketing
        _rx(
            r"advertis|marketing|promotional|brand awareness|lead generation"
            r"|sales (rep|representative|force|visit|campaign|target)"
            r"|target\w* (our )?(ads|customers|prescribers|physicians)",
        ),
        _rx(r"post-?marketing|marketing authori[sz]ation|social marketing"),
    ),
    _Rule(
        "54(d)",  # harmful products
        _rx(
            r"nicotine|tobacco|cigarette|\bvap(e|ing)\b|alcoholic|\bspirits\b|liquor|gambling|betting|weapon"
            r"|firearm|illicit drug",
            r"product|flavou?r|brand|launch|position|sell|sales|consumer (product|market|brand)s?|portfolio",
        ),
        _rx(
            r"cessation|quit(ting)?\b|stop(ping)? smoking|withdrawal|replacement therapy|harms? (of|caused by)"
            r"|non-?alcoholic"
        ),
    ),
)
PROHIBITED_RULES = tuple(replace(rule, negatable=True) for rule in PROHIBITED_RULES)

PERMITTED_RULES: tuple[_Rule, ...] = (
    _Rule(
        "53(1)(a)",
        _rx(r"public health|prevention|surveillance|quality (programme|program|of care|in healthcare)|patient safety"),
    ),
    _Rule("53(1)(b)", _rx(r"ministry|policy|policymaking|regulat|health authorit")),
    _Rule("53(1)(c)", _rx(r"official statistic|statistics office|national statistic|health report")),
    _Rule("53(1)(d)", _rx(r"teaching|education|curricul|training module")),
    _Rule(
        "53(1)(e)",
        _rx(r"research|stud(y|ies)|epidemiolog|(train|validat)\w* .{0,40}(model|algorithm)|predict"),
    ),
    _Rule(
        "53(1)(f)",
        _rx(r"improve (the )?(care|treatment|delivery)|treatment gap|optimi[sz]e treatment|intervene earlier"),
    ),
)

SPE_RULE = _Rule(
    SPE_CATEGORY,
    _rx(
        r"(aggregate[sd]?|statistics|anonymi[sz]ed (data|statistics))( data| statistics)? (are|is|would be) not "
        r"(enough|sufficient)"
        r"|cannot be (achieved|answered|done) with (anonymi[sz]ed|aggregate)"
        r"|not possible with (anonymi[sz]ed|aggregate)"
        r"|(need|needs|require|requires)\s+(individual|patient|record)[- ]level"
        r"|(individual|patient|record)[- ]level (data|histories|records|trajectories) (are|is) (needed|required|necessary)"
    ),
)

# --- Text helpers -----------------------------------------------------------

_SENTENCE_END = re.compile(r"[.;!?](?=\s|$)|\n")


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        out.append(text[start : m.start()].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [sentence for sentence in out if sentence]


def _negated(sentence: str, start: int) -> bool:
    return _NEGATION_CUE.search(sentence[max(0, start - NEGATION_WINDOW) : start]) is not None


def _rule_matches(rule: _Rule, sentence: str) -> bool:
    """A rule applies to one sentence only: every all_of pattern matches and no none_of pattern does.
    For a negatable rule at least one hit of the first all_of pattern must not follow a negation cue."""
    if not all(p.search(sentence) for p in rule.all_of) or any(p.search(sentence) for p in rule.none_of):
        return False
    if rule.negatable:
        return any(not _negated(sentence, m.start()) for m in rule.all_of[0].finditer(sentence))
    return True


def _apply_rule(rule: _Rule, text: str) -> Evidence | None:
    for sentence in _sentences(text):
        if _rule_matches(rule, sentence):
            return Evidence(source="rules", category=rule.category, quote=sentence)
    return None


def _apply_rules(rules: tuple[_Rule, ...], text: str) -> list[Evidence]:
    return [ev for rule in rules if (ev := _apply_rule(rule, text)) is not None]


# --- Request kind -----------------------------------------------------------


def _classify(request: AccessRequest) -> tuple[RequestKind, str | None]:
    as_norm = " ".join(request.requested_as.split()).lower()
    if "access application" in as_norm:
        return "access_application", None
    if "data request" in as_norm:
        return "statistics_request", None
    fmt = (request.requested_format or "").lower()
    if "record" in fmt or "pseudonym" in fmt:
        return "access_application", (
            f"requested_as '{request.requested_as}' not recognised; treated as an access application "
            f"based on requested_format '{request.requested_format}'."
        )
    return "statistics_request", (
        f"requested_as '{request.requested_as}' not recognised and requested_format gives no hint; "
        "treated as a health data request (statistics only)."
    )


def request_kind(request: AccessRequest) -> RequestKind:
    return _classify(request)[0]


# --- Purpose assessment -----------------------------------------------------


MIN_LLM_QUOTE_WORDS = 3


def _verified_llm_evidence(
    llm_items: list[Evidence],
    allowed: set[str],
    known: list[Evidence],
    full_text_norm: str,
    must_match: _Rule | None = None,
) -> list[Evidence]:
    """LLM evidence counts only with a known category, a quote of at least three words that appears verbatim
    in the request and, if `must_match` is given, a quote that the rule-based pattern also recognises."""
    seen = {(e.category, _normalise(e.quote)) for e in known}
    out: list[Evidence] = []
    for item in llm_items:
        quote_norm = _normalise(item.quote)
        key = (item.category, quote_norm)
        if (
            item.category not in allowed
            or len(quote_norm.split()) < MIN_LLM_QUOTE_WORDS
            or quote_norm not in full_text_norm
            or key in seen
            or (must_match is not None and not _rule_matches(must_match, item.quote))
        ):
            continue
        seen.add(key)
        out.append(Evidence(source="llm", category=item.category, quote=item.quote.strip()))
    return out


def assess_purpose(request: AccessRequest, llm: PurposeAssessment | None = None) -> PurposeAssessment:
    text = request.full_text()
    prohibited = _apply_rules(PROHIBITED_RULES, text)
    permitted = _apply_rules(PERMITTED_RULES, text)
    is_access = request_kind(request) == "access_application"
    spe = [ev] if is_access and (ev := _apply_rule(SPE_RULE, text)) is not None else []

    if llm is not None:
        text_norm = _normalise(text)
        prohibited += _verified_llm_evidence(llm.prohibited, set(ART54_POINTS), prohibited, text_norm)
        permitted += _verified_llm_evidence(llm.permitted, set(ART53_POINTS), permitted, text_norm)
        if is_access:
            spe += _verified_llm_evidence(llm.spe_justification, {SPE_CATEGORY}, spe, text_norm, SPE_RULE)

    return PurposeAssessment(prohibited=prohibited, permitted=permitted, spe_justification=spe)


# --- Decision ---------------------------------------------------------------

_STEP_META = (
    ("Prohibited purpose", "The purpose falls under a prohibited use of Art. 54(a)-(d)."),
    ("Health data request", "The applicant filed a health data request (anonymised statistics only, Art. 69)."),
    (
        "Access application with justification",
        "Access application that explains why anonymised statistics are not enough (Art. 66(3), 67(2)(e)).",
    ),
    ("Other access application", "Any other access application: data minimisation applies (Art. 66(2), 68(3))."),
)

_OPT_OUT_REASON = "Patients who have opted out of secondary use are excluded from all results (Art. 71)."
_SMALL_CELL_REASON = (
    "Small numbers are hidden: counts below 10 are shown as \"<10\", and percentages or averages based on fewer "
    "than 10 patients are suppressed, so that no individual can be recognised (Art. 69)."
)


def _trace(matched_step: int, evidence: list[Evidence]) -> list[RuleStep]:
    steps = []
    for number, (title, condition) in enumerate(_STEP_META, start=1):
        if number < matched_step:
            status, ev = "not_matched", []
        elif number == matched_step:
            status, ev = "matched", evidence
        else:
            status, ev = "not_evaluated", []
        steps.append(RuleStep(step=number, title=title, condition=condition, status=status, evidence=list(ev)))
    return steps


def _cite(category: str) -> str:
    return f"Art. {category}"


def _reject_reasons(prohibited: list[Evidence]) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for ev in prohibited:
        if ev.category in seen:
            continue
        seen.add(ev.category)
        use = ART54_POINTS.get(ev.category, "a use that Art. 54 prohibits")
        reasons.append(
            f'You wrote: "{ev.quote}". Health data may not be used for {use} ({_cite(ev.category)}).'
        )
    reasons.append(
        "Because this purpose is prohibited, no data and no statistics can be released for this request (Art. 54)."
    )
    return reasons


def _permitted_reason(permitted: list[Evidence]) -> str:
    if not permitted:
        return (
            "We could not clearly match your stated purpose to one of the permitted purposes, so staff will check "
            "it manually (Art. 53)."
        )
    parts = []
    seen: set[str] = set()
    for ev in permitted:
        if ev.category in seen:
            continue
        seen.add(ev.category)
        parts.append(f"{ART53_POINTS.get(ev.category, 'a permitted purpose')} ({_cite(ev.category)})")
    return "Your stated purpose is a permitted use of health data: " + "; ".join(parts) + "."


def decide(request: AccessRequest, assessment: PurposeAssessment) -> Decision:
    kind, kind_warning = _classify(request)
    warnings: list[str] = [kind_warning] if kind_warning else []

    if assessment.prohibited:
        return Decision(
            outcome="REJECT",
            articles=["54"],
            headline="Request rejected: the purpose is prohibited under Art. 54",
            reasons=_reject_reasons(assessment.prohibited),
            trace=_trace(1, assessment.prohibited),
            warnings=warnings,
        )

    if not assessment.permitted:
        warnings.append(NO_PERMITTED_PURPOSE_WARNING)
    purpose_reason = _permitted_reason(assessment.permitted)

    if kind == "statistics_request":
        return Decision(
            outcome="APPROVE_STATISTICAL",
            articles=["53", "69", "71"],
            headline="Approved: you receive anonymised statistics",
            reasons=[
                purpose_reason,
                "You asked for a health data request, so the answer is given as anonymised statistics only, "
                "without access to the underlying records (Art. 69).",
                _OPT_OUT_REASON,
                _SMALL_CELL_REASON,
            ],
            trace=_trace(2, assessment.permitted),
            warnings=warnings,
        )

    if assessment.spe_justification:
        quote = assessment.spe_justification[0].quote
        return Decision(
            outcome="APPROVE_SPE",
            articles=["53", "66", "68", "73", "71"],
            headline="Approved: pseudonymised records in a secure processing environment",
            reasons=[
                purpose_reason,
                f'You explained why anonymised statistics are not enough: "{quote}". Pseudonymised records are '
                "therefore justified (Art. 66(3), 67(2)(e), 68).",
                "You can work with the records only inside a secure processing environment under a data permit. "
                "Your activity is logged and the records cannot be downloaded (Art. 73).",
                _OPT_OUT_REASON,
                "Anything you take out of the environment must be anonymised statistics, checked by us first, "
                "with small numbers (below 10) hidden (Art. 73).",
            ],
            trace=_trace(3, assessment.spe_justification),
            warnings=warnings,
        )

    fmt = (request.requested_format or "").lower()
    asked_for = (
        "You asked for pseudonymised records"
        if "record" in fmt or "pseudonym" in fmt
        else "You submitted a data access application"
    )
    return Decision(
        outcome="APPROVE_STATISTICAL",
        articles=["53", "66", "69", "71"],
        headline="Approved as anonymised statistics instead of pseudonymised records",
        reasons=[
            purpose_reason,
            f"{asked_for} but did not explain why anonymised statistics would not be "
            "enough. Under data minimisation (Art. 66(2) and Art. 68(3)) you therefore receive anonymised statistics "
            "(Art. 69).",
            "If you need record-level data, send a new application that explains why anonymised statistics "
            "cannot answer your question (Art. 66(3)).",
            _OPT_OUT_REASON,
            _SMALL_CELL_REASON,
        ],
        trace=_trace(4, assessment.permitted),
        warnings=warnings,
    )
