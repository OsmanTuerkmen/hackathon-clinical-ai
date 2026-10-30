"""HTTP API (contract: docs/UI_AND_PITCH_PLAN.md §3). Run: uvicorn app.api:app --app-dir backend --port 8000"""
from __future__ import annotations

import json
import re
import threading

import duckdb
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import audit, db, llm, metrics, pipeline, spe

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    db.connection()
    yield


app = FastAPI(title="EHDS Gatekeeper", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
_blocked: dict[str, int] = {}


@app.get("/api/health")
def health():
    cfg = llm.config()
    return {"ok": True, "ai": {"enabled": cfg["enabled"], "model": cfg["model"] if cfg["enabled"] else None, "endpoint_host": cfg["endpoint_host"]},
            "audit_chain_valid": audit.verify_chain()}


@app.get("/api/samples")
def samples():
    return pipeline.samples()


@app.get("/api/articles")
def articles():
    return pipeline.ARTICLES


@app.post("/api/requests", status_code=202)
async def create_request(request: Request, bg: BackgroundTasks):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(422, "body is not valid JSON")
    try:
        rid = pipeline.submit(body)
    except pipeline.RequestError as e:
        raise HTTPException(422, str(e))
    bg.add_task(pipeline.process, rid)
    return {"id": rid, "status": "processing"}


@app.post("/api/requests/batch")
def batch(body: dict, bg: BackgroundTasks):
    ids = body.get("ids") or [f"R{i:02d}" for i in range(1, 11)]
    by_id = {s["id"]: s["json"] for s in pipeline.samples()}
    out = []
    for i in ids:
        if i in by_id:
            rid = pipeline.submit(by_id[i])
            bg.add_task(pipeline.process, rid)
            out.append(rid)
    return {"ids": out}


@app.get("/api/requests")
def list_requests():
    return [pipeline.summary(d) for d in sorted(pipeline.STORE.values(), key=lambda d: d["submitted"], reverse=True)]


def _get(rid: str) -> dict:
    d = pipeline.STORE.get(rid)
    if not d:
        raise HTTPException(404, f"unknown request {rid}")
    return d


@app.get("/api/requests/{rid}")
def get_request(rid: str):
    d = dict(_get(rid))
    d["audit"] = audit.for_request(rid)
    return d


@app.post("/api/requests/{rid}/override")
def override(rid: str, body: dict):
    d = _get(rid)
    if body.get("decision") not in ("REJECT", "APPROVE_STATISTICAL", "APPROVE_SPE"):
        raise HTTPException(422, "decision must be REJECT, APPROVE_STATISTICAL or APPROVE_SPE")
    if not str(body.get("note", "")).strip():
        raise HTTPException(422, "an override needs a reason (note)")
    actor = str(body.get("actor", "staff"))
    prev = (d.get("decision") or {}).get("outcome")
    d["decision"]["outcome"] = body["decision"]
    d["decision"]["articles"] = body.get("articles") or d["decision"]["articles"]
    d["decision"]["needs_review"] = False
    d["decision"]["override"] = {"from": prev, "to": body["decision"], "note": body["note"], "actor": actor}
    d["flags"]["overridden"] = True
    audit.log("decision.overridden", rid, actor=actor, detail=f"{prev} -> {body['decision']}: {body['note']}")
    return get_request(rid)


@app.post("/api/requests/{rid}/release")
def release(rid: str, body: dict | None = None):
    d = _get(rid)
    if d["status"] != "decided":
        raise HTTPException(409, "only decided requests can be released")
    d["status"] = "released"
    audit.log("decision.released", rid, actor=str((body or {}).get("actor", "staff")), detail="released to applicant")
    return get_request(rid)


def _spe_req(ws: str) -> tuple[str, dict]:
    m = re.fullmatch(r"spe_([A-Za-z0-9_-]{1,32})", ws)
    if not m:
        raise HTTPException(404, "unknown workspace")
    rid = m.group(1)
    d = _get(rid)
    if not d.get("spe"):
        raise HTTPException(404, "this request has no secure processing environment")
    return rid, d


@app.get("/api/spe/{ws}")
def spe_workspace(ws: str):
    rid, d = _spe_req(ws)
    man = spe.manifest(rid) or {}
    plan = (d.get("plan") or {})
    con = duckdb.connect(str(spe.SPE_DIR / f"{rid}.duckdb"), read_only=True)
    try:
        prev = con.execute("select patient_id, sex, substr(birth_date,1,4)::int as birth_year, region from patients order by patient_id limit 6").fetchall()
    finally:
        con.close()
    all_tables = ["patients", "conditions", "medications", "observations", "encounters"]
    notes = {r["table"]: (f"only {', '.join(r['codes'])}" if r.get("codes") else None) for r in (plan.get("raw") or {}).get("spe_records", [])}
    return {
        "id": ws, "request_id": rid, "schema": f"spe_{rid.lower()}", "permit": d["decision"].get("permit"),
        "cohort_size": man.get("cohort_size"),
        "cohort_definition": "; ".join(x["text"] for x in plan.get("readable", []) if x["label"] in ("Filter", "Cohort")),
        "tables": [{"name": t, "rows": man.get("tables", {}).get(t, 0), "copied": t in man.get("tables", {}),
                    "note": notes.get(t) or (None if t in man.get("tables", {}) else "not requested")} for t in all_tables],
        "preview": {"table": "patients", "columns": ["patient_id", "sex", "birth_year", "region"], "rows": [list(r) for r in prev]},
        "blocked_attempts": _blocked.get(rid, 0),
    }


@app.get("/api/spe/{ws}/download")
def spe_download(ws: str):
    rid, _ = _spe_req(ws)
    _blocked[rid] = _blocked.get(rid, 0) + 1
    entry = audit.log("spe.download_blocked", rid, actor="applicant", detail=f"download attempt #{_blocked[rid]} blocked (Art. 73)")
    return JSONResponse(status_code=403, content={
        "error": "download_blocked", "article": "73",
        "message": "Data in a secure processing environment cannot be downloaded. Only anonymised results may leave, after review (Art. 73(2)).",
        "audit_id": entry["id"], "blocked_attempts": _blocked[rid]})


@app.post("/api/spe/{ws}/export-request")
def spe_export(ws: str, body: dict):
    rid, _ = _spe_req(ws)
    audit.log("spe.export_requested", rid, actor="applicant", detail=f"artifact: {body.get('artifact', '?')}; pending output review")
    return {"status": "pending_review"}


@app.post("/api/metrics/run")
def metrics_run(body: dict | None = None):
    body = body or {}
    run_id = metrics.new_run()
    threading.Thread(target=metrics.execute, args=(run_id, int(body.get("runs", 3)), bool(body.get("include_custom", True))), daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/metrics/runs/{run_id}")
def metrics_get(run_id: str):
    r = metrics.RUNS.get(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    return r
