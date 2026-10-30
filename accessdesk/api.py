"""FastAPI application for staff, applicants, and the public register."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import evaluation
from . import ai_spec
from .cases import CaseRegistry
from .config import ROOT, build_desk, load_requests
from .evidence import drop_contained_evidence
from .exports import ExportConflict, ExportRegistry
from .letter import build as build_letter, table_label
from .plan import compiler, parser
from .safes import data as safe_data
from .safes import outputs, people, projects, settings

LETTER_TEXTS_PATH = ROOT / "accessdesk" / "templates" / "letter_texts.json"
DOWNLOAD_DETAIL = {
    "de": (
        "Download blockiert. Daten in der sicheren Verarbeitungsumgebung dürfen nicht "
        "heruntergeladen werden (Art. 73 Abs. 2). Nur geprüfte, nicht personenbezogene "
        "Ergebnisse dürfen hinaus. Der Versuch wurde protokolliert."
    ),
    "en": (
        "Download blocked. Data in the secure processing environment cannot be downloaded "
        "(Art. 73(2)). Only reviewed, non-personal results may leave. This attempt was logged."
    ),
}
DEFAULT_STATUSES = (
    "auto_decided", "review_needed", "held_identity", "released", "rejected_after_review",
)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewBody(APIModel):
    action: Literal["release", "hold", "reject"]
    reason: str = Field(min_length=20, max_length=2000)
    reviewer: str = Field(min_length=2, max_length=80)

    @field_validator("reason", "reviewer", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class SubmitApplicant(APIModel):
    name: str = Field(min_length=1, max_length=120)
    organisation: str = Field(min_length=1, max_length=200)
    country: str = Field(max_length=60)


class SubmitRequest(APIModel):
    id: str | None = None
    submitted: str | None = None
    applicant: SubmitApplicant
    requested_as: Literal["health data request", "health data access application"]
    requested_format: str | None = Field(default=None, max_length=120)
    purpose: str = Field(min_length=10, max_length=4000)
    question: str = Field(min_length=5, max_length=2000)
    definitions: list[str] = Field(min_length=1, max_length=30)
    team: list[str] = Field(default_factory=list)

    @field_validator("definitions")
    @classmethod
    def validate_definitions(cls, definitions):
        if any(not 3 <= len(item.strip()) <= 1000 for item in definitions):
            raise ValueError("each definition must contain 3 to 1,000 characters")
        return [item.strip() for item in definitions]


class SubmitBody(APIModel):
    request: SubmitRequest
    login: str | None = Field(default=None, min_length=1, max_length=120)


class DraftApplicant(APIModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=120)
    organisation: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=60)


class PrecheckRequest(APIModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    submitted: str | None = None
    applicant: DraftApplicant | None = None
    requested_as: str | None = Field(default=None, max_length=120)
    requested_format: str | None = Field(default=None, max_length=120)
    purpose: str | None = Field(default=None, max_length=4000)
    question: str | None = Field(default=None, max_length=2000)
    definitions: list[str] = Field(default_factory=list, max_length=30)
    team: list[str] = Field(default_factory=list, max_length=100)


class PrecheckBody(APIModel):
    request: PrecheckRequest
    login: str | None = Field(default=None, max_length=120)


class AIDraftBody(APIModel):
    text: str = Field(min_length=5, max_length=2000)
    lang: Literal["de", "en"]
    purpose: str | None = Field(default=None, max_length=4000)
    login: str | None = Field(default=None, max_length=120)


class SpeQueryBody(APIModel):
    sql: str = Field(min_length=1, max_length=20_000)
    login: str = Field(min_length=1, max_length=120)


class SpeExportBody(SpeQueryBody):
    title: str = Field(min_length=3, max_length=120)
    note: str = Field(default="", max_length=1000)


class ExportReviewBody(APIModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=20, max_length=2000)
    reviewer: str = Field(min_length=2, max_length=80)

    @field_validator("reason", "reviewer", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


def create_app(data_dir, runtime_dir=None):
    desk = build_desk(data_dir, runtime_dir=runtime_dir)
    cases = CaseRegistry(desk, data_dir)
    exports = ExportRegistry(desk.root)
    app = FastAPI(
        title="AccessDesk 2",
        version="2.0",
        default_response_class=UTF8JSONResponse,
        openapi_url=None,
        docs_url=None,
    )
    app.state.desk = desk
    app.state.cases = cases
    app.state.exports = exports
    app.add_event_handler("shutdown", desk.store.con.close)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        return UTF8JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError):
        return UTF8JSONResponse(
            {"detail": jsonable_encoder(exc.errors())},
            status_code=422,
        )

    def find_case(case_id):
        case = cases.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Unknown case")
        return case

    def permit_case(permit_id, required=True):
        for summary in cases.list():
            if summary["permit_id"] == permit_id:
                return cases.get(summary["id"])
        if required:
            raise HTTPException(status_code=404, detail="Unknown SPE permit")
        return None

    def authorize_spe(case, permit_id, login):
        manifest = case["result"].get("spe") or {}
        authorised = any(
            people.plain_name(person_name) == people.plain_name(login)
            for person_name in manifest.get("persons_with_access", [])
        )
        if not authorised:
            desk.audit.log(
                "spe_access_denied",
                case["summary"]["id"],
                actor=login or "anonymous",
                permit=permit_id,
                login=login,
            )
            raise HTTPException(status_code=403, detail="This person is not authorised for the SPE permit")
        return manifest

    def run_spe_query(case, manifest, sql, login, limit):
        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        request_id = case["summary"]["id"]
        try:
            result = settings.console_query(desk.root, manifest["permit_id"], sql, limit=limit)
        except settings.ConsoleError as exc:
            desk.audit.log(
                "spe_query", request_id, actor=login, permit=manifest["permit_id"],
                login=login, sql_sha256=sql_hash, rows=0, ok=False, error=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        desk.audit.log(
            "spe_query", request_id, actor=login, permit=manifest["permit_id"],
            login=login, sql_sha256=sql_hash, rows=result["row_count"], ok=True, error=None,
        )
        return result

    def audit_entries(request_id=None, limit=300):
        entries = desk.audit.tail(limit)
        if request_id:
            entries = [entry for entry in entries if entry["request_id"] == request_id]
        return entries

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/info")
    def info():
        summaries = cases.list()
        counts = Counter(summary["status"] for summary in summaries)
        for status in DEFAULT_STATUSES:
            counts.setdefault(status, 0)
        identities = _identities(desk.registry)
        ai = desk.ai.status()
        return {
            "patients": desk.store.total_patients,
            "opted_out": desk.store.opted_out,
            "load_seconds": desk.load_seconds,
            "ai": ai,
            "mode": "central",
            "version": "2.0",
            "counts": dict(counts),
            "identities": [
                {key: identity[key] for key in ("name", "organisation", "country")}
                for identity in identities
            ],
        }

    @app.get("/api/settings")
    def get_settings():
        return {"mode": "central", "ai": desk.ai.status(), "differencing_guard": True}

    @app.get("/api/cases")
    def list_cases(
        status: str | None = None,
        decision: str | None = None,
        q: str | None = Query(default=None, max_length=200),
        group: str | None = None,
    ):
        return cases.list(status=status, decision=decision, q=q, group=group)

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str):
        case = find_case(case_id)
        return {
            "summary": case["summary"],
            "result": case["result"],
            "reviews": case["reviews"],
            "visible_to_applicant": case["visible_to_applicant"],
        }

    @app.post("/api/cases/{case_id}/review")
    def review_case(case_id: str, body: ReviewBody):
        try:
            result = cases.review(case_id, body.action, body.reason, body.reviewer)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Unknown case")
        return result

    @app.post("/api/cases/{case_id}/ai-opinion")
    def request_case_ai_opinion(case_id: str):
        if not desk.ai.status()["enabled"]:
            _raise_ai_inactive()
        try:
            detail = cases.request_ai_opinion(case_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if detail is None:
            raise HTTPException(status_code=404, detail="Unknown case")
        opinion = detail["result"]["ai"].get("opinion")
        if opinion is None:
            status = detail["result"]["ai"].get("status") or {}
            raise HTTPException(
                status_code=503,
                detail=_ai_failure_detail({
                    "provider": status.get("provider"),
                    "reason": status.get("reason"),
                }),
            )
        return detail

    @app.get("/api/cases/{case_id}/audit")
    def case_audit(case_id: str):
        find_case(case_id)
        return audit_entries(case_id, limit=100_000)

    @app.get("/api/cases/{case_id}/letter")
    def case_letter(case_id: str, lang: Literal["de", "en"] = "de"):
        try:
            return build_letter(find_case(case_id), lang)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/identities")
    def identities():
        return _identities(desk.registry)

    @app.get("/api/applicant/cases")
    def applicant_cases(login: str = Query(min_length=1, max_length=120)):
        normalized_login = people.plain_name(login)
        summaries = []
        for summary in cases.list():
            case = cases.get(summary["id"])
            name_matches = people.plain_name(summary["applicant"]["name"]) == normalized_login
            custom_matches = (
                summary["group"] == "custom"
                and case.get("login") is not None
                and people.plain_name(case["login"]) == normalized_login
            )
            if name_matches or custom_matches:
                summaries.append(summary)
        return summaries

    @app.get("/api/applicant/cases/{case_id}")
    def applicant_case(case_id: str, login: str = Query(min_length=1, max_length=120)):
        case = find_case(case_id)
        summary, result = case["summary"], case["result"]
        name_matches = people.plain_name(summary["applicant"]["name"]) == people.plain_name(login)
        custom_matches = (
            summary["group"] == "custom"
            and case.get("login") is not None
            and people.plain_name(case["login"]) == people.plain_name(login)
        )
        if not (name_matches or custom_matches):
            raise HTTPException(status_code=403, detail="This case does not belong to this applicant")
        decision = result["decision"]
        response = {
            "summary": summary,
            "decision": {
                "decision": decision["decision"],
                "articles": decision["articles"],
                "articles_detail": decision["articles_detail"],
                "reason_de": decision["reason_de"],
                "reason_en": decision["reason_en"],
                "kind": decision["kind"],
            },
            "delivery": result["delivery"],
            "visible": case["visible_to_applicant"],
            "notes": result["notes"],
        }
        if case["visible_to_applicant"]:
            response["released"] = result["released"]
            response["funnel"] = [
                {**step, "count": outputs.protect_count(step["count"])}
                for step in result.get("funnel", [])
            ]
            manifest = result.get("spe")
            response["spe"] = None if not manifest else {
                "permit_id": manifest["permit_id"],
                "expires": manifest["expires"],
                "cohort_size": manifest["cohort_size"],
                "tables_copied": manifest["tables_copied"],
                "tables_not_copied": manifest["tables_not_copied"],
            }
        return response

    @app.post("/api/precheck")
    def precheck(body: PrecheckBody):
        request = body.request.model_dump(exclude_none=True)
        applicant = request.get("applicant")
        if isinstance(applicant, dict):
            request["applicant"] = applicant
        features = projects.analyze(request)
        decision = projects.decide(request, features)
        identity = desk.registry.check(request, features, login=body.login or "")
        warnings = []
        mappings, plan_summary, result_shape, protected_funnel, cohort_estimate = [], None, None, [], None
        try:
            ai_status = desk.ai.status()
            ai_mapper = (
                (lambda name, body: desk._map_term(name, body, cache_only=True))
                if ai_status["enabled"] else None
            )
            plan = parser.parse(request, desk.store, ai_mapper=ai_mapper)
            warnings.extend(plan.warnings)
            mappings = safe_data.mappings(plan, desk.store)
            for mapping in mappings:
                mapping["ai"] = bool(mapping.get("ai"))
            if decision["decision"] != "REJECT":
                protected_funnel = [
                    {**step, "count": outputs.protect_count(step["count"])}
                    for step in compiler.funnel(plan, desk.store)
                ]
                if protected_funnel:
                    cohort_estimate = protected_funnel[-1]["count"]
            groups = []
            for group in plan.groups:
                if group.dim == "age_band":
                    labels = [band.label for band in group.bands]
                elif group.dim == "year":
                    labels = [str(year) for year in (group.years or [2023, 2024, 2025])]
                else:
                    labels = list(desk.store.domains[group.dim])
                groups.append({"dim": group.dim, "labels": labels})
            plan_summary = {
                "unit": plan.unit,
                "groups": groups,
                "measures": [
                    {"key": measure.key, "label": measure.label, "type": measure.type}
                    for measure in plan.measures
                ],
            }
            result_shape = {
                "group_dims": [group["dim"] for group in groups],
                "cells": math.prod(len(group["labels"]) for group in groups),
            }
        except Exception as exc:
            warnings.append(f"Could not parse this draft: {exc}")
        art54 = [
            {
                "category": item["category"],
                "label_de": item["label_de"],
                "label_en": item["label_en"],
                "evidence": [
                    {key: evidence[key] for key in ("phrase", "field", "start", "end")}
                    for evidence in drop_contained_evidence(item["evidence"])
                ],
            }
            for item in features["prohibited"]
        ]
        return {
            "decision": {
                "decision": decision["decision"],
                "articles": decision["articles"],
                "reason_de": decision["reason_de"],
                "reason_en": decision["reason_en"],
                "trace": decision["trace"],
                "kind": decision["kind"],
            },
            "art54": art54,
            "allowed": features["allowed"],
            "justification": features["justifies_records"],
            "mappings": mappings,
            "plan": plan_summary,
            "result_shape": result_shape,
            "cohort_estimate": cohort_estimate,
            "funnel": protected_funnel,
            "warnings": warnings,
            "identity": {"status": identity["status"]},
            "flags": identity["flags"],
        }

    @app.get("/api/templates")
    def templates():
        with (ROOT / "demo" / "templates.json").open(encoding="utf-8") as stream:
            return json.load(stream)

    @app.post("/api/ai/draft")
    def ai_draft(body: AIDraftBody):
        status = desk.ai.status()
        if not status["enabled"]:
            _raise_ai_inactive()
        system, user = ai_spec.draft_messages(
            desk.store, body.text, body.lang, body.purpose
        )
        answer = desk.ai.call("draft", system, user, ai_spec.draft_schema())
        draft = answer["value"]
        if draft is None:
            raise HTTPException(
                status_code=503,
                detail=_ai_failure_detail(answer),
            )
        identity = next(
            (
                item for item in _identities(desk.registry)
                if body.login and people.plain_name(item["name"]) == people.plain_name(body.login)
            ),
            None,
        )
        applicant = identity or {
            "name": body.login or "",
            "organisation": "",
            "country": "",
        }
        request = {
            key: draft[key]
            for key in ("requested_as", "purpose", "question", "definitions")
        }
        request["applicant"] = {
            key: applicant.get(key, "") for key in ("name", "organisation", "country")
        }
        precheck_response = precheck(
            PrecheckBody(request=PrecheckRequest.model_validate(request), login=body.login)
        )
        return {
            "draft": draft,
            "precheck": precheck_response,
            "model": answer["model"],
            "provider": answer.get("provider", status.get("provider")),
            "cached": answer["cached"],
        }

    @app.post("/api/ai/explain/{case_id}")
    def ai_explain(case_id: str, login: str = Query(min_length=1, max_length=120)):
        case = cases.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        authorized = (
            people.plain_name(case["summary"]["applicant"]["name"]) == people.plain_name(login)
            or (
                case["summary"].get("group") == "custom"
                and people.plain_name(case.get("login") or "") == people.plain_name(login)
            )
        )
        if not authorized or not case["visible_to_applicant"]:
            raise HTTPException(status_code=403, detail="Applicant access denied")
        ai_status = desk.ai.status()
        if not ai_status["enabled"]:
            _raise_ai_inactive()
        system, user = ai_spec.explain_messages(case["result"])
        answer = desk.ai.call("explain", system, user, ai_spec.explain_schema())
        if answer["value"] is None:
            raise HTTPException(
                status_code=503,
                detail=_ai_failure_detail(answer),
            )
        return {
            **answer["value"],
            "model": answer["model"],
            "provider": answer.get("provider", ai_status.get("provider")),
            "cached": answer["cached"],
        }

    @app.post("/api/submit")
    def submit(body: SubmitBody):
        request = body.request.model_dump(exclude={"id"}, exclude_none=True)
        try:
            summary = cases.submit(request, login=body.login)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Could not process the request: {exc}",
            ) from exc
        return {"id": summary["id"], "summary": summary}

    @app.post("/api/decide")
    def decide(request: dict):
        try:
            result = desk.process(
                request, use_cache=False, actor="jury:decide", ai_live=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return decide_response(result)

    @app.get("/api/register")
    def register():
        with LETTER_TEXTS_PATH.open(encoding="utf-8") as stream:
            letter_texts = json.load(stream)
        entries = []
        for summary in cases.list():
            case = cases.get(summary["id"])
            request, result = case["result"]["request"], case["result"]
            status = summary["status"]
            publication_status = "in_review" if status in ("held_identity", "review_needed") else "decided"
            entry = {
                "reference": f"HDAB-AT/2026/{summary['id']}",
                "id": summary["id"],
                "received": summary["received_at"],
                "organisation": summary["applicant"]["organisation"],
                "kind": summary["kind"],
                "purpose": _public_text(request.get("purpose", ""), summary["applicant"]["name"]),
                "purpose_categories": _purpose_points(result["features"]["allowed"], letter_texts["categories"]),
                "publication_status": publication_status,
            }
            if publication_status == "decided":
                decision = result["decision"]
                entry.update({
                    "decision": decision["decision"],
                    "articles": decision["articles"],
                    "justification_de": _public_text(
                        decision["reason_de"], summary["applicant"]["name"]
                    ),
                    "justification_en": _public_text(
                        decision["reason_en"], summary["applicant"]["name"]
                    ),
                    "decided": _case_decided_at(case),
                    "permit": _public_permit(result.get("spe")),
                })
            entries.append(entry)
        return {
            "legal_basis": "Art. 57(1)(j)(ii)–(iii), Art. 58(1)(f) Regulation (EU) 2025/327",
            "entries": entries,
        }

    @app.get("/api/spe/{permit_id}")
    def spe_preview(permit_id: str, login: str = Query(min_length=1, max_length=120)):
        case = permit_case(permit_id)
        manifest = authorize_spe(case, permit_id, login)
        preview = settings.preview(desk.root, permit_id)
        if preview is None:
            raise HTTPException(status_code=404, detail="SPE workspace does not exist")
        desk.audit.log(
            "spe_viewed", case["summary"]["id"], actor=login,
            permit=permit_id, note="records viewed inside the SPE",
        )
        return {"manifest": manifest, "tables": preview["tables"]}

    @app.post("/api/spe/{permit_id}/query")
    def spe_query(permit_id: str, body: SpeQueryBody):
        case = permit_case(permit_id)
        manifest = authorize_spe(case, permit_id, body.login)
        return run_spe_query(case, manifest, body.sql, body.login, limit=200)

    @app.get("/api/spe/{permit_id}/download")
    def blocked_spe_download(permit_id: str, login: str | None = None):
        case = permit_case(permit_id, required=False)
        request_id = case["summary"]["id"] if case else permit_id
        settings.log_blocked_download(
            desk.audit,
            request_id,
            actor=login or "applicant",
            reason="Data may not leave the secure processing environment (Art. 73(2)).",
        )
        raise HTTPException(status_code=403, detail=DOWNLOAD_DETAIL)

    @app.get("/api/spe/{permit_id}/export/raw")
    def blocked_spe_raw_export(permit_id: str, login: str | None = None):
        return blocked_spe_download(permit_id, login)

    @app.post("/api/spe/{permit_id}/exports")
    def request_export(permit_id: str, body: SpeExportBody):
        case = permit_case(permit_id)
        manifest = authorize_spe(case, permit_id, body.login)
        query = run_spe_query(case, manifest, body.sql, body.login, limit=1000)
        record = exports.create(
            permit_id,
            case["summary"]["id"],
            body.title,
            body.note,
            body.sql,
            query["columns"],
            query["rows"],
            body.login,
            truncated=query["truncated"],
        )
        desk.audit.log(
            "export_requested", case["summary"]["id"], actor=body.login,
            export_id=record["id"], permit=permit_id, title=body.title,
            status=record["status"], check=record["check"]["result"],
        )
        return record

    @app.get("/api/spe/{permit_id}/exports")
    def list_applicant_exports(permit_id: str, login: str = Query(min_length=1, max_length=120)):
        case = permit_case(permit_id)
        authorize_spe(case, permit_id, login)
        return exports.list(permit_id=permit_id)

    @app.get("/api/exports")
    def list_exports(status: str | None = None):
        return exports.list(status=status)

    @app.get("/api/exports/{export_id}")
    def export_detail(export_id: str):
        record = exports.get(export_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown export")
        return record

    @app.post("/api/exports/{export_id}/review")
    def review_export(export_id: str, body: ExportReviewBody):
        try:
            record = exports.review(export_id, body.action, body.reason, body.reviewer)
        except ValueError as exc:
            status_code = 409 if isinstance(exc, ExportConflict) else 422
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown export")
        desk.audit.log(
            "export_reviewed", record["request_id"], actor=body.reviewer,
            export_id=export_id, permit=record["permit_id"], action=body.action,
            reason=body.reason, status=record["status"],
        )
        return record

    @app.get("/api/exports/{export_id}/download")
    def download_export(export_id: str, login: str = Query(min_length=1, max_length=120)):
        record = exports.get(export_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown export")
        case = permit_case(record["permit_id"], required=False)
        authorised = case is not None and any(
            people.plain_name(person_name) == people.plain_name(login)
            for person_name in (case["result"].get("spe") or {}).get("persons_with_access", [])
        )
        if record["status"] != "approved" or not authorised:
            settings.log_blocked_download(
                desk.audit,
                record["request_id"],
                actor=login,
                reason="Only an approved export may leave the secure processing environment (Art. 73(2)).",
            )
            raise HTTPException(status_code=403, detail=DOWNLOAD_DETAIL)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(record["columns"])
        writer.writerows(record["rows"])
        desk.audit.log(
            "export_downloaded", record["request_id"], actor=login,
            export_id=export_id, permit=record["permit_id"],
        )
        return Response(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="export_{export_id}.csv"'},
        )

    @app.get("/api/audit")
    def audit(limit: int = Query(default=300, ge=1, le=300), request_id: str | None = None):
        return audit_entries(request_id=request_id, limit=limit)

    @app.get("/api/audit/verify")
    def audit_verify():
        return desk.audit.verify()

    @app.get("/api/eval")
    def evaluate(suite: Literal["official", "all"] = "official"):
        requests = [request for group, request in load_requests(data_dir) if group == "test"]
        official = evaluation.run(desk, requests, runs=3)
        own = None
        if suite == "all":
            all_requests = [request for _, request in load_requests(data_dir)]
            oracle_path = ROOT / "tests" / "oracle" / "expected.json"
            if oracle_path.exists():
                with oracle_path.open(encoding="utf-8") as stream:
                    oracle = json.load(stream)
                request_dir = ROOT / "tests" / "oracle" / "requests"
                all_requests.extend(
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(request_dir.glob("T*.json"))
                )
                own = evaluation.run_strict(desk, all_requests, oracle)
        return {"official": official, "own": own}

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_document():
        if app.openapi_schema is None:
            app.openapi_schema = app.openapi()
        return app.openapi_schema

    @app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
    def api_docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{app.title} - Swagger UI",
        )

    dist = ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def frontend_missing():
            return (
                "<!doctype html><html lang='en'><meta charset='utf-8'>"
                "<title>AccessDesk 2</title><body><p>Frontend not built. "
                "API docs: <a href='/docs'>/docs</a></p></body></html>"
            )

    return app


def _identities(registry):
    rows = []
    for wallet in registry.data["wallets"]:
        organisation = next(
            (cred["claims"]["name"] for cred in wallet["credentials"] if cred["type"] == "organisation"),
            "",
        )
        person = next(
            (cred["claims"] for cred in wallet["credentials"] if cred["type"] == "person_identity"),
            {},
        )
        rows.append({
            "name": wallet["holder"],
            "organisation": organisation,
            "country": person.get("country", ""),
            "credential_types": [credential["type"] for credential in wallet["credentials"]],
        })
    return rows


def _ai_status(cases):
    return cases.desk.ai.status()


def _raise_ai_inactive():
    raise HTTPException(
        status_code=503,
        detail={
            "de": "KI ist nicht aktiv (kein API-Schlüssel).",
            "en": "AI is not active (no API key).",
        },
    )


def _ai_failure_detail(answer):
    if answer.get("provider") == "gemini" and answer.get("reason") == "quota_exhausted":
        return {
            "de": "Gemini-Kontingent erschöpft. Bitte später erneut versuchen.",
            "en": "Gemini quota exhausted. Please try again later.",
        }
    if answer.get("reason") == "authentication_error":
        return {
            "de": "Der KI-API-Schlüssel wurde nicht akzeptiert.",
            "en": "The AI API key was not accepted.",
        }
    return {"de": "KI-Dienst ist nicht verfügbar.", "en": "AI service is unavailable."}


def _purpose_points(allowed, category_texts):
    letters = []
    for entry in allowed:
        category = category_texts.get(entry.get("category"))
        if not category:
            continue
        for letter in re.findall(r"\bpoints?\s+\(([a-f])\)", category["en"]):
            if letter not in letters:
                letters.append(letter)
    return letters


def _case_decided_at(case):
    audit_path = Path(case["audit_path"])
    if not audit_path.is_file():
        return case["summary"]["received_at"]
    with audit_path.open(encoding="utf-8") as stream:
        entries = [json.loads(line) for line in stream if line.strip()]
    entry = next(
        (item for item in reversed(entries) if item["request_id"] == case["summary"]["id"]),
        None,
    )
    return (entry or {}).get("time", case["summary"]["received_at"])


def _public_permit(manifest):
    if not manifest:
        return None
    return {
        "expires": manifest["expires"],
        "record_types": [
            {
                "table": item["table"],
                "label_de": table_label(item["table"], "de", item.get("note")),
                "label_en": table_label(item["table"], "en", item.get("note")),
            }
            for item in manifest["tables_copied"]
        ],
    }


def _public_text(text, applicant_name):
    for token in people.plain_name(applicant_name).split():
        text = re.sub(rf"(?i)(?<!\w){re.escape(token)}(?!\w)", "", text)
    text = re.sub(r"\bp-[0-9a-f]{8}\b|\be\d{6}\b", "[redacted]", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def decide_response(result):
    return {
        "id": result["id"],
        "decision": result["decision"]["decision"],
        "articles": result["decision"]["articles"],
        "reason_en": result["decision"]["reason_en"],
        "reason_de": result["decision"]["reason_de"],
        "answer": (result.get("released") or {}).get("answer"),
        "cohort_size": (result.get("spe") or {}).get("cohort_size"),
        "delivery": result["delivery"],
        "warnings": result["warnings"],
    }
