"""Building blocks of the rule parser: text normalisation, defined terms and noun phrases.

``phrase_criteria`` turns a noun phrase of a request ("adults with type 2 diabetes who have a
HbA1c value", "how many of them have no active oral anticoagulant") into criteria. Every span it
interprets is masked; whatever content word is left afterwards (``residual``) is reported as not
understood, so an unknown qualifier can never silently widen or change the meaning.
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
        "of", "them", "these", "those", "they", "their", "its", "his", "her", "it", "one", "ones",
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
_FILLER_PHRASES = re.compile(r"\(\s*not\s+patients?\s*\)|\bper\s+patient\b")


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


def _window_start(masked: str, start: int, size: int = 4) -> int:
    """Start of the (up to ``size``) words directly before ``start``, stopping at a consumed span."""
    seg = start
    for n, wm in enumerate(reversed(list(re.finditer(r"\S+", masked[:start])))):
        if MASK in wm.group() or n == size:
            break
        seg = wm.start()
    return seg


def negation(masked: str, start: int) -> tuple[bool, str]:
    """Whether a negator stands in the window before ``start``; negators found are consumed."""
    seg = _window_start(masked, start)
    hits = list(_NEG.finditer(masked, seg, start))
    for h in hits:
        masked = mask(masked, h.start(), h.end())
    return bool(hits), masked


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
    found: list[Any] = []
    for pattern, how in _AGE_RULES:
        for m in list(pattern.finditer(masked)):
            if MASK in m.group(0):
                continue
            a = int(m.group("a"))
            b = int(m.group("b")) if how == "range" else None
            lo, hi = {
                "range": (a, b), "min": (a, None), "above": (a + 1, None), "max": (None, a), "below": (None, a - 1),
            }[how]  # fmt: skip
            found.append(AgeCriterion(kind="age", min=lo, max=hi))
            start = m.start("s") if m.group("s") in ("age", "aged", "") else m.end("s")
            masked = mask(masked, start, m.end())
    for m in list(_SEX.finditer(masked)):
        value = "male" if m.group(3) or m.group(1) == "male" else "female"
        found.append(SexCriterion(kind="sex", value=value))
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


def primary_clause(masked: str, ctx: Context) -> tuple[CodeSet | None, bool, str]:
    """(codes, found, masked): ``found`` with ``codes`` None means the clause was not understood."""
    m = PRIMARY_CLAUSE.search(masked)
    if m is None:
        return None, False, masked
    codes = primary_codes(m.group("x"), ctx)
    if codes is not None:
        ctx.add_mapping(m.group("x").strip(), codes, "primary_icd10")
    return codes, True, mask(masked, *m.span())


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


def phrase_criteria(text: str, ctx: Context, *, used: set[str] | None = None) -> Phrase:
    """Criteria of a noun phrase. Terms found are added to ``used``; leftovers go to ``unresolved``."""
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
            masked = mask(masked, *m.span())
            continue
        kind = KIND_FOR_SYSTEM[system]
        before = _before(masked, m.start())
        negate, masked = negation(masked, m.start())
        active = ctx.active_rule or bool(_ACTIVE_WORD.search(before))
        add_unique(out.criteria, [coded_criterion(kind, codes, negate=negate, active=active)])
        if kind == "measurement":
            out.measurements.append((m.group("name"), codes))
        ctx.add_mapping(m.group("name"), codes, TABLE_FOR_KIND[kind])
        masked = mask(masked, *m.span())

    # 2. main diagnosis of a stay ("with a main diagnosis of hip fracture", "primary_icd10 S72")
    primary, primary_found, masked = primary_clause(masked, ctx)
    if primary_found and primary is None:
        out.unresolved.append("main diagnosis")

    # 3. defined terms, longest name first
    for term in sorted(ctx.terms.values(), key=lambda t: -len(t.name)):
        if term.kind == "percent":
            continue
        for m in list(term.pattern().finditer(masked)):
            start, end = m.span()
            negate = False
            if masked[end : end + 5] == "-free":  # "diabetes-free"
                negate, end = True, end + 5
            if masked[max(0, start - 4) : start] == "non-":  # "non-smoker"
                negate, start = True, start - 4
            before = _before(masked, start)
            neg2, masked = negation(masked, start)
            negate = negate or neg2
            used.add(term.name)
            having = bool(_HAVING & set(before.split()))
            if term.kind == "criteria":
                if negate:
                    out.unresolved.append(f"not {term.name}")
                add_unique(out.criteria, term.criteria)
            elif term.kind == "encounter":
                if having:
                    out.criteria.append(
                        EncounterCriterion(
                            kind="encounter", types=term.enc_types, primary_icd10=term.enc_primary, negate=negate
                        )
                    )
                elif negate:
                    out.unresolved.append(f"not {term.name}")
                else:
                    out.encounter_subject = True
                    add_unique(out.enc_types, term.enc_types)
                    out.enc_primary = out.enc_primary or term.enc_primary
            else:
                assert term.codes is not None
                active = term.active or ctx.active_rule or bool(_ACTIVE_WORD.search(before))
                add_unique(out.criteria, [coded_criterion(term.kind, term.codes, negate=negate, active=active)])
                if term.kind == "measurement":
                    out.measurements.append((term.name, term.codes))
            masked = mask(masked, start, end)

    # 4. region filters ("in Wien", "in Steiermark or Vienna"); negated ones are not supported
    for m in list(_REGION.finditer(masked)):
        negated, _ = negation(masked, m.start())
        if negated or m.group("intro").startswith("outside"):
            out.unresolved.append(m.group(0))
        else:
            values = [REGION_NAMES[n] for n in _RN_ONE.findall(m.group("names"))]
            add_unique(out.criteria, [RegionCriterion(kind="region", values=list(dict.fromkeys(values)))])
        masked = mask(masked, *m.span())

    # 5. age / sex wording and subject words
    found, masked = age_sex_criteria(masked)
    add_unique(out.criteria, found)
    if m := _SUBJECT_ADULT.search(masked):
        if (ctx.terms.get("adult") or ctx.terms.get("adults")) is None:
            add_unique(out.criteria, [AgeCriterion(kind="age", min=18)])
            ctx.note("'adults' was read as aged 18 or older (no definition given).")
        masked = mask(masked, *m.span())
        out.has_subject = True
    if m := _SUBJECT_CHILD.search(masked):
        add_unique(out.criteria, [AgeCriterion(kind="age", max=17)])
        masked = mask(masked, *m.span())
        out.has_subject = True
    for m in list(_ENC_WORD.finditer(masked)):
        types = [m.group("type")] if m.group("type") else []
        before = _before(masked, m.start())
        if _HAVING & set(before.split()):
            negate, masked = negation(masked, m.start())
            out.criteria.append(EncounterCriterion(kind="encounter", types=types, negate=negate))
        else:
            out.encounter_subject = True
            add_unique(out.enc_types, types)
        masked = mask(masked, *m.span())
    if _SUBJECT_PERSON.search(masked):
        out.has_subject = True

    # 6. remaining "with X" / "who have X" phrases -> terminology lookup
    for m in list(_WITH.finditer(masked)):
        rest = m.group("rest")
        mods = _MODIFIERS.match(rest)
        mods_end = mods.end() if mods else 0
        modifiers = rest[:mods_end].split()
        body = rest[mods_end:]
        stop = _REST_STOP.search(body)
        target_text = body[: stop.start() if stop else len(body)].strip()
        if not target_text or not residual(target_text):
            continue
        negate, masked = negation(masked, m.start())
        negate = negate or m.group("intro") == "without" or "no" in modifiers
        active = ctx.active_rule or "active" in modifiers or "current" in modifiers
        for part in re.split(r"\s+and\s+", target_text):
            target = _TRAILING_FILLER.sub("", _MODIFIERS.sub("", part).strip())
            if not residual(target):
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
        masked = mask(masked, m.start(), m.start("rest") + mods_end + len(body[: stop.start() if stop else len(body)]))

    # 7. a main diagnosis belongs to the counted stays or to a stay criterion
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
    out.unresolved += residual(masked)
    return out
