"""Validation of incoming requests (same JSON format as requests/R01.json ... R10.json)."""
from __future__ import annotations

import json

MAX_BYTES = 64 * 1024
MAX_DEFINITIONS = 40
MAX_TEXT = 4000

REQUESTED_AS = {"health data request": "health data request",
                "health data access application": "health data access application"}
REQUESTED_FORMAT = {"anonymised statistics": "anonymised statistics",
                    "anonymized statistics": "anonymised statistics",
                    "pseudonymised records": "pseudonymised records",
                    "pseudonymized records": "pseudonymised records"}


class RequestError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _norm(s: str) -> str:
    return " ".join(str(s).strip().lower().split())


def parse_request(raw) -> dict:
    """Accept a dict or JSON text; return a normalised copy or raise RequestError."""
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > MAX_BYTES:
            raise RequestError([f"request is larger than {MAX_BYTES // 1024} KB"])
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RequestError(["the request must be UTF-8 encoded JSON"]) from exc
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise RequestError([f"request is larger than {MAX_BYTES // 1024} KB"])
        try:
            raw = json.loads(raw.lstrip("\ufeff"))  # files saved with a byte-order mark
        except json.JSONDecodeError as exc:
            raise RequestError([f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"]) from exc
    raw, notes = _lenient(raw)
    if not isinstance(raw, dict):
        raise RequestError(["the request must be a JSON object"])

    errors: list[str] = []
    req = dict(raw)
    if notes:
        req["normalisation_notes"] = notes
    for key in ("requested_as", "requested_format", "purpose", "question"):
        val = req.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"'{key}' is required and must be a non-empty string")
        elif len(val) > MAX_TEXT:
            errors.append(f"'{key}' is longer than {MAX_TEXT} characters")
    defs = req.get("definitions")
    if not isinstance(defs, list) or not all(isinstance(d, str) for d in defs):
        errors.append("'definitions' is required and must be a list of strings")
    elif len(defs) > MAX_DEFINITIONS:
        errors.append(f"at most {MAX_DEFINITIONS} definitions are supported")
    elif any(len(d) > MAX_TEXT for d in defs):
        errors.append(f"each definition must be shorter than {MAX_TEXT} characters")
    if isinstance(req.get("requested_as"), str) and req["requested_as"].strip():
        ra = REQUESTED_AS.get(_norm(req["requested_as"])) or _guess_requested_as(req["requested_as"])
        if not ra:
            errors.append("'requested_as' must be 'health data request' or 'health data access application'")
        else:
            req["requested_as"] = ra
    if isinstance(req.get("requested_format"), str) and req["requested_format"].strip():
        rf = REQUESTED_FORMAT.get(_norm(req["requested_format"])) or _guess_format(req["requested_format"])
        if not rf:
            errors.append("'requested_format' must be 'anonymised statistics' or 'pseudonymised records'")
        else:
            req["requested_format"] = rf
    applicant = req.get("applicant", {})
    if applicant is not None and not isinstance(applicant, dict):
        errors.append("'applicant' must be an object with name, organisation and country")
    if "id" in req and not isinstance(req["id"], (str, int)):
        errors.append("'id' must be a string")
    if errors:
        raise RequestError(errors)
    req["id"] = str(req.get("id") or "UNNUMBERED")
    req["applicant"] = applicant or {}
    req["definitions"] = [d.strip() for d in defs if d.strip()]
    return req


# ---------------------------------------------------------------------- lenient intake for unexpected uploads
_KEY_ALIASES = {
    "requested_as": ("requested_as", "requestedas", "requested as", "request_type", "requesttype", "type", "kind"),
    "requested_format": ("requested_format", "requestedformat", "requested format", "format", "output_format"),
    "purpose": ("purpose", "aim", "objective", "reason"),
    "question": ("question", "research_question", "researchquestion", "query"),
    "definitions": ("definitions", "definition", "defs", "terms"),
    "applicant": ("applicant", "requester", "requestor"),
    "id": ("id", "request_id", "requestid"),
}


def _guess_requested_as(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in ("access", "application", "permit")):
        return "health data access application"
    if "request" in t:
        return "health data request"
    return None


def _guess_format(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in ("record", "pseudonym", "individual", "patient-level", "microdata")):
        return "pseudonymised records"
    if any(w in t for w in ("stat", "aggregat", "anonym", "table", "count")):
        return "anonymised statistics"
    return None


def _lenient(raw):
    """Accept the usual variations of the challenge format (wrapped or listed requests, other key spellings,
    definitions as one text block, a missing type or format) and say what was normalised."""
    notes: list[str] = []
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        notes.append(f"the file contained a list of {len(raw)} requests; the first one was used")
        raw = raw[0]
    if isinstance(raw, dict) and "purpose" not in raw:
        inner = next((v for k, v in raw.items() if k.lower() in ("request", "application", "data") and isinstance(v, dict)),
                     None)
        if inner is not None:
            notes.append("the request was wrapped in another object and was unwrapped")
            raw = inner
    if not isinstance(raw, dict):
        return raw, notes
    lower = {str(k).strip().lower().replace("-", "_"): v for k, v in raw.items()}
    out = dict(raw)
    for key, aliases in _KEY_ALIASES.items():
        if key not in out:
            alias = next((a for a in aliases if a in lower), None)
            if alias is not None:
                out[key] = lower[alias]
                if alias != key:
                    notes.append(f"'{alias}' was read as '{key}'")
    defs = out.get("definitions")
    if isinstance(defs, str):
        out["definitions"] = [d.strip(" -•\t") for d in defs.splitlines() if d.strip(" -•\t")]
        notes.append("the definitions were given as one text and were split into lines")
    elif isinstance(defs, list):
        out["definitions"] = [str(d) for d in defs if isinstance(d, (str, int, float)) and str(d).strip()]
    fmt, kind = out.get("requested_format"), out.get("requested_as")
    if not (isinstance(kind, str) and kind.strip()) and isinstance(fmt, str) and fmt.strip():
        out["requested_as"] = ("health data access application" if _guess_format(fmt) == "pseudonymised records"
                               else "health data request")
        notes.append(f"'requested_as' was missing and was set to '{out['requested_as']}' from the format")
    if not (isinstance(fmt, str) and fmt.strip()) and isinstance(out.get("requested_as"), str):
        out["requested_format"] = "anonymised statistics"
        notes.append("'requested_format' was missing and was set to 'anonymised statistics'")
    return out, notes
