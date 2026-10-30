"""Small text utilities shared by the policy engine and the definition parser."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TOKEN_RE = re.compile(
    r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[.\-/_'’][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*|<=|>=|[%+<>≤≥=×,;:()'\"/*–-]")

IRREGULAR = {
    "women": "woman", "men": "man", "children": "child", "people": "person",
    "diagnoses": "diagnosis", "analyses": "analysis", "persons": "person",
}


@dataclass(frozen=True)
class Token:
    text: str
    norm: str
    start: int
    end: int


def fold(s: str) -> str:
    """Lower-case and strip accents (Süd -> sud) for robust matching."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def fold_keep_len(s: str) -> str:
    """Accent-fold and lower-case character by character, never changing the string length."""
    out = []
    for ch in s:
        f = fold(ch)
        out.append(f if len(f) == 1 else ch.lower())
    return "".join(out)


def norm_word(w: str) -> str:
    w = fold(w).replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) and not w[-2].isdigit():
        return w[:-1]
    return w


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(0), norm_word(m.group(0)), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def norm_phrase(text: str) -> tuple[str, ...]:
    return tuple(t.norm for t in tokenize(text) if t.norm not in ("(", ")", ",", "'", '"'))


class MentionIndex:
    """Longest-match lookup of multi-word terms in a token sequence."""

    def __init__(self):
        self._by_first: dict[str, list[tuple[tuple[str, ...], object]]] = {}

    def add(self, phrase: str | tuple[str, ...], payload: object) -> None:
        key = phrase if isinstance(phrase, tuple) else norm_phrase(phrase)
        if not key:
            return
        bucket = self._by_first.setdefault(key[0], [])
        if all(existing != key for existing, _ in bucket):
            bucket.append((key, payload))
            bucket.sort(key=lambda kv: -len(kv[0]))

    def match_at(self, tokens: list[Token], i: int, blocked: list[bool] | None = None):
        for key, payload in self._by_first.get(tokens[i].norm, []):
            j = i + len(key)
            if j <= len(tokens) and tuple(t.norm for t in tokens[i:j]) == key:
                if blocked and any(blocked[i:j]):
                    continue
                return j, payload
        return None

    def find_all(self, tokens: list[Token], blocked: list[bool] | None = None):
        """Yield (start, end, payload) for non-overlapping longest matches, left to right."""
        i = 0
        while i < len(tokens):
            if blocked and blocked[i]:
                i += 1
                continue
            hit = self.match_at(tokens, i, blocked)
            if hit:
                j, payload = hit
                yield i, j, payload
                i = j
            else:
                i += 1


def slug(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", fold(text)).strip("_")
    return (s[:maxlen].rstrip("_")) or "value"


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
