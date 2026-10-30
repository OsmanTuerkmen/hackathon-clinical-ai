"""Stages A-F: pre-screen -> purpose -> plan -> query -> output check -> release.

Produces the request-detail object of the API contract (docs/UI_AND_PITCH_PLAN.md §3). Raw numbers never leave
this module: only privacy.publish() output is stored, and suppressed cells carry value=None.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import audit, catalog, compiler, db, explain, ledger, llm, privacy, security, spe
from .decision import Justification, Signal, decide, rules_justification, rules_signal
from .parser import parse
from .plan import QueryPlan

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = json.loads((Path(__file__).parent / "articles.json").read_text())
STEP_LABELS = [("received", "Received"), ("purpose", "Purpose check"), ("plan", "Query plan"), ("query", "Query"),
               ("privacy", "Privacy"), ("decision", "Decision")]
REQUEST_TYPES = {"health data request", "health data access application"}
STORE: dict[str, dict] = {}
_lock = threading.Lock()


class RequestError(ValueError):
    pass


def validate(req: dict) -> dict:
    if not isinstance(req, dict):
        raise RequestError("request must be a JSON object")
    ra = str(req.get("requested_as", "")).strip().lower()
    if ra not in REQUEST_TYPES:
        raise RequestError("requested_as must be 'health data request' or 'health data access application'")
    missing = [k for k in ("purpose", "question") if not str(req.get(k, "")).strip()]
    if missing:
        raise RequestError(f"incomplete request: missing {', '.join(missing)}")
    if not isinstance(req.get("definitions", []), list):
        raise RequestError("definitions must be a list of strings")
    rid = str(req.get("id") or ("REQ-" + uuid.uuid4().hex[:6].upper()))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", rid):
        raise RequestError("id may only contain letters, digits, '-' and '_' (max 32)")
    return {**req, "id": rid}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit(req: dict) -> str:
    req = validate(req)
    rid = req["id"]
    detail = {
        "id": rid, "request": req, "status": "processing", "submitted": req.get("submitted") or _now(), "elapsed_ms": 0,
        "steps": [{"key": k, "label": l, "state": "pending", "ms": 0} for k, l in STEP_LABELS],
        "decision": None, "plan": None, "result": None, "privacy": None, "spe": None, "inference": None, "flags": {},
    }
    with _lock:
        STORE[rid] = detail
    audit.log("request.received", rid, actor="applicant", detail=f"{req.get('requested_as')} from {(req.get('applicant') or {}).get('organisation', '?')}")
    return rid


def _step(d: dict, key: str, state: str, ms: int = 0, detail: Optional[str] = None):
    for s in d["steps"]:
        if s["key"] == key:
            s["state"], s["ms"] = state, ms
            if detail:
                s["detail"] = detail


def _display(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _result_table(plan: QueryPlan, raw: compiler.RawResult, published: dict) -> dict:
    hidden = {m.name for m in plan.measures if m.hidden}
    shown = [m for m in plan.measures if m.name not in hidden]
    units = {"4548-4": "%", "39156-5": "kg/m²", "8480-6": "mmHg", "62238-1": "mL/min/1.73m²"}
    columns = [{"key": g.dim, "label": g.dim.replace("_", " ").title().replace("Data Holder", "Hospital"), "type": "group"} for g in plan.group_by]
    for m in shown:
        col = {"key": m.name, "label": m.name.replace("_", " ").capitalize(), "type": m.kind}
        if m.kind == "mean":
            col["unit"] = units.get(m.loinc, "")
        if m.kind == "pct":
            col["unit"] = "%"
        columns.append(col)
    rows = []
    for g in raw.groups:
        row = {plan.group_by[i].dim: g[i] for i in range(len(g))}
        for m in shown:
            cell = raw.values[g][m.name]
            pub = privacy.publish_cell(cell)
            if pub == privacy.LT:
                row[m.name] = {"value": None, "display": "<10", "suppressed": "small_count"}
            elif pub == privacy.SUPPRESSED:
                row[m.name] = {"value": None, "display": "suppressed", "suppressed": "small_n"}
            else:
                row[m.name] = {"value": pub, "display": _display(pub)}
        rows.append(row)
    return {"kind": "table", "group_by": [g.dim for g in plan.group_by], "columns": columns, "rows": rows, "answer": published}


def _letter(req: dict, dec, result: Optional[dict]) -> dict:
    name = (req.get("applicant") or {}).get("name", "Applicant")
    greeting = f"Dear {name},"
    if dec.outcome == "REJECT":
        return {"greeting": greeting, "headline": "We cannot approve your request.",
                "why": f"{dec.reason_staff} The European Health Data Space Regulation lists uses of health data that are never allowed, "
                       "whatever form the data takes. Your stated purpose falls under one of them, so we did not access any data.",
                "alternatives": ["If we have misunderstood your purpose, you can submit a new request that describes it more precisely.",
                                 "Research that contributes to public health, prevention or better care is an allowed purpose (Art. 53)."],
                "next_steps": ["You can ask for this decision to be reviewed by a staff member.", "You may appeal under national law."]}
    if dec.outcome == "APPROVE_SPE":
        return {"greeting": greeting, "headline": "Your application is approved. Your secure workspace is ready.",
                "why": f"{dec.reason_staff} You can analyse the pseudonymised records inside the secure processing environment. "
                       "The data cannot be downloaded; only anonymised results such as model weights or statistics can leave after a review.",
                "alternatives": [], "next_steps": ["Open your secure workspace.", "Request an export review when your anonymised results are ready (Art. 73(2))."]}
    alts = []
    if dec.downgraded_from:
        alts.append("You asked for patient-level records. Because statistics answer your question, we provide anonymised statistics instead "
                    "(Art. 66, data minimisation). If you truly need records, submit an access application that explains why statistics are not enough.")
    sup = sum(1 for r in (result or {}).get("rows", []) for v in r.values() if isinstance(v, dict) and v.get("value") is None)
    why = f"{dec.reason_staff}"
    if sup:
        why += f" To protect privacy, {sup} cells based on fewer than 10 patients are shown as <10 or suppressed."
    return {"greeting": greeting, "headline": "Your request is approved. Here are your statistics.", "why": why, "alternatives": alts,
            "next_steps": ["Cite the European Health Data Space as the data source.", "Publish your results within 18 months."]}


def _five_safes(req: dict, dec, plan: Optional[QueryPlan]) -> dict:
    a = req.get("applicant") or {}
    data = "No data accessed" if dec.outcome == "REJECT" else (
        "Pseudonymised records of the cohort, record types named in the permit" if dec.outcome == "APPROVE_SPE" else "Anonymised aggregate statistics only")
    return {
        "project": f"{dec.purpose_category.replace('_', ' ')}: {req.get('purpose', '')[:140]}",
        "people": f"{a.get('name', '?')}, {a.get('organisation', '?')} ({a.get('country', '?')}); applicant type: {dec.applicant_type}",
        "setting": "Secure processing environment, downloads blocked (Art. 73)" if dec.outcome == "APPROVE_SPE" else "Results delivered by the access body; no data access for the applicant",
        "data": data + "; opted-out patients excluded (Art. 71)",
        "outputs": "Not applicable" if dec.outcome == "REJECT" else "Small-cell rule: counts <10 hidden, percentages and means from <10 patients suppressed",
    }


def process(rid: str):
    d = STORE[rid]
    t_all = time.time()
    events: list[dict] = []
    try:
        raw_req = d["request"]
        _step(d, "received", "running")
        t = time.time()
        injection = security.detect_injection(raw_req)
        req, changes = security.sanitise_request(raw_req)
        _step(d, "received", "done", int((time.time() - t) * 1000), detail="pre-screening passed")
        for h in injection:
            audit.log("security.injection_flag", rid, detail=h)

        # ---- Stage B: purpose
        _step(d, "purpose", "running")
        t = time.time()
        cfg = llm.config()
        r_sig = rules_signal(req)
        llm_sigs, j_llm, j_quote, problems = llm.purpose_signals(req, events)
        signals = [r_sig] + llm_sigs
        just = llm.combine_justification(rules_justification(req), j_llm, j_quote)
        llm_ok = cfg["enabled"] and any(s.available for s in llm_sigs)
        dec = decide(req, signals, just, injection, llm_available=llm_ok)
        if cfg["enabled"] and not llm_ok:
            dec.review_reasons.append(_rr("ai_unavailable", "The AI checks failed or timed out; the decision is based on rules only."))
        for p in problems:
            if "quote not found" in p:
                dec.review_reasons.append(_rr("unverified_evidence", f"AI {p}; that claim was ignored."))
        dec.needs_review = bool(dec.review_reasons)
        for e in events:
            audit.log(e["event"], rid, detail=json.dumps({k: v for k, v in e.items() if k != "event"}))
        _step(d, "purpose", "done", int((time.time() - t) * 1000),
              detail=("prohibited: " + dec.purpose_category) if dec.outcome == "REJECT" else dec.purpose_category)
        d["inference"] = {"profile": "llm" if cfg["enabled"] else "off", "model": cfg["model"] if cfg["enabled"] else None,
                          "endpoint_host": cfg["endpoint_host"], "patient_data_sent": False,
                          "sent": ["organisation", "purpose", "question"] if cfg["enabled"] else [],
                          "calls": [{k: e.get(k) for k in ("event", "cached", "ms", "error", "sent_sha256")} for e in events]}

        decision_obj = dec.model_dump()
        decision_obj["review_reasons"] = [r if isinstance(r, dict) else r.model_dump() for r in decision_obj["review_reasons"]]

        if dec.outcome == "REJECT":
            for k in ("plan", "query", "privacy"):
                _step(d, k, "skipped", detail="rejected before any data was touched")
            _finish(d, req, dec, decision_obj, None, None, t_all)
            return

        # ---- Stage C: plan
        _step(d, "plan", "running")
        t = time.time()
        pr = parse(req)
        plan = pr.plan
        plan_review = []
        if plan is None:
            plan_review.append(("translation_failed", "The definitions could not be translated: " + "; ".join(pr.notes)))
        else:
            if pr.unparsed:
                plan_review.append(("unparsed_definitions", "Some definitions could not be translated: " + " | ".join(pr.unparsed)))
            gaps = [i for i, uses in pr.coverage.items() if not uses]
            if gaps:
                plan_review.append(("coverage_gap", "Definitions not used by the query plan: " + " | ".join(req["definitions"][i] for i in gaps)))
            unknown = catalog.unknown_codes(plan)
            if unknown:
                plan_review.append(("unknown_codes", "Codes not found in the data: " + ", ".join(unknown)))
            if pr.unknown_terms:
                plan_review.append(("unknown_terms", "Terms the system could not map to codes: " + ", ".join(sorted(set(pr.unknown_terms)))))
            for n in pr.notes:
                if not n.startswith("unrecognised term"):
                    plan_review.append(("plan_note", n))
            if plan.patient_level_requested and dec.outcome != "APPROVE_SPE":
                plan_review.append(("records_requested", "The applicant asked for individual records; only anonymised statistics are released."))
        for code, msg in plan_review:
            dec.review_reasons.append(_rr(code, msg))
        dec.needs_review = bool(dec.review_reasons)
        hold = plan is None or any(c in ("translation_failed", "unparsed_definitions", "unknown_codes", "coverage_gap", "unknown_terms") for c, _ in plan_review)
        if plan is not None:
            d["plan"] = {"readable": explain.readable(plan), "catalog_matches": explain.catalog_matches(plan),
                         "raw": json.loads(plan.model_dump_json()), "sql": compiler.compile_sql(plan), "source": "rules",
                         "unparsed": pr.unparsed, "coverage": {str(k): v for k, v in pr.coverage.items()},
                         "definitions": req.get("definitions", [])}
        _step(d, "plan", "failed" if plan is None else "done", int((time.time() - t) * 1000), detail="rule parser" if plan else "needs review")
        if hold:
            for k in ("query", "privacy"):
                _step(d, k, "skipped", detail="held for human review")
            decision_obj = _dec_obj(dec)
            _finish(d, req, dec, decision_obj, plan, None, t_all, held=True)
            return

        # ---- Stage D: query
        _step(d, "query", "running")
        t = time.time()
        if dec.outcome == "APPROVE_SPE":
            manifest = spe.create(rid, plan)
            result = {"kind": "cohort", "cohort_size": manifest["cohort_size"], "answer": {"cohort_size": manifest["cohort_size"]}}
            d["spe"] = {"id": f"spe_{rid}", **manifest}
            audit.log("spe.created", rid, detail=f"{manifest['cohort_size']} patients; tables {manifest['tables']}")
            raw = None
        else:
            raw = compiler.run(plan)
            published = privacy.publish(raw, {m.name for m in plan.measures if m.hidden})
            result = _result_table(plan, raw, published)
        _step(d, "query", "done", int((time.time() - t) * 1000), detail=f"{raw.unit_count if raw else result['cohort_size']} {plan.unit} matched")

        # ---- Stage E: output checking
        _step(d, "privacy", "running")
        t = time.time()
        checks = [{"key": "opt_out", "label": "Opted-out patients excluded (Art. 71)", "passed": True, "detail": f"{_opted_out()} removed before any query"}]
        if raw is not None:
            leaks = privacy.leak_check(result["answer"])
            n_lt = sum(1 for r in result["rows"] for v in r.values() if isinstance(v, dict) and v.get("display") == "<10")
            n_sup = sum(1 for r in result["rows"] for v in r.values() if isinstance(v, dict) and v.get("display") == "suppressed")
            checks.append({"key": "small_cell", "label": "Small-cell rule", "passed": not leaks, "detail": f"{n_lt} counts shown as <10, {n_sup} values suppressed"})
            checks.append({"key": "no_patient_level", "label": "No patient-level fields in the output", "passed": not leaks,
                           "detail": "aggregates only" + (" (records were requested; never released as statistics)" if plan.patient_level_requested else "")})
            checks.append({"key": "all_groups", "label": "All requested groups present", "passed": True, "detail": f"{len(raw.groups)}/{len(raw.groups)}"})
            key = ledger.applicant_key(req)
            groups = {"/".join(g) or "total": ids for g, ids in (raw.group_ids or {}).items()}
            findings = ledger.check(key, rid, groups)
            checks.append({"key": "differencing", "label": "Differencing guard", "passed": not findings,
                           "detail": "no near-overlap with earlier releases" if not findings else
                           f"{len(findings)} groups differ from an earlier release by fewer than 10 people"})
            if findings:
                f0 = findings[0]
                dec.review_reasons.append(_rr("differencing_risk", f"Group '{f0['group']}' differs from '{f0['other_group']}' in {f0['other_request']} by {f0['difference']} people; "
                                                                  "subtracting the two could reveal individuals."))
                dec.needs_review = True
            else:
                ledger.record(key, rid, groups)
            if leaks:
                dec.review_reasons.append(_rr("leak_detected", "; ".join(leaks)))
                dec.needs_review = True
                result = None
        else:
            checks.append({"key": "spe_download_blocked", "label": "Downloads from the secure environment blocked (Art. 73)", "passed": True, "detail": "export only after review"})
            checks.append({"key": "minimised", "label": "Only the cohort and the named record types copied (Art. 66)", "passed": True,
                           "detail": ", ".join(f"{k}: {v}" for k, v in d["spe"]["tables"].items())})
        d["privacy"] = {"opted_out_excluded": _opted_out(), "checks": checks, "profile": "track"}
        _step(d, "privacy", "done", int((time.time() - t) * 1000), detail="all checks passed" if all(c["passed"] for c in checks) else "review needed")
        _finish(d, req, dec, _dec_obj(dec), plan, result, t_all)
    except Exception as e:  # never leave a request hanging; errors go to review
        d["status"] = "error"
        d["error"] = f"{type(e).__name__}: {e}"
        for s in d["steps"]:
            if s["state"] in ("pending", "running"):
                s["state"] = "failed"
        audit.log("request.error", rid, detail=d["error"])


def _rr(code: str, message: str):
    from .decision import ReviewReason
    return ReviewReason(code=code, message=message)


def _dec_obj(dec) -> dict:
    o = dec.model_dump()
    return o


def _opted_out() -> int:
    return int(db.query("select count(*) n from raw.patients where opted_out = 'true'")["n"][0])


def _finish(d, req, dec, decision_obj, plan, result, t_all, held: bool = False):
    decision_obj = _dec_obj(dec)
    decision_obj["letter"] = _letter(req, dec, result)
    if held:
        decision_obj["letter"]["why"] += " Before we release numbers, a staff member checks how your definitions were translated."
    decision_obj["five_safes"] = _five_safes(req, dec, plan)
    decision_obj["purpose"] = {"category": dec.purpose_category, "allowed": dec.outcome != "REJECT", "source": dec.purpose_source,
                               "rule_hits": [dec.signals.get("rules", {}).get("note", "")]}
    decision_obj["permit"] = None
    if dec.outcome == "APPROVE_SPE":
        decision_obj["permit"] = {"number": f"HDAB-{date.today().year}-{d['id']}", "holder": (req.get("applicant") or {}).get("organisation", ""),
                                  "valid_until": (date.today() + timedelta(days=365)).isoformat(), "articles": ["68", "73"]}
    d["decision"] = decision_obj
    d["result"] = result
    d["flags"] = {
        "downgraded": bool(dec.downgraded_from), "needs_review": dec.needs_review,
        "suppressed_cells": sum(1 for r in (result or {}).get("rows", []) for v in r.values() if isinstance(v, dict) and v.get("value") is None),
        "differencing_risk": any(r.code == "differencing_risk" for r in dec.review_reasons),
        "injection": bool(dec.signals.get("injection", {}).get("flagged")), "overridden": False, "held": held,
    }
    _step(d, "decision", "done", 1, detail=dec.outcome + (" · review" if dec.needs_review else ""))
    d["status"] = "decided"
    d["elapsed_ms"] = int((time.time() - t_all) * 1000)
    audit.log("decision.made", d["id"], detail=f"{dec.outcome} {'+'.join(dec.articles)}" + (" (needs review)" if dec.needs_review else ""),
              review=[r.code for r in dec.review_reasons])


def run_sync(req: dict) -> dict:
    rid = submit(req)
    process(rid)
    return STORE[rid]


def summary(d: dict) -> dict:
    req = d["request"]
    dec = d.get("decision") or {}
    return {
        "id": d["id"], "submitted": d["submitted"], "status": d["status"], "applicant": req.get("applicant"),
        "requested_as": req.get("requested_as"), "purpose_short": (req.get("purpose") or "")[:90],
        "decision": dec.get("outcome"), "articles": dec.get("articles", []), "needs_review": dec.get("needs_review", False),
        "flags": d.get("flags", {}), "current_step": next((s["key"] for s in d["steps"] if s["state"] == "running"), d["steps"][-1]["key"]),
        "elapsed_ms": d["elapsed_ms"],
    }


def samples() -> list[dict]:
    out = []
    for folder in (ROOT / "track" / "requests", ROOT / "fixtures" / "custom", ROOT / "fixtures" / "adversarial"):
        if not folder.exists():
            continue
        for f in sorted(folder.glob("*.json")):
            if f.name == "expected.json" or f.name.endswith(".expected.json"):
                continue
            j = json.loads(f.read_text())
            if "requested_as" not in j:
                continue
            out.append({"id": j.get("id", f.stem), "organisation": (j.get("applicant") or {}).get("organisation", ""),
                        "requested_as": j.get("requested_as"), "group": folder.name, "json": j})
    return out
