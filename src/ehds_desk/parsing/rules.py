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
    MASK,
    TABLE_FOR_KIND,
    Context,
    Term,
    add_unique,
    age_sex_criteria,
    coded_criterion,
    mask,
    normalise,
    phrase_criteria,
    primary_clause,
    residual,
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
_ENC_COUNT = re.compile(
    r"^count\s+(?:(?P<type>inpatient|outpatient|emergency)\s+)?(?:stays|encounters|visits|admissions|hospitali[sz]ations)\b"
)
_START = r"(?:(?:whose|with|where)\s+(?:the\s+)?start_date\s+(?:is\s+)?|(?:that\s+|which\s+)?start(?:ed|ing|s)?\s+)?"
_DATE_RANGE = re.compile(rf"\b{_START}between\s+(?P<a>\d{{4}}-\d{{2}}-\d{{2}})\s+and\s+(?P<b>\d{{4}}-\d{{2}}-\d{{2}})")
_DATE_YEAR = re.compile(rf"\b{_START}in\s+(?P<y>\d{{4}})\b")
_REPORT = re.compile(r"^report (?:per|by|for each) (?P<dims>[^:]+):\s*(?P<items>.+)$", re.I)
_COHORT_SIZE = re.compile(r"\breport the size of the cohort\b|\bcohort size\b", re.I)

_CODE_LIST = re.compile(
    r"\b(?:start(?:s|ing)?|begin(?:s|ning)?)\s+with\s+(?P<codes>[a-z]\d{2}[a-z0-9.]*(?:\s*(?:,|or|and)\s*[a-z]\d{2}[a-z0-9.]*)*)"
)
# "Diabetes = E11." / "Hip fracture = ICD-10 S72." / "Metformin = ATC A10BA02." / "ICD-10 E11.*"
_BARE_CODES = re.compile(
    r"(?:(?:icd-?10|atc)(?:\s+codes?)?\s*:?\s*)?"
    r"(?P<codes>[a-z]\d{2}[a-z0-9.]*(?:\.?\*)?(?:\s*(?:,|or)\s*[a-z]\d{2}[a-z0-9.]*(?:\.?\*)?)*)"
)
_ICD_SHAPE = re.compile(r"[A-Z]\d{2}(?:\.\d+)?")
_ATC_SHAPE = re.compile(r"[A-Z]\d{2}[A-Z]{0,2}\d{0,2}")
_LOINC_DEF = re.compile(r"\(?\s*\bloinc\s*(?:code\s*)?(\d+-\d)\b\s*\)?")
_ENC_TYPES_DEF = re.compile(
    r"\b(?:encounters?|stays?|visits?|admissions?)\s+(?:with|of)\s+type\s+'?(?:inpatient|outpatient|emergency)'?"
    r"(?:\s*(?:,|or)\s*'?(?:inpatient|outpatient|emergency)'?)*"
    r"|\b(?:inpatient|outpatient|emergency)\s+(?:encounters?|stays?|visits?|admissions?)\b"
)
_ENC_NOUN = re.compile(r"\b(?:stays?|encounters?|visits?|admissions?|hospitali[sz]ations?)\b")
_PERCENT_DEF = re.compile(r"^(?P<num>.+?)\s*/\s*(?P<den>.+?)\s*(?:x|\*|times)\s*100\b", re.I)
_ATC_HINT = re.compile(r"\batc\b|\bmedications?\b|\bprescriptions?\b|\bdrugs?\b", re.I)
_ICD_HINT = re.compile(r"\bicd-?10\b|\bdiagnos[ie]s\b|\bconditions?\b", re.I)
_EXCLUSION_DEF = re.compile(r"\b(?:excluding|except|but\s+not|not|other\s+than|without|no|never)\b")
_REF_DATE = re.compile(r"\b(?:on|at|as\s+of)\s+(?P<d>\d{1,2}\s+[a-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})")
_DEF_WORDS = re.compile(r"\b(?:icd-?10|atc|loinc)(?:\s+codes?)?\b")
_ACTIVE_DEF = re.compile(r"\b(?:active|current|currently)\b")
# Words of a definition body that only describe where a code lives ("any condition with an ICD-10 code").
DEF_FILLER = frozenset(
    {"condition", "conditions", "code", "codes", "encounter", "encounters", "stay", "stays", "visit", "visits",
     "admission", "admissions", "type", "medication", "medications", "drug", "drugs", "entry", "entries",
     "record", "records", "sex", "gender"}
)  # fmt: skip


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
    enc_types: list[str] = field(default_factory=list)
    enc_primary: CodeSet | None = None
    start_from: date | None = None
    start_to: date | None = None
    left_out: list[Any] = field(default_factory=list)
    cohort_size: bool = False
    count_entry: list[Any] | None = None  # outcome of the "Count stays ..." sentence
    outcomes: list[list[Any]] = field(default_factory=list)  # [order, text, ok]

    def record(self, order: float, text: str, ok: bool) -> list[Any]:
        entry = [order, text, ok]
        self.outcomes.append(entry)
        return entry


# --- Definitions -------------------------------------------------------------------------------


def _term_name(display: str) -> str:
    return re.sub(r"^(?:an?|the)\s+", "", display.lower()).strip()


def _explicit_codeset(body: str, codes: list[str], label: str) -> CodeSet | None:
    if _ATC_HINT.search(body) and not _ICD_HINT.search(re.sub(r"\batc\s+codes?\b", "", body)):
        system = "atc"
    elif _ICD_HINT.search(body) or all(_ICD_SHAPE.fullmatch(c) for c in codes):
        system = "icd10"
    else:
        system = "atc"
    shape = _ATC_SHAPE if system == "atc" else _ICD_SHAPE
    if not all(shape.fullmatch(c) for c in codes):
        return None
    return CodeSet(system=system, prefixes=list(dict.fromkeys(codes)), label=label, source="explicit")


def _references(body_l: str, ctx: Context, own: str) -> bool:
    return any(t.name != own and t.kind != "percent" and t.pattern().search(body_l) for t in ctx.terms.values())


def _composite(name: str, display: str, body_l: str, ctx: Context) -> Term | None:
    """A term defined by a noun phrase over other terms ("Cohort = adults with ...")."""
    phrase = phrase_criteria(body_l, ctx)
    if phrase.unresolved:
        return None
    if phrase.encounter_subject:  # "inpatient stay with main diagnosis hip fracture"
        if phrase.criteria:
            return None
        return Term(name, display, "encounter", enc_types=phrase.enc_types, enc_primary=phrase.enc_primary)
    if not phrase.criteria:
        return None
    return Term(name, display, "criteria", criteria=phrase.criteria)


def _plain(name: str, display: str, body_l: str, active: bool, ctx: Context) -> Term | None:
    """A definition in words only ("a diagnosis of asthma"): terminology lookup of the body.

    The term name is looked up only when the body has no content of its own; otherwise a partial
    body ("asthma requiring oral steroids") would silently map to the broader term.
    """
    if _ENC_NOUN.search(body_l):
        return None  # a stay defined without main-diagnosis wording
    system = "atc" if re.search(r"\bprescription|\bmedication|\bdrug", body_l) else None
    if system is None and re.search(r"\bmeasurement|\bvalue|\btest\b|\blevel", body_l):
        system = "loinc"
    cs = ctx.terminology.lookup(body_l, system=system)
    if cs is None and not residual(body_l, DEF_FILLER):
        cs = ctx.terminology.lookup(display, system=system)
    if cs is None:
        return None
    kind = KIND_FOR_SYSTEM[cs.system]
    ctx.add_mapping(display, cs, TABLE_FOR_KIND[kind])
    return Term(name, display, kind, codes=cs, active=active)


def _analyse(name: str, display: str, body_l: str, ctx: Context) -> Term | None:
    """Codes, age, sex and stay types of one definition body, combined; leftovers -> None."""
    if _EXCLUSION_DEF.search(body_l):
        ctx.note(f"'{display}': exclusions inside a definition are not supported.")
        return None
    active = bool(_ACTIVE_DEF.search(body_l))
    masked = body_l
    for m in list(_REF_DATE.finditer(masked)):
        _check_reference_date(m.group(0), ctx, f"'{display}'")
        masked = mask(masked, *m.span())
    types: list[str] = []
    for m in list(_ENC_TYPES_DEF.finditer(masked)):
        add_unique(types, re.findall(r"inpatient|outpatient|emergency", m.group(0)))
        masked = mask(masked, *m.span())
    primary, primary_found, masked = primary_clause(masked, ctx)
    if primary_found and primary is None:
        return None
    codes: list[str] = []
    if m := _CODE_LIST.search(masked) or _BARE_CODES.fullmatch(masked.strip(f" {MASK}")):
        codes = [c.upper().rstrip(".") for c in re.findall(r"[a-z]\d{2}[a-z0-9.]*", m.group("codes"))]
        masked = mask(masked, *m.span()) if m.re is _CODE_LIST else MASK * len(masked)
    loinc = None
    if m := _LOINC_DEF.search(masked):
        loinc = m.group(1)
        masked = mask(masked, *m.span())
    found, masked = age_sex_criteria(masked)
    masked = _DEF_WORDS.sub(lambda w: MASK * len(w.group(0)), masked)
    if not (types or primary or codes or loinc or found):
        return _plain(name, display, body_l, active, ctx)
    if residual(masked, DEF_FILLER):
        return None
    if types or primary:
        if codes or loinc or found:
            return None
        return Term(name, display, "encounter", enc_types=types, enc_primary=primary)
    cs: CodeSet | None = None
    if codes:
        if loinc or (cs := _explicit_codeset(body_l, codes, display)) is None:
            return None
    elif loinc:
        cs = CodeSet(system="loinc", prefixes=[loinc], label=display, source="explicit")
    if cs is None:
        return Term(name, display, "criteria", criteria=found)
    kind = KIND_FOR_SYSTEM[cs.system]
    ctx.add_mapping(display, cs, TABLE_FOR_KIND[kind])
    if not found:
        return Term(name, display, kind, codes=cs, active=active)
    crit = coded_criterion(kind, cs, negate=False, active=active or ctx.active_rule)
    return Term(name, display, "criteria", criteria=[*found, crit])


def _define(display: str, body: str, ctx: Context) -> Term | None:
    """Analyse one ``Term = body`` definition; None if it cannot be understood."""
    name = _term_name(display)
    body_l = normalise(body).lower()
    if name == "cohort":
        return _composite(name, display, body_l, ctx)
    if m := _PERCENT_DEF.match(body_l):
        num, den = m.group("num"), m.group("den")
        rest = residual(body_l[m.end() :].replace("one decimal", ""))
        checks = [phrase_criteria(p, ctx, used=set()) for p in (num, den)]
        if rest or any(p.unresolved for p in checks):
            return None
        return Term(name, display, "percent", percent=(num, den))
    if _references(body_l, ctx, name) and (term := _composite(name, display, body_l, ctx)):
        return term
    return _analyse(name, display, body_l, ctx)


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


def _count_sentence(text: str, ctx: Context, st: _State) -> bool:
    """"Count [inpatient] stays [whose main diagnosis ...] [whose start_date is in YYYY | between d and d]".

    Only the start date with exactly one year or one range is supported; anything else (end_date,
    "after 2023", two years) is left over and makes the sentence not understood.
    """
    m = _ENC_COUNT.match(text)
    assert m is not None
    st.enc_count = True
    if m.group("type"):
        add_unique(st.enc_types, [m.group("type")])
    masked = mask(text, *m.span())
    primary, found, masked = primary_clause(masked, ctx)
    if found:
        if primary is None:
            return False
        st.enc_primary = primary
    ranges, years = list(_DATE_RANGE.finditer(masked)), list(_DATE_YEAR.finditer(masked))
    if len(ranges) + len(years) > 1:
        return False
    if ranges:
        st.start_from, st.start_to = date.fromisoformat(ranges[0].group("a")), date.fromisoformat(ranges[0].group("b"))
        masked = mask(masked, *ranges[0].span())
    elif years:
        year = int(years[0].group("y"))
        st.start_from, st.start_to = date(year, 1, 1), date(year, 12, 31)
        masked = mask(masked, *years[0].span())
    return not residual(masked)


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
        masked = mask(text.lower(), *m.span())
        if lo := _LEFT_OUT.search(masked):
            left = _measurement(lo.group("name"), None, ctx)
            if left is None:
                return False
            add_unique(st.left_out, [ObservationCriterion(kind="observation", codes=left[1])])
            masked = mask(masked, *lo.span())
        return not residual(masked)
    if _ENC_COUNT.match(text.lower()):
        return _count_sentence(text.lower(), ctx, st)
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
        entry = st.record(order, text, _other_sentence(norm, ctx, st))
        if _ENC_COUNT.match(norm.lower()):
            st.count_entry = entry
    names = {_term_name(m.group("term")) for _o, _t, m in definitions}
    deferred = []
    for order, text, m in definitions:
        name, body_l = _term_name(m.group("term")), m.group("body").lower()
        refers = any(Term(n, n, "criteria").pattern().search(body_l) for n in names - {name})
        if name == "cohort" or refers:
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
            chunk = re.sub(r"\b(?:by|in each|per|for each|across)\b", " ", qm.group(1))
            dims = _dimensions(chunk, st, ctx, strict=True)
            if isinstance(dims, list):
                add_unique(group_by, [d for d in dims if all(g.kind != d.kind for g in group_by)])
            else:
                st.record(len(sentences) + 0.5, request.question, False)
                ctx.note(f"The grouping '{qm.group(0).strip()}' in the question is not supported.")
        if not st.cohort_size and (qm := re.search(r"\bhow many\s+(.+?)(?=,|\?|\.|\s+(?:by|in each|per|for each|across)\b|$)", question)):
            item = qm.group(1)
            entry = st.record(len(sentences) + 1, item, False)
            entry[2] = parse_item(item, ctx, b, entry)
            ctx.note("No 'Report per ...' sentence: the item was taken from the question.")
    resolve_percent_terms(b, ctx)
    if (st.enc_count or b.encounter) and b.person_items:
        # stays are counted: an item about people would silently count stays, not distinct patients
        for entry, names in b.person_items:
            entry[2] = False
            b.drop(set(names))
        ctx.note("Stays are counted in this request; counting patients at the same time is not supported.")

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
        failed = [normalise(t).lower() for _o, t, ok in st.outcomes if not ok]
        for term in ctx.terms.values():
            if term.kind != "condition" or term.name in ctx.used_terms or term.codes is None:
                continue
            if any(term.pattern().search(f) for f in failed):
                continue  # meant for an item we did not understand: do not guess where it belongs
            add_unique(population, [ConditionCriterion(kind="condition", codes=term.codes)])
            ctx.note(
                f"'{term.display}' is defined but not used in a report item; it was added to the population "
                "(staff: please check)."
            )
        add_unique(population, st.left_out)
        metrics = b.metrics

    unit = "encounter" if (st.enc_count or b.encounter) else "patient"
    scope = None
    if unit == "encounter":
        types = b.enc_types or st.enc_types
        types_differ = b.enc_types and st.enc_types and set(b.enc_types) != set(st.enc_types)
        primary_differs = b.enc_primary and st.enc_primary and b.enc_primary != st.enc_primary
        if (types_differ or primary_differs) and st.count_entry is not None:
            st.count_entry[2] = False  # which stays are meant is ambiguous
            ctx.note("The count sentence and the report item describe different stays.")
        scope = EncounterScope(
            types=types, start_from=st.start_from, start_to=st.start_to, primary_icd10=b.enc_primary or st.enc_primary
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
