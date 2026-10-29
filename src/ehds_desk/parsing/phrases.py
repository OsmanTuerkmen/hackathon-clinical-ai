"""Building blocks of the rule parser: text normalisation, defined terms and noun phrases.

``phrase_criteria`` turns a noun phrase of a request ("adults with type 2 diabetes who have a
HbA1c value", "how many of them have no active oral anticoagulant") into patient criteria, using
the terms the request defined and, for undefined "with X" phrases, the terminology lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

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


# --- Age / sex analysers (shared by definition bodies and phrases) -----------------------------

_AGE_MIN = re.compile(
    r"\b(?:aged\s+)?(\d{1,3})\s*(?:years?(?:\s+old)?\s+)?(?:or|and)\s+(?:older|over|above)\b"
    r"|\baged\s+(\d{1,3})\s*\+"
)
_AGE_MAX = re.compile(r"\baged\s+(?:under|below|younger\s+than)\s+(\d{1,3})\b")
_AGE_RANGE = re.compile(r"\baged\s+(?:between\s+)?(\d{1,3})\s*(?:-|to|and)\s*(\d{1,3})\b")
_SEX = re.compile(r"\bsex\s+'?(female|male)'?|\b(women|woman|females?)\b|\b(men|man|males?)\b")


def age_sex_criteria(text: str) -> tuple[list[Any], list[tuple[int, int]]]:
    """Age and sex criteria found in ``text`` (lowercase) and the spans they cover."""
    found: list[Any] = []
    spans: list[tuple[int, int]] = []
    for m in _AGE_RANGE.finditer(text):
        found.append(AgeCriterion(kind="age", min=int(m.group(1)), max=int(m.group(2))))
        spans.append(m.span())
    for m in _AGE_MIN.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        found.append(AgeCriterion(kind="age", min=int(m.group(1) or m.group(2))))
        spans.append(m.span())
    for m in _AGE_MAX.finditer(text):
        found.append(AgeCriterion(kind="age", max=int(m.group(1)) - 1))
        spans.append(m.span())
    for m in _SEX.finditer(text):
        value = "male" if m.group(3) or m.group(1) == "male" else "female"
        found.append(SexCriterion(kind="sex", value=value))
        spans.append(m.span())
    return found, spans


# --- Noun phrases ------------------------------------------------------------------------------


@dataclass
class Phrase:
    criteria: list[Any] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    encounter_subject: bool = False
    enc_types: list[str] = field(default_factory=list)
    enc_primary: CodeSet | None = None
    measurements: list[tuple[str, CodeSet]] = field(default_factory=list)


_NEGATORS = frozenset({"no", "without", "not", "never"})
_HAVING = frozenset({"with", "without", "have", "has", "had", "having"})
_INLINE_CODE = re.compile(
    r"(?P<name>[\w/+-]+)\s+(?:(?:values?|measurements?|results?|prescriptions?|diagnos[ie]s)\s+)?"
    r"\(\s*(?P<sys>loinc|atc|icd-?10)\s*(?:code\s*)?(?P<code>[a-z0-9.-]+)\s*\)"
)
_SUBJECT_ADULT = re.compile(r"\badults?\b")
_SUBJECT_CHILD = re.compile(r"\b(?:children|child|minors?)\b")
_ENC_WORD = re.compile(
    r"\b(?:(?P<type>inpatient|outpatient|emergency)\s+)?(?:stays?|encounters?|admissions?|visits?|hospitali[sz]ations?)\b"
)
_INTROS = r"without|with|who\s+have|who\s+has|who\s+had|having|have|has|had|taking|using|receiving|on"
# The rest of a with-phrase ends before the next with-phrase, so "with X without Y" yields two.
_WITH = re.compile(
    rf"\b(?P<intro>{_INTROS})\s+(?P<rest>(?:(?!\b(?:{_INTROS}|who)\b)[^,;\x00])*)"
)
_MODIFIERS = re.compile(
    r"^(?:(?:a|an|the|any|some|no|active|current|currently|at least one|at least|one or more|one|valid|recorded)\s+)*"
)
_REST_STOP = re.compile(r"\s+(?:in|aged|by|per|whose|that|which|from|on)\b|\s*\(|$")
_REGIONS = {r.lower(): r for r in REGIONS}
_REGION = re.compile(r"\b(?:in|from|living in|resident in)\s+(?:the\s+)?(?:region\s+(?:of\s+)?)?(" + "|".join(map(re.escape, _REGIONS)) + r")\b")
_TRAILING_FILLER = re.compile(r"\s+(?:values?|measurements?|results?|recorded|documented)$")


def _window(masked: str, start: int, size: int = 3) -> list[str]:
    """Up to ``size`` words directly before ``start``, stopping at an already consumed span."""
    out: list[str] = []
    for word in reversed(masked[:start].split()):
        if MASK in word or len(out) == size:
            break
        out.append(word.strip(",;:()'"))
    return out


def _mask(text: str, start: int, end: int) -> str:
    return text[:start] + MASK * (end - start) + text[end:]


def _is_active(ctx: Context, before: list[str]) -> bool:
    return ctx.active_rule or "active" in before or "current" in before or "currently" in before


def phrase_criteria(text: str, ctx: Context, *, used: set[str] | None = None) -> Phrase:
    """Criteria of a noun phrase (lowercase, normalised). Terms found are added to ``used``."""
    used = ctx.used_terms if used is None else used
    out = Phrase()
    masked = normalise(text).lower()

    # 1. inline explicit codes: "HbA1c value (LOINC 4548-4)"
    for m in list(_INLINE_CODE.finditer(masked)):
        system = {"loinc": "loinc", "atc": "atc"}.get(m.group("sys"), "icd10")
        code = m.group("code") if system == "loinc" else m.group("code").upper()
        try:
            codes = CodeSet(system=system, prefixes=[code], label=m.group("name"), source="explicit")
        except ValueError:
            out.unresolved.append(m.group(0))
            continue
        before = _window(masked, m.start())
        kind = KIND_FOR_SYSTEM[system]
        negate = bool(_NEGATORS & set(before))
        add_unique(out.criteria, [coded_criterion(kind, codes, negate=negate, active=_is_active(ctx, before))])
        if kind == "measurement":
            out.measurements.append((m.group("name"), codes))
        ctx.add_mapping(m.group("name"), codes, TABLE_FOR_KIND[kind])
        masked = _mask(masked, *m.span())

    # 2. defined terms, longest name first
    for term in sorted(ctx.terms.values(), key=lambda t: -len(t.name)):
        if term.kind == "percent":
            continue
        for m in list(term.pattern().finditer(masked)):
            before = _window(masked, m.start())
            negate = bool(_NEGATORS & set(before))
            used.add(term.name)
            if term.kind == "criteria":
                add_unique(out.criteria, term.criteria)
            elif term.kind == "encounter":
                if _HAVING & set(before):
                    out.criteria.append(
                        EncounterCriterion(
                            kind="encounter", types=term.enc_types, primary_icd10=term.enc_primary, negate=negate
                        )
                    )
                else:
                    out.encounter_subject = True
                    add_unique(out.enc_types, term.enc_types)
                    out.enc_primary = out.enc_primary or term.enc_primary
            else:
                assert term.codes is not None
                crit = coded_criterion(term.kind, term.codes, negate=negate, active=_is_active(ctx, before))
                add_unique(out.criteria, [crit])
                if term.kind == "measurement":
                    out.measurements.append((term.name, term.codes))
            masked = _mask(masked, *m.span())

    # 3. region filters, inline age / sex and subject words
    regions = [_REGIONS[m.group(1)] for m in _REGION.finditer(masked)]
    if regions:
        add_unique(out.criteria, [RegionCriterion(kind="region", values=list(dict.fromkeys(regions)))])
        for m in list(_REGION.finditer(masked)):
            masked = _mask(masked, *m.span())
    found, spans = age_sex_criteria(masked)
    add_unique(out.criteria, found)
    for span in spans:
        masked = _mask(masked, *span)
    m = _SUBJECT_ADULT.search(masked)
    if m:
        adult = ctx.terms.get("adult") or ctx.terms.get("adults")
        if adult is None:
            add_unique(out.criteria, [AgeCriterion(kind="age", min=18)])
            ctx.note("'adults' was read as aged 18 or older (no definition given).")
        masked = _mask(masked, *m.span())
    m = _SUBJECT_CHILD.search(masked)
    if m:
        add_unique(out.criteria, [AgeCriterion(kind="age", max=17)])
        masked = _mask(masked, *m.span())
    for m in list(_ENC_WORD.finditer(masked)):
        types = [m.group("type")] if m.group("type") else []
        before = _window(masked, m.start())
        if _HAVING & set(before):
            out.criteria.append(EncounterCriterion(kind="encounter", types=types, negate=bool(_NEGATORS & set(before))))
        else:
            out.encounter_subject = True
            add_unique(out.enc_types, types)
        masked = _mask(masked, *m.span())

    # 4. remaining "with X" / "who have X" phrases -> terminology lookup
    for m in list(_WITH.finditer(masked)):
        rest = m.group("rest")
        mods = _MODIFIERS.match(rest)
        modifiers = (mods.group(0) if mods else "").split()
        rest = rest[mods.end() if mods else 0 :]
        stop = _REST_STOP.search(rest)
        rest = rest[: stop.start() if stop else len(rest)].strip()
        if not rest or rest[0].isdigit() or rest in ("them", "these", "those", "it", "one decimal"):
            continue
        negate = m.group("intro") == "without" or "no" in modifiers
        active = ctx.active_rule or "active" in modifiers or "current" in modifiers
        for part in re.split(r"\s+and\s+", rest):
            target = _TRAILING_FILLER.sub("", _MODIFIERS.sub("", part).strip())
            if not target:
                continue
            codes = ctx.terminology.lookup(target)
            if codes is None:
                out.unresolved.append(target)
                continue
            kind = KIND_FOR_SYSTEM[codes.system]
            add_unique(out.criteria, [coded_criterion(kind, codes, negate=negate, active=active)])
            if kind == "measurement":
                out.measurements.append((target, codes))
            ctx.add_mapping(target, codes, TABLE_FOR_KIND[kind])
    return out
