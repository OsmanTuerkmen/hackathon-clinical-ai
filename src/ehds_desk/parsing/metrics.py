"""Report items -> metrics: counts, percentages and means over a common base population.

The first count defines the base population; later counts keep only their extra criteria, "% with X"
adds a hidden count, "that share" divides the previous count by the base and a defined percentage
("Prevalence = A / B x 100") is matched to counts by comparing the criteria of A and B.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import CodeSet, CountMetric, MeanMetric, PercentMetric
from .phrases import Context, Term, normalise, phrase_criteria, same_criteria, snake_case, strip_end

_FORMAT_ONLY = re.compile(r"^(?:(?:with|rounded to|to|in)\s+)?(?P<n>one|two|three|\d)\s+decimals?(?:\s+places?)?$")
_FORMAT_TAIL = re.compile(r"[\s,]*(?:with|rounded to|to|in)\s+(?:one|two|three|\d)\s+decimals?(?:\s+places?)?$", re.I)
# An item after " and " that does not start like this continues the previous item's condition list
# ("patients with heart failure and hypertension").
_ITEM_START = re.compile(
    r"^(?:%|(?:the|their|its|that|this|those|these|a|an|all|any|number|numbers|count|total|how|mean|average|"
    r"median|share|percent|percentage|proportion|prevalence|rate|patients?|people|persons?|adults?|women|woman|"
    r"men|man|females?|males?|children|child|stays?|encounters?|admissions?|visits?|one|two|\d+)\b)",
    re.I,
)
_PCT_WORDS = re.compile(r"%|\bshares?\b|\bpercent(?:age)?s?\b|\bprevalence\b|\bproportions?\b|\brates?\b")
_MEAN_WORDS = re.compile(r"\b(?:mean|average)\b")
_RELATIVE = re.compile(r"\b(?:of|among)\s+(?:them|these|those)\b")
_LEADING = re.compile(r"^(?:(?:the|their|its|and|that|this|those|these)\s+)+")


# --- Metric builder --------------------------------------------------------------------


class Metrics:
    """Collects metrics; the first count defines the base population."""

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.metrics: list[Any] = []
        self.full: dict[str, list[Any]] = {}  # count name -> full criteria (base + where)
        self.base: list[Any] | None = None
        self.base_name: str | None = None
        self.last_count: str | None = None
        self.encounter = False
        self.enc_types: list[str] = []
        self.enc_primary: CodeSet | None = None
        self.pending: list[tuple[list[Any], str, Term]] = []

    def _name(self, label: str) -> str:
        base = snake_case(label)
        name, i = base, 2
        taken = {m.name for m in self.metrics}
        while name in taken:
            name, i = f"{base}_{i}", i + 1
        return name

    def count(self, label: str, crit: list[Any], *, display: bool = True, relative: bool = False) -> str | None:
        if self.base is None:
            self.base = list(crit)
        missing = [c for c in self.base if c not in crit]
        if missing and not relative:
            self.ctx.note(f"'{label}' does not cover the base population of the first count.")
            return None
        where = [c for c in crit if c not in self.base]
        name = self._name(label)
        self.metrics.append(CountMetric(kind="count", name=name, label=label, where=where, display=display))
        self.full[name] = self.base + where
        if self.base_name is None:
            self.base_name = name
        else:
            self.last_count = name
        return name

    def base_count(self) -> str:
        if self.base_name is None:
            self.count("All units", list(self.base or []), display=False)
        assert self.base_name is not None
        return self.base_name

    def find_or_add(self, crit: list[Any], label: str) -> str | None:
        for name, full in self.full.items():
            if same_criteria(full, crit):
                return name
        if self.base is not None and any(c not in crit for c in self.base):
            return None
        return self.count(label, crit, display=False)

    def percent(self, label: str, numerator: str, denominator: str) -> None:
        self.metrics.append(
            PercentMetric(kind="percent", name=self._name(label), label=label, numerator=numerator, denominator=denominator)
        )

    def encounter_subject(self, types: list[str], primary: CodeSet | None) -> bool:
        if self.encounter and (types and self.enc_types and types != self.enc_types or primary != self.enc_primary):
            return False
        self.encounter = True
        self.enc_types = self.enc_types or types
        self.enc_primary = self.enc_primary or primary
        return True


def _label(text: str) -> str:
    """Display label: the item as written, without leading articles and the rounding remark."""
    text = _FORMAT_TAIL.sub("", strip_end(normalise(text)))
    text = re.sub(r"^(?:(?:the|their|its|and|that|this|those|these)\s+)+", "", text, flags=re.I) or text
    return text[:1].upper() + text[1:]


def _clean_item(raw: str, ctx: Context) -> str:
    text = strip_end(normalise(raw)).lower()
    if _FORMAT_TAIL.search(text):
        ctx.note("Results are reported with one decimal.")
    return _LEADING.sub("", _FORMAT_TAIL.sub("", text)).strip()


def parse_item(raw: str, ctx: Context, b: Metrics, entry: list[Any]) -> bool:
    text = _clean_item(raw, ctx)
    if not text or _FORMAT_ONLY.match(text):
        ctx.note("Results are reported with one decimal.")
        return True
    label = _label(strip_end(normalise(raw)))

    if _PCT_WORDS.search(text):
        for term in ctx.terms.values():
            if term.kind == "percent" and term.pattern().search(text):
                b.pending.append((entry, _label(term.display), term))
                return True
        phrase = phrase_criteria(_PCT_WORDS.sub(" ", text), ctx)
        if phrase.unresolved:
            return False
        base = b.base_count()
        if not phrase.criteria:
            if b.last_count is None:
                return False
            b.percent(label, b.last_count, base)
            return True
        hidden = b.count(f"{label} (count)", phrase.criteria, display=False, relative=True)
        if hidden is None:
            return False
        b.percent(label, hidden, base)
        return True

    if _MEAN_WORDS.search(text):
        rest = _LEADING.sub("", _MEAN_WORDS.sub(" ", text).strip())
        parts = re.split(r"\s+(?:of|among|in|for)\s+", rest, maxsplit=1)
        what, of = parts[0], parts[1] if len(parts) > 1 else ""
        meas = phrase_criteria(what, ctx, used=set()).measurements
        cs = meas[0][1] if meas else ctx.terminology.lookup(what, system="loinc")
        if cs is None:
            return False
        if of:
            pop = phrase_criteria(of, ctx)
            if pop.unresolved:
                return False
            if b.base is None:
                b.base = list(pop.criteria)  # a later count must cover this population
            elif any(c not in b.base for c in pop.criteria):
                return False
        ctx.add_mapping(what.strip(), cs, "observations")
        b.metrics.append(MeanMetric(kind="mean", name=b._name(label), label=label, codes=cs))
        return True

    relative = bool(_RELATIVE.search(text))
    text = re.sub(r"^(?:numbers?|count|total)\s+of\s+", "", text)
    text = re.sub(r"\bhow many\b(?:\s+(?:of|among)\s+(?:them|these|those))?", " ", text)
    phrase = phrase_criteria(text, ctx)
    if phrase.unresolved:
        return False
    if not (phrase.has_subject or relative):
        return False  # nothing says what is counted ("the total"): never fall back to "all units"
    if phrase.encounter_subject and not b.encounter_subject(phrase.enc_types, phrase.enc_primary):
        return False
    return b.count(label, phrase.criteria, relative=relative) is not None


def split_items(items: str) -> list[str]:
    """Split at ', ' and ' and ' outside parentheses; re-join 'with X and Y' condition lists."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(items):
        ch = items[i]
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and items.startswith(", ", i):
            parts.append(cur)
            cur = ""
            i += 2
            continue
        if depth == 0 and items.startswith(" and ", i):
            between_numbers = re.search(r"\d\s*$", cur) and re.match(r"\d|(?:older|over|above|younger|below|under)\b", items[i + 5 :])
            continues = between_numbers or (
                re.search(r"\b(?:with|without|have|has)\b", cur, re.I) and not _ITEM_START.match(items[i + 5 :])
            )
            if not continues:
                parts.append(cur)
                cur = ""
                i += 5
                continue
        cur += ch
        i += 1
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def resolve_percent_terms(b: Metrics, ctx: Context) -> None:
    for entry, label, term in b.pending:
        assert term.percent is not None
        num_text, den_text = term.percent
        num_p, den_p = phrase_criteria(num_text, ctx), phrase_criteria(den_text, ctx)
        if num_p.unresolved or den_p.unresolved:
            entry[2] = False
            continue
        num = b.find_or_add(num_p.criteria, _label(strip_end(num_text)))
        den = b.find_or_add(den_p.criteria, _label(strip_end(den_text)))
        if num is None or den is None:
            entry[2] = False
            continue
        b.percent(label, num, den)
