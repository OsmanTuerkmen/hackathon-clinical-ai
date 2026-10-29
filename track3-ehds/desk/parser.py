"""Deterministic interpreter: request definitions (plain English) -> query plan IR.

The IR (see ir.py) is a small JSON structure with concepts (ICD-10 / ATC / LOINC / encounter filters,
patient attributes), a population, grouping dimensions and measures. Nothing here is specific to a
request ID: every number is derived from the definitions, the question and the vocabulary.

Safety rule: every content word of a definition must be understood. If words remain that the
interpreter cannot place (for example an unsupported filter), it raises InterpretationError instead
of silently ignoring them.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field

from . import vocabulary as V
from .config import REFERENCE_DATE, REFERENCE_YEAR
from .text import MentionIndex, fold, fold_keep_len, norm_phrase, norm_word, slug, tokenize

I = re.IGNORECASE


class InterpretationError(Exception):
    def __init__(self, message: str, where: str = "", hint: str = ""):
        super().__init__(message)
        self.message = message
        self.where = where
        self.hint = hint

    def to_dict(self):
        return {"message": self.message, "where": self.where, "hint": self.hint}


# Words that carry no meaning for the cohort logic and may be ignored safely.
FILLER = {
    "patient", "person", "individual", "subject", "case", "with", "who", "whom", "whose", "that", "which",
    "have", "has", "had", "having", "a", "an", "the", "any", "at", "least", "one", "1", "value", "measurement",
    "measured", "recorded", "record", "result", "reading", "diagnosis", "diagnosed", "condition", "code",
    "prescription", "prescribed", "medication", "drug", "medicine", "treatment", "treated", "therapy", "on",
    "taking", "use", "using", "user", "is", "are", "be", "been", "being", "of", "and", "all", "total", "number",
    "count", "there", "were", "was", "their", "they", "these", "those", "this", "in", "for", "from", "to", "by",
    "each", "every", "(", ")", ",", ";", ":", "'", '"', "-", "–", "also", "both", "documented", "known",
    "registered", "file", "row", "entry", "still", "ever", "least", "type", "data", "available", "documented",
    "conditions.csv", "medications.csv", "observations.csv", "encounters.csv", "patients.csv", "dataset", "s",
}
SUPPORTED_HINT = ("The desk computes counts of patients or encounters, percentages, and means or medians of LOINC "
                  "measurements, filtered by ICD-10, ATC, LOINC values, age, sex, region, hospital, encounter type, "
                  "dates and primary_icd10. Give the code for unfamiliar terms or rephrase.")
PATIENT_NOUNS = {"patient", "person", "people", "individual", "subject", "adult", "woman", "man", "child", "resident"}
FORMAT_RE = re.compile(r"[,;]?\s*\(?(?:with |rounded to |to |as )?(?:one|1|a single) decimal(?: place)?s?\)?\s*$", I)
HEAD_WORDS = {"%", "percentage", "percent", "proportion", "share", "that", "their", "the", "this", "its", "mean",
              "average", "median", "number", "how", "count", "total", "patient", "adult", "woman", "man", "child",
              "person", "people", "stay", "encounter", "visit", "admission", "rate", "prevalence"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
DATE_TXT = r"(\d{4}-\d{2}-\d{2}|\d{1,2} (?:january|february|march|april|may|june|july|august|september|october|november|december) \d{4})"
ICD_RE = r"[A-Z]\d{1,2}(?:\.\d{0,3})?"
ATC_RE = r"[A-Z](?:\d{2}(?:[A-Z](?:[A-Z](?:\d{2})?)?)?)?"
CMP_WORDS = [
    (r"(?:of )?(?:at least|no less than|>=|≥|of at least)", ">="),
    (r"(?:of )?(?:at most|no more than|<=|≤|of at most)", "<="),
    (r"(?:of )?(?:above|over|greater than|more than|higher than|exceeding|>)", ">"),
    (r"(?:of )?(?:below|under|less than|lower than|<)", "<"),
]
UNIT_RE = r"(?:\s*(?:%|percent|kg/m2|kg/m²|mm ?\[?hg\]?|mmhg|ml/min(?:/1\.73 ?m2)?|ml/min/\{1\.73_m2\}))?"
NUM_RE = r"(\d+(?:\.\d+)?)"


def parse_date(s: str) -> str:
    s = s.strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{1,2}) ([a-z]+) (\d{4})", s)
    if m and m.group(2) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    raise InterpretationError(f"cannot read the date '{s}'")


def date_range_from(text: str):
    """Return (from, to, span) for a date expression inside `text`, or None."""
    t = text.lower()
    pats = [
        (rf"\bbetween {DATE_TXT} and {DATE_TXT}", lambda m: (parse_date(m.group(1)), parse_date(m.group(2)))),
        (r"\bbetween (\d{4}) and (\d{4})\b", lambda m: (f"{m.group(1)}-01-01", f"{m.group(2)}-12-31")),
        (r"\bfrom (\d{4}) (?:to|until|through) (\d{4})\b", lambda m: (f"{m.group(1)}-01-01", f"{m.group(2)}-12-31")),
        (rf"\b(?:on or after|since|from) {DATE_TXT}", lambda m: (parse_date(m.group(1)), None)),
        (rf"\b(?:on or before|until|up to) {DATE_TXT}", lambda m: (None, parse_date(m.group(1)))),
        (rf"\bbefore {DATE_TXT}", lambda m: (None, _day_before(parse_date(m.group(1))))),
        (rf"\bafter {DATE_TXT}", lambda m: (_day_after(parse_date(m.group(1))), None)),
        (r"\b(?:in|during) (?:the year )?(\d{4})\b", lambda m: (f"{m.group(1)}-01-01", f"{m.group(1)}-12-31")),
        (r"\b(?:since|from) (\d{4})\b", lambda m: (f"{m.group(1)}-01-01", None)),
    ]
    for pat, fn in pats:
        m = re.search(pat, t)
        if m:
            lo, hi = fn(m)
            return lo, hi, (m.start(), m.end())
    return None


def _day_before(d: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


def _day_after(d: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()


def norm_icd(code: str) -> str:
    c = code.strip().upper().rstrip(".")
    if len(c) > 3 and "." not in c:
        c = c[:3] + "." + c[3:]
    return c


@dataclass
class Concept:
    cid: str
    label: str
    kind: str  # set | condition | medication | observation | encounter | ratio
    spec: dict = field(default_factory=dict)
    source: str = ""
    text: str = ""
    referenced: bool = False
    pending: str | None = None
    head: str = ""
    role: str = ""

    def public(self) -> dict:
        d = {"id": self.cid, "label": self.label, "kind": self.kind, "source": self.source}
        if self.role:
            d["role"] = self.role
        d.update(copy.deepcopy(self.spec))
        if self.text:
            d["definition"] = self.text
        return d


@dataclass
class Item:
    pos: int
    kind: str  # atom | neg | active | or | cmp | date | pdiag | pick | atleast
    payload: object = None
    end: int = 0


# =============================================================================================
class PlanBuilder:
    def __init__(self, request: dict, mode: str, catalog: dict | None = None):
        assert mode in ("statistics", "spe")
        self.req = request
        self.mode = mode
        self.catalog = catalog or {}
        self.concepts: dict[str, Concept] = {}
        self.index = MentionIndex()
        self.vocab_index = V.build_index()
        self.vocab_concepts: dict[str, str] = {}
        self.age_bands: list[dict] | None = None
        self.age_band_source = ""
        self.active_rule = {"date": REFERENCE_DATE, "source": "data/README.md (default)"}
        self.active_used = False
        self.count_rules: list[dict] = []
        self.left_out: list[tuple[str, str]] = []
        self.report: dict | None = None
        self.interpretations: list[dict] = []
        self.notes: list[str] = []
        self.measures: list[dict] = []
        self._resolving: list[str] = []

    # ------------------------------------------------------------------ concepts
    def _new_cid(self, label: str) -> str:
        base = slug(label, 32) or "concept"
        cid, n = base, 2
        while cid in self.concepts:
            cid, n = f"{base}_{n}", n + 1
        return cid

    def add_concept(self, label: str, kind: str, spec: dict, source: str, text: str = "",
                    aliases: list[str] | None = None, pending: str | None = None) -> Concept:
        c = Concept(self._new_cid(label), label.strip(), kind, spec, source, text, pending=pending)
        toks = norm_phrase(label)
        c.head = toks[-1] if toks else ""
        self.concepts[c.cid] = c
        for alias in [label] + (aliases or []):
            self.index.add(alias, c.cid)
        return c

    def vocab_concept(self, entry: V.VocabEntry) -> Concept:
        key = f"{entry.kind}:{entry.label}"
        if key in self.vocab_concepts:
            return self.concepts[self.vocab_concepts[key]]
        if entry.kind == "condition":
            spec = {"icd10": [{"code": c, "match": "prefix"} for c in entry.codes]}
        elif entry.kind == "medication":
            spec = {"atc": list(entry.codes)}
        elif entry.kind == "observation":
            existing = next((c for c in self.concepts.values()
                             if c.kind == "observation" and c.spec.get("loinc") == entry.codes[0]), None)
            if existing:
                self.vocab_concepts[key] = existing.cid
                return existing
            spec = {"loinc": entry.codes[0], "pick": None, "unit": entry.unit}
        else:
            spec = {"types": list(entry.codes)}
        c = Concept(self._new_cid(entry.label), entry.label, entry.kind, spec, "vocabulary")
        c.head = norm_phrase(entry.label)[-1]
        self.concepts[c.cid] = c
        self.vocab_concepts[key] = c.cid
        return c

    def concept(self, cid: str) -> Concept:
        c = self.concepts[cid]
        if c.pending is not None:
            self._resolve(c)
        return c

    def _resolve(self, c: Concept) -> None:
        if c.cid in self._resolving:
            raise InterpretationError(f"the definition of '{c.label}' refers to itself", c.source)
        self._resolving.append(c.cid)
        try:
            body, c.pending = c.pending, None
            if c.kind == "ratio":
                num, den = c.spec.pop("_num"), c.spec.pop("_den")
                c.spec["numerator"] = self.parse_set(num, c.source)
                c.spec["denominator"] = self.parse_set(den, c.source)
            else:
                expr, enc_head = self.parse_set(body, c.source, want_head=True)
                if enc_head is not None:
                    base = self.concepts[enc_head]
                    c.kind, c.spec = "encounter", copy.deepcopy(base.spec)
                    rest = [a for a in _and_args(expr) if not (a.get("op") == "has_encounter" and a["id"] == enc_head)]
                    if rest:
                        raise InterpretationError(
                            f"'{c.label}' mixes an encounter with patient filters; define the patient group "
                            "separately", c.source)
                else:
                    c.kind, c.spec = "set", {"expr": expr}
        finally:
            self._resolving.pop()

    # ------------------------------------------------------------------ entry point
    def build(self) -> dict:
        texts = [("definition " + str(i), d) for i, d in enumerate(self.req.get("definitions", []), 1)
                 if not re.match(r"^\s*use (?:the |each )", d, I)]
        self._scan_inline_codes(texts + [("question", self.req.get("question", ""))])
        for i, d in enumerate(self.req.get("definitions", []), 1):
            self._definition(d, i)
        for c in list(self.concepts.values()):
            if c.pending is not None:
                self._resolve(c)
        self._apply_count_rules()
        if self.mode == "spe":
            ir = self._build_spe()
        else:
            ir = self._build_statistics()
        return ir

    # ------------------------------------------------------------------ inline code annotations
    def _scan_inline_codes(self, texts: list[tuple[str, str]]) -> None:
        for where, t in texts:
            for m in re.finditer(r"\(\s*loinc:?\s*(\d{1,7}-\d)\s*\)", t, I):
                code = m.group(1)
                if any(c.kind == "observation" and c.spec.get("loinc") == code for c in self.concepts.values()):
                    continue
                term = self._term_before(t[:m.start()], "observation", code)
                ventry = V.observation_by_loinc(code)
                c = self.add_concept(term, "observation", {"loinc": code, "pick": None,
                                                           "unit": ventry.unit if ventry else ""},
                                     f"{where} (inline code)", aliases=list(ventry.terms) if ventry else [])
                self.interpretations.append({"where": where, "text": f"{term} {m.group(0).strip()}",
                                             "meaning": f"'{c.label}' = observations with LOINC {code}"})

    def _term_before(self, prefix: str, kind: str, code: str) -> str:
        toks = tokenize(prefix)[-6:]
        for start in range(len(toks)):
            hit = self.vocab_index.match_at(toks, start)
            if hit and isinstance(hit[1], V.VocabEntry) and hit[1].kind == kind and code in hit[1].codes:
                return prefix[toks[start].start:toks[hit[0] - 1].end]
        words = [t for t in toks if t.norm not in FILLER and t.norm not in ("value", "level")]
        if not words:
            raise InterpretationError(f"cannot tell which measurement LOINC {code} refers to")
        return prefix[words[-1].start:words[-1].end]

    # ------------------------------------------------------------------ definitions
    def _definition(self, text: str, i: int) -> None:
        where = f"definition {i}"
        t = text.strip().rstrip(".").strip()
        low = t.lower()
        if re.match(r"^report\b", low):
            self._report(t, where)
        elif re.match(r"^age (?:bands?|groups?|categor(?:y|ies))\b", low):
            self._age_bands(t, where)
        elif re.match(r"^an? (?:medication|prescription|drug|medicine) is (?:considered )?active\b", low):
            self._active_rule(t, where)
        elif re.match(r"^use (?:the |each patient'?s? )?(?:latest|most recent|last|first|earliest|highest|lowest)\b",
                      low):
            self._value_rule(t, where)
        elif re.match(r"^count (?:only )?(?:the )?(?:stays?|encounters?|visits?|admissions?|patients?|episodes?|"
                      r"hospitali[sz]ations?)\b", low):
            self._count_rule(t, where)
        elif "=" in t or re.search(r"\b(?:means|is defined as|are defined as)\b", low):
            parts = [p for p in re.split(r"\s*;\s*", t) if p.strip()]
            if len(parts) > 1 and all(("=" in p or re.search(r"\b(?:means|is defined as)\b", p, I)) for p in parts):
                for p in parts:
                    self._concept_definition(p, where, text)
            else:
                self._concept_definition(t, where, text)
        else:
            raise InterpretationError(f"cannot interpret this definition: \"{text}\"", where,
                                      "Use 'Term = meaning', 'Age bands ...: a-b, ...', 'Use the latest X (LOINC ...) "
                                      "per patient', 'Count stays (not patients) ...' or 'Report per ...: ...'.")

    def _concept_definition(self, t: str, where: str, original: str) -> None:
        m = re.match(r"^\s*(.+?)\s*(?:=|\bmeans\b|\bis defined as\b|\bare defined as\b)\s*(.+?)\s*\.?\s*$", t, I)
        if not m:
            raise InterpretationError(f"cannot read the definition \"{t}\"", where)
        name, body = m.group(1).strip(), m.group(2).strip()
        aliases = []
        pm = re.match(r"^(.+?)\s*\(([^)]+)\)$", name)
        if pm:
            name, aliases = pm.group(1).strip(), [pm.group(2).strip()]
        name_l = name.lower()
        c = self._interpret_body(name, body, where, original, aliases)
        self.interpretations.append({"where": where, "text": original, "meaning": describe_concept(c, self)})
        if name_l in ("cohort", "study cohort", "study population", "population", "selected patients"):
            c.role = "cohort"

    def _interpret_body(self, name: str, body: str, where: str, original: str, aliases: list[str]) -> Concept:
        b = body.strip().rstrip(".")
        low = b.lower()
        # ratio: "A / B x 100"
        if re.search(r"\s/\s|\bdivided by\b", low):
            num, den = re.split(r"\s/\s|\bdivided by\b", b, maxsplit=1, flags=I)
            den = re.sub(r"\s*(?:[×x*]|times)\s*100\b.*$", "", den, flags=I)
            den = FORMAT_RE.sub("", den).strip().rstrip(",")
            return self.add_concept(name, "ratio", {"_num": num.strip(), "_den": den.strip(), "scale": 100},
                                    where, original, aliases, pending="ratio")
        enc_word = re.search(r"\b(encounters?|primary_icd10|main diagnosis|primary diagnosis|principal diagnosis|"
                             r"stays?|visits?|admissions?|hospitali[sz]ations?)\b", low)
        patient_head = re.match(r"^(?:all |any )?(patients?|people|persons?|adults?|women|men|children|individuals?)\b",
                                low)
        if enc_word and not patient_head:
            return self._encounter_definition(name, b, where, original, aliases)
        if re.search(r"\bicd-?10\b", low):
            return self._condition_definition(name, b, where, original, aliases)
        if re.search(r"\batc\b", low):
            return self._medication_definition(name, b, where, original, aliases)
        lo = re.search(r"\bloinc:?\s*(\d{1,7}-\d)\b", b, I)
        if lo and not re.search(CMP_ANY, low):
            code = lo.group(1)
            rest = (b[:lo.start()] + b[lo.end():])
            leftovers = [t.text for t in tokenize(rest) if t.norm not in FILLER | {"loinc", "value"}
                         and not self._is_vocab_obs(t.norm)]
            existing = next((c for c in self.concepts.values()
                             if c.kind == "observation" and c.spec.get("loinc") == code), None)
            if existing:
                for alias in [name] + aliases:
                    self.index.add(alias, existing.cid)
                return existing
            ventry = V.observation_by_loinc(code)
            if leftovers:
                raise InterpretationError(f"cannot interpret '{' '.join(leftovers)}' in \"{original}\"", where)
            return self.add_concept(name, "observation", {"loinc": code, "pick": None,
                                                          "unit": ventry.unit if ventry else ""},
                                    where, original, aliases)
        # everything else is a patient set described in words (age, sex, region, other concepts, vocabulary)
        return self.add_concept(name, "set", {}, where, original, aliases, pending=b)

    def _check_leftover(self, rest: str, where: str, original: str, extra: set[str] | frozenset = frozenset()) -> None:
        extra_n = {norm_word(x) for x in extra} | set(extra)
        left = [t.text for t in tokenize(rest) if t.norm not in FILLER and t.norm not in extra_n]
        if left:
            raise InterpretationError(f"cannot interpret '{' '.join(left)}' in \"{original}\"", where,
                                      "Rephrase the definition or give explicit codes.")

    def _is_vocab_obs(self, norm: str) -> bool:
        return any(norm in norm_phrase(t) for e in V.OBSERVATIONS for t in e.terms)

    def _condition_definition(self, name, b, where, original, aliases) -> Concept:
        codes, consumed = [], []
        for m in re.finditer(rf"icd-?10 (?:codes? )?(?:that )?(?:starting|starts|beginning|begins|start|begin) with "
                             rf"((?:{ICD_RE})(?:\s*(?:,|or|and)\s*(?:{ICD_RE}))*)", b, I):
            codes += [{"code": norm_icd(c), "match": "prefix"} for c in re.findall(ICD_RE, m.group(1).upper())]
            consumed.append(m.span())
        for m in re.finditer(rf"icd-?10 (?:codes? )?((?:{ICD_RE})(?:\s*(?:,|or|and)\s*(?:{ICD_RE}))*)(?!\w)", b, I):
            if any(s <= m.start() < e for s, e in consumed):
                continue
            codes += [{"code": norm_icd(c), "match": "category"} for c in re.findall(ICD_RE, m.group(1).upper())]
            consumed.append(m.span())
        if not codes:
            raise InterpretationError(f"no ICD-10 code found in \"{original}\"", where)
        spec = {"icd10": codes}
        rest = _cut(b, consumed)
        dr = date_range_from(rest) if re.search(r"\b(onset|diagnosed|first recorded|onset_date)\b", rest, I) else None
        if dr:
            spec["onset_from"], spec["onset_to"] = dr[0], dr[1]
            rest = rest[:dr[2][0]] + rest[dr[2][1]:]
        self._check_leftover(rest, where, original, extra={"icd", "icd-10", "onset", "onset_date", "start", "begin",
                                                           "starting", "beginning", "with", "or", "date", "first"})
        return self.add_concept(name, "condition", spec, where, original, aliases)

    def _medication_definition(self, name, b, where, original, aliases) -> Concept:
        codes, consumed = [], []
        for m in re.finditer(rf"atc (?:codes? )?(?:that )?(?:starting|starts|beginning|begins|start|begin) with "
                             rf"((?:{ATC_RE})(?:\s*(?:,|or|and)\s*(?:{ATC_RE}))*)(?![A-Za-z0-9])", b, I):
            codes += [c for c in re.findall(r"[A-Z][A-Z0-9]*", m.group(1).upper()) if c not in ("OR", "AND")]
            consumed.append(m.span())
        for m in re.finditer(rf"atc (?:codes? )?((?:{ATC_RE})(?:\s*(?:,|or|and)\s*(?:{ATC_RE}))*)(?![A-Za-z0-9])", b, I):
            if any(s <= m.start() < e for s, e in consumed):
                continue
            codes += [c for c in re.findall(r"[A-Z][A-Z0-9]*", m.group(1).upper()) if c not in ("OR", "AND")]
            consumed.append(m.span())
        if not codes:
            raise InterpretationError(f"no ATC code found in \"{original}\"", where)
        spec = {"atc": codes}
        rest = _cut(b, consumed)
        if re.search(r"\bactive\b", rest, I):
            spec["active_required"] = True
            rest = re.sub(r"\b(?:that is |which is )?active(?: on 31 december \d{4})?\b", " ", rest, flags=I)
        self._check_leftover(rest, where, original, extra={"atc", "start", "begin", "starting", "beginning", "or"})
        return self.add_concept(name, "medication", spec, where, original, aliases)

    def _encounter_definition(self, name, b, where, original, aliases) -> Concept:
        spec: dict = {}
        rest = b
        # an encounter defined via another encounter concept ("inpatient stay whose primary_icd10 ...")
        toks = tokenize(rest)
        for s, e, cid in self.index.find_all(toks):
            base = self.concepts[cid]
            if base.kind == "encounter":
                spec = copy.deepcopy(base.spec)
                base.referenced = True
                rest = rest[:toks[s].start] + " " + rest[toks[e - 1].end:]
                break
        types = []
        for m in re.finditer(r"\btype\s*(?:=|is|of)?\s*['\"]?(inpatient|outpatient|emergency)['\"]?"
                             r"(?:\s*(?:or|,)\s*['\"]?(inpatient|outpatient|emergency)['\"]?)?", rest, I):
            types += [g.lower() for g in m.groups() if g]
        rest = re.sub(r"\btype\s*(?:=|is|of)?\s*['\"]?(?:inpatient|outpatient|emergency)['\"]?"
                      r"(?:\s*(?:or|,)\s*['\"]?(?:inpatient|outpatient|emergency)['\"]?)?", " ", rest, flags=I)
        for word, typ in (("inpatient", "inpatient"), ("outpatient", "outpatient"), ("emergency", "emergency")):
            if re.search(rf"\b{word}\b", rest, I):
                types.append(typ)
                rest = re.sub(rf"\b{word}\b", " ", rest, flags=I)
        if types:
            spec["types"] = sorted(set(types), key=V.ENCOUNTER_TYPES.index)
        rest = self._encounter_filters(spec, rest, where)
        if "types" not in spec:
            spec["types"] = list(V.ENCOUNTER_TYPES)
        self._check_leftover(rest, where, original, extra={"encounter", "stay", "visit", "admission", "episode",
                                                           "hospitalisation", "hospitalization", "with", "whose",
                                                           "where", "or"})
        return self.add_concept(name, "encounter", spec, where, original, aliases)

    def _encounter_filters(self, spec: dict, rest: str, where: str) -> str:
        m = re.search(rf"\bprimary_icd10\s*(?:code\s*)?(?:that\s*)?(?:is\s*)?(?:starting|starts|beginning|begins|start)"
                      rf"\s*with\s*((?:{ICD_RE})(?:\s*(?:,|or)\s*(?:{ICD_RE}))*)", rest, I)
        if m:
            spec["primary_icd10"] = [norm_icd(c) for c in re.findall(ICD_RE, m.group(1).upper())]
            rest = rest[:m.start()] + " " + rest[m.end():]
        else:
            m = re.search(rf"\b(?:primary_icd10|(?:main|primary|principal) diagnosis)\s*(?:code\s*)?(?:=|is|of)?\s*"
                          rf"(?:icd-?10\s*)?((?:{ICD_RE})(?:\s*(?:,|or)\s*(?:{ICD_RE}))*)(?![A-Za-z0-9])", rest, I)
            if m and re.search(r"\d", m.group(1)):
                spec["primary_icd10"] = [norm_icd(c) for c in re.findall(ICD_RE, m.group(1).upper())]
                rest = rest[:m.start()] + " " + rest[m.end():]
            else:
                m = re.search(r"\b(?:with |whose )?(?:a |an |the )?(?:main|primary|principal) diagnosis (?:of |is |was )?"
                              r"(?:a |an )?(.+?)(?=$|,|;|\bin \d{4}\b|\bthat\b|\bwhose\b|\bstart)", rest, I)
                if m:
                    spec["primary_icd10"] = self._diagnosis_codes(m.group(1), where)
                    rest = rest[:m.start()] + " " + rest[m.end():]
        dr = date_range_from(rest)
        if dr:
            spec["start_from"], spec["start_to"] = dr[0], dr[1]
            rest = rest[:dr[2][0]] + " " + rest[dr[2][1]:]
            rest = re.sub(r"\b(start_date|start date|started|starting|starts|began|begins|admitted)\b", " ", rest,
                          flags=I)
        for alias, holder in V.DATA_HOLDER_ALIASES.items():
            mm = re.search(rf"\b(?:at|in|by|data_holder\s*=?)?\s*'?{alias}'?", fold_keep_len(rest))
            if mm:
                spec["data_holders"] = [holder]
                rest = rest[:mm.start()] + " " + rest[mm.end():]
        return rest

    def _diagnosis_codes(self, term: str, where: str) -> list[str]:
        term = term.strip().strip("'\"").rstrip(".")
        codes = re.findall(rf"\b{ICD_RE}\b", term.upper())
        if codes and re.search(r"\d", term):
            return [norm_icd(c) for c in codes]
        toks = tokenize(term)
        hit = self.index.match_at(toks, 0) if toks else None
        if hit and hit[0] == len(toks) and self.concepts[hit[1]].kind == "condition":
            c = self.concepts[hit[1]]
            c.referenced = True
            return [x["code"] for x in c.spec["icd10"]]
        hit = self.vocab_index.match_at(toks, 0) if toks else None
        if hit and hit[0] == len(toks) and hit[1].kind == "condition":
            return list(hit[1].codes)
        raise InterpretationError(f"cannot map the main diagnosis '{term}' to ICD-10 codes", where,
                                  "Give the code, e.g. 'primary_icd10 starting with I50'.")

    # ------------------------------------------------------------------ rules
    def _age_bands(self, t: str, where: str) -> None:
        m = re.search(r":\s*(.+)$", t)
        if not m:
            raise InterpretationError("age bands must be listed after a colon, e.g. 'Age bands: 18-49, 50-64, 65+'",
                                      where)
        ref = re.search(r"31 december (\d{4})", t, I)
        if ref and int(ref.group(1)) != REFERENCE_YEAR:
            raise InterpretationError(f"age reference year {ref.group(1)} differs from the data reference date "
                                      f"31 December {REFERENCE_YEAR}", where)
        def band(s: str):
            s = s.strip().rstrip(".").strip()
            if mm := re.fullmatch(r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})(?: years)?", s, I):
                return s, int(mm.group(1)), int(mm.group(2))
            if mm := re.fullmatch(r"(\d{1,3})\s*(?:\+|years? or older|or older|and older|and over|or over|or above)", s, I):
                return s, int(mm.group(1)), None
            if mm := re.fullmatch(r"(?:<\s*|under |below |younger than )(\d{1,3})(?: years)?", s, I):
                return s, 0, int(mm.group(1)) - 1
            return None

        bands = []
        for raw in re.split(r"\s*[,;]\s*", m.group(1).strip()):
            raw = re.sub(r"^(?:and|or)\s+", "", raw.strip(), flags=I)
            if not raw:
                continue
            parsed = [band(raw)] if band(raw) else [band(p) for p in re.split(r"\s+and\s+", raw, flags=I)]
            if not all(parsed):
                raise InterpretationError(f"cannot read the age band '{raw}'", where,
                                          "Write bands like '18-49, 50-64, 65+' or 'under 18, 18-64, 65 and older'.")
            for s, lo, hi in parsed:
                if hi is not None and hi < lo:
                    raise InterpretationError(f"age band '{s}' is empty", where)
                bands.append({"label": re.sub(r"\s*(-|–)\s*", "-", s), "min": lo, "max": hi})
        ordered = sorted(bands, key=lambda b: b["min"])
        for a, b in zip(ordered, ordered[1:]):
            if a["max"] is None or a["max"] >= b["min"]:
                raise InterpretationError(f"age bands '{a['label']}' and '{b['label']}' overlap", where)
        self.age_bands = bands
        self.age_band_source = where
        self.interpretations.append({"where": where, "text": t,
                                     "meaning": "age bands (age = 2025 - birth year): " +
                                                ", ".join(b["label"] for b in bands)})

    def _active_rule(self, t: str, where: str) -> None:
        low = t.lower()
        dm = re.search(DATE_TXT, low)
        date = parse_date(dm.group(1)) if dm else REFERENCE_DATE
        ok = (re.search(r"start_date is on or before", low) and re.search(r"end_date is empty or on or after", low))
        if not ok:
            raise InterpretationError("only the rule 'start_date is on or before <date> and end_date is empty or on or "
                                      "after that day' is supported", where)
        self.active_rule = {"date": date, "source": where}
        self.interpretations.append({"where": where, "text": t,
                                     "meaning": f"active on {date}: start_date <= {date} and (end_date empty or "
                                                f">= {date})"})

    def _value_rule(self, t: str, where: str) -> None:
        m = re.match(r"^use (?:the |each patient'?s? )?(latest|most recent|last|first|earliest|highest|lowest) "
                     r"(.+?) (?:value |measurement |result )?(?:per|for each|of each) patient\b\s*(.*)$", t, I)
        if not m:
            raise InterpretationError(f"cannot read the value rule \"{t}\"", where)
        pick = {"latest": "latest", "most recent": "latest", "last": "latest", "first": "earliest",
                "earliest": "earliest", "highest": "highest", "lowest": "lowest"}[m.group(1).lower()]
        what, tail = m.group(2), m.group(3)
        lo = re.search(r"\(?\s*loinc:?\s*(\d{1,7}-\d)\s*\)?", what, I)
        if lo:
            code = lo.group(1)
            term = (what[:lo.start()] + what[lo.end():]).strip()
            c = next((c for c in self.concepts.values() if c.kind == "observation" and c.spec["loinc"] == code), None)
            if c is None:
                ventry = V.observation_by_loinc(code)
                c = self.add_concept(term or (ventry.label if ventry else code), "observation",
                                     {"loinc": code, "pick": None, "unit": ventry.unit if ventry else ""}, where, t,
                                     aliases=list(ventry.terms) if ventry else [])
            elif term:
                self.index.add(term, c.cid)
        else:
            toks = tokenize(what)
            hit = self.index.match_at(toks, 0) if toks else None
            c = None
            if hit and self.concepts[hit[1]].kind == "observation":
                c = self.concepts[hit[1]]
            else:
                vh = self.vocab_index.match_at(toks, 0) if toks else None
                if vh and vh[1].kind == "observation":
                    c = self.vocab_concept(vh[1])
                    self.index.add(what, c.cid)
            if c is None:
                raise InterpretationError(f"cannot map the measurement '{what}' to a LOINC code", where,
                                          "Add the code, e.g. 'Use the latest BMI (LOINC 39156-5) per patient'.")
        if c.spec.get("pick") and c.spec["pick"] != pick:
            raise InterpretationError(f"two different value rules for '{c.label}'", where)
        c.spec["pick"] = pick
        c.spec["pick_source"] = where
        meaning = f"'{c.label}' (LOINC {c.spec['loinc']}): use the {pick} value per patient"
        tail = tail.strip().lstrip(";,").strip()
        if tail:
            lm = re.match(r"^(?:and )?(?:patients|people|those) (?:without|with no) (?:a |an |any )?(.+?) are "
                          r"(?:left out|excluded|not included|dropped|removed)$", tail, I)
            if not lm:
                raise InterpretationError(f"cannot interpret '{tail}'", where)
            self.left_out.append((c.cid, where))
            meaning += f"; patients without a {c.label} value are left out"
        self.interpretations.append({"where": where, "text": t, "meaning": meaning})

    def _count_rule(self, t: str, where: str) -> None:
        m = re.match(r"^count (?:only )?(?:the )?(stays?|encounters?|visits?|admissions?|patients?|episodes?|"
                     r"hospitali[sz]ations?)\b\s*(?:\((?:and )?not (\w+)\)|,? not (\w+),?)?\s*(.*)$", t, I)
        if not m:
            raise InterpretationError(f"cannot read the counting rule \"{t}\"", where)
        noun = norm_word(m.group(1))
        tail = m.group(4) or ""
        rule = {"noun": noun, "unit": "patient" if noun == "patient" else "encounter", "where": where}
        dr = date_range_from(tail)
        if dr:
            rule["start_from"], rule["start_to"] = dr[0], dr[1]
            tail = tail[:dr[2][0]] + " " + tail[dr[2][1]:]
        self._check_leftover(tail, where, t, extra={"whose", "start_date", "start", "date", "started", "starting",
                                                     "begin", "began", "that", "which", "where", "with", "admitted"})
        self.count_rules.append(rule)
        meaning = f"count {'patients' if rule['unit'] == 'patient' else 'encounters (not patients)'}"
        if dr:
            meaning += f" with start_date between {rule['start_from'] or '...'} and {rule['start_to'] or '...'}"
        self.interpretations.append({"where": where, "text": t, "meaning": meaning})

    def _apply_count_rules(self) -> None:
        for rule in self.count_rules:
            if rule["unit"] == "patient":
                continue
            targets = [c for c in self.concepts.values() if c.kind == "encounter" and c.source != "vocabulary"
                       and (rule["noun"] in ("encounter", "visit") or c.head == rule["noun"]
                            or norm_word(c.label.split()[-1]) == rule["noun"])]
            if not targets:
                raise InterpretationError(f"the counting rule refers to '{rule['noun']}s' but no such encounter is "
                                          "defined", rule["where"])
            for c in targets:
                if "start_from" in rule or "start_to" in rule:
                    c.spec["start_from"] = rule.get("start_from")
                    c.spec["start_to"] = rule.get("start_to")
                c.spec["count_unit"] = "encounter"

    def _report(self, t: str, where: str) -> None:
        if self.report is not None:
            raise InterpretationError("more than one 'Report' definition", where)
        low = t.lower()
        if re.search(r"\b(?:for each|per|every|one row per|one line per) (?:individual )?patient\b"
                     r"(?!'?s?\s+(?:region|sex|age|residence|hospital|home|data))|\bpatient ids?\b|\bbirth dates?\b|"
                     r"\bpatient-level\b|\blist of (?:all )?patients\b|\bindividual records\b", low):
            self.report = {"kind": "patient_level", "where": where, "text": t}
            return
        if re.search(r"\b(?:size of the cohort|cohort size|number of patients in the cohort|size of the dataset)\b", low):
            self.report = {"kind": "cohort_size", "where": where, "text": t}
            return
        m = re.match(r"^report (?:per|by|for each|for every|broken down by) (.+?)\s*:\s*(.+)$", t, I)
        if m:
            dims_text, measures_text = m.group(1), m.group(2)
        else:
            m = re.match(r"^report(?: overall| in total| for all patients)?\s*:?\s*(?:the )?(.+)$", t, I)
            if not m:
                raise InterpretationError(f"cannot read the report line \"{t}\"", where)
            dims_text, measures_text = "", m.group(1)
        self.report = {"kind": "table", "where": where, "text": t, "dims_text": dims_text,
                       "measures_text": measures_text}

    # ------------------------------------------------------------------ set phrases
    def parse_set(self, text: str, where: str, want_head: bool = False):
        """Interpret a noun phrase describing patients (e.g. 'adults with type 2 diabetes who have ...')."""
        tokens = tokenize(text)
        n = len(tokens)
        used = [False] * n
        items: list[Item] = []
        low = fold_keep_len(text)

        def mark(s: int, e: int) -> tuple[int, int] | None:
            idx = [k for k, tk in enumerate(tokens) if tk.start < e and tk.end > s]
            if not idx or any(used[k] for k in idx):
                return None
            for k in idx:
                used[k] = True
            return idx[0], idx[-1] + 1

        # 0. inline code annotations and group context phrases
        for m in re.finditer(r"\(\s*(?:loinc|icd-?10|atc):?\s*[A-Za-z0-9.\-]+\s*\)", text, I):
            mark(*m.span())
        for m in re.finditer(r"\b(?:in|within|per|for|of) (?:the|each|every|that|this|a given) (?:region|band|age band|"
                             r"age group|group|hospital|sex|data holder|year|state)\b", low):
            mark(*m.span())
        # 1. main diagnosis of an encounter (needs to run before concept mentions)
        for m in re.finditer(rf"\b(?:with |whose )?(?:a |an |the )?(?:primary_icd10|(?:main|primary|principal) diagnosis)"
                             rf"\s*(?:code\s*)?(?:that\s*)?(?:starting with|starts with|beginning with|of|is|=)?\s*"
                             rf"(.+?)(?=$|,|;|\bin \d{{4}}\b|\bthat\b|\bwhose\b|\bwho\b|\bat klinikum\b|\bstart)", text, I):
            codes = self._diagnosis_codes(m.group(1), where)
            span = mark(*m.span())
            if span:
                items.append(Item(span[0], "pdiag", codes, span[1]))
        # 2. defined concept mentions
        for s, e, cid in self.index.find_all(tokens, used):
            for k in range(s, e):
                used[k] = True
            items.append(Item(s, "atom", ("concept", cid), e))
        # 3. other patterns
        for pat, fn in self._patterns():
            for m in re.finditer(pat, low):
                span = mark(*m.span())
                if span:
                    kind, payload = fn(m)
                    items.append(Item(span[0], kind, payload, span[1]))
        # 4. vocabulary mentions
        for s, e, entry in self.vocab_index.find_all(tokens, used):
            for k in range(s, e):
                used[k] = True
            c = self.vocab_concept(entry)
            items.append(Item(s, "atom", ("concept", c.cid), e))
        # 5. single-word operators
        for k, tk in enumerate(tokens):
            if used[k]:
                continue
            w = tk.norm
            if w in ("no", "not", "without", "never", "none", "non", "neither", "nor"):
                items.append(Item(k, "neg", w, k + 1)); used[k] = True
            elif w in ("or", "either"):
                if w == "or":
                    items.append(Item(k, "or", None, k + 1))
                used[k] = True
            elif w == "and":
                items.append(Item(k, "and", None, k + 1)); used[k] = True
            elif w in ("with", "who", "having", "whose", "that"):
                items.append(Item(k, "with", None, k + 1)); used[k] = True
            elif w in ("active", "current", "currently", "ongoing"):
                items.append(Item(k, "active", None, k + 1)); used[k] = True
            elif w in ("latest", "last", "recent"):
                items.append(Item(k, "pick", "latest", k + 1)); used[k] = True
            elif w == "most" and k + 1 < n and tokens[k + 1].norm == "recent":
                used[k] = True
            elif w in ("earliest", "first"):
                items.append(Item(k, "pick", "earliest", k + 1)); used[k] = True
        # 6. anything left that is not filler -> refuse
        left = [tokens[k].text for k in range(n) if not used[k] and tokens[k].norm not in FILLER]
        if left:
            raise InterpretationError(f"cannot interpret '{' '.join(left)}' in \"{text}\"", where, SUPPORTED_HINT)
        items.sort(key=lambda it: it.pos)
        first_atom = min((it.pos for it in items if it.kind == "atom"), default=n)
        patient_head = any(tokens[k].norm in PATIENT_NOUNS for k in range(first_atom))
        expr, enc_head = self._assemble(items, text, where, want_head and not patient_head)
        return (expr, enc_head) if want_head else expr

    def _patterns(self):
        def age_ge(m):
            return "atom", ("age", ">=", int(m.group(1)))

        def age_gt(m):
            return "atom", ("age", ">=", int(m.group(1)) + 1)

        def age_lt(m):
            return "atom", ("age", "<", int(m.group(1)))

        def age_between(m):
            return "atom", ("age_between", int(m.group(1)), int(m.group(2)))

        def region(m):
            return "atom", ("attr", "region", V.REGION_ALIASES[fold(m.group(1))])

        def holder(m):
            return "atom", ("attr", "data_holder", V.DATA_HOLDER_ALIASES[fold(m.group(1)).replace("  ", " ")])

        def sex(value):
            return lambda m: ("atom", ("attr", "sex", value))

        def cmp(op):
            return lambda m: ("cmp", (op, m.group(1)))

        def date(m):
            dr = date_range_from(m.group(0))
            return "date", (dr[0], dr[1], m.group(0))

        def atleast(m):
            word = m.group(1)
            nmap = {"two": 2, "three": 3, "four": 4, "five": 5}
            return "atleast", int(nmap.get(word, word))

        def default_age(word, cmp, value, meaning):
            def fn(m):
                note = f"No definition of '{word}' was supplied; used the standard meaning: {meaning}."
                if note not in self.notes:
                    self.notes.append(note)
                return "atom", ("age", cmp, value)
            return fn

        ref = r"(?:\s+(?:on|at|as of)\s+31 december (\d{4}))?"
        region_alt = "|".join(sorted((re.escape(a) for a in V.REGION_ALIASES), key=len, reverse=True))
        holder_alt = r"klinikum (?:nord|süd|sued|sud|west)"
        pats = [
            (r"\b(?:sex|gender)\s*(?:=|is|:|of)?\s*['\"]?(?:female|women|woman)['\"]?", sex("female")),
            (r"\b(?:sex|gender)\s*(?:=|is|:|of)?\s*['\"]?(?:male|men|man)['\"]?", sex("male")),
            (rf"\b(?:region|federal state)\s*(?:=|is|:|of)?\s*['\"]?({region_alt})['\"]?", region),
            (rf"\b(?:data_holder|data holder|hospital)\s*(?:=|is|:|of)?\s*['\"]?({holder_alt})['\"]?", holder),
            (rf"\baged? (?:between )?(\d{{1,3}}) ?(?:-|–|to|and) ?(\d{{1,3}})(?: years)?{ref}", age_between),
            (rf"\b(?:aged? )?(\d{{1,3}}) years? (?:old )?(?:or|and) (?:older|over|above){ref}", age_ge),
            (rf"\baged? (\d{{1,3}}) ?(?:\+|years? or older|or older|and older|and over|or over|or above){ref}", age_ge),
            (rf"\baged? (?:at least|no younger than) (\d{{1,3}})(?: years)?{ref}", age_ge),
            (rf"\b(?:at least|no younger than) (\d{{1,3}}) years?(?: old)?{ref}", age_ge),
            (rf"\b(?:older than|over) (\d{{1,3}}) years?(?: old)?{ref}", age_gt),
            (rf"\bage[ds]?\s*(?:>=|≥)\s*(\d{{1,3}}){ref}", age_ge),
            (rf"\bage[ds]?\s*>\s*(\d{{1,3}}){ref}", age_gt),
            (rf"\bage[ds]?\s*<\s*(\d{{1,3}}){ref}", age_lt),
            (rf"\bage[ds]?\s*(?:<=|≤)\s*(\d{{1,3}}){ref}", lambda m: ("atom", ("age", "<", int(m.group(1)) + 1))),
            (rf"(?<![\w.-])(\d{{1,3}})\s*\+(?:\s+years)?{ref}(?![\w.])", age_ge),
            (rf"\baged? (?:over|above|older than) (\d{{1,3}})(?: years)?{ref}", age_gt),
            (rf"\baged? (?:under|below|younger than|less than) (\d{{1,3}})(?: years)?{ref}", age_lt),
            (rf"\b(?:who are |that are )?(?:younger than|under) (\d{{1,3}}) years?(?: old)?{ref}", age_lt),
            (rf"\b(?:living |resident |residing |who live |who lives )?(?:in )?({region_alt})\b", region),
            (rf"\b(?:treated |seen |registered )?(?:at |in |by |from )?(?:the )?({holder_alt})\b", holder),
            (r"\b(?:women|woman|female|females|girls?)\b", sex("female")),
            (r"\b(?:men|man|male|males|boys?)\b", sex("male")),
            (r"\badults?\b", default_age("adults", ">=", 18, "aged 18 or older on 31 December 2025")),
            (r"\b(?:children|child|minors?)\b", default_age("children", "<", 18, "aged under 18 on 31 December 2025")),
            (r"\bat least (\d+|two|three|four|five)\b(?= )", atleast),
            (r"\b(\d+|two|three|four|five) or more\b(?= )", atleast),
            (rf"\b(?:diagnosed|onset|starting|started|start_date|starts|admitted|prescribed)?\s*(?:between {DATE_TXT} and "
             rf"{DATE_TXT}|between \d{{4}} and \d{{4}}|from \d{{4}} (?:to|until) \d{{4}}|(?:on or after|on or before|"
             rf"since|before|after|until) {DATE_TXT}|(?:in|during) (?:the year )?\d{{4}}|since \d{{4}})", date),
            (rf"{NUM_RE}{UNIT_RE} (?:or|and) (?:higher|more|above|greater|over)\b", cmp(">=")),
            (rf"{NUM_RE}{UNIT_RE} (?:or|and) (?:lower|less|below|under)\b", cmp("<=")),
        ]
        for words, op in CMP_WORDS:
            pats.append((rf"(?<![\w-]){words}\s*{NUM_RE}{UNIT_RE}(?![\w-])", cmp(op)))
        return pats

    def _assemble(self, items: list[Item], text: str, where: str, want_head: bool):
        atoms: list[dict] = []   # each: {"expr":..., "neg":bool, "or_before":bool, "pos":int}
        pending_neg = pending_active = pending_or = pending_and = pending_with = False
        pending_pick = pending_atleast = pending_neg_word = None
        enc_head = None
        for it in items:
            if it.kind == "neg":
                pending_neg = True
                pending_neg_word = it.payload
            elif it.kind == "active":
                pending_active = True
            elif it.kind == "or":
                pending_or = True
            elif it.kind == "pick":
                pending_pick = it.payload
            elif it.kind == "atleast":
                pending_atleast = it.payload
            elif it.kind == "and":
                pending_and = True
            elif it.kind == "with":
                pending_with = True
            elif it.kind == "atom":
                expr, enc = self._atom_expr(it.payload, pending_active, pending_pick, pending_atleast, where)
                if pending_active and not (expr.get("op") == "has_medication"):
                    raise InterpretationError(f"'active' must be followed by a medication in \"{text}\"", where)
                if want_head and enc and not atoms and enc_head is None:
                    enc_head = enc
                if atoms and atoms[-1]["neg"] and not pending_neg and pending_and and not pending_with \
                        and not atoms[-1]["neg_word"] in ("neither", "nor"):
                    raise InterpretationError(
                        f"\"{text}\" is ambiguous: does the negation cover both terms?", where,
                        "Write 'without A and without B' (neither), 'without A or B' (neither), or "
                        "'without A and with B'.")
                atoms.append({"expr": expr, "neg": pending_neg, "neg_word": pending_neg_word,
                              "or_before": pending_or and bool(atoms), "pos": it.pos})
                pending_neg = pending_active = pending_or = pending_and = pending_with = False
                pending_pick = pending_atleast = pending_neg_word = None
            elif it.kind in ("cmp", "date", "pdiag"):
                if not atoms:
                    raise InterpretationError(f"'{text}': a filter appears before the thing it applies to", where)
                last = atoms[-1]
                last["expr"] = self._bind(last["expr"], it, text, where)
                if enc_head and last["expr"].get("op") == "has_encounter":
                    enc_head = last["expr"]["id"]
        if pending_neg or pending_active or pending_atleast:
            raise InterpretationError(f"incomplete phrase \"{text}\"", where)
        if not atoms:
            expr = {"op": "all"}
        else:
            groups: list[list[dict]] = []
            for a in atoms:
                if a["or_before"]:
                    groups[-1].append(a)
                else:
                    groups.append([a])
            parts = []
            for g in groups:
                if len(g) > 1 and g[0]["neg"] and not any(a["neg"] for a in g[1:]):
                    # "without A or B" = neither A nor B
                    parts.append({"op": "not", "arg": {"op": "or", "args": [a["expr"] for a in g]}})
                    continue
                es = [{"op": "not", "arg": a["expr"]} if a["neg"] else a["expr"] for a in g]
                parts.append(es[0] if len(es) == 1 else {"op": "or", "args": es})
            expr = parts[0] if len(parts) == 1 else {"op": "and", "args": parts}
        return expr, (enc_head if want_head else None)

    def _atom_expr(self, payload, active: bool, pick, atleast, where: str):
        kind = payload[0]
        if kind == "age":
            return {"op": "age", "cmp": payload[1], "value": payload[2]}, None
        if kind == "age_between":
            return {"op": "age_between", "min": payload[1], "max": payload[2]}, None
        if kind == "attr":
            return {"op": "attr", "field": payload[1], "values": [payload[2]]}, None
        cid = payload[1]
        c = self.concept(cid)
        c.referenced = True
        if pick and c.kind != "observation":
            raise InterpretationError(f"'{'first' if pick == 'earliest' else 'latest'}' only applies to measurements, "
                                      f"not to '{c.label}'", where, SUPPORTED_HINT)
        if atleast and c.kind != "encounter":
            raise InterpretationError(f"'at least N' is only supported for encounters (got '{c.label}')", where)
        if c.kind == "set":
            if pick:
                raise InterpretationError(f"'{pick}' cannot apply to '{c.label}'", where)
            return {"op": "ref", "id": cid}, None
        if c.kind == "condition":
            return {"op": "has_condition", "id": cid}, None
        if c.kind == "medication":
            act = active or bool(c.spec.get("active_required"))
            if act:
                self.active_used = True
            return {"op": "has_medication", "id": cid, "active": act}, None
        if c.kind == "observation":
            if pick:
                if c.spec.get("pick") and c.spec["pick"] != pick:
                    raise InterpretationError(f"conflicting value rules for '{c.label}'", where)
                c.spec["pick"] = pick
            return {"op": "has_observation", "id": cid}, None
        if c.kind == "encounter":
            e = {"op": "has_encounter", "id": cid}
            if atleast:
                e["min_count"] = atleast
            return e, cid
        if c.kind == "ratio":
            raise InterpretationError(f"'{c.label}' is a ratio and cannot be used to select patients", where)
        raise InterpretationError(f"unsupported concept kind {c.kind}", where)

    def _bind(self, expr: dict, it: Item, text: str, where: str) -> dict:
        op = expr.get("op")
        if it.kind == "cmp":
            if op != "has_observation":
                raise InterpretationError(f"a comparison in \"{text}\" must follow a measurement", where)
            c = self.concepts[expr["id"]]
            if not c.spec.get("pick"):
                raise InterpretationError(f"\"{text}\" compares {c.label} but the definitions do not say which value "
                                          "per patient to use", where, "Add e.g. 'Use the latest ... per patient'.")
            return {"op": "observation_value", "id": expr["id"], "cmp": it.payload[0], "value": it.payload[1]}
        if it.kind == "date":
            lo, hi, phrase = it.payload
            if op == "has_encounter":
                new = self._derive(expr["id"], {"start_from": lo, "start_to": hi}, f"started {phrase.strip()}")
                return {**expr, "id": new}
            if op == "has_condition" and re.search(r"diagnosed|onset", phrase, I):
                return {**expr, "id": self._derive(expr["id"], {"onset_from": lo, "onset_to": hi}, phrase.strip())}
            if op == "has_medication" and re.search(r"start|prescribed", phrase, I):
                return {**expr, "id": self._derive(expr["id"], {"start_from": lo, "start_to": hi}, phrase.strip())}
            raise InterpretationError(f"cannot tell what the date '{phrase.strip()}' in \"{text}\" applies to", where)
        if it.kind == "pdiag":
            if op != "has_encounter":
                raise InterpretationError(f"a main diagnosis (primary_icd10) in \"{text}\" must follow an encounter",
                                          where)
            return {**expr, "id": self._derive(expr["id"], {"primary_icd10": it.payload},
                                               "main diagnosis " + "/".join(it.payload))}
        return expr

    def _derive(self, cid: str, changes: dict, desc: str) -> str:
        base = self.concepts[cid]
        spec = copy.deepcopy(base.spec)
        spec.update({k: v for k, v in changes.items()})
        for c in self.concepts.values():
            if c.kind == base.kind and c.spec == spec:
                c.referenced = True
                return c.cid
        c = Concept(self._new_cid(f"{base.label} {desc}"), f"{base.label} ({desc})", base.kind, spec,
                    f"derived from '{base.label}'")
        c.head = base.head
        c.referenced = True
        self.concepts[c.cid] = c
        return c.cid

    # ------------------------------------------------------------------ statistics mode
    def _build_statistics(self) -> dict:
        if self.report is None:
            raise InterpretationError("no 'Report ...' definition says which statistics to produce", "definitions")
        if self.report["kind"] == "patient_level":
            raise InterpretationError("the report asks for patient-level output (patient IDs, birth dates or one row "
                                      "per patient), which an anonymised statistical answer can never contain",
                                      self.report["where"],
                                      "Ask for counts per group, or apply for access to a secure processing "
                                      "environment and explain why statistics are not enough.")
        if self.report["kind"] == "cohort_size":
            cohort = self._cohort_expr()
            self.measures = [{"id": "m1", "type": "count_patients", "label": "Patients in the cohort",
                              "phrase": "cohort size", "set": cohort, "visible": True}]
            dims = []
        else:
            dims = self._dimensions(self.report["dims_text"], self.report["where"])
            self._measures(self.report["measures_text"], self.report["where"])
        population = self._population()
        return self._ir(population, dims)

    def _dimensions(self, text: str, where: str) -> list[dict]:
        if not text.strip():
            return []
        t = re.sub(r"\(([^)]*)\)", r" \1 ", text.lower())
        parts = [p.strip() for p in re.split(r"\s*(?:,|\band\b|×|\bx\b|\bby\b|/)\s*", t) if p.strip()]
        dims, seen = [], set()
        for p in parts:
            p = " ".join(p.split())
            p = re.sub(r"^(?:the |each |every )?(?:patient'?s? )?", "", p).strip()
            if re.fullmatch(r"(?:(?:home )?regions?|federal states?|states?|bundesl[aä]nder|bundesland|province|"
                            r"(?:region|state|place) of residence|residence|patient region)", p):
                d = {"type": "region", "groups": list(V.REGIONS)}
            elif re.fullmatch(r"(?:\d+-year )?(?:age ?bands?|bands?|age ?groups?|age ?categor(?:y|ies)|age)", p):
                if not self.age_bands:
                    raise InterpretationError("the report is broken down by age band, but no age bands are defined",
                                              where, "Add e.g. 'Age bands on 31 December 2025: 18-49, 50-64, 65+.'")
                d = {"type": "age_band", "groups": self.age_bands}
            elif re.fullmatch(r"(?:sex|gender)", p):
                d = {"type": "sex", "groups": list(V.SEXES)}
            elif re.fullmatch(r"(?:hospitals?|data[ _]holders?|hospital data_holder|data_holder hospital|"
                              r"data holder hospital|clinics?|holders?)", p) or p in ("data_holder", "data holder"):
                d = {"type": "data_holder", "groups": list(V.DATA_HOLDERS)}
            elif re.fullmatch(r"(?:calendar |start )?years?", p):
                d = {"type": "year", "groups": []}
            elif p in ("data_holder", "hospital (data_holder)"):
                d = {"type": "data_holder", "groups": list(V.DATA_HOLDERS)}
            else:
                raise InterpretationError(f"cannot group by '{p}'", where,
                                          "Supported: region, age band, sex, hospital (data_holder), year.")
            if d["type"] in seen:
                continue
            seen.add(d["type"])
            dims.append(d)
        for d in dims:
            if d["type"] in ("region", "data_holder", "sex"):
                observed = self.catalog.get(d["type"], [])
                d["groups"] = d["groups"] + [g for g in observed if g not in d["groups"]]
        return dims

    def _split_measures(self, text: str) -> list[str]:
        text = FORMAT_RE.sub("", text.strip().rstrip("."))
        parts, depth, cur = [], 0, ""
        for ch in text:
            depth += ch == "("
            depth -= ch == ")"
            if ch in ",;" and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        out: list[str] = []
        for part in parts:
            part = re.sub(r"^\s*(?:and|or|as well as|plus)\s+", "", part.strip(), flags=I)
            if not part or FORMAT_RE.fullmatch(part) or re.fullmatch(r"(?:with |to )?(?:one|1) decimal(?: places?)?", part,
                                                                       I):
                continue
            chunks = re.split(r"\s+and\s+", part, flags=I)
            merged = [chunks[0]]
            for ch in chunks[1:]:
                if self._starts_measure(ch):
                    merged.append(ch)
                else:
                    merged[-1] += " and " + ch
            for m in merged:
                m = FORMAT_RE.sub("", m).strip()
                if not m:
                    continue
                if out and not self._starts_measure(m):
                    out[-1] += ", " + m
                else:
                    out.append(m)
        return out

    def _starts_measure(self, text: str) -> bool:
        toks = tokenize(text)
        if not toks:
            return False
        if toks[0].norm in HEAD_WORDS or toks[0].text == "%":
            return True
        if len(toks) > 1 and toks[0].norm == "of" and toks[1].norm in ("whom", "them", "these", "those"):
            return True
        hit = self.index.match_at(toks, 0)
        return bool(hit and self.concepts[hit[1]].kind in ("set", "ratio", "encounter"))

    def _measures(self, text: str, where: str) -> None:
        phrases = self._split_measures(text)
        if not phrases:
            raise InterpretationError("the report line does not name any statistic", where)
        last_count = base_count = None
        parents: dict[str, str] = {}
        for phrase in phrases:
            p = FORMAT_RE.sub("", phrase).strip()
            pl = p.lower()
            percent = bool(re.match(r"^(?:the |a )?(%|percent(?:age)?s?|proportions?|shares?)\b", pl)
                           or re.search(r"\b(?:in|as a) ?%$|\(%\)$|\bpercent(?:age)?$", pl) or pl.startswith("%"))
            ref_prev = bool(re.search(r"\bof (?:them|these|those|whom)\b|\bhow many of them\b", pl))
            core = re.sub(r"\b(?:how many )?of (?:them|these|those|whom)\b", " ", p, flags=I)
            core = re.sub(r"^\s*(?:the |a )?(?:total )?(?:number|count|numbers) of\s+", "", core, flags=I)
            core = re.sub(r"^\s*how many\s+", "", core, flags=I)
            core = re.sub(r"\s*(?:\(%\)|\bin %|\bas a %|\bas a percentage|\bin percent)\s*$", "", core, flags=I).strip()
            mean = re.match(r"^(?:the |their |its )?(mean|average|median)\b\s*(?:of )?(?:the )?(.*)$", core, I)
            ratio_hit = self._ratio_concept(core)
            if ratio_hit:
                c = self.concepts[ratio_hit]
                c.referenced = True
                num = self._count_for(c.spec["numerator"], None, hidden=True)
                den = self._count_for(c.spec["denominator"], None, hidden=True)
                self._add_measure({"type": "percent", "label": f"{c.label} (%)", "phrase": p,
                                   "numerator": num, "denominator": den, "visible": True})
            elif (pm := re.match(r"^(?:the )?(?:prevalence|share|proportion|percentage|rate|%)\s+of\s+(.+?)\s+"
                                 r"(?:among|within|in)\s+(?:all\s+|the\s+)?(.+)$", core, I)):
                den_set = self.parse_set(pm.group(2), where)
                den = self._count_for(den_set, None, hidden=True)
                num = self._count_for(_and([den_set, self.parse_set(pm.group(1), where)]), self._measure(den), hidden=True)
                label = p if "%" in p else f"{p} (%)"
                self._add_measure({"type": "percent", "label": label[0].upper() + label[1:], "phrase": p,
                                   "numerator": num, "denominator": den, "visible": True})
            elif mean:
                fn = mean.group(1).lower()
                fn = "mean" if fn == "average" else fn
                rest = mean.group(2)
                expr = self.parse_set(rest, where) if rest.strip() else {"op": "all"}
                value, others = None, []
                for a in _and_args(expr):
                    if a.get("op") == "has_observation" and value is None:
                        value = a["id"]
                    else:
                        others.append(a)
                if value is None:
                    raise InterpretationError(f"\"{p}\" does not name a measurement to average", where)
                obs = self.concepts[value]
                if not obs.spec.get("pick"):
                    raise InterpretationError(f"the definitions do not say which {obs.label} value per patient to "
                                              "use", where, f"Add e.g. 'Use the latest {obs.label} per patient'.")
                if others:
                    base_set = _and(others)
                elif last_count:
                    base_set = self._measure(last_count)["set"]
                else:
                    base_set = {"op": "all"}
                self._add_measure({"type": fn, "label": f"{fn.capitalize()} {obs.label}", "phrase": p,
                                   "observation": value, "set": base_set, "visible": True})
            elif percent:
                stripped = re.sub(r"^(?:the |a )?(?:%|percent(?:age)?s?|proportions?|shares?)\s*", "", core, flags=I)
                if re.fullmatch(r"(?:that|this|the|their|its)?\s*(?:share|proportion|percentage)?\s*", core, I) or \
                        re.fullmatch(r"(?:that|this|their|its)\s+(?:share|proportion|percentage)\b.*", core, I) and \
                        not stripped.strip():
                    if not last_count:
                        raise InterpretationError(f"\"{p}\" refers to an earlier number but none precedes it", where)
                    num = last_count
                    den = parents.get(last_count) or (base_count if base_count != last_count else None)
                    if not den:
                        raise InterpretationError(f"cannot tell what \"{p}\" is a share of", where)
                    nm = self._measure(num)
                    label = f"Share with {nm['desc']} (%)" if nm.get("desc") else f"{nm['label']} (%)"
                    self._add_measure({"type": "percent", "label": label, "phrase": p,
                                       "numerator": num, "denominator": den, "visible": True})
                else:
                    of_m = re.match(r"^of (.+?) (who (?:have|has|are|had)|with|having|on|taking|without|that have) (.+)$",
                                    stripped, I)
                    if of_m and not ref_prev:
                        den_set = self.parse_set(of_m.group(1), where)
                        num_set = _and([den_set, self.parse_set(of_m.group(2) + " " + of_m.group(3), where)])
                        den = self._count_for(den_set, None, hidden=True)
                    else:
                        basis = last_count if ref_prev else base_count
                        if not basis:
                            raise InterpretationError(f"cannot tell what \"{p}\" is a percentage of", where)
                        den = basis
                        num_set = _and([self._measure(basis)["set"], self.parse_set(stripped, where)])
                    num = self._count_for(num_set, self._measure(den), hidden=True)
                    label = p if "%" in p else f"{p} (%)"
                    self._add_measure({"type": "percent", "label": label[0].upper() + label[1:], "phrase": p,
                                       "numerator": num, "denominator": den, "visible": True})
            else:
                expr, enc_head = self.parse_set(core, where, want_head=True)
                if ref_prev:
                    if not last_count:
                        raise InterpretationError(f"\"{p}\" refers to an earlier group but none precedes it", where)
                    expr = _and([self._measure(last_count)["set"], expr])
                force_patients = any(r["unit"] == "patient" for r in self.count_rules)
                label, desc = p[0].upper() + p[1:], None
                if ref_prev:
                    desc = re.sub(r"^\s*(?:who |that )?(?:have|has|are|is|had|with)\s+", "", core, flags=I).strip()
                    label = f"Of them: {desc}"
                if enc_head and not force_patients:
                    rest = [a for a in _and_args(expr) if not (a.get("op") == "has_encounter" and a["id"] == enc_head)]
                    m = self._add_measure({"type": "count_encounters", "label": label, "phrase": p, "desc": desc,
                                           "encounter": enc_head, "set": _and(rest) if rest else {"op": "all"},
                                           "visible": True})
                else:
                    m = self._add_measure({"type": "count_patients", "label": label, "phrase": p, "desc": desc,
                                           "set": expr, "visible": True})
                if ref_prev and last_count:
                    parents[m] = last_count
                else:
                    base_count = m
                last_count = m

    def _ratio_concept(self, text: str) -> str | None:
        toks = [t for t in tokenize(text) if t.norm not in ("the", "a", "%", "(", ")", "rate", "in", "percent")]
        if not toks:
            return None
        hit = self.index.match_at(toks, 0)
        if hit and hit[0] == len(toks) and self.concepts[hit[1]].kind == "ratio":
            if self.concepts[hit[1]].pending is not None:
                self._resolve(self.concepts[hit[1]])
            return hit[1]
        return None

    def _measure(self, mid: str) -> dict:
        return next(m for m in self.measures if m["id"] == mid)

    def _add_measure(self, m: dict) -> str:
        m["id"] = f"m{len(self.measures) + 1}"
        self.measures.append(m)
        return m["id"]

    def _count_for(self, expr: dict, like: dict | None, hidden: bool) -> str:
        """Find or create a count measure for `expr` (same counting unit as `like`)."""
        typ = like["type"] if like and like["type"] == "count_encounters" else "count_patients"
        key = json.dumps({"t": typ, "s": expr, "e": like.get("encounter") if like else None}, sort_keys=True)
        for m in self.measures:
            if m["type"] in ("count_patients", "count_encounters"):
                k = json.dumps({"t": m["type"], "s": m["set"], "e": m.get("encounter")}, sort_keys=True)
                if k == key:
                    return m["id"]
        m = {"type": typ, "label": "(internal) " + describe_expr(expr, self), "phrase": "", "set": expr,
             "visible": not hidden}
        if typ == "count_encounters":
            m["encounter"] = like["encounter"]
        return self._add_measure(m)

    # ------------------------------------------------------------------ population and cohort
    def _population(self) -> dict:
        parts: list[dict] = []
        reasons: list[str] = []
        for cid, where in self.left_out:
            parts.append({"op": "has_observation", "id": cid})
            reasons.append(f"patients without {self.concepts[cid].label} are left out ({where})")
            self.concepts[cid].referenced = True
        q_tokens = tokenize(self.req.get("question", ""))
        q_hits, q_negated = set(), set()
        for s, _, cid in self.index.find_all(q_tokens):
            q_hits.add(cid)
            if any(t.norm in ("without", "no", "not", "excluding", "except", "never", "non", "neither", "nor")
                   for t in q_tokens[max(0, s - 3):s]):
                q_negated.add(cid)
        for c in list(self.concepts.values()):
            if c.referenced or c.source == "vocabulary" or c.source.startswith("derived"):
                continue
            if c.kind == "observation":
                continue
            if c.kind == "ratio":
                self.notes.append(f"'{c.label}' is defined but not requested in the report; it was not computed.")
                continue
            if c.cid in q_negated:
                raise InterpretationError(f"'{c.label}' appears negated in the question but is not used in the report "
                                          "line, so its role is ambiguous", c.source,
                                          "State it in the report line, e.g. 'patients with hypertension without "
                                          f"{c.label.lower()}'.")
            if c.cid in q_hits:
                expr, _ = self._atom_expr(("concept", c.cid), False, None, None, c.source)
                parts.append(expr)
                reasons.append(f"'{c.label}' is defined ({c.source}) and named in the question, so it restricts the "
                               "population")
            else:
                raise InterpretationError(f"'{c.label}' is defined ({c.source}) but neither the report nor the question "
                                          "uses it, so its role is ambiguous", c.source,
                                          "Use the term in the report line or remove the definition.")
        self.population_reasons = reasons
        return _and(parts) if parts else {"op": "all"}

    def _cohort_expr(self) -> dict:
        cohort = [c for c in self.concepts.values() if c.role == "cohort"]
        if cohort:
            c = cohort[0]
            c.referenced = True
            if c.kind == "set":
                return {"op": "ref", "id": c.cid}
            expr, _ = self._atom_expr(("concept", c.cid), False, None, None, c.source)
            return expr
        q = self.req.get("question", "")
        m = re.search(r"\b(?:records?|data|conditions|medications|values|observations|encounters)\b[^.]*?\b(?:for|of) "
                      r"(?:all )?(.+?)(?:\.|$)", q, I)
        if m:
            return self.parse_set(m.group(1), "question")
        raise InterpretationError("the cohort is not defined", "definitions",
                                  "Add e.g. 'Cohort = adults with type 2 diabetes who have at least one HbA1c value.'")

    # ------------------------------------------------------------------ SPE mode
    def _build_spe(self) -> dict:
        cohort = self._cohort_expr()
        record_types = self._record_types()
        self.measures = [{"id": "m1", "type": "count_patients", "label": "Patients in the cohort",
                          "phrase": "cohort size", "set": cohort, "visible": True, "exact": True}]
        population = self._population()
        ir = self._ir(population, [])
        ir["spe"] = {"cohort": cohort, "record_types": record_types}
        return ir

    def _record_types(self) -> list[dict]:
        q = self.req.get("question", "")
        m = re.search(r"\b(?:provide|give|share|make available|access to|copy)\b(?: us)?(?: with)?\s+(?:the )?"
                      r"(?:pseudonymi[sz]ed |pseudonymous |de-identified |anonymi[sz]ed )?(.+?)\s+(?:for|of|on|from)\s+"
                      r"(?:all\s+)?(?:the\s+)?(?:patients|adults|people|women|men|children|persons|individuals|cohort|"
                      r"those|\w+ (?:with|who))", q, I)
        text = m.group(1) if m else q
        out: list[dict] = []
        if re.search(r"\b(conditions?|diagnos[ie]s)\b", text, I):
            out.append({"table": "conditions"})
        if re.search(r"\b(medications?|prescriptions?|drugs?|medicines?)\b", text, I):
            out.append({"table": "medications"})
        if re.search(r"\b(encounters?|visits?|stays?|admissions?|hospitali[sz]ations?)\b", text, I):
            out.append({"table": "encounters"})
        if re.search(r"\b(demographics?|birth dates?|age|sex|region|data[_ ]holder)\b", text, I):
            out.append({"table": "patients"})
        # data minimisation: named measurements (e.g. "HbA1c values") restrict observations to their LOINC codes;
        # only a generic word ("observations", "lab results") without any named measurement copies all of them
        loincs: list | None = []
        toks = tokenize(text)
        for _, _, cid in self.index.find_all(toks):
            c = self.concepts[cid]
            if c.kind == "observation":
                loincs.append(c.spec["loinc"])
        for _, _, entry in self.vocab_index.find_all(toks):
            if entry.kind == "observation" and entry.codes[0] not in loincs:
                loincs.append(entry.codes[0])
        if not loincs and re.search(r"\b(observations?|measurements?|lab(?:oratory)? (?:values|results)|vital signs)\b",
                                    text, I):
            loincs = None
        if loincs is None:
            out.append({"table": "observations"})
        elif loincs:
            out.append({"table": "observations", "loinc": sorted(set(loincs))})
        if not out:
            raise InterpretationError("the application does not say which record types are needed", "question",
                                      "Name them, e.g. 'Provide pseudonymised conditions, medications and HbA1c "
                                      "values for ...'.")
        return out

    # ------------------------------------------------------------------ IR assembly
    def _ir(self, population: dict, dims: list[dict]) -> dict:
        if any(d["type"] == "year" for d in dims):
            if not all(m["type"] == "count_encounters" for m in self.measures if m["visible"]):
                raise InterpretationError("grouping by year is only supported for encounter counts", "report")
        used = set()

        def walk(e):
            if isinstance(e, dict):
                if "id" in e and e.get("op"):
                    used.add(e["id"])
                for v in e.values():
                    walk(v)
            elif isinstance(e, list):
                for v in e:
                    walk(v)
        walk(population)
        for m in self.measures:
            walk(m)
            for key in ("encounter", "observation"):
                if m.get(key):
                    used.add(m[key])
        changed = True
        while changed:
            changed = False
            for cid in list(used):
                c = self.concepts[cid]
                before = len(used)
                walk(c.spec)
                changed |= len(used) != before
        concepts = {cid: self.concepts[cid].public() for cid in self.concepts if cid in used}
        return {
            "version": 1,
            "mode": self.mode,
            "reference_date": REFERENCE_DATE,
            "active_rule": self.active_rule if self.active_used else None,
            "concepts": concepts,
            "population": population,
            "population_reasons": getattr(self, "population_reasons", []),
            "dimensions": dims,
            "measures": self.measures,
            "interpretation": self.interpretations,
            "notes": self.notes,
        }


CMP_ANY = r"(?:above|below|over|under|greater than|less than|at least|at most|>=|<=|[<>≥≤]|or (?:higher|lower|more|less))"


def _cut(text: str, spans: list[tuple[int, int]]) -> str:
    out, last = [], 0
    for s, e in sorted(spans):
        out.append(text[last:s])
        last = e
    out.append(text[last:])
    return " ".join(out)


def _and_args(expr: dict) -> list[dict]:
    if expr.get("op") == "and":
        out = []
        for a in expr["args"]:
            out += _and_args(a)
        return out
    if expr.get("op") == "all":
        return []
    return [expr]


def _and(parts: list[dict]) -> dict:
    flat: list[dict] = []
    for p in parts:
        for a in _and_args(p):
            if a not in flat:
                flat.append(a)
    if not flat:
        return {"op": "all"}
    return flat[0] if len(flat) == 1 else {"op": "and", "args": flat}


# --------------------------------------------------------------------------- descriptions
def describe_concept(c: Concept, pb: "PlanBuilder | None" = None) -> str:
    s = c.spec
    if c.kind == "condition":
        codes = ", ".join(x["code"] + ("*" if x["match"] == "prefix" else " (incl. subcodes)") for x in s["icd10"])
        extra = ""
        if s.get("onset_from") or s.get("onset_to"):
            extra = f", onset {s.get('onset_from') or '...'} to {s.get('onset_to') or '...'}"
        return f"'{c.label}' = a row in conditions with ICD-10 {codes}{extra}"
    if c.kind == "medication":
        return f"'{c.label}' = a row in medications with ATC {', '.join(a + '*' for a in s['atc'])}" + \
            (" (active only)" if s.get("active_required") else "")
    if c.kind == "observation":
        return f"'{c.label}' = observations with LOINC {s['loinc']}"
    if c.kind == "encounter":
        bits = [f"type {'/'.join(s.get('types', []))}"]
        if s.get("primary_icd10"):
            bits.append("primary_icd10 " + "/".join(x + "*" for x in s["primary_icd10"]))
        if s.get("start_from") or s.get("start_to"):
            bits.append(f"start_date {s.get('start_from') or '...'} to {s.get('start_to') or '...'}")
        if s.get("data_holders"):
            bits.append("data_holder " + "/".join(s["data_holders"]))
        return f"'{c.label}' = encounters with " + ", ".join(bits)
    if c.kind == "ratio":
        return f"'{c.label}' = ratio x 100 (numerator / denominator)"
    if c.pending is not None:
        return f"'{c.label}' = patients: {c.pending}"
    if pb is not None and "expr" in s:
        return f"'{c.label}' = patients: {describe_expr(s['expr'], pb)}"
    return f"'{c.label}'"


def describe_expr(e: dict, pb: PlanBuilder) -> str:
    op = e.get("op")
    if op == "all":
        return "all patients"
    if op == "and":
        return " AND ".join(describe_expr(a, pb) for a in e["args"])
    if op == "or":
        return "(" + " OR ".join(describe_expr(a, pb) for a in e["args"]) + ")"
    if op == "not":
        return "NOT " + describe_expr(e["arg"], pb)
    if op == "age":
        return f"age {e['cmp']} {e['value']}"
    if op == "age_between":
        return f"age {e['min']}-{e['max']}"
    if op == "attr":
        return f"{e['field']} = {'/'.join(e['values'])}"
    c = pb.concepts.get(e.get("id"))
    label = c.label if c else e.get("id")
    if op == "ref":
        return label
    if op == "has_medication":
        return f"{'active ' if e.get('active') else ''}{label}"
    if op == "observation_value":
        return f"{label} {e['cmp']} {e['value']}"
    if op == "has_observation":
        return f"has {label}"
    if op == "has_encounter":
        return f"{'>= ' + str(e['min_count']) + ' x ' if e.get('min_count') else ''}{label}"
    return label


def build_plan(request: dict, mode: str, catalog: dict | None = None) -> dict:
    return PlanBuilder(request, mode, catalog).build()
