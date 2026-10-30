"""Prompts and JSON schemas for the optional AI helper (lead-authored).

The AI only ever sees request text and the list of codes that occur in the
data, never patient records. It has four narrow jobs, each with a strict JSON
schema (structured outputs, output_config.format):

1. draft     free-text question (DE/EN) -> formal request in the house style
2. purpose   second opinion on the purpose; can only send a case to review
3. term      term -> codes, chosen from an enum of codes present in the data
4. explain   plain-language explanation of a decision for the applicant

Every AI answer is checked afterwards by deterministic code: drafts go
through the same parser and pre-check as typed requests, codes must exist in
the data, quotes must appear verbatim in the request. Change prompt text only
after re-checking it; accessdesk/ai.py must use these constants verbatim.
"""
import json
import os

from .plan import terminology

MODEL = os.environ.get("ACCESSDESK_AI_MODEL", "claude-opus-5-5")
EFFORT = {"draft": "medium", "purpose": "low", "term": "low", "explain": "low"}
MAX_TOKENS = {"draft": 2000, "purpose": 800, "term": 400, "explain": 600}

REQUEST_KINDS = ["health data request", "health data access application"]


# ---------------------------------------------------------------- code list
def allowed_codes(store):
    """Codes the AI may use: every code in the data, ICD-10 categories present
    in the data and the code-list prefixes that match at least one data code."""
    data = {(s, c) for (s, c) in store.descriptions}
    codes = {c for (s, c) in data}
    codes |= {c.split(".")[0] for (s, c) in data if s == "icd10"}
    for system, code, _label, _syns in terminology.CODEBOOK:
        for prefix in code.split("|"):
            if any(s == system and c.startswith(prefix) for (s, c) in data):
                codes.add(prefix)
    return sorted(codes)


def code_list_text(store):
    """Human-readable code list for prompts, built from the data at runtime."""
    lines = []
    icd = sorted(c for (s, c) in store.descriptions if s == "icd10")
    for cat in sorted({c.split(".")[0] for c in icd}):
        subs = [c for c in icd if c.split(".")[0] == cat]
        labels = [store.descriptions[("icd10", c)] for c in subs if store.descriptions[("icd10", c)]]
        label = terminology.label_for("icd10", cat) or (labels[0] if labels else "")
        if labels:
            members = "; ".join(f"{c} {store.descriptions[('icd10', c)]}" for c in subs)
            lines.append(f"ICD-10 {cat}: {label} (in the data: {members})")
        else:
            lines.append(f"ICD-10 {cat}: {label} (in the data: {', '.join(subs)}; only as main diagnosis "
                         "primary_icd10 of inpatient stays)")
    atc = sorted(c for (s, c) in store.descriptions if s == "atc")
    for system, code, label, _syns in terminology.CODEBOOK:
        if system == "atc" and "|" not in code and any(c.startswith(code) and c != code for c in atc):
            members = ", ".join(f"{c} {store.descriptions[('atc', c)]}" for c in atc if c.startswith(code))
            lines.append(f"ATC {code}: {label} (in the data: {members})")
    for c in atc:
        lines.append(f"ATC {c}: {store.descriptions[('atc', c)]}")
    for (s, c), label in sorted(store.descriptions.items()):
        if s == "loinc":
            lines.append(f"LOINC {c}: {label}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 1 draft
DRAFT_SYSTEM = """You help researchers and public bodies write a request to the Austrian Health Data Access Body (European Health Data Space, Regulation (EU) 2025/327). You turn their question, written in German or English, into a formal request in English that the access body's rule engine can read. You never see patient data and must not ask for any.

Write the definitions ONLY with the sentence patterns below, exactly as shown, replacing the <...> parts. The rule engine does not understand other phrasings.

Population and attributes
- Adult = aged 18 or older on 31 December 2025.
- <Name> = aged <a>-<b> on 31 December 2025.   (also: aged <n> or older on 31 December 2025 / aged <n> or younger on 31 December 2025)
- Women = sex 'female'.   /   Men = sex 'male'.
- Age bands on 31 December 2025: <a>-<b>, <c>-<d>, <e>+.

Diagnoses, drugs and measurements (codes only from the code list)
- <Condition> = any condition with an ICD-10 code starting with <code>.   (two codes: starting with <code> or <code>)
- <Drug class> = ATC code starting with <code>.   (two codes: starting with <code> or <code>)
- A medication is active on 31 December 2025 if start_date is on or before that day and end_date is empty or on or after that day.   (add this sentence whenever a measure says "active")
- Use the latest <measurement> (LOINC <code>) per patient; patients without a <measurement> are left out.

Hospital stays and visits
- Inpatient stay = encounter with type 'inpatient'.   (emergency visits: type 'emergency'; outpatient visits: type 'outpatient')
- <Name> stay = inpatient stay whose main diagnosis (primary_icd10) starts with <code>.
- Count stays (not patients) whose start_date is in <year>.   (or: whose start_date is between <year> and <year>)
- Length of stay = end_date minus start_date in days.

Shares and cohorts
- <Share> = <numerator group> / <denominator group> × 100, one decimal.
- Cohort = adults with <condition> who have at least one <measurement> value (LOINC <code>).   (only for access applications)

The last definition is always the report sentence:
- Report per <region | hospital | age band | sex | year>[ and <second dimension>]: <measure>, <measure> and <measure>, one decimal.
  Measures look like: "adults with <condition>", "how many of them have <X>", "how many of them have no active <drug>", "that share in %", "% with an active <drug>", "adults with <condition> who have a <measurement> value and their mean <measurement>", "<name> stays".
  Thresholds on the latest measurement value ARE supported: "how many of them have a <measurement> above <number>" (also: below, at least). Example: "Report per region: women with breast cancer who have a BMI value, how many of them have a BMI above 30, and that share in %, one decimal."
- For an access application that needs individual-level records: Report the size of the cohort you would make available.

Rules
1. Use only codes from the code list. If the question needs data that is not in the data set (for example income, smoking status, deaths or a laboratory test that is not listed), do not invent a code: list it under "unsupported".
2. Groups can only be region (the 9 Austrian federal states), hospital (data_holder), age band, sex, or year (for stays). List any other grouping under "unsupported".
3. requested_as is "health data request" (anonymised statistics) unless the user clearly needs individual-level records inside a secure processing environment; then it is "health data access application".
4. Keep the user's stated purpose faithfully, in English. Never rephrase a purpose to make it sound more acceptable and never add reasons the user did not give. If record-level data is wanted without a reason why statistics are not enough, say in "assumptions" that such a reason is required.
5. If the purpose may be prohibited under Article 54 (decisions against people, insurance or credit terms, job decisions, advertising or marketing, harmful products such as tobacco, alcohol or weapons), keep it as stated and add a warning to "assumptions". Do not try to make the request pass.
6. "question" restates the user's question in one English sentence.
7. Write "assumptions" and "unsupported" in the user's language ({lang}), as short sentences, one per choice you made (for example the age bands or the code you chose)."""


def draft_schema():
    return {
        "type": "object",
        "properties": {
            "requested_as": {"type": "string", "enum": REQUEST_KINDS},
            "purpose": {"type": "string"},
            "question": {"type": "string"},
            "definitions": {"type": "array", "items": {"type": "string"}},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "unsupported": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["requested_as", "purpose", "question", "definitions", "assumptions", "unsupported"],
        "additionalProperties": False,
    }


def draft_messages(store, text, lang, purpose=None):
    lang_name = "German" if lang == "de" else "English"
    user = f"<code_list>\n{code_list_text(store)}\n</code_list>\n\n<user_question>\n{text.strip()}\n</user_question>"
    if purpose:
        user += f"\n\n<stated_purpose>\n{purpose.strip()}\n</stated_purpose>"
    return DRAFT_SYSTEM.replace("{lang}", lang_name), user


# ---------------------------------------------------------------- 2 purpose
PURPOSE_SYSTEM = """You assist the Austrian Health Data Access Body under Regulation (EU) 2025/327 (European Health Data Space). Read one data request and judge only its purpose. You never see patient data.

Article 54 prohibits seeking access to and processing health data for:
(a) taking decisions detrimental to a natural person or a group of natural persons based on their electronic health data;
(b) taking decisions in relation to a natural person or a group of natural persons in relation to job offers, offering less favourable terms in the provision of goods or services, including exclusion from the benefit of an insurance or credit contract, the modification of their contributions and insurance premiums or conditions of loans, or any other decisions that discriminate against them on the basis of the health data obtained;
(c) carrying out advertising or marketing activities;
(d) developing products or services that may harm individuals, public health or society at large, such as illicit drugs, alcoholic beverages, tobacco and nicotine products, weaponry, or products or services designed or modified to create addiction;
(e) carrying out activities in conflict with ethical provisions laid down in national law.

Article 53(1) allows: (a) public interest in public or occupational health; (b) policymaking and regulatory activities of public sector bodies; (c) official statistics; (d) education or teaching in health or care; (e) scientific research related to health or care, including (i) development and innovation of products or services and (ii) training, testing and evaluating algorithms; (f) improving the delivery of care and treatment.

Look past friendly wording: consider who the applicant is and what they would do with the result. A pharmaceutical brand team asking where a drug is prescribed most is marketing even if it says "awareness". An employer, insurer or bank asking about diagnoses is suspect even if it says "planning".

statistics_sufficient is true if anonymised aggregate statistics would answer the question, and false only if the purpose genuinely needs individual-level records (for example training a prediction model).
evidence_quote copies the decisive words verbatim from the purpose or the question (at most 20 words); use an empty string if nothing is suspicious.
explanation_en and explanation_de are at most two short sentences each, in plain language."""


def purpose_schema():
    return {
        "type": "object",
        "properties": {
            "prohibited": {"type": "boolean"},
            "category": {"type": "string", "enum": ["none", "detrimental_decisions", "jobs_insurance_credit",
                                                    "advertising_marketing", "harmful_products", "ethics"]},
            "allowed_purposes": {"type": "array",
                                 "items": {"type": "string", "enum": ["a", "b", "c", "d", "e", "e_i", "e_ii", "f"]}},
            "statistics_sufficient": {"type": "boolean"},
            "evidence_quote": {"type": "string"},
            "explanation_en": {"type": "string"},
            "explanation_de": {"type": "string"},
        },
        "required": ["prohibited", "category", "allowed_purposes", "statistics_sufficient", "evidence_quote",
                     "explanation_en", "explanation_de"],
        "additionalProperties": False,
    }


def purpose_messages(request):
    text = json.dumps({k: request.get(k) for k in ("applicant", "requested_as", "purpose", "question", "definitions")},
                      ensure_ascii=False, sort_keys=True, indent=1)
    return PURPOSE_SYSTEM, f"<request>\n{text}\n</request>"


# ---------------------------------------------------------------- 3 term
TERM_SYSTEM = """Map one medical term from a health data request to the codes used in the data set. Choose only from the code list; a code prefix matches all of its sub-codes. If nothing in the list means the same thing, answer system "none" with no codes; never pick a code that is merely related. note is one short English sentence that explains the match."""


def term_schema(store):
    return {
        "type": "object",
        "properties": {
            "system": {"type": "string", "enum": ["icd10", "atc", "loinc", "none"]},
            "codes": {"type": "array", "items": {"type": "string", "enum": allowed_codes(store)}},
            "note": {"type": "string"},
        },
        "required": ["system", "codes", "note"],
        "additionalProperties": False,
    }


def term_messages(store, name, body):
    return TERM_SYSTEM, (f"<code_list>\n{code_list_text(store)}\n</code_list>\n\n"
                         f"<term>\n{name} = {body}\n</term>")


# ---------------------------------------------------------------- 4 explain
EXPLAIN_SYSTEM = """Explain a decision of the Austrian Health Data Access Body to the applicant in plain language (CEFR level B1), once in German and once in English. Use only the facts given. Do not give legal advice, do not change or question the decision, and do not mention numbers that are not given. At most three short sentences per language."""


def explain_schema():
    return {
        "type": "object",
        "properties": {"explanation_de": {"type": "string"}, "explanation_en": {"type": "string"}},
        "required": ["explanation_de", "explanation_en"],
        "additionalProperties": False,
    }


def explain_messages(result):
    dec = result["decision"]
    rel = result.get("released") or {}
    facts = {
        "decision": dec["decision"],
        "request_type": dec.get("kind"),
        "articles": [f"Art. {a['n']}: {a['title_en']}" for a in dec.get("articles_detail", [])],
        "reason_en": dec.get("reason_en"),
        "delivery": (result.get("delivery") or {}).get("en"),
        "hidden_cells": sum((rel.get("gate") or {}).get(k, 0)
                            for k in ("counts_hidden", "pct_suppressed", "means_suppressed")),
        "opted_out_people_excluded": result.get("opted_out_excluded"),
        "cohort_size": (result.get("spe") or {}).get("cohort_size"),
    }
    return EXPLAIN_SYSTEM, f"<decision>\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n</decision>"
