"""Deterministic rule parser: plain-English ``definitions`` (+ ``question``) -> typed QuerySpec.

Sentence classes (first match wins): term definition, age bands, active-medication rule, latest
measurement, encounter counting, "Report per ...", cohort size. Every definition sentence and every
report item ends up in ``ParseReport.understood`` or ``ParseReport.not_understood``. Nothing here is
specific to a request id or its exact wording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError, computed_field

from ..models import (
    AccessRequest,
    AgeBand,
    CodeSet,
    ConditionCriterion,
    Dimension,
    EncounterScope,
    ObservationCriterion,
    QuerySpec,
)
from ..terminology import Terminology, TermMapping
from .metrics import Metrics, parse_item, resolve_percent_terms, split_items
from .phrases import (
    KIND_FOR_SYSTEM,
    TABLE_FOR_KIND,
    Context,
    Term,
    add_unique,
    age_sex_criteria,
    normalise,
    phrase_criteria,
    strip_end,
)


class ParseReport(BaseModel):
    understood: list[str] = []
    not_understood: list[str] = []
    notes: list[str] = []
    mappings: list[TermMapping] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complete(self) -> bool:
        return not self.not_understood


# --- Sentence patterns ---------------------------------------------------------------------------

_TERM_DEF = re.compile(r"^(?P<term>[^=]{1,80}?)\s*=\s*(?P<body>.+)$")
_AGE_BANDS = re.compile(r"^age\s+(?:bands?|groups?)\b(?P<head>[^:]*):\s*(?P<bands>.+)$", re.I)
_ACTIVE_RULE = re.compile(r"\bmedications?\s+(?:is|are)\s+active\b", re.I)
_LATEST = re.compile(r"\buse the (?:latest|last|most recent) (?P<name>.+?) (?:\(loinc (?P<code>[\d-]+)\) )?per patient", re.I)
_LEFT_OUT = re.compile(r"\bpatients without (?:a |an |any )?(?P<name>.+?) are (?:left out|excluded)", re.I)
_ENC_COUNT = re.compile(r"\bcount (?:stays|encounters|visits|admissions)\b", re.I)
_REPORT = re.compile(r"^report (?:per|by|for each) (?P<dims>[^:]+):\s*(?P<items>.+)$", re.I)
_COHORT_SIZE = re.compile(r"\breport the size of the cohort\b|\bcohort size\b", re.I)

_CODE_INTRO = re.compile(r"\b(?:start(?:s|ing)?|begin(?:s|ning)?)\s+with\b", re.I)
_CODE = re.compile(r"\b[A-Z]\d{2}(?:[A-Z]{1,2}\d{0,2}|\.\d+)?\b")
_ICD_SHAPE = re.compile(r"[A-Z]\d{2}(?:\.\d+)?")
_ATC_SHAPE = re.compile(r"[A-Z]\d{2}[A-Z]{0,2}\d{0,2}")
_LOINC = re.compile(r"\bloinc\s*(?:code\s*)?(\d+-\d)\b", re.I)
_ENC_DEF = re.compile(
    r"\bencounters?\s+(?:with|of)\s+type\s+'?(inpatient|outpatient|emergency)'?"
    r"|\b(inpatient|outpatient|emergency)\s+(?:encounter|stay|admission|visit)s?\b",
    re.I,
)
_PRIMARY = re.compile(r"\b(?:main|primary)\s+diagnosis\b|\bprimary_icd10\b", re.I)
_PRIMARY_TEXT = re.compile(r"\b(?:main|primary)\s+diagnosis(?:\s*\(primary_icd10\))?(?:\s+(?:is|of|=))?\s+(?P<x>.+)$", re.I)
_PERCENT_DEF = re.compile(r"^(?P<num>.+?)\s*/\s*(?P<den>.+?)\s*(?:x|\*|times)\s*100\b", re.I)
_ATC_HINT = re.compile(r"\batc\b|\bmedications?\b|\bprescriptions?\b|\bdrugs?\b", re.I)
_ICD_HINT = re.compile(r"\bicd-?10\b|\bdiagnos[ie]s\b|\bconditions?\b", re.I)


_DIMS: list[tuple[str, re.Pattern[str]]] = [
    ("age_band", re.compile(r"\bage\s*(?:bands?|groups?|classes?)\b|\bbands?\b")),
    ("region", re.compile(r"\bregions?\b|\bfederal\s+states?\b|\bstates?\b|\bprovinces?\b|\bbundesl[aä]nd")),
    ("data_holder", re.compile(r"\bhospitals?\b|\bdata[ _]holders?\b|\bclinics?\b|\bsites?\b|\bklinik")),
    ("sex", re.compile(r"\bsex\b|\bgenders?\b")),
]
_PATIENT_DIM = re.compile(r"\bpatients?\b|\bperson\b|\bindividual")
RECORD_TYPE_ORDER = ["patients", "conditions", "medications", "observations", "encounters"]
_RECORD_PATTERNS = {
    "patients": re.compile(r"\bdemographic|\bbirth|\bpatient data\b", re.I),
    "conditions": re.compile(r"\bconditions?\b|\bdiagnos", re.I),
    "medications": re.compile(r"\bmedications?\b|\bprescriptions?\b|\bdrugs?\b", re.I),
    "observations": re.compile(r"\bobservations?\b|\bmeasurements?\b|\blab(?:oratory|s)?\b|\bvalues?\b", re.I),
    "encounters": re.compile(r"\bencounters?\b|\bvisits?\b|\bstays?\b|\badmissions?\b", re.I),
}
_VALUE_WORDS = re.compile(r"((?:[\w/+-]+\s+){0,2}[\w/+-]+)\s+values?\b", re.I)


@dataclass
class _State:
    bands: list[AgeBand] | None = None
    enc_count: bool = False
    start_from: date | None = None
    start_to: date | None = None
    left_out: list[Any] = field(default_factory=list)
    cohort_size: bool = False
    outcomes: list[list[Any]] = field(default_factory=list)  # [order, text, ok]

    def record(self, order: float, text: str, ok: bool) -> list[Any]:
        entry = [order, text, ok]
        self.outcomes.append(entry)
        return entry


# --- Definitions -------------------------------------------------------------------------------


def _term_name(display: str) -> str:
    return re.sub(r"^(?:an?|the)\s+", "", display.lower()).strip()


def _codes_after_intro(body: str) -> list[str]:
    m = _CODE_INTRO.search(body)
    return _CODE.findall(body[m.end() :]) if m else []


def _explicit_codeset(body: str, codes: list[str], label: str) -> CodeSet | None:
    if _ATC_HINT.search(body) and not _ICD_HINT.search(body.replace("ATC code", "")):
        system = "atc"
    elif _ICD_HINT.search(body) or all(_ICD_SHAPE.fullmatch(c) for c in codes):
        system = "icd10"
    else:
        system = "atc"
    shape = _ATC_SHAPE if system == "atc" else _ICD_SHAPE
    if not all(shape.fullmatch(c) for c in codes):
        return None
    return CodeSet(system=system, prefixes=list(dict.fromkeys(codes)), label=label, source="explicit")


def _system_hint(body: str) -> str | None:
    b = body.lower()
    if re.search(r"\bstay|\badmission|\bmain diagnosis|\bprimary diagnosis", b):
        return "primary"
    if re.search(r"\bprescription|\bmedication|\bdrug", b):
        return "atc"
    if re.search(r"\bmeasurement|\bvalue|\btest\b|\blevel", b):
        return "loinc"
    return None


def _references(body_l: str, ctx: Context, own: str) -> bool:
    return any(t.name != own and t.kind != "percent" and t.pattern().search(body_l) for t in ctx.terms.values())


def _composite(name: str, display: str, body_l: str, ctx: Context) -> Term | None:
    """A term defined by a noun phrase over other terms ("Cohort = adults with ...")."""
    phrase = phrase_criteria(body_l, ctx)
    if phrase.unresolved or not phrase.criteria:
        return None
    return Term(name, display, "criteria", criteria=phrase.criteria)


def _primary_from_text(text: str, ctx: Context) -> CodeSet | None:
    """Main diagnosis named in words: a defined condition term, else the terminology."""
    for term in sorted(ctx.terms.values(), key=lambda t: -len(t.name)):
        if term.kind == "condition" and term.pattern().search(text.lower()):
            ctx.used_terms.add(term.name)
            return term.codes
    return ctx.terminology.lookup(text, system="icd10")


def _define(display: str, body: str, ctx: Context) -> Term | None:
    """Analyse one ``Term = body`` definition; None if it cannot be understood."""
    name = _term_name(display)
    body_l = body.lower()
    if name == "cohort":
        return _composite(name, display, body_l, ctx)
    m = _PERCENT_DEF.match(body_l)
    if m:
        return Term(name, display, "percent", percent=(m.group("num"), m.group("den")))

    codes = _codes_after_intro(body)
    enc = _ENC_DEF.search(body)
    if enc or _PRIMARY.search(body):
        types = [(enc.group(1) or enc.group(2)).lower()] if enc else []
        primary = None
        if _PRIMARY.search(body):
            if codes:
                primary = CodeSet(system="icd10", prefixes=list(dict.fromkeys(codes)), label=display, source="explicit")
            elif pm := _PRIMARY_TEXT.search(body):
                primary = _primary_from_text(strip_end(pm.group("x")), ctx)
            if primary is None:
                return None
            ctx.add_mapping(display, primary, "primary_icd10")
        return Term(name, display, "encounter", enc_types=types, enc_primary=primary)
    if _references(body_l, ctx, name) and (term := _composite(name, display, body_l, ctx)):
        return term
    if codes:
        cs = _explicit_codeset(body, codes, display)
        if cs is None:
            return None
        kind = KIND_FOR_SYSTEM[cs.system]
        ctx.add_mapping(display, cs, TABLE_FOR_KIND[kind])
        return Term(name, display, kind, codes=cs)
    lm = _LOINC.search(body)
    if lm:
        cs = CodeSet(system="loinc", prefixes=[lm.group(1)], label=display, source="explicit")
        ctx.add_mapping(display, cs, "observations")
        return Term(name, display, "measurement", codes=cs)
    found, _spans = age_sex_criteria(body_l)
    if found:
        return Term(name, display, "criteria", criteria=found)

    hint = _system_hint(body)
    system = None if hint in (None, "primary") else hint
    cs = ctx.terminology.lookup(body, system=system) or ctx.terminology.lookup(display, system=system)
    if cs is None:
        return None
    if hint == "primary" and cs.system == "icd10":
        ctx.add_mapping(display, cs, "primary_icd10")
        types = [t.lower() for t in re.findall(r"\b(inpatient|outpatient|emergency)\b", body_l)]
        return Term(name, display, "encounter", enc_types=types, enc_primary=cs)
    kind = KIND_FOR_SYSTEM[cs.system]
    ctx.add_mapping(display, cs, TABLE_FOR_KIND[kind])
    return Term(name, display, kind, codes=cs)


# --- Other sentence classes ----------------------------------------------------------------------


def _parse_bands(text: str) -> list[AgeBand] | None:
    bands: list[AgeBand] = []
    for part in re.split(r"\s*,\s*|\s+and\s+(?!older|over)", strip_end(text)):
        part = re.sub(r"\s+years?$", "", part.strip())
        if not part:
            continue
        if m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", part):
            bands.append(AgeBand(label=part, min=int(m.group(1)), max=int(m.group(2))))
        elif m := re.fullmatch(r"(\d+)\s*\+|(\d+)\s+(?:and|or)\s+(?:older|over)", part):
            bands.append(AgeBand(label=part, min=int(m.group(1) or m.group(2))))
        elif m := re.fullmatch(r"(?:under|<)\s*(\d+)", part):
            bands.append(AgeBand(label=part, min=0, max=int(m.group(1)) - 1))
        else:
            return None
    return bands or None


def _default_bands(width: int) -> list[AgeBand]:
    bands, lo = [], 0
    while lo + width <= 90:
        bands.append(AgeBand(label=f"{lo}-{lo + width - 1}", min=lo, max=lo + width - 1))
        lo += width
    bands.append(AgeBand(label=f"{lo}+", min=lo))
    return bands


def _check_reference_date(text: str, ctx: Context, what: str) -> None:
    m = re.search(r"\bon\s+(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})", text, re.I)
    if m and m.group(1).lower() not in ("31 december 2025", "2025-12-31"):
        ctx.note(f"{what} refer to {m.group(1)}; the data's reference date 31 December 2025 is used.")


def _measurement(name: str, code: str | None, ctx: Context) -> tuple[str, CodeSet] | None:
    name = re.sub(r"\s+(?:values?|measurements?|results?)$", "", name.strip().lower())
    if code:
        cs = CodeSet(system="loinc", prefixes=[code], label=name, source="explicit")
    elif name in ctx.terms and ctx.terms[name].kind == "measurement":
        cs = ctx.terms[name].codes
    else:
        cs = ctx.terminology.lookup(name, system="loinc")
    if cs is None:
        return None
    ctx.add_mapping(name, cs, "observations")
    return name, cs


def _other_sentence(text: str, ctx: Context, st: _State) -> bool:
    """Non-definition, non-report sentences; False if no pattern applies."""
    if m := _AGE_BANDS.match(text):
        st.bands = _parse_bands(m.group("bands"))
        _check_reference_date(m.group("head"), ctx, "Age bands")
        return st.bands is not None
    if _ACTIVE_RULE.search(text):
        ctx.active_rule = True
        _check_reference_date(text, ctx, "Active medications")
        return True
    if m := _LATEST.search(text):
        found = _measurement(m.group("name"), m.group("code"), ctx)
        if found is None:
            return False
        name, cs = found
        ctx.terms.setdefault(name, Term(name, m.group("name"), "measurement", codes=cs))
        if lo := _LEFT_OUT.search(text):
            left = _measurement(lo.group("name"), None, ctx) or (None, cs)
            add_unique(st.left_out, [ObservationCriterion(kind="observation", codes=left[1])])
        return True
    if _ENC_COUNT.search(text):
        st.enc_count = True
        if m := re.search(r"\bbetween\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})", text):
            st.start_from, st.start_to = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        elif m := re.search(r"\bin\s+(\d{4})\b", text):
            year = int(m.group(1))
            st.start_from, st.start_to = date(year, 1, 1), date(year, 12, 31)
        return True
    if _COHORT_SIZE.search(text):
        st.cohort_size = True
        return True
    return False


# --- Report sentence: dimensions -----------------------------------------------------------------


def _dimension(chunk: str, st: _State, ctx: Context) -> Dimension | str | None:
    """A Dimension, "patient" for a patient-level listing, or None if not understood."""
    c = chunk.lower()
    for kind, pattern in _DIMS:
        if pattern.search(c):
            if kind != "age_band":
                return Dimension(kind=kind)
            bands = st.bands
            if bands is None and (w := re.search(r"(\d+)[- ]year", c)):
                bands = _default_bands(int(w.group(1)))
                ctx.note(f"No age bands defined; {w.group(1)}-year bands were used.")
            return Dimension(kind="age_band", bands=bands) if bands else None
    return "patient" if _PATIENT_DIM.search(c) else None


def _dimensions(dims_text: str, st: _State, ctx: Context, *, strict: bool) -> list[Dimension] | str | None:
    out: list[Dimension] = []
    for chunk in re.split(r"\s+and\s+|\s*,\s*|\s+x\s+", dims_text.strip()):
        if not chunk.strip():
            continue
        dim = _dimension(chunk, st, ctx)
        if isinstance(dim, Dimension):
            if all(d.kind != dim.kind for d in out):
                out.append(dim)
        elif strict:
            return dim
    return out


# --- Record types (access applications) ----------------------------------------------------------


def _record_types(request: AccessRequest, ctx: Context) -> tuple[list[str], CodeSet | None]:
    text = normalise(f"{request.question} {request.purpose}")
    types = [t for t in RECORD_TYPE_ORDER if _RECORD_PATTERNS[t].search(text)]
    if "observations" not in types:
        return types, None
    prefixes: list[str] = []
    for m in _VALUE_WORDS.finditer(text):
        words = m.group(1).split()
        for n in range(len(words), 0, -1):
            cs = ctx.terminology.lookup(" ".join(words[-n:]), system="loinc")
            if cs is not None:
                add_unique(prefixes, cs.prefixes)
                break
    if not prefixes:
        return types, None
    return types, CodeSet(system="loinc", prefixes=prefixes, label="requested measurements", source="lexicon")


def _is_access_application(request: AccessRequest) -> bool:
    return "access application" in request.requested_as.lower() or "pseudonym" in (request.requested_format or "").lower()


# --- Entry point ---------------------------------------------------------------------------------


def _sentences(definitions: list[str]) -> list[tuple[float, str, str]]:
    out: list[tuple[float, str, str]] = []
    for i, original in enumerate(definitions):
        norm = normalise(original)
        parts = [p.strip() for p in norm.split(";")]
        if len(parts) > 1 and all("=" in p for p in parts):
            out += [(i + j / 100, p, strip_end(p)) for j, p in enumerate(parts)]
        else:
            out.append((float(i), original, strip_end(norm)))
    return out


def parse_rules(request: AccessRequest, terminology: Terminology) -> tuple[QuerySpec | None, ParseReport]:
    ctx = Context(terminology)
    st = _State()
    sentences = _sentences(request.definitions)
    definitions = [(o, t, m) for o, t, n in sentences if (m := _TERM_DEF.match(n)) and not _REPORT.match(n)]
    def_orders = {o for o, _t, _m in definitions}
    reports = [(o, t, n) for o, t, n in sentences if _REPORT.match(n)]
    others = [(o, t, n) for o, t, n in sentences if o not in def_orders and not _REPORT.match(n)]

    # Pass A: other sentences (active rule, bands, latest measurement ...) and simple definitions;
    # definitions that refer to other terms (or define the cohort) wait until those are known.
    for order, text, norm in others:
        st.record(order, text, _other_sentence(norm, ctx, st))
    names = {_term_name(m.group("term")) for _o, _t, m in definitions}
    deferred = []
    for order, text, m in definitions:
        name, body_l = _term_name(m.group("term")), m.group("body").lower()
        refers = any(Term(n, n, "criteria").pattern().search(body_l) for n in names - {name})
        if name == "cohort" or (refers and not _PERCENT_DEF.match(body_l)):
            deferred.append((order, text, m))
            continue
        term = _define(m.group("term").strip(), m.group("body"), ctx)
        if term is not None:
            ctx.terms[term.name] = term
        st.record(order, text, term is not None)
    for order, text, m in deferred:
        term = _define(m.group("term").strip(), m.group("body"), ctx)
        if term is not None:
            ctx.terms[term.name] = term
        st.record(order, text, term is not None)

    # Pass B: report sentences -> group_by + metrics.
    b = Metrics(ctx)
    group_by: list[Dimension] = []
    for order, text, norm in reports:
        m = _REPORT.match(norm)
        assert m is not None
        dims = _dimensions(m.group("dims"), st, ctx, strict=True)
        if dims == "patient":
            ctx.note("A patient-level listing is not available as statistics.")
            st.record(order, text, False)
            continue
        head = norm[: m.start("items")].strip()
        st.record(order, head, isinstance(dims, list))
        if isinstance(dims, list):
            add_unique(group_by, dims)
        for j, item in enumerate(split_items(m.group("items"))):
            entry = st.record(order + (j + 1) / 1000, item, False)
            entry[2] = parse_item(item, ctx, b, entry)

    question = normalise(request.question).lower()
    if not reports:
        for qm in re.finditer(r"\b(?:by|in each|per|for each|across)\s+([^?.;]+)", question):
            dims = _dimensions(qm.group(1), st, ctx, strict=False)
            if isinstance(dims, list):
                add_unique(group_by, [d for d in dims if all(g.kind != d.kind for g in group_by)])
        if not st.cohort_size and (qm := re.search(r"\bhow many\s+(.+?)(?=,|\?|\.|\s+(?:by|in each|per|for each|across)\b|$)", question)):
            item = qm.group(1)
            entry = st.record(len(sentences) + 1, item, False)
            entry[2] = parse_item(item, ctx, b, entry)
            ctx.note("No 'Report per ...' sentence: the item was taken from the question.")
    resolve_percent_terms(b, ctx)

    spec = _build_spec(request, ctx, st, b, group_by)
    st.outcomes.sort(key=lambda e: e[0])
    report = ParseReport(
        understood=[t for _o, t, ok in st.outcomes if ok],
        not_understood=[t for _o, t, ok in st.outcomes if not ok],
        notes=ctx.notes,
        mappings=ctx.mappings,
    )
    return spec, report


def _build_spec(
    request: AccessRequest, ctx: Context, st: _State, b: Metrics, group_by: list[Dimension]
) -> QuerySpec | None:
    if st.cohort_size:
        cohort = ctx.terms.get("cohort")
        population = list(cohort.criteria) if cohort is not None else list(b.base or [])
        if not population:
            ctx.note("The cohort could not be determined.")
            return None
        metrics: list[Any] = []
    else:
        if not b.metrics:
            ctx.note("No metric could be derived from the request.")
            return None
        population = list(b.base or [])
        for term in ctx.terms.values():
            if term.kind == "condition" and term.name not in ctx.used_terms and term.codes is not None:
                add_unique(population, [ConditionCriterion(kind="condition", codes=term.codes)])
                ctx.note(f"'{term.display}' is defined but not used in a report item; it restricts the population.")
        add_unique(population, st.left_out)
        metrics = b.metrics

    unit = "encounter" if (st.enc_count or b.encounter) else "patient"
    scope = None
    if unit == "encounter":
        scope = EncounterScope(
            types=b.enc_types, start_from=st.start_from, start_to=st.start_to, primary_icd10=b.enc_primary
        )
    record_types: list[str] = []
    obs_codes = None
    if _is_access_application(request):
        record_types, obs_codes = _record_types(request, ctx)
    try:
        return QuerySpec(
            unit=unit,
            population=population,
            encounter_scope=scope,
            group_by=group_by,
            metrics=metrics,
            output="cohort_size" if st.cohort_size else "statistics",
            record_types=record_types,
            observation_codes=obs_codes,
        )
    except ValidationError as exc:
        ctx.note(f"No valid query could be built: {exc.errors()[0]['msg']}")
        return None
