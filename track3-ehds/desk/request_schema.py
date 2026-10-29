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
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RequestError([f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"]) from exc
    if not isinstance(raw, dict):
        raise RequestError(["the request must be a JSON object"])

    errors: list[str] = []
    req = dict(raw)
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
        ra = REQUESTED_AS.get(_norm(req["requested_as"]))
        if not ra:
            errors.append("'requested_as' must be 'health data request' or 'health data access application'")
        else:
            req["requested_as"] = ra
    if isinstance(req.get("requested_format"), str) and req["requested_format"].strip():
        rf = REQUESTED_FORMAT.get(_norm(req["requested_format"]))
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
