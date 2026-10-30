"""Building blocks of the rule parser: text normalisation, defined terms and noun phrases.

``phrase_criteria`` turns a noun phrase of a request ("adults with type 2 diabetes who have a
HbA1c value", "how many of them have no active oral anticoagulant") into criteria. Every span it
interprets is masked; whatever content word is left afterwards (``residual``) is reported as not
understood, so an unknown qualifier can never silently widen or change the meaning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ..data import REGIONS
from ..models import (
    AgeCriterion,
    CodeSet,
    ConditionCriterion,
    EncounterCriterion,
    MedicationCriterion,
    ObservationCriterion,
    RegionCriterion,
    SexCriterion,
)
from ..terminology import Table, Terminology, TermMapping

TermKind = Literal["condition", "medication", "measurement", "encounter", "percent", "criteria"]

_TRANSLATE = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "“": "'", "”": "'",
        "„": "'", '"': "'", "´": "'", "`": "'", "×": "x", "‐": "-", "‑": "-",
        "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-", " ": " ",
        "≥": ">=", "≤": "<=",
    }
)  # fmt: skip
_SPACES = re.compile(r"\s+")
MASK = "\x00"


def normalise(text: str) -> str:
    """Unicode quotes -> ', x for the multiplication sign, dashes -> -, single spaces."""
    return _SPACES.sub(" ", text.translate(_TRANSLATE)).strip()


def strip_end(text: str) -> str:
    return text.strip().rstrip(" .;:").strip()


def snake_case(label: str) -> str:
    s = label.lower().replace("%", " pct ")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:60] or "metric"


def mask(text: str, start: int, end: int) -> str:
    return text[:start] + MASK * (end - start) + text[end:]


# --- Residual check ----------------------------------------------------------------------------

# Words that carry no meaning of their own in a noun phrase. Anything else that is left after all
# recognised spans are masked makes the sentence "not understood".
FILLER: frozenset[str] = frozenset(
    {
        "a", "an", "the", "any", "all", "some", "each", "every", "both", "also", "ever", "still",
        "of", "them", "these", "those", "they", "their", "its", "his", "her", "it", "ones",
        "how", "many", "much", "number", "numbers", "count", "counts", "total",
        "who", "which", "that", "whose", "what", "where",
        "have", "has", "had", "having", "is", "are", "was", "were", "be", "been", "being",
        "with", "and", "in", "on", "at", "for", "by", "from", "but", "there",
        "patient", "patients", "people", "person", "persons", "individual", "individuals",
        "value", "values", "measurement", "measurements", "result", "results", "recorded",
        "documented", "level", "levels", "least", "active", "current", "currently",
        "treated", "treatment", "receiving", "received", "receive", "taking", "take", "takes",
        "using", "use", "uses", "prescribed", "prescription", "prescriptions",
        "diagnosed", "diagnosis", "diagnoses", "region", "living", "live", "lives", "resident", "residing",
    }
)  # fmt: skip
# "one" alone is not filler ("patients with one stay" means exactly one); these phrases are.
# "per patient" is not: in a report item it asks for a ratio ("stays per patient"); the
# "Use the latest X per patient" sentence consumes it with its own pattern.
_FILLER_PHRASES = re.compile(r"\(\s*not\s+patients?\s*\)|\bat\s+least\s+one\b|\bone\s+or\s+more\b")


def mask_filler_phrases(text: str) -> str:
    return _FILLER_PHRASES.sub(lambda m: MASK * len(m.group(0)), text)


def residual(masked: str, extra: frozenset[str] = frozenset()) -> list[str]:
    """Content words of ``masked`` that no rule consumed."""
    text = _FILLER_PHRASES.sub(" ", masked.replace(MASK, " "))
    return [w for w in re.findall(r"\w+|%", text) if w not in FILLER and w not in extra]


# --- Defined terms --------------------------------------------------------------------------


@dataclass
class Term:
    name: str  # lowercase, normalised
    display: str  # as written in the request
    kind: TermKind
    codes: CodeSet | None = None
    criteria: list[Any] = field(default_factory=list)  # kind "criteria"
    enc_types: list[str] = field(default_factory=list)  # kind "encounter"
    enc_primary: CodeSet | None = None  # kind "encounter"
    percent: tuple[str, str] | None = None  # kind "percent": numerator / denominator phrase
    active: bool = False  # medication: the definition itself says "active" / "current"

    def pattern(self) -> re.Pattern[str]:
        base = self.name[:-1] if self.name.endswith("s") and len(self.name) > 3 else self.name
        return re.compile(r"(?<![\w\x00])" + re.escape(base) + r"(?:s|es)?(?![\w\x00])")


TABLE_FOR_KIND: dict[str, Table] = {
    "condition": "conditions",
    "medication": "medications",
    "measurement": "observations",
}
KIND_FOR_SYSTEM: dict[str, TermKind] = {"icd10": "condition", "atc": "medication", "loinc": "measurement"}


@dataclass
class Context:
    """Parser state shared by all sentences of one request."""

    terminology: Terminology
    terms: dict[str, Term] = field(default_factory=dict)
    active_rule: bool = False
    mappings: list[TermMapping] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    used_terms: set[str] = field(default_factory=set)

    def add_mapping(self, term: str, codes: CodeSet, table: Table) -> None:
        key = (term.lower(), table, tuple(codes.prefixes))
        if any((m.term.lower(), m.table, tuple(m.codes.prefixes)) == key for m in self.mappings):
            return
        self.mappings.append(self.terminology.verify(term, codes, table))

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


def coded_criterion(kind: str, codes: CodeSet, *, negate: bool, active: bool) -> Any:
    if kind == "condition":
        return ConditionCriterion(kind="condition", codes=codes, negate=negate)
    if kind == "medication":
        return MedicationCriterion(kind="medication", codes=codes, active_only=active, negate=negate)
    return ObservationCriterion(kind="observation", codes=codes, negate=negate)


def add_unique(target: list[Any], items: list[Any]) -> list[Any]:
    for item in items:
        if item not in target:
            target.append(item)
    return target


def same_criteria(a: list[Any], b: list[Any]) -> bool:
    return all(x in b for x in a) and all(y in a for y in b)


# --- Negation --------------------------------------------------------------------------------

_NEG = re.compile(r"\b(?:no|not|without|never|excluding|except|lacks?|lacking|free\s+of|other\s+than)\b")
_ACTIVE_WORD = re.compile(r"\b(?:active|current|currently)\b")


def negated_mention(term: Term, text: str) -> bool:
    """Whether ``text`` (lowercase) mentions ``term`` negated ("without X", "non-X", "X-free")."""
    for m in term.pattern().finditer(text):
        before = " ".join(text[: m.start()].split()[-_NEG_DISTANCE:])
        if _NEG.search(before) or text[m.end() : m.end() + 5] == "-free" or text[max(0, m.start() - 4) : m.start()] == "non-":
            return True
    return False


def _window_start(masked: str, start: int, size: int = 4) -> int:
    """Start of the (up to ``size``) words directly before ``start``, stopping at a consumed span."""
    seg = start
    for n, wm in enumerate(reversed(list(re.finditer(r"\S+", masked[:start])))):
        if MASK in wm.group() or n == size:
            break
        seg = wm.start()
    return seg


# --- Age / sex -------------------------------------------------------------------------------

_SUBJ = r"\b(?P<s>aged?|patients?|people|persons?|adults?|women|men|individuals?|children|those|ones)"
_YRS = r"(?:\s+years?(?:\s+old)?)?"
_N = r"(?P<a>\d{1,3})"
_AGE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?between\s+{_N}\s+and\s+(?P<b>\d{{1,3}}){_YRS}"), "range"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?(?:from\s+)?{_N}\s*(?:-|to)\s*(?P<b>\d{{1,3}}){_YRS}"), "range"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?{_N}{_YRS}\s+(?:or|and)\s+(?:older|over|above)\b"), "min"),
    (re.compile(rf"(?P<s>){_N}\s+years?(?:\s+old)?\s+(?:or|and)\s+(?:older|over|above)\b"), "min"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?(?:>=|at\s+least)\s*{_N}{_YRS}"), "min"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?{_N}\s*\+"), "min"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?(?:older\s+than|over|above|>)\s*{_N}{_YRS}"), "above"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?(?:<=|at\s+most)\s*{_N}{_YRS}"), "max"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?{_N}{_YRS}\s+(?:or|and)\s+(?:younger|under|below)\b"), "max"),
    (re.compile(rf"{_SUBJ}\s+(?:aged\s+)?(?:younger\s+than|under|below|<)\s*{_N}{_YRS}"), "below"),
]
_SEX = re.compile(
    r"\b(?:sex|gender)\s*(?:=|is|:)?\s*'?(female|male)'?|\b(women|woman|females?)\b|\b(men|man|males?)\b"
)


def age_sex_criteria(masked: str) -> tuple[list[Any], str]:
    """Age and sex criteria in ``masked`` (lowercase); their spans come back masked.

    A bare number threshold ("BMI over 30") is not an age: the age wording needs "aged",
    "years" or a person noun directly before it.
    """
    found, masked = age_sex_spans(masked)
    return [c for c, _span in found], masked


def age_sex_spans(masked: str) -> tuple[list[tuple[Any, tuple[int, int]]], str]:
    """Like ``age_sex_criteria`` but with the text span of each criterion."""
    found: list[tuple[Any, tuple[int, int]]] = []
    for pattern, how in _AGE_RULES:
        for m in list(pattern.finditer(masked)):
            if MASK in m.group(0):
                continue
            a = int(m.group("a"))
            b = int(m.group("b")) if how == "range" else None
            lo, hi = {
                "range": (a, b), "min": (a, None), "above": (a + 1, None), "max": (None, a), "below": (None, a - 1),
            }[how]  # fmt: skip
            start = m.start("s") if m.group("s") in ("age", "aged", "") else m.end("s")
            found.append((AgeCriterion(kind="age", min=lo, max=hi), (start, m.end())))
            masked = mask(masked, start, m.end())
    for m in list(_SEX.finditer(masked)):
        value = "male" if m.group(3) or m.group(1) == "male" else "female"
        found.append((SexCriterion(kind="sex", value=value), m.span()))
        masked = mask(masked, *m.span())
    return found, masked


# --- Regions ---------------------------------------------------------------------------------

REGION_NAMES: dict[str, str] = {r.lower(): r for r in REGIONS} | {
    "vienna": "Wien",
    "carinthia": "Kärnten",
    "lower austria": "Niederösterreich",
    "upper austria": "Oberösterreich",
    "styria": "Steiermark",
    "tyrol": "Tirol",
}
_RN = "|".join(re.escape(n) for n in sorted(REGION_NAMES, key=len, reverse=True))
_REGION = re.compile(
    rf"\b(?P<intro>outside(?:\s+of)?|(?:living|resident|residing|based)\s+in|in|from)\s+(?:the\s+)?"
    rf"(?:(?:region|federal\s+state|state|province)\s+(?:of\s+)?)?(?P<names>(?:{_RN})(?:\s*(?:,|or|and)\s*(?:{_RN}))*)\b"
)
_RN_ONE = re.compile(rf"\b(?:{_RN})\b")


# --- Main diagnosis of a stay ----------------------------------------------------------------

PRIMARY_CLAUSE = re.compile(
    r"\b(?:(?:with|whose|having|where|and)\s+(?:a\s+|an\s+|the\s+)?)?"
    r"(?:(?:main|primary)\s+diagnos[ie]s(?:\s*\(\s*primary_icd10\s*\))?|primary_icd10)"
    r"(?:\s+(?:is|of|=)|\s*[:=])?(?:\s+(?:starts?|starting|begins?|beginning)\s+with)?\s+"
    r"(?P<x>[^,;\x00]+?)(?=\s+(?:and|who|whose|in|by|per|for)\b|[,;\x00]|$)"
)
_ICD_LIST = re.compile(r"[a-z]\d{2}(?:\.\d+)?(?:\s*(?:,|or)\s*[a-z]\d{2}(?:\.\d+)?)*")


def primary_codes(text: str, ctx: Context) -> CodeSet | None:
    """Main diagnosis named by codes, by a defined term or in words (terminology)."""
    x = re.sub(r"^(?:an?|the)\s+", "", text.strip().lower())
    if _ICD_LIST.fullmatch(x):
        codes = [c.upper() for c in re.findall(r"[a-z]\d{2}(?:\.\d+)?", x)]
        return CodeSet(system="icd10", prefixes=list(dict.fromkeys(codes)), label=text.strip(), source="explicit")
    for term in sorted(ctx.terms.values(), key=lambda t: -len(t.name)):
        if term.pattern().fullmatch(x):
            if term.kind == "condition" and term.codes is not None:
                ctx.used_terms.add(term.name)
                return term.codes
            if term.kind == "encounter" and term.enc_primary is not None and not term.enc_types:
                ctx.used_terms.add(term.name)
                return term.enc_primary
            return None
    return ctx.terminology.lookup(x, system="icd10")


def primary_clause(masked: str, ctx: Context) -> tuple[CodeSet | None, tuple[int, int] | None, str]:
    """(codes, span, masked): a span with ``codes`` None means the clause was not understood."""
    m = PRIMARY_CLAUSE.search(masked)
    if m is None:
        return None, None, masked
    codes = primary_codes(m.group("x"), ctx)
    if codes is not None:
        ctx.add_mapping(m.group("x").strip(), codes, "primary_icd10")
    return codes, m.span(), mask(masked, *m.span())


# --- Noun phrases ------------------------------------------------------------------------------


@dataclass
class Phrase:
    criteria: list[Any] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    encounter_subject: bool = False
    enc_types: list[str] = field(default_factory=list)
    enc_primary: CodeSet | None = None
    measurements: list[tuple[str, CodeSet]] = field(default_factory=list)
    has_subject: bool = False  # a counted unit is named ("patients", "adults", "stays", ...)
    person_subject: bool = False  # people are named ("patients", "women", ...)


_HAVING = frozenset({"with", "without", "have", "has", "had", "having"})
_INLINE_CODE = re.compile(
    r"(?P<name>[\w/+-]+)\s+(?:(?:values?|measurements?|results?|prescriptions?|diagnos[ie]s)\s+)?"
    r"\(\s*(?P<sys>loinc|atc|icd-?10)\s*(?:code\s*)?(?P<code>[a-z0-9.-]+)\s*\)"
)
_SUBJECT_ADULT = re.compile(r"\badults?\b")
_SUBJECT_CHILD = re.compile(r"\b(?:children|child|minors?)\b")
_SUBJECT_PERSON = re.compile(r"\b(?:patients?|people|persons?|individuals?)\b")
_ENC_WORD = re.compile(
    r"\b(?:(?P<type>inpatient|outpatient|emergency)\s+)?(?:stays?|encounters?|admissions?|visits?|hospitali[sz]ations?)\b"
)
_INTROS = r"without|with|who\s+have|who\s+has|who\s+had|having|have|has|had|taking|using|receiving|on"
# The rest of a with-phrase ends before the next with-phrase, so "with X without Y" yields two.
_WITH = re.compile(rf"\b(?P<intro>{_INTROS})\s+(?P<rest>(?:(?!\b(?:{_INTROS}|who)\b)[^,;\x00])*)")
_MODIFIERS = re.compile(
    r"^(?:(?:a|an|the|any|some|no|active|current|currently|at least one|at least|one or more|one|valid|recorded)\s+)*"
)
_REST_STOP = re.compile(
    r"\s+(?:in|aged|by|per|whose|that|which|from|on|but|or|excluding|except|other|outside|not|never|free|"
    r"lacking|living|resident|older|younger|over|under|above|below|between|treated|diagnosed|recorded|at|"
    r"since|after|before|during|within|requiring)\b|\s*\(|$"
)
_TRAILING_FILLER = re.compile(r"\s+(?:values?|measurements?|results?|recorded|documented)$")


def _before(masked: str, start: int) -> str:
    return masked[_window_start(masked, start) : start]


@dataclass
class _Item:
    """One recognised element of a phrase; ``apply(negate)`` adds it to the result."""

    pos: int
    end: int
    apply: Callable[[bool], None]
    inherent: bool = False  # negated by its own wording ("without", "no", "-free", "non-")


_NEG_DISTANCE = 4  # max words between a negator and the element it negates
_LIST_GAP = re.compile(r"^\s*(?:,|and|or)\s*(?:(?:a|an|the|any)\s+)?$")
_PERSON = re.compile(
    r"\b(?:patients?|people|persons?|individuals?|adults?|women|woman|men|man|children|child|females?|males?)\b"
)


def _coded(out: Phrase, kind: str, codes: CodeSet, active: bool, name: str) -> Callable[[bool], None]:
    def apply(negate: bool) -> None:
        add_unique(out.criteria, [coded_criterion(kind, codes, negate=negate, active=active)])
        if kind == "measurement" and not negate:
            out.measurements.append((name, codes))

    return apply


def _plain(out: Phrase, crit: list[Any], label: str) -> Callable[[bool], None]:
    """Criteria that cannot be negated (age, sex, region, composite terms)."""

    def apply(negate: bool) -> None:
        if negate:
            out.unresolved.append(f"not {label}")
        else:
            add_unique(out.criteria, crit)

    return apply


def _encounter(out: Phrase, having: bool, types: list[str], primary: CodeSet | None, label: str) -> Callable[[bool], None]:
    def apply(negate: bool) -> None:
        if having:  # "patients with an inpatient stay": a patient criterion
            out.criteria.append(EncounterCriterion(kind="encounter", types=types, primary_icd10=primary, negate=negate))
        elif negate:
            out.unresolved.append(f"not {label}")
        else:  # the stays themselves are counted
            out.encounter_subject = True
            add_unique(out.enc_types, types)
            out.enc_primary = out.enc_primary or primary

    return apply


def _split_and(text: str) -> list[tuple[int, str]]:
    """Parts of an "X and Y" list with their offsets in ``text``."""
    parts, pos = [], 0
    for sep in re.finditer(r"\s+and\s+", text):
        parts.append((pos, text[pos : sep.start()]))
        pos = sep.end()
    parts.append((pos, text[pos:]))
    return parts


def _bind_negators(original: str, items: list[_Item]) -> tuple[set[int], list[tuple[int, int]]]:
    """Each negator negates only the FIRST element after it (within a few words).

    Returns the indices of negated items and the spans of the negators used. A negator inside an
    element (a main-diagnosis clause) or without an element close behind it is left unconsumed,
    so the residual check reports it.
    """
    bound: set[int] = set()
    spans: list[tuple[int, int]] = []
    for n in _NEG.finditer(mask_filler_phrases(original)):  # not the "not" in "(not patients)"
        if any(it.pos <= n.start() < it.end for it in items):
            continue
        nxt = next((i for i, it in enumerate(items) if it.pos >= n.end()), None)
        if nxt is None or len(original[n.end() : items[nxt].pos].split()) > _NEG_DISTANCE:
            continue
        bound.add(nxt)
        spans.append(n.span())
    return bound, spans


def phrase_criteria(text: str, ctx: Context, *, used: set[str] | None = None) -> Phrase:
    """Criteria of a noun phrase. Terms found are added to ``used``; leftovers go to ``unresolved``.

    Every step records the elements it recognises with their text position; negation is decided
    afterwards in text order (``_bind_negators``), so a negator can never jump over the element
    it belongs to onto a neighbouring term.
    """
    used = ctx.used_terms if used is None else used
    out = Phrase()
    original = normalise(text).lower()
    masked = original
    items: list[_Item] = []

    # 1. inline explicit codes: "HbA1c value (LOINC 4548-4)"
    for m in list(_INLINE_CODE.finditer(masked)):
        system = {"loinc": "loinc", "atc": "atc"}.get(m.group("sys"), "icd10")
        code = m.group("code") if system == "loinc" else m.group("code").upper()
        try:
            codes = CodeSet(system=system, prefixes=[code], label=m.group("name"), source="explicit")
        except ValueError:
            out.unresolved.append(m.group(0))
            masked = mask(masked, *m.span())
            continue
        kind = KIND_FOR_SYSTEM[system]
        active = ctx.active_rule or bool(_ACTIVE_WORD.search(_before(masked, m.start())))
        items.append(_Item(m.start(), m.end(), _coded(out, kind, codes, active, m.group("name"))))
        ctx.add_mapping(m.group("name"), codes, TABLE_FOR_KIND[kind])
        masked = mask(masked, *m.span())

    # 2. main diagnosis of a stay ("with a main diagnosis of hip fracture", "primary_icd10 S72")
    primary, pspan, masked = primary_clause(masked, ctx)
    if pspan is not None:
        if primary is None:
            out.unresolved.append("main diagnosis")
        items.append(_Item(pspan[0], pspan[1], _plain(out, [], "main diagnosis")))

    # 3. defined terms, longest name first
    for term in sorted(ctx.terms.values(), key=lambda t: -len(t.name)):
        if term.kind == "percent":
            continue
        for m in list(term.pattern().finditer(masked)):
            start, end = m.span()
            inherent = False
            if masked[end : end + 5] == "-free":  # "diabetes-free"
                inherent, end = True, end + 5
            if masked[max(0, start - 4) : start] == "non-":  # "non-smoker"
                inherent, start = True, start - 4
            before = _before(masked, start)
            used.add(term.name)
            if term.kind == "criteria":
                apply = _plain(out, term.criteria, term.name)
            elif term.kind == "encounter":
                having = bool(_HAVING & set(before.split()))
                apply = _encounter(out, having, term.enc_types, term.enc_primary, term.name)
            else:
                assert term.codes is not None
                active = term.active or ctx.active_rule or bool(_ACTIVE_WORD.search(before))
                apply = _coded(out, term.kind, term.codes, active, term.name)
            items.append(_Item(start, end, apply, inherent))
            masked = mask(masked, start, end)

    # 4. region filters ("in Wien", "in Steiermark or Vienna"); negated ones are not supported
    for m in list(_REGION.finditer(masked)):
        if m.group("intro").startswith("outside"):
            out.unresolved.append(m.group(0))
        else:
            values = list(dict.fromkeys(REGION_NAMES[n] for n in _RN_ONE.findall(m.group("names"))))
            items.append(_Item(m.start(), m.end(), _plain(out, [RegionCriterion(kind="region", values=values)], m.group(0))))
        masked = mask(masked, *m.span())

    # 5. age / sex wording and subject words
    found, masked = age_sex_spans(masked)
    for crit, (s, e) in found:
        items.append(_Item(s, e, _plain(out, [crit], original[s:e])))
    if m := _SUBJECT_ADULT.search(masked):
        adult = [] if (ctx.terms.get("adult") or ctx.terms.get("adults")) else [AgeCriterion(kind="age", min=18)]
        if adult:
            ctx.note("'adults' was read as aged 18 or older (no definition given).")
        items.append(_Item(m.start(), m.end(), _plain(out, adult, "adults")))
        masked = mask(masked, *m.span())
        out.has_subject = True
    if m := _SUBJECT_CHILD.search(masked):
        items.append(_Item(m.start(), m.end(), _plain(out, [AgeCriterion(kind="age", max=17)], "children")))
        masked = mask(masked, *m.span())
        out.has_subject = True
    for m in list(_ENC_WORD.finditer(masked)):
        types = [m.group("type")] if m.group("type") else []
        having = bool(_HAVING & set(_before(masked, m.start()).split()))
        items.append(_Item(m.start(), m.end(), _encounter(out, having, types, None, m.group(0))))
        masked = mask(masked, *m.span())
    if _SUBJECT_PERSON.search(masked):
        out.has_subject = True

    # 6. remaining "with X" / "who have X" phrases -> terminology lookup
    for m in list(_WITH.finditer(masked)):
        rest = m.group("rest")
        mods = _MODIFIERS.match(rest)
        mods_end = mods.end() if mods else 0
        body = rest[mods_end:]
        stop = _REST_STOP.search(body)
        target_text = body[: stop.start() if stop else len(body)].rstrip()
        if not target_text or not residual(_NEG.sub(" ", target_text)):
            continue  # only filler / negators ("who have never been ..."): the negator binds later
        inherent = m.group("intro") == "without" or "no" in rest[:mods_end].split()
        modifiers = rest[:mods_end].split()
        parts = _split_and(target_text)
        if inherent and len(parts) > 1:
            out.unresolved.append(f"negation of a list: {target_text}")
        for i, (offset, part) in enumerate(parts):
            pmods = _MODIFIERS.match(part)
            pmods_end = pmods.end() if pmods else 0
            target = _TRAILING_FILLER.sub("", part[pmods_end:].strip())
            if not residual(target):
                continue
            codes = ctx.terminology.lookup(target)
            if codes is None:
                out.unresolved.append(target)
                continue
            part_mods = part[:pmods_end].split()
            active = ctx.active_rule or bool({"active", "current"} & {*modifiers, *part_mods})
            kind = KIND_FOR_SYSTEM[codes.system]
            pos = m.start("rest") + mods_end + offset + pmods_end
            neg = (inherent and i == 0) or "no" in part_mods
            items.append(_Item(pos, pos + len(target), _coded(out, kind, codes, active, target), neg))
            ctx.add_mapping(target, codes, TABLE_FOR_KIND[kind])
        masked = mask(masked, m.start(), m.start("rest") + mods_end + len(target_text))

    # 7. negation in text order, then build the criteria
    items.sort(key=lambda it: it.pos)
    bound, neg_spans = _bind_negators(original, items)
    for s, e in neg_spans:
        masked = mask(masked, s, e)
    for i, it in enumerate(items):
        negated = it.inherent or i in bound
        if negated and i + 1 < len(items) and _LIST_GAP.match(original[it.end : items[i + 1].pos]):
            out.unresolved.append("negation of a list (which items are excluded is ambiguous)")
        it.apply(negated)

    # 8. a main diagnosis belongs to the counted stays or to a stay criterion
    if primary is not None:
        enc_crit = [c for c in out.criteria if isinstance(c, EncounterCriterion) and c.primary_icd10 is None]
        if out.encounter_subject and out.enc_primary in (None, primary):
            out.enc_primary = primary
        elif not out.encounter_subject and enc_crit:
            out.criteria[out.criteria.index(enc_crit[-1])] = enc_crit[-1].model_copy(update={"primary_icd10": primary})
        else:
            out.unresolved.append("main diagnosis")
    if out.encounter_subject and any(isinstance(c, ConditionCriterion) for c in out.criteria):
        out.unresolved.append("diagnosis of a stay (only the main diagnosis is supported)")

    out.has_subject = out.has_subject or out.encounter_subject or bool(out.criteria)
    out.person_subject = bool(_PERSON.search(original))
    out.unresolved += residual(masked)
    return out
