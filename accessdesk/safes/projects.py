"""Decides REJECT / APPROVE_STATISTICAL / APPROVE_SPE and cites the articles.

Step 1 extracts features from the request text with transparent rules and
keeps the exact phrases as evidence. Step 2 applies the fixed decision order
of the access body. The optional AI helper can add a second opinion, but it
never changes the decision on its own: a disagreement only asks staff to
review, so results stay reproducible.
"""
import re

# Art. 54: prohibited purposes (paraphrased).
PROHIBITED = {
    "insurance": {
        "patterns": [r"insurance premiums?", r"\bpremiums?\b", r"\btariffs?\b", r"underwrit", r"actuarial",
                     r"risk[- ]based pricing", r"\bcredit (?:score|scoring|decision|contract)",
                     r"\bcredit[- ](?:limits?|terms?)\b", r"\brepayment terms?\b", r"\bloan terms?\b",
                     r"\blending decisions?\b", r"\bloans?\b",
                     r"exclude .{0,30}(?:insurance|cover)"],
        "en": "Using health data to set insurance premiums or conditions, or to exclude people from insurance or credit, is prohibited (Art. 54).",
        "de": "Gesundheitsdaten dürfen nicht genutzt werden, um Versicherungsprämien oder -bedingungen festzulegen oder Menschen von Versicherungen oder Krediten auszuschließen (Art. 54).",
        "label_en": "Insurance or credit decisions", "label_de": "Versicherungs- oder Kreditentscheidungen",
    },
    "employment": {
        "patterns": [r"\bemployees?\b", r"\bemployer\b", r"sick leave", r"renew(?:ing)? (?:the |their |our )?contracts?",
                     r"\bhiring\b", r"\brecruit", r"job applicants?", r"job offers?", r"\bdismiss",
                     r"\bpromotion of staff", r"\bfixed[- ]term (?:staff|employees?|workers?)\b",
                     r"\b(?:staff|employees?|workers?) to keep\b",
                     r"\bdecide which .{0,40}(?:staff|employees?|workers?)\b"],
        "requires": r"contract|hiring|recruit|job|sick leave|dismiss|promot|performance|list|who has|decid|select",
        "en": "Using health data for decisions about employees or job applicants is prohibited (Art. 54).",
        "de": "Gesundheitsdaten dürfen nicht für Entscheidungen über Beschäftigte oder Bewerber:innen genutzt werden (Art. 54).",
        "label_en": "Decisions about employees", "label_de": "Entscheidungen über Beschäftigte",
    },
    "marketing": {
        "patterns": [r"advertis", r"\bmarketing\b", r"promotional", r"\bpromote (?:our|the|a|their) (?:product|drug|brand)",
                     r"sales (?:team|target|campaign)", r"target (?:our |the )?(?:campaign|ads)",
                     r"\bbrand communications?\b",
                     r"\braise awareness (?:for|of) .{0,40}\bbrand\b",
                     r"\bposition (?:the |our )?(?:product|brand|drug)\b"],
        "exceptions": [r"post[- ]marketing", r"marketing authori[sz]ation"],
        "requires": r"communicat|awareness|position|advertis|promot|campaign|launch|market|sales|target",
        "en": "Advertising and marketing are prohibited purposes (Art. 54).",
        "de": "Werbung und Marketing sind verbotene Zwecke (Art. 54).",
        "label_en": "Advertising or marketing", "label_de": "Werbung oder Marketing",
    },
    "harmful_products": {
        "patterns": [r"nicotine", r"tobacco", r"cigarettes?", r"\bvap(?:e|es|ing)\b", r"alcoholic (?:beverages?|drinks?)",
                     r"\bspirits\b", r"\bbeer\b", r"\bliquor\b", r"\bweapons?\b", r"firearms?", r"gambling", r"\bbetting\b"],
        "requires": r"develop|flavou?r|product|launch|sell|position|brand|market|consumer",
        "exceptions": [r"cessation", r"quit(?:ting)?\b", r"stop smoking", r"prevent(?:ion|ing)? of (?:smoking|alcohol)"],
        "en": "Developing or promoting products that harm health, such as tobacco and nicotine products, alcohol or weapons, is prohibited (Art. 54).",
        "de": "Die Entwicklung oder Vermarktung gesundheitsschädlicher Produkte wie Tabak- und Nikotinprodukte, Alkohol oder Waffen ist verboten (Art. 54).",
        "label_en": "Harmful products (tobacco, nicotine, alcohol …)", "label_de": "Schädliche Produkte (Tabak, Nikotin, Alkohol …)",
    },
    "detrimental": {
        "patterns": [r"match(?:ing)? (?:the |these |their )?(?:records|data) (?:with|against)", r"\b(?:employee|customer|client|member) list",
                     r"see who (?:has|have|is)", r"identify (?:which|who|the) (?:individual|person|people|patients|customers|employees)",
                     r"re-?identif", r"black-?list", r"deny (?:them|access|treatment|service)"],
        "en": "Taking decisions that harm individuals or groups based on their health data is prohibited (Art. 54).",
        "de": "Entscheidungen, die Einzelnen oder Gruppen aufgrund ihrer Gesundheitsdaten schaden, sind verboten (Art. 54).",
        "label_en": "Decisions against individuals", "label_de": "Entscheidungen gegen Einzelpersonen",
    },
}

REIDENTIFY = [r"match(?:ing)? (?:the |these |their )?(?:records|data) (?:with|against)", r"(?:employee|customer|client|member) list",
              r"see who", r"re-?identif", r"identify (?:which|who)"]

# Art. 53: allowed purposes, used to explain an approval.
ALLOWED = [
    ("research", r"\bresearch\w*|\bstud(?:y|ies)\b|epidemiolog\w*|investigat\w*", "Research", "Forschung"),
    ("public_health", r"public health|prevention|surveillance|health authorit\w*", "Public health", "öffentliche Gesundheit"),
    ("policy", r"policy|quality programme|quality program|quality in healthcare|quality improvement|improv(?:e|ing) care|care pathways?|guidelines?|treatment gap", "Policy-making and improving care", "Gesundheitspolitik und Versorgungsqualität"),
    ("statistics", r"official statistics|statistics office|health report|national statistics", "Official statistics", "amtliche Statistik"),
    ("education", r"teaching|education|curricul\w*|training (?:of|for) (?:students|gps|doctors|physicians)|module", "Teaching", "Lehre"),
    ("innovation", r"\btrain(?:s|ing)? (?:and validate )?(?:a |the |our )?(?:model|algorithm)|machine learning|prediction (?:model|software)|\bai\b|algorithm", "Training and testing algorithms", "Training und Test von Algorithmen"),
]

JUSTIFIES_RECORDS = [r"(?:aggregates?|aggregated data|statistics|summary data) (?:are|is|would be) not (?:enough|sufficient)",
                     r"\binsufficient\b", r"individual[- ]level", r"patient[- ]level", r"record[- ]level",
                     r"cannot be answered with (?:statistics|aggregates)", r"longitudinal (?:individual|patient)"]

ORG_TYPES = [
    ("insurance", r"versicherung|insurance|assurance|insurer|krankenkasse"),
    ("bank", r"\bbank(?:s|ing)?\b|credit unions?|credit institutions?"),
    ("marketing", r"marketing|advertis|agency|communications|media\b|\bpr\b"),
    ("employer_hr", r"\bhr\b|human resources|people\s*(?:&|and)\s*culture|talent|personnel|personal(?:abteilung)?"),
    ("harmful_industry", r"tobacco|nicotine|pouch|spirits|brewery|vape|distiller"),
    ("public_authority", r"ministry|federal|national statistics|statistics office|authority|agency for health|bundesministerium"),
    ("research", r"universit|institute|research|cancer cent|academ|hospital|clinic|klinikum|centre for|center for|practice"),
    ("company", r"gmbh|\bag\b|ltd|inc\b|company|spin-off|corp"),
]
ORG_LABELS = {
    "insurance": ("Insurer", "Versicherung"), "marketing": ("Marketing company", "Marketingfirma"),
    "bank": ("Bank or credit institution", "Bank oder Kreditinstitut"),
    "employer_hr": ("Employer (HR)", "Arbeitgeber (Personalabteilung)"),
    "harmful_industry": ("Tobacco/alcohol industry", "Tabak-/Alkoholindustrie"),
    "public_authority": ("Public authority", "Behörde"), "research": ("Research / healthcare", "Forschung / Versorgung"),
    "company": ("Company", "Unternehmen"), "unknown": ("Unknown", "Unbekannt"),
}
SUSPICIOUS_ORGS = {"insurance", "bank", "marketing", "employer_hr", "harmful_industry"}

ARTICLE_TITLES = {
    "53": ("Purposes for which health data may be reused", "Zulässige Zwecke der Sekundärnutzung"),
    "54": ("Prohibited purposes", "Verbotene Zwecke"),
    "66": ("Data minimisation: anonymised first, pseudonymised only if justified", "Datenminimierung: zuerst anonymisiert, pseudonymisiert nur wenn begründet"),
    "67": ("Health data access application", "Antrag auf Datenzugang"),
    "68": ("Data permit", "Datengenehmigung"),
    "69": ("Health data request (anonymised statistics)", "Datenanfrage (anonymisierte Statistik)"),
    "71": ("Right to opt out", "Widerspruchsrecht"),
    "73": ("Secure processing environment", "Sichere Verarbeitungsumgebung"),
}


def _find(patterns, text, field):
    hits = []
    for p in patterns:
        for m in re.finditer(p, text, re.I):
            hits.append({"phrase": text[m.start():m.end()], "field": field, "start": m.start(), "end": m.end()})
    return hits


def org_type(org: str):
    for t, p in ORG_TYPES:
        if re.search(p, org, re.I):
            return t
    return "unknown"


def analyze(request):
    purpose = request.get("purpose", "")
    question = request.get("question", "")
    fields = {"purpose": purpose, "question": question}
    prohibited = []
    for cat, spec in PROHIBITED.items():
        hits = []
        for fname, text in fields.items():
            hits += _find(spec["patterns"], text, fname)
        if not hits:
            continue
        full = purpose + " " + question
        if any(re.search(e, full, re.I) for e in spec.get("exceptions", [])) and cat == "harmful_products":
            continue
        if spec.get("exceptions"):
            hits = [h for h in hits if not any(re.search(e, fields[h["field"]][max(0, h["start"] - 10):h["end"] + 20], re.I)
                                               for e in spec["exceptions"])]
        if spec.get("requires") and not re.search(spec["requires"], full, re.I):
            continue
        if hits:
            prohibited.append({"category": cat, "evidence": hits, "label_en": spec["label_en"], "label_de": spec["label_de"]})
    allowed = []
    org = request.get("applicant", {}).get("organisation", "")
    for field, text in (("purpose", purpose), ("organisation", org)):
        for key, pat, en, de in ALLOWED:
            hits = _find([pat], text, field)
            if hits:
                allowed.append({"category": key, "en": en, "de": de, "evidence": hits[:2]})
        if allowed:
            break   # the purpose text wins; the organisation is only a fallback
    justification = _find(JUSTIFIES_RECORDS, purpose, "purpose") + _find(JUSTIFIES_RECORDS, question, "question")
    reid = _find(REIDENTIFY, purpose, "purpose") + _find(REIDENTIFY, question, "question")
    return {
        "prohibited": prohibited,
        "allowed": allowed,
        "justifies_records": justification,
        "reidentification": reid,
        "org_type": org_type(request.get("applicant", {}).get("organisation", "")),
    }


def _join(items, lang):
    """'Research', 'Public health' -> 'Research and public health'. Uses
    'as well as' / 'sowie' when an item already contains 'and' / 'und'."""
    items = list(dict.fromkeys(items))
    if lang == "en":
        items = items[:1] + [i[0].lower() + i[1:] if not i[:2].isupper() else i for i in items[1:]]
    if len(items) <= 1:
        out = "".join(items)
        return out[:1].upper() + out[1:]
    word = " und " if lang == "de" else " and "
    last = " sowie " if lang == "de" else " as well as "
    sep = last if any(word in i for i in items) else word
    out = ", ".join(items[:-1]) + sep + items[-1]
    return out[0].upper() + out[1:]


def decide(request, features):
    kind = (request.get("requested_as") or "").lower()
    if not kind:
        kind = "health data access application" if "pseudonym" in (request.get("requested_format") or "").lower() else "health data request"
    trace = []
    allowed = features["allowed"]
    p_en = _join([a["en"] for a in allowed], "en") or "The stated purpose"
    p_de = _join([a["de"] for a in allowed], "de") or "Der angegebene Zweck"
    plural = len({a["en"] for a in allowed}) > 1 or (len(allowed) == 1 and allowed[0]["category"] == "policy")
    verb_en, verb_de = ("are allowed purposes", "sind erlaubte Zwecke") if plural else ("is an allowed purpose", "ist ein erlaubter Zweck")

    # 1. prohibited purpose
    if features["prohibited"]:
        cat = features["prohibited"][0]
        spec = PROHIBITED[cat["category"]]
        trace.append({"step": 1, "rule": "Prohibited purpose? (Art. 54)", "result": True,
                      "evidence": [h["phrase"] for p in features["prohibited"] for h in p["evidence"]]})
        reason_en, reason_de = spec["en"], spec["de"]
        if features["reidentification"]:
            reason_en += " Matching the data with a list of named people would also re-identify them, which Art. 61(3) forbids."
            reason_de += " Ein Abgleich mit einer Namensliste würde Personen außerdem re-identifizieren; das verbietet Art. 61(3)."
        return {"decision": "REJECT", "articles": ["54"], "reason_en": reason_en, "reason_de": reason_de,
                "kind": kind, "trace": trace}
    trace.append({"step": 1, "rule": "Prohibited purpose? (Art. 54)", "result": False, "evidence": []})

    # 2. health data request -> statistics
    if "request" in kind and "access" not in kind:
        trace.append({"step": 2, "rule": "Health data request? (Art. 69)", "result": True, "evidence": [kind]})
        return {"decision": "APPROVE_STATISTICAL", "articles": ["53", "69"],
                "reason_en": f"{p_en} {verb_en} (Art. 53). Statistics answer the question (Art. 69).",
                "reason_de": f"{p_de} {verb_de} (Art. 53). Anonymisierte Statistik beantwortet die Frage (Art. 69).",
                "kind": kind, "trace": trace}
    trace.append({"step": 2, "rule": "Health data request? (Art. 69)", "result": False, "evidence": [kind]})

    # 3. access application that explains why statistics are not enough
    just = features["justifies_records"]
    if just:
        trace.append({"step": 3, "rule": "Explains why statistics are not enough? (Art. 66)", "result": True,
                      "evidence": [h["phrase"] for h in just]})
        return {"decision": "APPROVE_SPE", "articles": ["53", "66", "68", "73"],
                "reason_en": (f"{p_en} {verb_en} (Art. 53). The applicant explains why statistics are not enough, "
                              "so pseudonymised data is justified (Art. 66). Access only under a data permit inside a "
                              "secure processing environment, without download (Art. 68, 73)."),
                "reason_de": (f"{p_de} {verb_de} (Art. 53). Der Antrag begründet, warum Statistik nicht reicht, daher "
                              "sind pseudonymisierte Daten gerechtfertigt (Art. 66). Zugang nur mit Datengenehmigung in "
                              "einer sicheren Verarbeitungsumgebung, ohne Download (Art. 68, 73)."),
                "kind": kind, "trace": trace}
    trace.append({"step": 3, "rule": "Explains why statistics are not enough? (Art. 66)", "result": False, "evidence": []})

    # 4. any other access application -> statistics
    trace.append({"step": 4, "rule": "Other access application → statistics (Art. 66, 69)", "result": True, "evidence": []})
    return {"decision": "APPROVE_STATISTICAL", "articles": ["53", "66", "69"],
            "reason_en": (f"{p_en} {verb_en} (Art. 53). Statistics answer the question, so pseudonymised records are "
                          "not justified (Art. 66). Approved as statistics instead (Art. 69)."),
            "reason_de": (f"{p_de} {verb_de} (Art. 53). Statistik beantwortet die Frage, daher sind pseudonymisierte "
                          "Einzeldaten nicht gerechtfertigt (Art. 66). Stattdessen als Statistik genehmigt (Art. 69)."),
            "kind": kind, "trace": trace}
