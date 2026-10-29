"""Assembles formal decision letters from the reviewed bilingual templates."""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .safes.projects import ARTICLE_TITLES

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "letter_texts.json"
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
TABLE_NAMES = {
    "conditions": {"de": "Diagnosen", "en": "conditions"},
    "medications": {"de": "Medikation", "en": "medications"},
    "observations": {"de": "Messwerte", "en": "measurements"},
    "encounters": {"de": "Kontakte", "en": "encounters"},
    "patients": {"de": "Stammdaten", "en": "demographics"},
}


def build(case, lang):
    if lang not in ("de", "en"):
        raise ValueError("lang must be de or en")
    with TEMPLATE_PATH.open(encoding="utf-8") as stream:
        texts = json.load(stream)
    summary, result = case["summary"], case["result"]
    request, decision = result["request"], result["decision"]
    kind = summary["kind"]
    decision_name = decision["decision"]
    review = case["reviews"][-1] if case["reviews"] else None
    decision_time = _decision_time(case, request["id"])
    submitted = _format_date(request.get("submitted"), lang)
    decision_date = _format_date(decision_time, lang)
    draft = summary["status"] in ("held_identity", "review_needed")
    hold_reason = result["delivery"].get(lang, "")
    applicant = request.get("applicant") or {}
    features = result["features"]

    header = {
        "lang": lang,
        "reference": texts["reference_format"].format(id=request["id"]),
        "date": decision_date,
        "authority": texts["authority"][lang],
        "authority_address": texts["authority_address"][lang],
        "demo_notice": texts["demo_notice"][lang],
        "draft": draft,
        "draft_notice": texts["draft_notice"][lang].format(hold_reason=hold_reason) if draft else None,
        "title": texts["document_title"][lang],
        "labels": {name: value[lang] for name, value in texts["labels"].items()},
    }
    subject = texts["subject"][kind][lang].format(submitted=submitted)
    operative_key = "APPROVE_SPE" if decision_name == "APPROVE_SPE" else f"{decision_name}_{kind}"
    operative = texts["operative"][operative_key][lang]

    reasoning = [_format(
        texts["reasoning"]["facts"][lang],
        submitted=submitted,
        kind=texts["kinds"][kind][lang],
        applicant_name=applicant.get("name", ""),
        organisation=applicant.get("organisation", ""),
        purpose=request.get("purpose", ""),
        question=request.get("question", ""),
    )]
    prohibited = features.get("prohibited") or []
    if prohibited:
        base_decision = case["result"]["decision"]
        evidence = _quotes(
            [item["phrase"] for entry in prohibited for item in entry.get("evidence", [])][:3],
            lang,
        )
        reasoning.append(_format(
            texts["reasoning"]["purpose_prohibited"][lang],
            reason=base_decision["reason_de" if lang == "de" else "reason_en"],
            evidence=evidence,
        ))
    elif features.get("allowed"):
        categories = "; ".join(dict.fromkeys(
            texts["categories"][entry["category"]][lang]
            for entry in features["allowed"]
            if entry["category"] in texts["categories"]
        ))
        reasoning.append(_format(
            texts["reasoning"]["purpose_allowed"][lang],
            categories=categories,
        ))
    else:
        reasoning.append(texts["reasoning"]["purpose_allowed_unspecified"][lang])

    if decision_name != "REJECT":
        form_key = (
            "form_request" if kind == "request"
            else "form_application_spe" if decision_name == "APPROVE_SPE"
            else "form_application_statistics"
        )
        form_text = texts["reasoning"][form_key][lang]
        if form_key == "form_application_spe":
            evidence = _quotes(
                [item["phrase"] for item in features.get("justifies_records", [])[:3]],
                lang,
            )
            form_text = _format(form_text, evidence=evidence)
        reasoning.append(form_text)

    manifest = result.get("spe")
    released = result.get("released")
    annex = None
    conditions = []
    if decision_name == "APPROVE_STATISTICAL":
        reasoning.append(_format(
            texts["reasoning"]["data_protection_statistics"][lang],
            opted_out=result["opted_out_excluded"],
        ))
        conditions = [_format(item[lang]) for item in texts["conditions"]["statistics"]]
        if case["visible_to_applicant"]:
            annex = {
                "type": "statistics",
                "group_dims": released["group_dims"],
                "measures": released["measures"],
                "rows": released["rows"],
            }
    elif decision_name == "APPROVE_SPE":
        copied, not_copied = _tables(manifest, lang)
        reasoning.append(_format(
            texts["reasoning"]["data_protection_spe"][lang],
            cohort_size=manifest["cohort_size"],
            tables=", ".join(copied),
            not_tables=", ".join(not_copied),
        ))
        values = {
            "tables": ", ".join(copied),
            "persons": ", ".join(manifest["persons_with_access"]),
            "expires": manifest["expires"],
        }
        conditions = [_format(item[lang], **values) for item in texts["conditions"]["spe"]]
        if case["visible_to_applicant"]:
            annex = {
                "type": "permit",
                "permit_id": manifest["permit_id"],
                "cohort_size": manifest["cohort_size"],
                "tables": copied,
                "not_tables": not_copied,
                "persons": manifest["persons_with_access"],
                "expires": manifest["expires"],
            }
    else:
        reasoning.append(texts["reasoning"]["no_processing"][lang])

    identity_status = result["who"]["status"]
    reasoning.append(_format(
        texts["reasoning"]["identity"][lang],
        identity_status=texts["identity_status"][identity_status][lang],
    ))
    if review and review["action"] == "reject":
        reasoning.append(_format(
            texts["reasoning"]["review_rejection"][lang],
            review_reason=review["reason"],
        ))
    reasoning.append(texts["reasoning"]["publication"][lang])

    signature = []
    if review:
        signature.append(_format(
            texts["signature"]["reviewed"][lang],
            reviewer=review["reviewer"],
            review_date=_format_date(review["reviewed_at"], lang),
            review_reason=review["reason"],
        ))
    else:
        signature.append(_format(
            texts["signature"]["automated"][lang],
            date=decision_date,
        ))
    latest_entry = _latest_audit_entry(case, request["id"])
    signature.append(_format(
        texts["signature"]["checksum"][lang],
        audit_hash=latest_entry["hash"] if latest_entry else "",
    ))
    articles = [
        {"n": article, "title": ARTICLE_TITLES[article][1 if lang == "de" else 0]}
        for article in decision["articles"]
    ]
    return {
        "header": header,
        "applicant": {
            "name": applicant.get("name", ""),
            "organisation": applicant.get("organisation", ""),
            "country": applicant.get("country", ""),
        },
        "subject": subject,
        "operative": operative,
        "reasoning": reasoning,
        "conditions": conditions,
        "annex": annex,
        "remedy": texts["remedy"][lang],
        "signature": signature,
        "articles": articles,
    }


def _format(template, **values):
    return template.format(**values)


def _quotes(phrases, lang):
    left, right = ("„", "“") if lang == "de" else ("“", "”")
    return "; ".join(f"{left}{phrase}{right}" for phrase in phrases)


def _tables(manifest, lang):
    copied, not_copied = [], []
    for table in manifest["tables_copied"]:
        name = TABLE_NAMES[table["table"]][lang]
        if table.get("note"):
            codes = re.findall(r"\d{1,6}-\d", table["note"])
            if codes:
                name += f" (LOINC {', '.join(codes)})"
        copied.append(name)
    not_copied = [TABLE_NAMES[table][lang] for table in manifest["tables_not_copied"]]
    return copied, not_copied


def _latest_audit_entry(case, request_id):
    audit_path = Path(case.get("audit_path", ""))
    if audit_path.is_file():
        with audit_path.open(encoding="utf-8") as stream:
            entries = [json.loads(line) for line in stream if line.strip()]
        return next((entry for entry in reversed(entries) if entry["request_id"] == request_id), None)
    return None


def _decision_time(case, request_id):
    review = case["reviews"][-1] if case["reviews"] else None
    if review:
        value = review["reviewed_at"]
    else:
        audit_path = Path(case.get("audit_path", ""))
        entries = []
        if audit_path.is_file():
            with audit_path.open(encoding="utf-8") as stream:
                entries = [json.loads(line) for line in stream if line.strip()]
        entry = next(
            (
                item for item in reversed(entries)
                if item["request_id"] == request_id and item["action"].startswith("result_")
            ),
            None,
        )
        value = (entry or {}).get("time")
    return value or case["result"]["request"].get("submitted") or datetime.now(timezone.utc).isoformat()


def _format_date(value, lang):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return str(value or "")
    if lang == "de":
        return parsed.strftime("%d.%m.%Y")
    return f"{parsed.day} {MONTHS[parsed.month - 1]} {parsed.year}"
