"""End-to-end processing of one request: validate -> decide -> plan -> execute -> audit -> answer."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from pathlib import Path

from . import policy
from .audit import audit_spe, audit_statistics
from .datastore import DataStore, get_store
from .executor import Executor, released_json
from .ir import PlanValidationError, validate
from .parser import InterpretationError, PlanBuilder, describe_expr
from .request_schema import RequestError, parse_request
from .spe import SPEManager

DECISION_LABELS = {
    policy.REJECT: "Rejected",
    policy.APPROVE_STATISTICAL: "Approved - anonymised statistics",
    policy.APPROVE_SPE: "Approved - secure processing environment",
    policy.NO_DECISION: "No automated decision - referred to staff",
}


class Desk:
    def __init__(self, store: DataStore | None = None, spe_dir=None, planner=None, state_dir=None):
        self.store = store or get_store()
        self.spe = SPEManager(self.store, spe_dir) if spe_dir else SPEManager(self.store)
        self.catalog = self.store.code_catalog()
        self.planner = planner
        self.cases: list[dict] = []
        self._lock = threading.Lock()
        self._counter = 0
        self.case_file = Path(state_dir) / "cases.jsonl" if state_dir else None
        if self.case_file and self.case_file.exists():  # the case register survives restarts
            for line in self.case_file.read_text(encoding="utf-8").splitlines():
                try:
                    self.cases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            self.cases = self.cases[-500:]
            self._counter = max((int(c["case_id"][2:]) for c in self.cases), default=0)

    # ------------------------------------------------------------------ main entry
    def process(self, raw, source: str = "api", identity: dict | None = None) -> dict:
        """identity: verified applicant (simulated ID Austria) - recorded for accountability, never used to decide."""
        t0 = time.perf_counter()
        with self._lock:
            self._counter += 1
            case_id = f"C-{self._counter:04d}"
        case: dict = {"case_id": case_id, "source": source, "received_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "identity": identity}
        try:
            req = parse_request(raw)
        except RequestError as exc:
            case.update({"status": "INVALID_REQUEST", "errors": exc.errors, "request": None, "decision": None,
                         "fulfilment": {"status": "NOT_PRODUCED", "message": "The request is not valid."},
                         "patient_data_queried": False, "privacy_checks": []})
            case["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return self._store(case)

        case["request"] = req
        decision = policy.decide(req)
        case["status"] = "DECIDED"
        case["decision"] = decision.to_dict() | {"label": DECISION_LABELS[decision.outcome]}
        case["patient_data_queried"] = False
        case["privacy_checks"] = []
        case["result"] = None
        case["plan"] = None
        case["sql"] = []
        case["fulfilment"] = {"status": "NOT_APPLICABLE"}

        if decision.outcome == policy.REJECT:
            case["fulfilment"] = {"status": "NONE", "message": "Rejected before any patient data was queried."}
        elif decision.outcome == policy.NO_DECISION:
            case["fulfilment"] = {"status": "NONE", "message": "Referred to staff; no patient data was queried."}
        else:
            mode = "spe" if decision.outcome == policy.APPROVE_SPE else "statistics"
            try:
                plan, planner_info = self._plan(req, mode)
                validate(plan)
                case["plan"] = plan
                case["planner"] = planner_info
                ex = Executor(self.store, plan)
                case["patient_data_queried"] = True
                if mode == "statistics":
                    self._statistics(case, ex, plan)
                else:
                    self._secure_environment(case, ex, plan, req, decision)
                case["sql"] = ex.sql
            except InterpretationError as exc:
                case["fulfilment"] = {"status": "NOT_PRODUCED", "error": exc.to_dict(),
                                      "message": "The desk could not interpret the request safely, so no numbers "
                                                 "were produced. Staff will contact the applicant."}
            except PlanValidationError as exc:
                case["fulfilment"] = {"status": "NOT_PRODUCED", "error": {"message": "; ".join(exc.errors)},
                                      "message": "The query plan failed validation; no data was released."}
            except Exception as exc:  # fail closed: an unexpected error never releases partial results
                traceback.print_exc()
                case["result"] = None
                case["fulfilment"] = {"status": "NOT_PRODUCED",
                                      "error": {"message": f"internal error ({type(exc).__name__}); nothing was "
                                                           "released"},
                                      "message": "The desk hit an internal error, so nothing was released. Staff "
                                                 "have been notified."}
        case["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        case["fingerprint"] = fingerprint(case)
        return self._store(case)

    def _plan(self, req: dict, mode: str):
        try:
            pb = PlanBuilder(req, mode, self.catalog)
            plan = pb.build()
            plan["described"] = describe_plan(plan, pb)
            return plan, {"engine": "deterministic rules", "llm_used": False}
        except InterpretationError as exc:
            if self.planner is None:
                raise
            plan, info = self.planner(req, mode, self.catalog, exc)
            return plan, info

    def _statistics(self, case: dict, ex: Executor, plan: dict) -> None:
        result, internal = ex.run_statistics()
        released = released_json(result)
        checks = audit_statistics(released, internal, plan, self.store)
        case["privacy_checks"] = checks
        if any(c["status"] == "fail" for c in checks):
            case["fulfilment"] = {"status": "WITHHELD", "message": "A privacy check failed; nothing was released."}
            return
        case["result"] = released
        case["fulfilment"] = {"status": "RELEASED", "message": "Anonymised statistics released."}

    def _secure_environment(self, case: dict, ex: Executor, plan: dict, req: dict, decision) -> None:
        cohort = ex.cohort_ids(plan["spe"]["cohort"])
        permit = {"articles": decision.articles, "purpose": req["purpose"],
                  "applicant": (req.get("applicant") or {}).get("organisation", "")}
        with self.spe.lock:  # build and audit the same workspace atomically
            manifest = self.spe.build(req, plan["spe"]["record_types"], cohort, permit)
            status, _ = self.spe.request_download(manifest["workspace_id"], actor="privacy audit (self-test)")
            db_path = self.spe.path(manifest["workspace_id"]) / "workspace.sqlite"
            case["privacy_checks"] = audit_spe(manifest, cohort, plan["spe"]["record_types"], self.store, db_path,
                                               status)
        if any(c["status"] == "fail" for c in case["privacy_checks"]):
            case["fulfilment"] = {"status": "WITHHELD", "message": "A privacy check failed; the workspace is locked."}
            return
        case["result"] = {"kind": "spe", "cohort_size": manifest["cohort_size"],
                          "workspace_id": manifest["workspace_id"], "tables": manifest["tables"],
                          "permit_token": manifest["permit_token"],
                          "download_policy": "blocked", "storage": manifest["storage"]}
        case["fulfilment"] = {"status": "SPE_READY",
                              "message": "Pseudonymised records were copied into an isolated secure processing "
                                         "environment. They can be analysed there but not downloaded."}

    def _store(self, case: dict) -> dict:
        with self._lock:
            self.cases.append(case)
            if len(self.cases) > 500:
                self.cases = self.cases[-500:]
            if self.case_file:
                self.case_file.parent.mkdir(parents=True, exist_ok=True)
                with self.case_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
        return case

    def get_case(self, case_id: str) -> dict | None:
        return next((c for c in reversed(self.cases) if c["case_id"] == case_id), None)


# ---------------------------------------------------------------------- views
def applicant_view(case: dict) -> dict:
    req = case.get("request") or {}
    d = case.get("decision") or {}
    return {
        "case_id": case["case_id"],
        "status": case["status"],
        "errors": case.get("errors"),
        "request_id": req.get("id"),
        "applicant": req.get("applicant"),
        "requested_as": req.get("requested_as"),
        "decision": {k: d.get(k) for k in ("outcome", "label", "articles", "article_titles", "reason", "notes")}
        if d else None,
        "fulfilment": case.get("fulfilment"),
        "result": case.get("result"),
        "interpretation_notes": (case.get("plan") or {}).get("notes", []),
        "patient_data_queried": case.get("patient_data_queried"),
        "privacy_summary": privacy_summary(case.get("privacy_checks", [])),
        "elapsed_ms": case.get("elapsed_ms"),
        "submitted_by": ({k: case["identity"][k] for k in ("name", "method", "eidas_loa")}
                         if case.get("identity") else None),
    }


def staff_view(case: dict, spe: SPEManager | None = None) -> dict:
    v = applicant_view(case)
    v.update({
        "request": case.get("request"),
        "decision_detail": case.get("decision"),
        "plan": case.get("plan"),
        "planner": case.get("planner"),
        "sql": case.get("sql"),
        "privacy_checks": case.get("privacy_checks"),
        "received_at": case.get("received_at"),
        "fingerprint": case.get("fingerprint"),
        "identity": case.get("identity"),
    })
    res = case.get("result") or {}
    if res.get("kind") == "spe" and spe is not None:
        v["spe_log"] = spe.log_for(res["workspace_id"])
    return v


def privacy_summary(checks: list[dict]) -> dict:
    return {"passed": sum(c["status"] == "pass" for c in checks), "failed": sum(c["status"] == "fail" for c in checks),
            "total": len(checks)}


def fingerprint(case: dict) -> str:
    d = case.get("decision") or {}
    res = case.get("result") or {}
    core = {"outcome": d.get("outcome"), "articles": d.get("articles"), "fulfilment": case["fulfilment"].get("status")}
    if res.get("kind") == "statistics":
        core["rows"] = [[r["label"], r["cells"]] for r in res["rows"]]
    elif res.get("kind") == "spe":
        core["cohort"] = res["cohort_size"]
        core["tables"] = {t: [v["rows"], v["patients"]] for t, v in res["tables"].items()}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def describe_plan(plan: dict, pb: PlanBuilder) -> dict:
    measures = []
    for m in plan["measures"]:
        if m["type"] in ("count_patients", "count_encounters"):
            what = describe_expr(m["set"], pb)
            if m["type"] == "count_encounters":
                what = f"encounters '{pb.concepts[m['encounter']].label}' of patients: {what}"
            measures.append({"id": m["id"], "label": m["label"], "visible": m.get("visible", False),
                             "computes": f"count of {what}"})
        elif m["type"] == "percent":
            measures.append({"id": m["id"], "label": m["label"], "visible": True,
                             "computes": f"{m['numerator']} / {m['denominator']} x 100"})
        elif m.get("derived"):
            dv = pb.concepts[m["derived"]]
            what = (f"{dv.label.lower()} per '{pb.concepts[m['encounter']].label}' encounter (end_date - start_date, "
                    "suppressed below 10 distinct patients)") if m.get("encounter") else f"{dv.label.lower()} per patient"
            measures.append({"id": m["id"], "label": m["label"], "visible": True,
                             "computes": f"{m['type']} of {what} over {describe_expr(m['set'], pb)}"})
        else:
            measures.append({"id": m["id"], "label": m["label"], "visible": True,
                             "computes": f"{m['type']} of {pb.concepts[m['observation']].label} "
                                         f"({pb.concepts[m['observation']].spec.get('pick')} value per patient) over "
                                         f"{describe_expr(m['set'], pb)}"})
    out = {"population": describe_expr(plan["population"], pb), "measures": measures,
           "groups": [d["type"] for d in plan["dimensions"]]}
    if plan.get("spe"):
        out["cohort"] = describe_expr(plan["spe"]["cohort"], pb)
    return out


def answer_of(case: dict):
    """Compact answer used by the evaluator: {group: [values...]} or {'cohort_size': n}."""
    res = case.get("result")
    if not res:
        return None
    if res["kind"] == "spe":
        return {"cohort_size": res["cohort_size"]}
    return {r["label"]: [r["cells"][c["id"]] for c in res["columns"]] for r in res["rows"]}
