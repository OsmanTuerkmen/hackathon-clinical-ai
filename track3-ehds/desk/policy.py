"""Decision engine for Regulation (EU) 2025/327, Chapter IV (rule-based, deterministic).

Decision order (challenge README):
 1. Prohibited purpose                                   -> REJECT               Art. 54
 2. Health data request                                  -> APPROVE_STATISTICAL  Art. 53, 69
 3. Access application explaining why statistics are not -> APPROVE_SPE          Art. 53, 66, 68, 73
    enough
 4. Any other access application                         -> APPROVE_STATISTICAL  Art. 53, 66, 69

Only purpose, question, definitions, requested_as and requested_format are used. The request ID,
applicant name and organisation are never inspected. If no Art. 53 purpose can be recognised the
desk does not decide automatically (NO_DECISION) and refers the case to staff.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import sentences

REJECT = "REJECT"
APPROVE_STATISTICAL = "APPROVE_STATISTICAL"
APPROVE_SPE = "APPROVE_SPE"
NO_DECISION = "NO_DECISION"

ARTICLE_TITLES = {
    "53": "Purposes for secondary use",
    "54": "Prohibited secondary use",
    "66": "Data minimisation and purpose limitation",
    "67": "Health data access applications",
    "68": "Data permit",
    "69": "Health data request (anonymised statistics only)",
    "71": "Right to opt out",
    "73": "Secure processing environment",
}

I = re.IGNORECASE


@dataclass
class Finding:
    point: str
    label: str
    evidence: str
    field: str


@dataclass
class Decision:
    outcome: str
    articles: list[str]
    reason: str
    trace: list[dict] = field(default_factory=list)
    purposes: list[Finding] = field(default_factory=list)
    prohibited: list[Finding] = field(default_factory=list)
    justification: Finding | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def f(x: Finding):
            return {"point": x.point, "label": x.label, "evidence": x.evidence, "field": x.field}
        return {
            "outcome": self.outcome,
            "articles": self.articles,
            "article_titles": {a: ARTICLE_TITLES.get(a, "") for a in self.articles},
            "reason": self.reason,
            "trace": self.trace,
            "purposes": [f(p) for p in self.purposes],
            "prohibited": [f(p) for p in self.prohibited],
            "justification": f(self.justification) if self.justification else None,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- Art. 54 patterns
# Phrases that contain trigger words but describe permitted activities; removed before matching.
BENIGN = [
    r"marketing authori[sz]ations?", r"post-?marketing", r"pre-?marketing", r"nicotine replacement( therap\w*)?",
    r"smoking cessation", r"tobacco control", r"alcohol control", r"quit(ting)? smoking", r"stop(ping)? smoking",
    r"(alcohol|nicotine|tobacco) (dependence|addiction|use disorder) treatment",
    r"treat\w* (alcohol|nicotine|tobacco) (dependence|addiction|use disorder)",
    r"(gambling|betting|alcohol|nicotine|tobacco|smoking|drug)[- ](addiction|dependence|use disorder|related harm|harms?|"
    r"prevention|control|cessation|abuse)",
    r"(against|prevent\w*|reduc\w*|treat\w*|fight\w*|tackl\w*) (?:\w+ ){0,2}(gambling|betting|smoking|tobacco|nicotine|"
    r"alcohol|drug use)",
    r"labou?r market", r"market access",
]

HARMFUL_PRODUCT = (r"\b(nicotine|tobacco|cigarettes?|cigars?|e-?cigarettes?|vap(?:e|es|ing)|snus|nicotine pouch(?:es)?|"
                   r"heated tobacco|alcoholic (?:beverages?|drinks?)|alcohol products?|spirits|liquor|beer|wine|"
                   r"illicit drugs?|recreational drugs?|weapons?|weaponry|firearms?|ammunition|gambling|betting|casinos?)\b")
COMMERCIAL_CONTEXT = (r"\b(develop\w*|design\w*|launch\w*|sell\w*|sales|market(?:s|ing|ed)?|position\w*|flavou?rs?|"
                      r"products?|brands?|consumers?|customers?|commerciali[sz]\w*|retail\w*|portfolio|"
                      r"compan(?:y|ies)|campaigns?|business|revenue|profits?)\b")
PROHIBITED_RULES = [
    ("54(1)(b)", "setting insurance premiums or excluding people from insurance",
     [r"\b(insurance|insurer|insurers|policyholders?)\b[^.]{0,100}?\b(premiums?|pric\w*|tariffs?|underwrit\w*|"
      r"risk[- ]?(?:based|adjusted|rating)|exclu\w*|refus\w*|den(?:y|ial)|coverage decisions?)",
      r"\b(premiums?|underwrit\w*|insurability)\b[^.]{0,100}?\b(insurance|insurer|customers?|policyholders?|"
      r"actual risk|risk)\b",
      r"\b(adjust|raise|increase|change|set)\w* (?:their |the |our )?(?:contracts?|premiums?|tariffs?|prices?|"
      r"rates|conditions)\b[^.]{0,60}?\b(customers?|clients?|policyholders?|members?|patients?|diabetics?|them)\b",
      r"\b(customers?|clients?|policyholders?|members?)\b[^.]{0,80}?\b(adjust|raise|increase|change)\w* (?:their |the )?"
      r"(?:contracts?|premiums?|tariffs?|prices?|rates|conditions)\b"]),
    ("54(1)(b)", "decisions on credit or loans",
     [r"\b(credit ?(?:scor\w*|worthiness|decisions?|limits?|risk)|creditworthiness|loan (?:decisions?|applications?|"
      r"approvals?|conditions)|mortgages?|lending decisions?)\b"]),
    ("54(1)(b)", "decisions about job offers or employees",
     [r"\b(employees?|employers?|employment|staff list|workforce|job applicants?|applicants for jobs?|job candidates?|"
      r"hiring|recruit\w*|job offers?|contracts?)\b[^.]{0,120}?\b(match\w*|link\w*|merg\w*|cross-?referenc\w*|"
      r"identify\w*|see who|find out who|decid\w*|renew\w*|dismiss\w*|terminat\w*|screen\w*|select\w*|hire)\b",
      r"\b(match\w*|link\w*|merg\w*|cross-?referenc\w*|see who|find out who|decid\w*|renew\w*|dismiss\w*|"
      r"terminat\w*|screen\w*)\b[^.]{0,120}?\b(employees?|employee list|staff list|workforce|job applicants?|"
      r"hiring|job offers?|contracts?)\b"]),
    ("54(1)(a)", "decisions about identified individuals or re-identification",
     [r"\b(re-?identif\w*|de-?anonymi[sz]\w*|de-?pseudonymi[sz]\w*)\b",
      r"\b(match|link|merge|combine|cross-?reference)\w*\b[^.]{0,60}?\b(our|their|an?|the)\b[^.]{0,30}?"
      r"\b(list|database|register|registry|crm|customer data|client data)\b",
      r"\bsee who has\b", r"\bfind out who (has|is)\b",
      r"\bwhich of (?:our|their|the) (?:customers|clients|employees|staff|members|policyholders|applicants|users|"
      r"tenants|students)\b",
      r"\bidentify (?:individual|specific|single) (?:patients|persons|people|customers|employees|clients)\b",
      r"\b(den(?:y|ied|ies|ial)|refus\w*|exclud\w*|blacklist\w*)\b[^.]{0,60}?\b(patients?|persons?|people|individuals?|"
      r"customers?|applicants?)\b",
      r"\b(patients?|persons?|people|individuals?|customers?|employees?|applicants?)\b[^.]{0,40}?\b(?:should|will|would|"
      r"to|are|could) be (?:denied|refused|excluded|rejected|dismissed|charged more|penali[sz]ed)\b"]),
    ("54(1)(c)", "advertising or marketing",
     [r"\b(advertis\w*|marketing|promotional|ad campaigns?|sales campaigns?|sales strateg\w*|sales targets?|"
      r"brand awareness|lead generation|sales representatives?|sales reps?|sales force|field force|market share|"
      r"sell more|(?:increase|boost|grow|drive)\w* (?:the |our |their )?sales)\b",
      r"\bsales of (?:our|their|its) \b",
      r"\bmarket(?:ing)? (?:it|them|this|our|their) (?:\w+ ){0,2}(?:to|for|among|towards)\b",
      r"\bpromot\w* (?:our|their|the|a|its|new) (?:\w+ )?(?:products?|drugs?|brands?|medicines?|services?)\b"]),
    ("54(1)(d)", "developing harmful products (tobacco, nicotine, alcohol, weapons, addictive products)",
     [r"__HARMFUL__"]),
    ("54(1)(d)", "products designed to create addiction",
     [r"\b(designed|modified|optimi[sz]ed) (?:\w+ ){0,3}to (?:create|increase|maximi[sz]e) (?:addiction|dependence|"
      r"compulsive use)\b"]),
]

# Second line of defence: wording that does not match an explicit Art. 54 rule but suggests commercial,
# insurance, employment or individual-level use. Such requests are never approved automatically.
RED_FLAGS = [
    ("commercial relationship with the people concerned",
     r"\b(?:our|their|its) (?:customers?|clients?|policyholders?|members?|employees?|staff|workforce|applicants?|"
     r"subscribers?|consumers?)\b"),
    ("customer targeting or profiling",
     r"\b(?:customer|client|consumer)s? (?:acquisition|segmentation|targeting|retention|profil\w*|scor\w*|base|lists?|"
     r"data(?:base)?)\b"),
    ("targeting prescribers or consumers", r"\btarget\w* (?:\w+ ){0,2}(?:prescribers|physicians|doctors|consumers|"
                                           r"customers|buyers|pharmacies)\b"),
    ("pricing, profit or competition", r"\b(?:pric(?:e|es|ing)|profit\w*|revenue|market share|competitors?|"
                                       r"commercial (?:advantage|strateg\w*)|business case|go-to-market|product launch|"
                                       r"brand\w*)\b"),
    ("insurance underwriting or credit", r"\b(?:underwrit\w*|actuar\w*|insurability|premiums?|loans?|lending|"
                                         r"mortgages?|credit)\b"),
    ("employment decisions", r"\b(?:employers?|human resources|hr department|hiring|recruit\w*|job applicants?|"
                             r"contract renewals?|sick leave of (?:our|the) )\b"),
    ("identifying or contacting individual people",
     r"\b(?:identify\w*|find|locate|contact\w*|reach out to|name)\b[^.]{0,30}?\b(?:individual|specific|named|single|"
     r"particular|these|those) (?:patients?|persons?|people|individuals)\b"),
]


def detect_red_flags(req: dict) -> list[Finding]:
    found: list[Finding] = []
    for fname, text in _fields(req)[:2]:
        for sent in sentences(text):
            clean = _strip_benign(sent)
            for label, pat in RED_FLAGS:
                if re.search(pat, clean, I) and not any(f.label == label for f in found):
                    found.append(Finding("54", label, sent, fname))
    return found


# --------------------------------------------------------------------------- Art. 53 patterns
PURPOSE_RULES = [
    ("53(1)(a)", "public health and quality of care",
     r"\b(public health|population health|prevention|preventive|prevent|surveillance|occupational health|"
     r"patient safety|quality (?:of|in) (?:care|healthcare|health care)|quality programme|quality improvement|"
     r"quality of treatment|safety of (?:medicinal products|medicines|medical devices)|pharmacovigilance|"
     r"cross-border threats?|outbreaks?|epidemics?|pandemics?|disease burden|health threats?|treatment gap)\b"),
    ("53(1)(b)", "policy-making",
     r"\b(polic(?:y|ies)|policymaking|policy-making|regulator\w*|ministry|health authorit\w*|public sector|"
     r"planning|plan (?:a|the|our|new) (?:\w+ ){0,2}(?:programme|program|services|capacity|campaign)|guidelines?|"
     r"resource allocation|health services planning|capacity planning)\b"),
    ("53(1)(c)", "official statistics",
     r"\b(official statistics|statistics office|statistical office|national statistics|annual (?:health )?report|"
     r"health report|eurostat|hospital use statistics)\b"),
    ("53(1)(d)", "teaching",
     r"\b(teaching|education\w*|curricul\w*|lectures?|students?|course materials?|training (?:module|course|"
     r"programme|program) for)\b"),
    ("53(1)(e)", "scientific research",
     r"\b(research\w*|we study|study|studies|investigat\w*|epidemiolog\w*|risk factors?|cohort stud\w*|"
     r"clinical trials?|health technology assessments?|scientific)\b"),
    ("53(1)(e)(i)", "developing health products or services",
     r"\b(develop\w* (?:a |an |new |our )?(?:clinical |medical |digital |prediction )?(?:software|tools?|apps?|"
     r"applications?|devices?|services?|treatments?|diagnostics?))\b"),
    ("53(1)(e)(ii)", "training and testing algorithms",
     r"\b(algorithms?|machine learning|artificial intelligence|ai (?:systems?|models?)|prediction models?|"
     r"predictive models?|risk models?|clinical prediction|decision support|(?:train|validat|test)\w* "
     r"(?:and (?:validat|test)\w* )?(?:a |an |the |our )?(?:\w+ )?models?|model that predicts)\b"),
    ("53(1)(f)", "improving care",
     r"\b(improv\w* (?:the )?(?:care|treatment|delivery of care|healthcare|health care|outcomes|management|"
     r"prescribing)|optimi[sz]\w* (?:of )?(?:treatment|therapy|care)|intervene earlier|better care|"
     r"care pathways?|clinical practice|delivery of care|treatment of patients)\b"),
]

# --------------------------------------------------------------------------- Art. 66(3) patterns
JUSTIFICATION_RULES = [
    r"\b(aggregates?|aggregated (?:data|statistics|numbers|counts)|(?:anonymi[sz]ed )?statistics|anonymi[sz]ed data|"
    r"summary (?:data|statistics))\b[^.;]{0,40}?\b(?:are|is|would be|will be)?\s*(?:not enough|insufficient|"
    r"not sufficient|inadequate|not adequate|cannot answer|can ?not answer|do not suffice|does not suffice|"
    r"would not suffice|won't suffice|are not suitable|is not suitable|cannot capture|can't capture|"
    r"do not capture|does not capture|would lose|lose the)",
    r"\b(?:needs?|requires?|required|necessary|necessitates?|depends on|only possible with|must use)\b[^.;]{0,50}?"
    r"\b(?:individual|patient|person|record)[- ]level\b",
    r"\b(?:needs?|requires?|required|necessary|necessitates?|depends on|only possible with|must use)\b[^.;]{0,50}?"
    r"\b(?:individual|each patient'?s?|per-patient)\s+(?:\w+\s+)?(?:sequences?|histories|history|trajectories|"
    r"records|time series|timelines?|follow-up)\b",
    r"\b(?:individual|patient|person|record)[- ]level (?:data|records|histories|history|information|trajectories)"
    r"\b[^.;]{0,30}?\b(?:are|is)\s+(?:needed|required|necessary|essential|indispensable)",
    r"\bcannot be (?:achieved|answered|done|met) (?:with|using|from) (?:anonymi[sz]ed|aggregated?|statistical)",
    r"\bnot possible (?:with|using|from) (?:anonymi[sz]ed|aggregated?|statistical)",
]
NEGATED_BEFORE = re.compile(r"\b(not|no|don't|do not|does not|doesn't|never|without)\s+(\w+\s+){0,2}$", I)


def _strip_benign(text: str) -> str:
    for pat in BENIGN:
        text = re.sub(pat, " ", text, flags=I)
    return text


def _fields(req: dict) -> list[tuple[str, str]]:
    return [("purpose", req.get("purpose", "")), ("question", req.get("question", "")),
            ("definitions", " ".join(req.get("definitions", [])))]


def detect_prohibited(req: dict) -> list[Finding]:
    found: list[Finding] = []
    for fname, text in _fields(req):
        for sent in sentences(text):
            clean = _strip_benign(sent)
            for point, label, patterns in PROHIBITED_RULES:
                for pat in patterns:
                    lab = label
                    if pat == "__HARMFUL__":
                        prod = re.search(HARMFUL_PRODUCT, clean, I)
                        hit = prod and re.search(COMMERCIAL_CONTEXT, clean, I)
                        if hit:
                            lab = f"developing or positioning harmful products ({prod.group(0).lower()})"
                    else:
                        hit = re.search(pat, clean, I)
                    if hit:
                        if not any(f.point == point for f in found):
                            found.append(Finding(point, lab, sent, fname))
                        break
    return found


def detect_purposes(req: dict) -> list[Finding]:
    found: list[Finding] = []
    for fname, text in _fields(req)[:2]:
        for sent in sentences(text):
            for point, label, pat in PURPOSE_RULES:
                if re.search(pat, sent, I) and not any(f.point == point for f in found):
                    found.append(Finding(point, label, sent, fname))
    order = [p for p, _, _ in PURPOSE_RULES]
    return sorted(found, key=lambda f: order.index(f.point))


def detect_justification(req: dict) -> Finding | None:
    for fname, text in _fields(req)[:2]:
        for sent in sentences(text):
            for pat in JUSTIFICATION_RULES:
                m = re.search(pat, sent, I)
                if m and not NEGATED_BEFORE.search(sent[:m.start()]):
                    return Finding("66(3)", "applicant explains why anonymised statistics are not enough", sent, fname)
    return None


def _purpose_phrase(purposes: list[Finding]) -> str:
    labels = []
    for p in purposes:
        lab = p.label
        if lab not in labels:
            labels.append(lab)
    if not labels:
        return ""
    text = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    plural = len(labels) > 1 or labels[0].endswith("statistics")
    verb = "are allowed purposes" if len(labels) > 1 else ("is an allowed purpose" if not plural
                                                          else "are an allowed purpose")
    points = [p.point for p in purposes]
    short = [points[0]] + [p.replace("53(1)", "", 1) for p in points[1:]]
    return f"{text[0].upper() + text[1:]} {verb} (Art. {', '.join(short)})."


def decide(req: dict) -> Decision:
    trace: list[dict] = []
    prohibited = detect_prohibited(req)
    trace.append({"step": 1, "rule": "Prohibited purpose? (Art. 54)",
                  "result": "yes" if prohibited else "no",
                  "evidence": [f"Art. {f.point}: {f.label} - \"{f.evidence}\"" for f in prohibited]})
    if prohibited:
        main = prohibited[0]
        extra = [f for f in prohibited[1:] if f.label != main.label]
        reason = (f"The stated purpose involves {main.label}, which is a prohibited secondary use "
                  f"(Art. {main.point}).")
        if extra:
            reason += " It also involves " + "; ".join(f"{f.label} (Art. {f.point})" for f in extra) + "."
        reason += " The request was rejected before any patient data was queried."
        for step, rule in ((2, "Health data request?"), (3, "Access application with justification?"),
                           (4, "Other access application?")):
            trace.append({"step": step, "rule": rule, "result": "not evaluated", "evidence": []})
        return Decision(REJECT, ["54"], reason, trace, detect_purposes(req), prohibited)

    purposes = detect_purposes(req)
    notes = []
    if purposes and all(p.point in ("53(1)(a)", "53(1)(b)", "53(1)(c)") for p in purposes):
        notes.append("Art. 53(2): purposes (a)-(c) are reserved for public sector bodies; staff should confirm "
                     "the applicant's status.")
    if not purposes:
        trace.append({"step": "1b", "rule": "Allowed purpose recognised? (Art. 53)", "result": "no",
                      "evidence": []})
        return Decision(NO_DECISION, [], "No allowed purpose under Art. 53(1) could be recognised in the stated "
                        "purpose, so the desk does not decide automatically. The case is referred to staff and no "
                        "data was queried.", trace, purposes, [], None, notes)
    trace.append({"step": "1b", "rule": "Allowed purpose recognised? (Art. 53)", "result": "yes",
                  "evidence": [f"Art. {p.point}: {p.label} - \"{p.evidence}\"" for p in purposes]})
    flags = detect_red_flags(req)
    trace.append({"step": "1c", "rule": "Signals of commercial or individual-level use? (Art. 54 safeguard)",
                  "result": "yes" if flags else "no", "evidence": [f"{f.label} - \"{f.evidence}\"" for f in flags]})
    if flags:
        return Decision(NO_DECISION, [], "The purpose does not match an explicit prohibited use, but it shows signals "
                        "of possible commercial or individual-level use (" + "; ".join(f.label for f in flags) +
                        "). The desk does not approve such requests automatically: the case is referred to staff for "
                        "an Art. 54 review and no data was queried.", trace, purposes, flags, None, notes)
    purpose_text = _purpose_phrase(purposes)

    if req["requested_as"] == "health data request":
        trace.append({"step": 2, "rule": "Health data request? (Art. 69)", "result": "yes",
                      "evidence": ["requested_as = 'health data request'"]})
        trace.append({"step": 3, "rule": "Access application with justification?", "result": "not evaluated",
                      "evidence": []})
        trace.append({"step": 4, "rule": "Other access application?", "result": "not evaluated", "evidence": []})
        reason = (f"{purpose_text} A health data request is answered only with anonymised statistics (Art. 69); "
                  "small cells are suppressed.")
        if req.get("requested_format") == "pseudonymised records":
            notes.append("The request asks for pseudonymised records, but a health data request can only be answered "
                         "in an anonymised statistical format (Art. 69(1)).")
        return Decision(APPROVE_STATISTICAL, ["53", "69"], reason, trace, purposes, [], None, notes)

    trace.append({"step": 2, "rule": "Health data request? (Art. 69)", "result": "no",
                  "evidence": ["requested_as = 'health data access application'"]})
    just = detect_justification(req)
    if just:
        trace.append({"step": 3, "rule": "Access application that explains why statistics are not enough? "
                      "(Art. 66(3))", "result": "yes", "evidence": [f"\"{just.evidence}\""]})
        trace.append({"step": 4, "rule": "Other access application?", "result": "not evaluated", "evidence": []})
        reason = (f"{purpose_text} The applicant explains why anonymised statistics are not enough "
                  f"(\"{just.evidence}\"), so pseudonymised data is justified (Art. 66). Access is granted only "
                  "under a data permit (Art. 68) inside a secure processing environment (Art. 73): only the selected "
                  "patients and the requested record types are copied in, and downloads are blocked.")
        return Decision(APPROVE_SPE, ["53", "66", "68", "73"], reason, trace, purposes, [], just, notes)

    trace.append({"step": 3, "rule": "Access application that explains why statistics are not enough? "
                  "(Art. 66(3))", "result": "no", "evidence": ["no statement that anonymised statistics are "
                                                                 "insufficient"]})
    trace.append({"step": 4, "rule": "Other access application -> statistics (Art. 66(2), 69)", "result": "yes",
                  "evidence": []})
    reason = (f"{purpose_text} The application does not explain why anonymised statistics would not be enough, so "
              "pseudonymised records are not justified (Art. 66). It is approved as anonymised statistics instead "
              "(Art. 69).")
    return Decision(APPROVE_STATISTICAL, ["53", "66", "69"], reason, trace, purposes, [], None, notes)
