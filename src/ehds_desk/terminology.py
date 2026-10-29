"""Plain-text terminology mapping, verified against the codes that occur in the data.

``lookup`` maps free text to a ``CodeSet`` (lexicon first, then description match against the
data). ``verify`` lists which concrete codes in a table fall under a ``CodeSet`` and how many
rows each has, so access-body staff can see what a term really resolved to.

All catalogue queries run once in ``Terminology.__init__``; table and column names come from
the constant ``_TABLES`` whitelist, never from caller input.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .data import Database
from .models import CodeSet
from .terminology_lexicon import BENIGN_WORDS, LEXICON, QUALIFIER_EXCLUSIONS, STOP_WORDS, LexEntry

System = Literal["icd10", "atc", "loinc"]
Table = Literal["conditions", "primary_icd10", "medications", "observations"]

JACCARD_THRESHOLD = 0.5

# mapping table -> (system, view, code column, description column or None)
_TABLES: dict[str, tuple[System, str, str, str | None]] = {
    "conditions": ("icd10", "cond", "icd10", "description"),
    "primary_icd10": ("icd10", "enc", "primary_icd10", None),
    "medications": ("atc", "med", "atc", "name"),
    "observations": ("loinc", "obs", "loinc", "name"),
}


class CodeMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    description: str
    rows: int


class TermMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    term: str
    codes: CodeSet
    table: Table
    matches: list[CodeMatch]
    warning: str | None = None


_TYPE_II = re.compile(r"\btype\s+ii\b")
_TYPE_I = re.compile(r"\btype\s+i\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    """Lowercase, 'type ii' -> 'type 2', punctuation -> spaces, strip plural 's' per word."""
    t = text.lower()
    t = _TYPE_II.sub("type 2", t)
    t = _TYPE_I.sub("type 1", t)
    return [_singular(w) for w in _NON_ALNUM.sub(" ", t).split()]


def content_tokens(text: str) -> list[str]:
    """``tokens`` without the filler words of definition bodies ("an active prescription of")."""
    return [w for w in tokens(text) if w not in STOP_WORDS]


def _find_run(haystack: list[str], needle: list[str]) -> int:
    """Index of the first whole-word occurrence of ``needle`` in ``haystack``, else -1."""
    n = len(needle)
    if n == 0:
        return -1
    for i in range(len(haystack) - n + 1):
        if haystack[i : i + n] == needle:
            return i
    return -1


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class Terminology:
    def __init__(self, db: Database):
        cur = db.cursor()
        # table -> {code: (description, rows)}; one query per table.
        self._codes: dict[str, dict[str, tuple[str, int]]] = {}
        for table, (_system, view, code_col, desc_col) in _TABLES.items():
            if desc_col is None:
                sql = (
                    f"SELECT {code_col}, {code_col}, COUNT(*) FROM {view} "
                    f"WHERE {code_col} IS NOT NULL GROUP BY {code_col}"
                )
            else:
                sql = (
                    f"SELECT {code_col}, MIN({desc_col}), COUNT(*) FROM {view} "
                    f"WHERE {code_col} IS NOT NULL GROUP BY {code_col}"
                )
            self._codes[table] = {
                code: (desc, int(rows)) for code, desc, rows in cur.execute(sql).fetchall()
            }
        # Encounters carry no description: reuse the conditions one, else the lexicon label.
        cond = self._codes["conditions"]
        primary = self._codes["primary_icd10"]
        for code, (_, rows) in list(primary.items()):
            primary[code] = (cond[code][0] if code in cond else self._lexicon_label(code), rows)

        # system -> {code: description}, merged over all tables of that system.
        self._by_system: dict[str, dict[str, str]] = {"icd10": {}, "atc": {}, "loinc": {}}
        for table, (system, *_rest) in _TABLES.items():
            for code, (desc, _rows) in self._codes[table].items():
                self._by_system[system].setdefault(code, desc)

        self._lex_tokens: list[tuple[list[str], LexEntry]] = [
            (content_tokens(s), e) for e in LEXICON for s in e.synonyms
        ]
        self._desc_tokens: dict[str, list[tuple[str, str, set[str]]]] = {
            system: [(code, desc, set(content_tokens(desc))) for code, desc in sorted(d.items())]
            for system, d in self._by_system.items()
        }

    @staticmethod
    def _lexicon_label(code: str) -> str:
        best: tuple[int, str] | None = None
        for e in LEXICON:
            if e.system != "icd10":
                continue
            for p in e.prefixes:
                if code.startswith(p) and (best is None or len(p) > best[0]):
                    best = (len(p), e.label)
        return best[1] if best else code

    def catalogue(self) -> dict[str, list[tuple[str, str]]]:
        """Codes with descriptions per system (no rows); for the LLM prompt."""
        return {s: sorted(d.items()) for s, d in self._by_system.items()}

    def lookup(self, text: str, system: System | None = None) -> CodeSet | None:
        words = content_tokens(text)
        if not words:
            return None

        best: tuple[int, int, int, LexEntry] | None = None  # words, chars, start, entry
        for syn, entry in self._lex_tokens:
            if system is not None and entry.system != system:
                continue
            start = _find_run(words, syn)
            if start >= 0:
                key = (len(syn), sum(map(len, syn)))
                if best is None or key > best[:2]:
                    best = (*key, start, entry)
        if best is not None:
            n, _chars, start, e = best
            if start > 0 and words[start - 1] in QUALIFIER_EXCLUSIONS:
                # A different condition ("pulmonary hypertension"): do not map, do not
                # fall back to a looser match; the term goes to manual review.
                return None
            if any(w not in BENIGN_WORDS for w in (*words[:start], *words[start + n :])):
                # The synonym covers only part of the term ("insulin resistance"): mapping it
                # would silently widen or change the meaning, so it goes to manual review.
                return None
            return CodeSet(
                system=e.system, prefixes=list(e.prefixes), label=e.label, source="lexicon"
            )

        wanted = set(words)
        found: list[tuple[float, str, str, str]] = []  # score, code, description, system
        for sys_name in (system,) if system else ("icd10", "atc", "loinc"):
            for code, desc, dtoks in self._desc_tokens[sys_name]:
                score = _jaccard(wanted, dtoks)
                # Accept only a clearly better-than-borderline overlap or an input that is a
                # subset of the description; a bare 0.5 would silently narrow the term.
                if score > JACCARD_THRESHOLD or wanted <= dtoks:
                    found.append((score, code, desc, sys_name))
        if not found:
            return None
        # Highest score wins, ties -> alphabetical code.
        score, code, desc, sys_name = min(found, key=lambda h: (-h[0], h[1]))
        if score <= JACCARD_THRESHOLD and len(found) > 1:
            # Only subset matches and several candidates ("diabetes" -> E11.65 / E11.9):
            # picking one would silently narrow the term, so leave it to manual review.
            return None
        return CodeSet(system=sys_name, prefixes=[code], label=desc, source="data_match")

    def verify(self, term: str, codes: CodeSet, table: Table) -> TermMapping:
        system, *_rest = _TABLES[table]
        prefixes = tuple(codes.prefixes)
        matches: list[CodeMatch] = []
        warning: str | None = None
        if codes.system != system:
            warning = f"Table '{table}' holds {system} codes, but '{term}' maps to {codes.system}."
        else:
            matches = [
                CodeMatch(code=code, description=desc, rows=rows)
                for code, (desc, rows) in sorted(self._codes[table].items())
                if code.startswith(prefixes)
            ]
            if not matches:
                warning = (
                    f"No code starting with {', '.join(prefixes)} occurs in '{table}' "
                    f"for '{term}'."
                )
        return TermMapping(
            term=term, codes=codes, table=table, matches=matches, warning=warning
        )
