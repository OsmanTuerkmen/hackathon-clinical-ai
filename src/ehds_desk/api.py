"""Local demo HTTP interface; pseudonymised rows are available only in SPE previews."""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import spe
from .config import REPO_ROOT
from .disclosure import PATIENT_ID_PATTERN, LeakError
from .law import ARTICLES
from .models import AccessRequest
from .pipeline import DeskService, ProcessResult

DOWNLOAD_BLOCKED = {
    "blocked": True,
    "article": "73",
    "reason": "Downloads of pseudonymised records are blocked. Only anonymised results reviewed by the access body "
    "may leave the secure processing environment (Art. 73(2)).",
}


def _safe_json(value) -> JSONResponse:
    """Keep patient identifiers out of every response other than the explicit SPE preview."""
    content = jsonable_encoder(value, custom_encoder={Decimal: str})
    if PATIENT_ID_PATTERN.search(json.dumps(content, ensure_ascii=False)):
        raise LeakError("Response contains a patient identifier")
    return JSONResponse(content)


def create_app(service: DeskService | None = None) -> FastAPI:
    application = FastAPI(title="EHDS Access Desk")

    @lru_cache(maxsize=1)
    def desk() -> DeskService:
        # Importing api:app for the CLI must not load data, secrets or create runtime files.
        return service if service is not None else DeskService()

    @application.exception_handler(LeakError)
    async def leak_error(_request: Request, _error: LeakError) -> JSONResponse:
        return JSONResponse({"detail": "The response could not be released safely."}, status_code=500)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # FastAPI's default validation response echoes input, which may contain patient data.
        return JSONResponse({"detail": "Invalid request body or parameters."}, status_code=422)

    @application.exception_handler(spe.InvalidPermitId)
    async def invalid_permit(_request: Request, _error: spe.InvalidPermitId) -> JSONResponse:
        return JSONResponse({"detail": "Invalid permit identifier."}, status_code=400)

    @application.exception_handler(spe.SpeNotFound)
    async def missing_spe(_request: Request, _error: spe.SpeNotFound) -> JSONResponse:
        return JSONResponse({"detail": "Secure processing environment not found."}, status_code=404)

    def stored_request(request_id: str) -> AccessRequest:
        try:
            return desk().get_request(request_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Request not found.") from None

    @application.get("/api/health")
    def health():
        svc = desk()
        cursor = svc.db.cursor()
        try:
            patients = cursor.execute("SELECT count(*) FROM pat").fetchone()[0]
        finally:
            cursor.close()
        available = svc.settings.llm_mode != "off" and bool(svc.settings.anthropic_api_key)
        return _safe_json({"status": "ok", "patients": patients, "llm": "available" if available else "off"})

    @application.get("/api/requests")
    def requests():
        return _safe_json(desk().list_requests())

    @application.get("/api/requests/{request_id}", response_model=AccessRequest)
    def get_request(request_id: str):
        return _safe_json(stored_request(request_id))

    @application.post("/api/process", response_model=ProcessResult)
    def process(request: AccessRequest):
        return _safe_json(desk().process(request))

    @application.post("/api/process/{request_id}", response_model=ProcessResult)
    def process_stored(request_id: str):
        return _safe_json(desk().process(stored_request(request_id)))

    @application.get("/api/law")
    def law():
        return _safe_json(ARTICLES)

    @application.get("/api/spe/{permit_id}", response_model=spe.SpeManifest)
    def manifest(permit_id: str):
        return _safe_json(spe.load_manifest(permit_id, desk().settings.var_dir))

    @application.get("/api/spe/{permit_id}/preview/{table}")
    def preview(permit_id: str, table: str):
        try:
            rows = spe.preview(permit_id, table, desk().settings.var_dir)
        except spe.InvalidPermitId:
            raise
        except ValueError:
            raise HTTPException(status_code=400, detail="Table is not available in this workspace.") from None
        # Decimal stays exact; dates become ISO strings. Only this endpoint may contain patient IDs.
        return JSONResponse(jsonable_encoder(rows, custom_encoder={Decimal: str}))

    @application.get("/api/spe/{permit_id}/audit", response_model=list[spe.AuditEvent])
    def audit(permit_id: str):
        var_dir = desk().settings.var_dir
        spe.load_manifest(permit_id, var_dir)  # audit_log alone returns [] for unknown permits
        return _safe_json(spe.audit_log(permit_id, var_dir))

    @application.get("/api/spe/{permit_id}/download/{table:path}", status_code=403)
    def download(permit_id: str, table: str):
        var_dir = desk().settings.var_dir
        spe.load_manifest(permit_id, var_dir)  # invalid/unknown permits must remain 400/404
        try:
            spe.attempt_download(permit_id, table, var_dir)
        except ValueError:
            # The SPE function audits unknown and unpermitted tables before rejecting them.
            pass
        return JSONResponse(DOWNLOAD_BLOCKED, status_code=403)

    web_dir = REPO_ROOT / "web"
    if web_dir.is_dir():
        @application.get("/spe/{permit_id}", include_in_schema=False)
        def workspace(permit_id: str):
            if not (web_dir / "index.html").is_file():
                raise HTTPException(status_code=404, detail="Workspace page not found.")
            return FileResponse(web_dir / "index.html")

        # Last route: API paths take precedence. Only web/ is exposed, never the repo or var/.
        application.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return application


app = create_app()
