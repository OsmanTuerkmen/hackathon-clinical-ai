"""Request parsing: plain-English definitions -> QuerySpec."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..config import Settings
from ..models import AccessRequest, PurposeAssessment, QuerySpec
from ..terminology import Terminology
from .rules import ParseReport, parse_rules


class ParseResult(BaseModel):
    spec: QuerySpec | None
    report: ParseReport
    source: Literal["rules", "llm", "llm_cache", "none"]
    llm_purpose: PurposeAssessment | None = None


def parse_request(request: AccessRequest, terminology: Terminology, settings: Settings) -> ParseResult:
    """Parse the request into a QuerySpec. Rules only for now; the LLM path is attached behind this function."""
    spec, report = parse_rules(request, terminology)
    return ParseResult(spec=spec, report=report, source="rules" if spec is not None else "none", llm_purpose=None)


__all__ = ["ParseReport", "ParseResult", "parse_request", "parse_rules"]
