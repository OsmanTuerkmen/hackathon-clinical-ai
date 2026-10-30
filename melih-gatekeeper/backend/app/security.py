"""Input hygiene and prompt-injection defences that do not depend on any model.

- sanitise(): NFKC, strip zero-width/bidi controls, length caps
- detect_injection(): deterministic heuristics (EN+DE); a hit routes the request to human review
- datamark(): spotlighting, interleaves a per-request marker into untrusted text
- canary + verify_quote(): detect hijacked or hallucinated model output
"""
from __future__ import annotations

import base64
import re
import secrets
import unicodedata

MAX_FIELD = 2000
MAX_DEFINITIONS = 25
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿­]")

INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("override_instructions", r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(previous|prior|above|earlier|all|your|system)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?)"),
    ("override_instructions_de", r"\b(ignoriere|vergiss|missachte|überschreibe)\b.{0,40}\b(vorherigen?|bisherigen?|alle|obigen?)\b.{0,20}\b(anweisungen|regeln|instruktionen)"),
    ("role_change", r"\b(you are now|act as|pretend (to be|you are)|from now on you|du bist jetzt|tu so als)\b"),
    ("system_prompt", r"\b(system prompt|systemprompt|developer message|hidden instructions?)\b"),
    ("decision_injection", r"\b(decision|entscheidung|outcome|result)\s*[:=]\s*\"?(approve|reject|approve_spe|approve_statistical|genehmigt)"),
    ("decision_injection", r"(?-i:\bAPPROVE_(SPE|STATISTICAL)\b|\bREJECT\b|\bAPPROVED?\b)"),
    ("authority_claim", r"\b(approved|authori[sz]ed|pre-?approved|genehmigt) by (the )?(hdab|director|access body|ministry|staff|admin)"),
    ("chat_template", r"<\|[a-z_]+\|>|\[/?INST\]|<</?SYS>>|^\s*(system|assistant|user)\s*:|###\s*(instruction|system)"),
    ("embedded_json", r"\{\s*\"[a-z_]+\"\s*:"),
    ("data_exfiltration", r"\b(output|print|return|list|include|reveal)\b.{0,30}\b(patient[_ ]?ids?|birth ?dates?|raw (data|records|rows)|all records)\b"),
    ("roleplay", r"\b(for a (novel|story|game)|hypothetically|in a fictional)\b"),
    ("url", r"https?://"),
]
_B64 = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
_OTHER_SCRIPT = re.compile(r"[Ͱ-ϿЀ-ӿ]")  # Greek/Cyrillic look-alikes mixed into Latin words


_CONFUSABLES = str.maketrans("аеорсухіјѕԁԍһӏАВЕКМНОРСТХІЈЅοαρντυεικΑΒΕΖΗΙΚΜΝΟΡΤΥΧ",
                             "aeopcyxijsdghlABEKMHOPCTXIJSoapvtueikABEZHIKMNOPTYX")


def sanitise_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _INVISIBLE.sub("", s).translate(_CONFUSABLES)
    return s[:MAX_FIELD]


def sanitise_request(req: dict) -> tuple[dict, list[str]]:
    """Returns a cleaned copy plus a list of changes made (changes themselves are a weak injection signal)."""
    changes = []
    out = dict(req)
    for k in ("purpose", "question", "requested_as", "requested_format"):
        if k in out and isinstance(out[k], str):
            clean = sanitise_text(out[k])
            if clean != unicodedata.normalize("NFKC", out[k]):
                changes.append(f"{k}: removed invisible characters or truncated")
            out[k] = clean
    if isinstance(out.get("applicant"), dict):
        out["applicant"] = {k: sanitise_text(v) if isinstance(v, str) else v for k, v in out["applicant"].items()}
    defs = out.get("definitions") or []
    if len(defs) > MAX_DEFINITIONS:
        changes.append(f"definitions truncated to {MAX_DEFINITIONS}")
    out["definitions"] = [sanitise_text(d) for d in defs[:MAX_DEFINITIONS] if isinstance(d, str)]
    for raw, clean in zip(defs, out["definitions"]):
        if isinstance(raw, str) and _INVISIBLE.search(raw):
            changes.append("definitions: removed invisible characters")
            break
    return out, changes


def _fields(req: dict) -> dict[str, str]:
    f = {k: req.get(k, "") or "" for k in ("purpose", "question")}
    a = req.get("applicant") or {}
    f["applicant"] = " ".join(str(a.get(k, "")) for k in ("name", "organisation"))
    f["definitions"] = "\n".join(req.get("definitions") or [])
    return f


def detect_injection(raw_req: dict) -> list[str]:
    """Run on the RAW request (before sanitising) so hidden characters are themselves a finding."""
    hits = []
    for field, text in _fields(raw_req).items():
        if not text:
            continue
        if _INVISIBLE.search(text):
            hits.append(f"{field}: invisible characters")
        norm = unicodedata.normalize("NFKC", _INVISIBLE.sub("", text))
        for name, pat in INJECTION_PATTERNS:
            if re.search(pat, norm, re.I | re.M):
                hits.append(f"{field}: {name}")
        for blob in _B64.findall(norm):
            try:
                decoded = base64.b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8")
                if sum(ch.isprintable() for ch in decoded) > 0.9 * len(decoded):
                    hits.append(f"{field}: base64-encoded text")
                    break
            except Exception:
                pass
        for word in re.findall(r"\w+", norm):
            if _LATIN.search(word) and _OTHER_SCRIPT.search(word):
                hits.append(f"{field}: mixed-script word '{word}'")
                break
    return sorted(set(hits))


def new_marker() -> str:
    return "ˆ" + secrets.token_hex(2)


def datamark(text: str, marker: str) -> str:
    """Spotlighting (Hines et al. 2024): interleave a marker so the model can tell data from instructions."""
    return marker.join(text.split())


def new_canary() -> str:
    return "CANARY-" + secrets.token_hex(6)


def normalise_for_match(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", _INVISIBLE.sub("", s or ""))).strip().lower()


def verify_quote(quote: str | None, *sources: str) -> bool:
    """An evidence quote counts only if it appears verbatim (after whitespace/case normalisation) in the request."""
    if not quote or len(quote.strip()) < 4:
        return False
    q = normalise_for_match(quote).strip(" .\"'")
    return any(q in normalise_for_match(s) for s in sources)
