"""Request parsing: plain-English definitions -> QuerySpec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..config import Settings
from ..models import AccessRequest, PurposeAssessment, QuerySpec
from ..terminology import Terminology
from .rules import ParseReport, parse_rules
from . import llm


class ParseResult(BaseModel):
    spec: QuerySpec | None
    report: ParseReport
    source: Literal["rules", "llm", "llm_cache", "none"]
    llm_purpose: PurposeAssessment | None = None


def parse_request(request: AccessRequest, terminology: Terminology, settings: Settings) -> ParseResult:
    """Prefer complete deterministic rules; optionally translate unhandled request text."""
    spec, report = parse_rules(request, terminology)
    result = ParseResult(spec=spec, report=report, source="rules" if spec is not None else "none")
    if report.complete or settings.llm_mode != "auto" or not settings.anthropic_api_key:
        return result
    try:
        translated, purpose, cached = llm.parse_with_llm(request, terminology, settings)
    except (llm.LLMError, TimeoutError):
        report.notes.append("LLM assistance unavailable or unsuccessful; rule result retained, needs manual review.")
        return result
    mappings = llm.verify_spec(translated, terminology)
    return ParseResult(
        spec=translated, llm_purpose=purpose, source="llm_cache" if cached else "llm",
        report=ParseReport(
            understood=[*report.understood, *report.not_understood],
            notes=[*report.notes, "Remaining request text translated by LLM; staff should review the generated query.",
                   *(mapping.warning for mapping in mappings if mapping.warning)],
            mappings=mappings,
        ),
    )


__all__ = ["ParseReport", "ParseResult", "parse_request", "parse_rules"]
