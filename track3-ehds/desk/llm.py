"""Optional LLM fallback planner (off by default).

When the deterministic parser cannot interpret a request, a constrained LLM may propose an IR plan.
- Only request TEXT is sent (requested_as, requested_format, purpose, question, definitions) together
  with the static IR schema. No patient data, no data-derived statistics, no applicant identity.
- The reply must be a JSON IR; it is validated by ir.validate() and checked against the code catalog
  before any query runs. Anything invalid is refused and the case stays "not produced".
- The decision (REJECT / APPROVE_*) is never delegated to the model.

Enable with environment variables:
  DESK_LLM_PROVIDER=anthropic|openai   DESK_LLM_MODEL=<model name>
  ANTHROPIC_API_KEY=... or OPENAI_API_KEY=...
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable

from . import vocabulary as V
from .config import REFERENCE_DATE
from .ir import PlanValidationError, validate
from .parser import InterpretationError

SCHEMA_PROMPT = f"""You translate a health data request into a JSON query plan. Reply with JSON only.
Reference date {REFERENCE_DATE}; age = 2025 - birth year. Data tables: patients(sex female|male, region,
data_holder), conditions(icd10), medications(atc, start_date, end_date), observations(loinc, value, date),
encounters(type inpatient|outpatient|emergency, start_date, data_holder, primary_icd10).
Plan format:
{{"version": 1, "mode": "statistics" | "spe",
 "concepts": {{"<id>": {{"kind": "condition", "label": "...", "icd10": [{{"code": "E11", "match": "prefix"}}]}}
             | {{"kind": "medication", "label": "...", "atc": ["B01AA"]}}
             | {{"kind": "observation", "label": "...", "loinc": "4548-4", "pick": "latest"}}
             | {{"kind": "encounter", "label": "...", "types": ["inpatient"], "start_from": "2025-01-01",
                 "start_to": "2025-12-31", "primary_icd10": ["I50"]}}
             | {{"kind": "set", "label": "...", "expr": <expr>}}}},
 "population": <expr>,
 "dimensions": [{{"type": "region"|"sex"|"data_holder"|"year", "groups": []}} |
                {{"type": "age_band", "groups": [{{"label": "18-49", "min": 18, "max": 49}}, {{"label": "65+", "min": 65, "max": null}}]}}],
 "measures": [{{"id": "m1", "type": "count_patients", "label": "...", "set": <expr>, "visible": true}},
              {{"id": "m2", "type": "count_encounters", "encounter": "<encounter id>", "label": "...", "set": <expr>, "visible": true}},
              {{"id": "m3", "type": "percent", "numerator": "m2", "denominator": "m1", "label": "...", "visible": true}},
              {{"id": "m4", "type": "mean", "observation": "<observation id>", "label": "...", "set": <expr>, "visible": true}}],
 "spe": {{"cohort": <expr>, "record_types": [{{"table": "conditions"}}, {{"table": "observations", "loinc": ["4548-4"]}}]}}}}
<expr> := {{"op": "all"}} | {{"op": "and"|"or", "args": [<expr>, ...]}} | {{"op": "not", "arg": <expr>}}
 | {{"op": "age", "cmp": ">=", "value": 18}} | {{"op": "age_between", "min": 18, "max": 64}}
 | {{"op": "attr", "field": "sex"|"region"|"data_holder", "values": ["female"]}} | {{"op": "ref", "id": "<set id>"}}
 | {{"op": "has_condition", "id": "<id>"}} | {{"op": "has_medication", "id": "<id>", "active": true}}
 | {{"op": "has_observation", "id": "<id>"}} | {{"op": "observation_value", "id": "<id>", "cmp": ">=", "value": "8.0"}}
 | {{"op": "has_encounter", "id": "<id>"}}
Percent numerators/denominators must be earlier count measures (use "visible": false for helper counts).
Use only codes stated in the definitions or standard ICD-10/ATC/LOINC codes. If the request cannot be
expressed exactly in this format, reply {{"error": "<reason>"}} instead of guessing."""

Transport = Callable[[str, str], str]


def request_text_only(req: dict) -> dict:
    """The only information that leaves the desk."""
    return {k: req.get(k) for k in ("requested_as", "requested_format", "purpose", "question", "definitions")}


class LLMPlanner:
    def __init__(self, transport: Transport, label: str):
        self.transport = transport
        self.label = label

    def __call__(self, req: dict, mode: str, catalog: dict, deterministic_error: InterpretationError):
        payload = json.dumps({"mode": mode, "request": request_text_only(req)}, ensure_ascii=False)
        try:
            reply = self.transport(SCHEMA_PROMPT, payload)
        except Exception as exc:  # network / provider errors -> conservative failure
            raise InterpretationError(f"{deterministic_error.message}; the LLM fallback was unavailable ({exc})",
                                      deterministic_error.where, deterministic_error.hint) from exc
        plan = _parse_json(reply)
        if "error" in plan:
            raise InterpretationError(f"{deterministic_error.message}; the LLM fallback also declined: "
                                      f"{plan['error']}", deterministic_error.where, deterministic_error.hint)
        plan.setdefault("version", 1)
        plan["mode"] = mode
        plan.setdefault("population", {"op": "all"})
        plan.setdefault("dimensions", [])
        try:
            validate(plan)
        except PlanValidationError as exc:
            raise InterpretationError(f"{deterministic_error.message}; the LLM proposal failed validation: "
                                      f"{'; '.join(exc.errors[:3])}", deterministic_error.where) from exc
        unknown = _codes_not_in_data(plan, catalog)
        notes = plan.setdefault("notes", [])
        notes.append(f"Plan proposed by {self.label} because the rule-based interpreter failed "
                     f"({deterministic_error.message}). It passed schema validation; staff review recommended.")
        if unknown:
            notes.append("Codes with no records in the data: " + ", ".join(sorted(unknown)))
        plan.setdefault("interpretation", [])
        plan.setdefault("population_reasons", [])
        plan["described"] = {"population": "see raw IR", "measures": [
            {"id": m["id"], "label": m.get("label", m["id"]), "visible": m.get("visible", False),
             "computes": m["type"]} for m in plan["measures"]], "groups": [d["type"] for d in plan["dimensions"]]}
        reference = {"region": V.REGIONS, "sex": V.SEXES, "data_holder": V.DATA_HOLDERS}
        for d in plan["dimensions"]:
            if d["type"] in reference:  # every requested group is listed, even if empty
                d["groups"] = list(reference[d["type"]]) + [g for g in catalog.get(d["type"], [])
                                                            if g not in reference[d["type"]]]
        return plan, {"engine": self.label, "llm_used": True, "deterministic_error": deterministic_error.message}


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise InterpretationError("the LLM reply contained no JSON plan")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise InterpretationError(f"the LLM reply was not valid JSON ({exc.msg})") from exc
    if not isinstance(obj, dict):
        raise InterpretationError("the LLM reply was not a JSON object")
    return obj


def _codes_not_in_data(plan: dict, catalog: dict) -> set[str]:
    missing = set()
    for c in plan["concepts"].values():
        if c["kind"] == "condition":
            for it in c["icd10"]:
                if not any(x.startswith(it["code"]) for x in catalog.get("icd10", [])):
                    missing.add(it["code"])
        elif c["kind"] == "medication":
            missing |= {a for a in c["atc"] if not any(x.startswith(a) for x in catalog.get("atc", []))}
        elif c["kind"] == "observation" and c["loinc"] not in catalog.get("loinc", []):
            missing.add(c["loinc"])
    return missing


def _http_json(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        with exc:
            raise RuntimeError(f"provider answered HTTP {exc.code}") from None


def from_environment() -> LLMPlanner | None:
    provider = (os.environ.get("DESK_LLM_PROVIDER") or "").strip().lower()
    model = (os.environ.get("DESK_LLM_MODEL") or "").strip()
    base = (os.environ.get("DESK_LLM_BASE_URL") or "").strip().rstrip("/")  # e.g. an EU-hosted gateway or a test server
    if not provider:
        return None
    if not model:
        raise SystemExit("DESK_LLM_PROVIDER is set but DESK_LLM_MODEL is missing")
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY is not set")

        def transport(system: str, user: str) -> str:
            out = _http_json(f"{base or 'https://api.anthropic.com'}/v1/messages",
                             {"x-api-key": key, "anthropic-version": "2023-06-01"},
                             {"model": model, "max_tokens": 4000, "temperature": 0, "system": system,
                              "messages": [{"role": "user", "content": user}]})
            return "".join(part.get("text", "") for part in out.get("content", []))
    elif provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("OPENAI_API_KEY is not set")

        def transport(system: str, user: str) -> str:
            out = _http_json(f"{base or 'https://api.openai.com'}/v1/chat/completions", {"Authorization": f"Bearer {key}"},
                             {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            return out["choices"][0]["message"]["content"]
    else:
        raise SystemExit(f"unknown DESK_LLM_PROVIDER '{provider}' (use anthropic or openai)")
    return LLMPlanner(transport, f"LLM fallback ({provider}:{model})")
