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
from .terminology_lexicon import LEXICON, LexEntry

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


def normalise(text: str) -> str:
    return " ".join(tokens(text))


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


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
            (tokens(s), e) for e in LEXICON for s in e.synonyms
        ]
        self._desc_tokens: dict[str, list[tuple[str, str, set[str]]]] = {
            system: [(code, desc, set(tokens(desc))) for code, desc in sorted(d.items())]
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
        words = tokens(text)
        if not words:
            return None

        best: tuple[int, int, LexEntry] | None = None
        for syn, entry in self._lex_tokens:
            if system is not None and entry.system != system:
                continue
            if _contains_run(words, syn):
                key = (len(syn), sum(map(len, syn)))
                if best is None or key > best[:2]:
                    best = (*key, entry)
        if best is not None:
            e = best[2]
            return CodeSet(
                system=e.system, prefixes=list(e.prefixes), label=e.label, source="lexicon"
            )

        wanted = set(words)
        hit: tuple[float, str, str, str] | None = None  # score, code, description, system
        for sys_name in (system,) if system else ("icd10", "atc", "loinc"):
            for code, desc, dtoks in self._desc_tokens[sys_name]:
                score = _jaccard(wanted, dtoks)
                if score < JACCARD_THRESHOLD:
                    continue
                if hit is None or score > hit[0] or (score == hit[0] and code < hit[1]):
                    hit = (score, code, desc, sys_name)
        if hit is None:
            return None
        _, code, desc, sys_name = hit
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
