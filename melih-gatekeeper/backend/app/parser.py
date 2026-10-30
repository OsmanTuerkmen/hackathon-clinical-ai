"""Rule-based translator: request definitions -> QueryPlan, without any model.

Each definition line is matched against a small grammar. The resulting concepts are then resolved against the
"Report per ...:" items and the question to decide the population, the groups and the measures.
Every plan element keeps the definition lines it came from (coverage check).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import db
from .plan import Criterion, EncounterFilter, GroupBy, Measure, Population, QueryPlan, SpeRecordType
from .terminology import TERMS

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}


def parse_date(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    return m.group(0) if m else None


@dataclass
class Concept:
    name: str
    kind: str  # condition | medication | observation | primary | age | sex | encounter | ratio
    codes: list[str] = field(default_factory=list)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    sex: Optional[str] = None
    enc_types: list[str] = field(default_factory=list)
    ratio: Optional[tuple[str, str]] = None
    lines: list[int] = field(default_factory=list)
    builtin: bool = False
    value_op: Optional[str] = None
    value: Optional[float] = None


@dataclass
class Mention:
    concept: Concept
    negated: bool = False
    active: bool = False
    value_op: Optional[str] = None
    value: Optional[float] = None
    mean: bool = False


@dataclass
class ParseResult:
    plan: Optional[QueryPlan]
    unparsed: list[str]
    notes: list[str]
    coverage: dict[int, list[str]]  # definition line -> plan elements using it
    unknown_terms: list[str] = field(default_factory=list)


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") and len(word) > 3 else word


def _name_regex(name: str) -> re.Pattern:
    words = [re.escape(_stem(w)) + r"s?" for w in name.lower().split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])")


DIM_WORDS = [
    (r"age bands?|bands?|age groups?", "age_band"),
    (r"regions?|federal states?|bundesl[äa]nder?", "region"),
    (r"hospitals?|data[ _]holders?|kliniken|klinikum", "data_holder"),
    (r"sex|gender|geschlecht", "sex"),
]
FORMAT_ITEM = re.compile(r"^(one|two|1|2) decimals?$|^rounded|^with one decimal$", re.I)
OBS_UNITS = r"%|kg/m2|mmhg|mm\[hg\]|ml/min"


class Parser:
    def __init__(self, request: dict):
        self.req = request
        self.defs: list[str] = [d.strip() for d in request.get("definitions", []) if d and d.strip()]
        self.concepts: dict[str, Concept] = {}
        self.unparsed: list[str] = []
        self.notes: list[str] = []
        self.active_date: Optional[str] = None
        self.bands: list[str] = []
        self.band_lines: list[int] = []
        self.require_value: set[str] = set()
        self.count_encounters = False
        self.enc_filter = EncounterFilter()
        self.enc_lines: list[int] = []
        self.cohort_phrase: Optional[tuple[str, int]] = None
        self.report: Optional[tuple[list[str], str, int, Optional[str]]] = None  # dims, items, line, scope
        self.report_size = False
        self.patient_level = False
        self.unknown_terms: list[str] = []

    # ---------------- definition lines ----------------
    def _add(self, c: Concept):
        self.concepts[c.name.lower()] = c

    def parse_line(self, i: int, line: str) -> bool:
        text = line.strip().rstrip(".")
        low = text.lower()
        m = re.search(r"medication is active on (.+?) if", low)
        if m:
            self.active_date = parse_date(text) or db.REFERENCE_DATE
            return True
        m = re.match(r"(?:age bands?|age groups?)(?: on [^:]+)?:\s*(.+)$", text, re.I)
        if m:
            self.bands = [b.strip().replace("–", "-").replace(" ", "") for b in re.split(r",|;", m.group(1)) if b.strip()]
            self.band_lines.append(i)
            return True
        m = re.match(r"use the latest (.+?) \(loinc ([\d-]+)\)(?: per patient)?(.*)$", low)
        if m:
            name = text[len("Use the latest "):len("Use the latest ") + len(m.group(1))]
            self._add(Concept(name, "observation", [m.group(2)], lines=[i]))
            if re.search(r"without (a|an|any) .* (are|is) (left out|excluded)", m.group(3)):
                self.require_value.add(m.group(2))
            return True
        if re.search(r"count (stays|visits|encounters|admissions) \(not patients\)|count (stays|visits|encounters)\b", low):
            self.count_encounters = True
            self.enc_lines.append(i)
            self._years(low)
            return True
        m = re.match(r"^cohort\s*=\s*(.+)$", text, re.I)
        if m:
            self.cohort_phrase = (m.group(1), i)
            for code in re.findall(r"\(loinc ([\d-]+)\)", low):
                name = re.search(r"(?:one|a|an) (.+?) value \(loinc", low)
                self._add(Concept(name.group(1) if name else code, "observation", [code], lines=[i]))
            return True
        m = re.match(r"^report (?:per|by) ([^:]+):\s*(.+)$", text, re.I)
        if m:
            dims_text, scope = m.group(1), None
            sm = re.search(r"\s+in\s+(.+)$", dims_text)
            if sm:
                dims_text, scope = dims_text[: sm.start()], sm.group(1)
            self.report = (self._dims(dims_text), m.group(2), i, scope)
            return True
        m = re.match(r"^report for each (?:patient|person)(?: in ([^:]+))?:\s*(.+)$", text, re.I)
        if m:
            self.patient_level = True
            self.report = ([], "patients", i, m.group(1))
            return True
        if re.match(r"^report (?:the )?(?:size of the cohort|cohort size|number of patients in the cohort)", low):
            self.report_size = True
            self.report = ([], "cohort", i, None)
            return True
        m = re.match(r"^report:\s*(.+)$", text, re.I)
        if m:
            self.report = ([], m.group(1), i, None)
            return True
        ok = False
        for part in [p for p in re.split(r";\s*", text) if p.strip()]:
            ok = self._parse_named(i, part.strip()) or ok
        return ok

    def _years(self, low: str):
        m = re.search(r"start_?date (?:is )?in (\d{4})|start(?:ed|ing)? in (\d{4})", low)
        if m:
            y = m.group(1) or m.group(2)
            self.enc_filter.start_from, self.enc_filter.start_to = f"{y}-01-01", f"{y}-12-31"
        m = re.search(r"end_?date (?:is )?in (\d{4})|end(?:ed|ing)? in (\d{4})", low)
        if m:
            y = m.group(1) or m.group(2)
            self.enc_filter.end_from, self.enc_filter.end_to = f"{y}-01-01", f"{y}-12-31"

    def _parse_named(self, i: int, part: str) -> bool:
        m = re.match(r"^(.+?)\s*=\s*(.+)$", part)
        if not m:
            return False
        name, body = m.group(1).strip(), m.group(2).strip()
        low = body.lower()
        th = re.search(r"\(loinc ([\d-]+)\)[^0-9<>]*?(above|over|greater than|higher than|>=|>|below|under|less than|lower than|<=|<|at least)\s*(\d+(?:\.\d+)?)", low)
        if th:
            op = {"above": ">", "over": ">", "greater than": ">", "higher than": ">", ">": ">", ">=": ">=", "at least": ">=",
                  "below": "<", "under": "<", "less than": "<", "lower than": "<", "<": "<", "<=": "<="}[th.group(2)]
            self._add(Concept(name, "observation", [th.group(1)], lines=[i], value_op=op, value=float(th.group(3))))
            return True
        codes_m = re.search(r"(icd-?10|atc|loinc)(?: codes?)?\s*(?:starting|that starts?|beginning) with\s+(.+)$", low)
        prim = re.search(r"(?:primary_icd10|main diagnosis|primary diagnosis)[^A-Za-z0-9]*(?:code\s*)?(?:starting|starts?|beginning)? ?with\s+([A-Z0-9., or]+)", body, re.I)
        if re.search(r"\bencounter|\bstay|\bvisit", low) and (re.search(r"type '?(inpatient|outpatient|emergency)", low) or prim):
            types = re.findall(r"type '?(inpatient|outpatient|emergency)", low) or (["inpatient"] if "stay" in low else [])
            codes = re.findall(r"[A-Z]\d{2}[\d.]*", prim.group(1).upper()) if prim else []
            self._add(Concept(name, "encounter", codes=codes, enc_types=types, lines=[i]))
            return True
        if codes_m:
            sysname = codes_m.group(1).replace("-", "")
            codes = [c.strip().upper().rstrip(".") for c in re.split(r",|\bor\b|\band\b", codes_m.group(2)) if c.strip()]
            codes = [re.sub(r"[^A-Z0-9.\-]", "", c) for c in codes if re.search(r"\d", c)]
            kind = {"icd10": "condition", "atc": "medication", "loinc": "observation"}[sysname]
            if kind == "condition" and "primary" in low:
                kind = "primary"
            self._add(Concept(name, kind, codes, lines=[i]))
            return True
        m2 = re.search(r"aged (\d+) (?:years )?(?:or|and) (?:older|over|above)|aged (\d+)\+|(\d+) years or older", low)
        if m2:
            self._add(Concept(name, "age", age_min=int(next(g for g in m2.groups() if g)), lines=[i]))
            return True
        m2 = re.search(r"aged (\d+) ?(?:to|-|–) ?(\d+)", low)
        if m2:
            self._add(Concept(name, "age", age_min=int(m2.group(1)), age_max=int(m2.group(2)), lines=[i]))
            return True
        m2 = re.search(r"(?:younger than|under) (\d+)", low)
        if m2:
            self._add(Concept(name, "age", age_max=int(m2.group(1)) - 1, lines=[i]))
            return True
        m2 = re.search(r"sex '?(female|male)'?", low)
        if m2:
            self._add(Concept(name, "sex", sex=m2.group(1), lines=[i]))
            return True
        m2 = re.match(r"(.+?)\s*/\s*(.+?)(?:\s*[×x*]\s*100)?(?:,.*)?$", body)
        if m2 and ("100" in body or "%" in body or "share" in name.lower() or "prevalence" in name.lower() or "rate" in name.lower()):
            self._add(Concept(name, "ratio", ratio=(m2.group(1).strip(), m2.group(2).strip()), lines=[i]))
            return True
        if "type" in low and "encounter" in low:
            types = re.findall(r"(inpatient|outpatient|emergency)", low)
            self._add(Concept(name, "encounter", enc_types=types, lines=[i]))
            return True
        # plain-English definition like "Diabetes = type 2 diabetes"
        hit = self._builtin(low)
        if hit:
            c = Concept(name, hit.kind, hit.codes, lines=[i], builtin=True)
            self._add(c)
            return True
        return False

    def _dims(self, text: str) -> list[str]:
        found = []
        for m in re.finditer("|".join(f"(?P<d{k}>{p})" for k, (p, _) in enumerate(DIM_WORDS)), text.lower()):
            dim = DIM_WORDS[int(m.lastgroup[1:])][1]
            if dim not in found:
                found.append(dim)
        return found

    @staticmethod
    def _builtin(low: str) -> Optional[Concept]:
        for term in sorted(TERMS, key=len, reverse=True):
            if _name_regex(term).search(low):
                src, codes = TERMS[term]
                return Concept(term, src, list(codes), builtin=True)
        return None

    # ---------------- mentions in free text ----------------
    def mentions(self, text: str) -> list[Mention]:
        low = text.lower()
        spans: list[tuple[int, int, Concept]] = []
        for c in sorted(self.concepts.values(), key=lambda c: len(c.name), reverse=True):
            if c.kind == "ratio":
                continue
            for m in _name_regex(c.name).finditer(low):
                if not any(s <= m.start() < e for s, e, _ in spans):
                    spans.append((m.start(), m.end(), c))
        for term in sorted(TERMS, key=len, reverse=True):  # plain-English terms the definitions don't cover
            for m in _name_regex(term).finditer(low):
                if any(s <= m.start() < e or s < m.end() <= e for s, e, _ in spans):
                    continue
                src, codes = TERMS[term]
                if any(c.kind == src and set(c.codes) & set(codes) for _, _, c in spans):
                    continue
                spans.append((m.start(), m.end(), Concept(term, src, list(codes), builtin=True)))
        for word, sex in (("women", "female"), ("female", "female"), ("frauen", "female"), ("men", "male"), ("male", "male"), ("männer", "male")):
            for m in re.finditer(rf"(?<![\w-]){word}(?![\w-])", low):
                if not any(s <= m.start() < e for s, e, _ in spans) and not any(c.kind == "sex" for *_, c in spans):
                    spans.append((m.start(), m.end(), Concept(word, "sex", sex=sex, builtin=True)))
        for m in re.finditer(r"aged (\d+) (?:years )?(?:and|or) (?:over|older|above)|(\d+) years (?:and|or) older|(\d+)\s*\+", low):
            if not any(c.kind == "age" for *_, c in spans):
                spans.append((m.start(), m.end(), Concept("age", "age", age_min=int(next(g for g in m.groups() if g)), builtin=True)))
        out = []
        for s, e, c in sorted(spans, key=lambda x: x[0]):
            before = low[max(0, s - 40):s]
            after = low[e:e + 40]
            mention = Mention(c, value_op=c.value_op, value=c.value)
            mention.negated = bool(re.search(r"\b(no|without|not on|not taking|never)\b(?:\s+[\w-]+){0,3}\s*$", before))
            mention.active = bool(re.search(r"\bactive\b(?:\s+[\w-]+){0,2}\s*$", before)) or "active" in after[:12]
            mention.mean = bool(re.search(r"\b(mean|average|avg)\b(?:\s+[\w()-]+){0,3}\s*$", before))
            vm = re.match(r"\s*(?:value\s*)?(above|over|greater than|higher than|>=|>|below|under|less than|lower than|<=|<|of at least|at least)\s*(\d+(?:\.\d+)?)", after)
            if c.kind == "observation" and vm:
                op = {"above": ">", "over": ">", "greater than": ">", "higher than": ">", ">": ">", ">=": ">=", "at least": ">=", "of at least": ">=",
                      "below": "<", "under": "<", "less than": "<", "lower than": "<", "<": "<", "<=": "<="}[vm.group(1)]
                mention.value_op, mention.value = op, float(vm.group(2))
            out.append(mention)
        return out

    # ---------------- building ----------------
    def criterion(self, mn: Mention) -> Optional[Criterion]:
        c = mn.concept
        if c.kind == "condition":
            return Criterion(source="condition", codes=c.codes, negate=mn.negated, label=c.name)
        if c.kind == "medication":
            date = (self.active_date or db.REFERENCE_DATE) if (mn.active or self.active_date) else None
            return Criterion(source="medication", codes=c.codes, active_on=date, negate=mn.negated, label=("active " if date else "") + c.name)
        if c.kind == "observation":
            if mn.value_op:
                return Criterion(source="observation", codes=c.codes, pick="latest", value_op=mn.value_op, value=mn.value, negate=mn.negated,
                                 label=f"latest {c.name} {mn.value_op} {mn.value:g}")
            return Criterion(source="observation", codes=c.codes, negate=mn.negated, label=f"has {c.name}")
        if c.kind in ("primary", "encounter") and not self.count_encounters:
            return Criterion(source="encounter", codes=c.codes, encounter_types=c.enc_types or (["inpatient"] if c.kind == "primary" else []),
                             negate=mn.negated, label=c.name)
        return None

    def build(self) -> ParseResult:
        for i, line in enumerate(self.defs):
            if not self.parse_line(i, line):
                self.unparsed.append(line)
        question = self.req.get("question", "")
        coverage: dict[int, list[str]] = {}

        def cover(lines, what):
            for ln in lines:
                coverage.setdefault(ln, []).append(what)

        if self.report is None:
            self.notes.append("no 'Report per ...' line; output derived from the question")
            self.report = (self._dims(question.split(",")[-1] if " by " not in question else question.split(" by ")[-1]), question, -1, None)
        dims, items_text, report_line, scope = self.report
        if report_line >= 0:
            cover([report_line], "report")
        pop = Population()
        regions = set(db.domain("region"))
        holders = set(db.domain("data_holder"))
        for text in filter(None, [scope, question, items_text]):
            for r in regions:
                if re.search(rf"\b{re.escape(r)}\b", text) and r not in pop.regions:
                    pop.regions.append(r)
            for h in holders:
                if h.lower() in text.lower() and h not in pop.data_holders and "data_holder" not in dims:
                    pop.data_holders.append(h)

        unit = "encounters" if self.count_encounters or re.search(r"\b(stays|visits|admissions|encounters)\b", items_text.lower()) else "patients"
        if unit == "encounters":
            self._years(question.lower())
            self._years(items_text.lower())

        # split report items
        items: list[str] = []
        for chunk in re.split(r",\s*", items_text):
            items += [p for p in re.split(r"\s+and\s+(?=(?:the|their|that|its|his|her|mean|average|how|number|share|%|percent|proportion)\b)", chunk) if p.strip()]
        items = [it.strip().rstrip(".") for it in items if it.strip() and not FORMAT_ITEM.match(it.strip())]
        if self.report_size or self.patient_level:
            items = ["cohort size" if self.report_size else "patients"]

        # population: base item + question concepts + cohort definition
        base_mentions: list[Mention] = []
        if self.cohort_phrase:
            base_mentions = self.mentions(self.cohort_phrase[0])
            cover([self.cohort_phrase[1]], "population")
        item_mentions = [self.mentions(it) for it in items]
        for it in items:
            left = self._leftover(it)
            if left:
                self.notes.append(f"unrecognised term in '{it}': {' '.join(left)}")
                self.unknown_terms += left
        count_items = [k for k, it in enumerate(items) if not self._is_pct(it) and not any(m.mean for m in item_mentions[k])]
        if not base_mentions and count_items:
            base_mentions = [m for m in item_mentions[count_items[0]]]
        base_keys = {self._key(m) for m in base_mentions}
        distinguishing = set()
        for k, ms in enumerate(item_mentions):
            for m in ms:
                if self._key(m) not in base_keys:
                    distinguishing.add(m.concept.name)
        for m in self.mentions(question):
            if m.concept.name in distinguishing or self._key(m) in base_keys or m.mean:
                continue
            if m.concept.kind in ("observation",) and not m.value_op:
                continue
            if m.negated:
                continue
            base_mentions.append(m)
            base_keys.add(self._key(m))
        if unit == "encounters":
            for m in base_mentions + [x for ms in item_mentions for x in ms]:
                if m.concept.kind in ("encounter", "primary"):
                    if m.concept.enc_types:
                        self.enc_filter.types = sorted(set(self.enc_filter.types) | set(m.concept.enc_types))
                    if m.concept.codes:
                        self.enc_filter.primary_icd10 = sorted(set(self.enc_filter.primary_icd10) | set(m.concept.codes))
                        if not self.enc_filter.types:
                            self.enc_filter.types = ["inpatient"]
                    cover(m.concept.lines, "encounter filter")
            if not self.enc_filter.types and re.search(r"inpatient", items_text + question, re.I):
                self.enc_filter.types = ["inpatient"]
            if not self.enc_filter.types and re.search(r"emergency", items_text + question, re.I):
                self.enc_filter.types = ["emergency"]
            cover(self.enc_lines, "encounter filter")
        seen = set()
        for m in base_mentions:
            k = self._key(m)
            if k in seen:
                continue
            seen.add(k)
            c = m.concept
            cover(c.lines, "population")
            if c.kind == "age":
                pop.age_min = c.age_min if c.age_min is not None else pop.age_min
                pop.age_max = c.age_max if c.age_max is not None else pop.age_max
            elif c.kind == "sex":
                pop.sex = c.sex
            else:
                crit = self.criterion(m)
                if crit:
                    pop.criteria.append(crit)
        for code in sorted(self.require_value):
            if not any(cr.source == "observation" and code in cr.codes and not cr.negate for cr in pop.criteria):
                name = next((c.name for c in self.concepts.values() if c.kind == "observation" and code in c.codes), code)
                pop.criteria.append(Criterion(source="observation", codes=[code], label=f"has {name}"))

        # measures
        measures: list[Measure] = []
        names: set[str] = set()

        def uniq(n):
            n = re.sub(r"^(how many (of them )?(have|has|had|are|were|get|take)|number of|the|that|their|its|with)\s+", "", n.lower().strip())
            n = re.sub(r"\b(an?|the)\b\s*", "", n)
            n = re.sub(r"[^a-z0-9]+", "_", n).strip("_")[:44].strip("_") or "value"
            base, k = n, 2
            while n in names:
                n, k = f"{base}_{k}", k + 1
            names.add(n)
            return n

        base_name = None
        last_count = None
        for k, it in enumerate(items):
            ms = item_mentions[k]
            extra = [m for m in ms if self._key(m) not in base_keys and m.concept.kind not in ("age", "sex")]
            ratio = next((c for c in self.concepts.values() if c.kind == "ratio" and _name_regex(c.name).search(it.lower())), None)
            mean_m = next((m for m in ms if m.mean and m.concept.kind == "observation"), None)
            if mean_m:
                measures.append(Measure(name=uniq("mean_" + mean_m.concept.name), kind="mean", loinc=mean_m.concept.codes[0]))
                cover(mean_m.concept.lines, measures[-1].name)
                continue
            if ratio or self._is_pct(it):
                if base_name is None:
                    base_name = uniq("patients" if unit == "patients" else "stays")
                    measures.insert(0, Measure(name=base_name, kind="count", hidden=True))
                if ratio:
                    cover(ratio.lines, "ratio")
                    num_ms = [m for m in self.mentions(ratio.ratio[0]) if self._key(m) not in base_keys]
                    num_crit = [cr for cr in (self.criterion(m) for m in num_ms) if cr]
                    num = next((x.name for x in measures if x.kind == "count" and x.criteria and
                                [c.model_dump() for c in x.criteria] == [c.model_dump() for c in num_crit]), None) if num_crit else last_count
                    if num is None:
                        measures.append(Measure(name=uniq(ratio.ratio[0]), kind="count", criteria=num_crit, hidden=True))
                        num = measures[-1].name
                    measures.append(Measure(name=uniq(ratio.name + "_pct"), kind="pct", numerator=num, denominator=base_name))
                    continue
                crits = [cr for cr in (self.criterion(m) for m in extra) if cr]
                if crits:
                    measures.append(Measure(name=uniq(" ".join(c.label for c in crits)), kind="count", criteria=crits, hidden=True))
                    num = measures[-1].name
                    for m in extra:
                        cover(m.concept.lines, num)
                else:
                    num = last_count
                if num is None or num == base_name:
                    self.notes.append(f"share without a numerator: '{it}'")
                    continue
                measures.append(Measure(name=uniq("share_" + num[:34] + "_pct"), kind="pct", numerator=num, denominator=base_name))
                continue
            crits = [cr for cr in (self.criterion(m) for m in extra) if cr]
            for m in extra:
                cover(m.concept.lines, "measure")
            if not crits:
                if base_name is None:
                    base_name = uniq(it if len(it) < 40 else ("patients" if unit == "patients" else "stays"))
                    measures.append(Measure(name=base_name, kind="count"))
                else:
                    for x in measures:
                        if x.name == base_name:
                            x.hidden = False
                last_count = base_name
            else:
                measures.append(Measure(name=uniq(it), kind="count", criteria=crits))
                last_count = measures[-1].name
            if base_name is None and not crits:
                base_name = last_count
        if base_name and not any(x.name == base_name for x in measures):
            measures.insert(0, Measure(name=base_name, kind="count", hidden=True))
        if not measures:
            measures = [Measure(name="patients" if unit == "patients" else "stays", kind="count")]

        group_by = []
        for d in dims:
            if d == "age_band":
                if not self.bands:
                    self.notes.append("grouping by age band without band definition")
                    continue
                group_by.append(GroupBy(dim="age_band", bands=self.bands))
                cover(self.band_lines, "group_by")
            else:
                group_by.append(GroupBy(dim=d))
        if self.bands and not any(g.dim == "age_band" for g in group_by):
            group_by.append(GroupBy(dim="age_band", bands=self.bands))
            cover(self.band_lines, "group_by")
        if self.active_date:
            for ln, line in enumerate(self.defs):
                if "active on" in line.lower():
                    cover([ln], "medication activity")

        spe = []
        if self.req.get("requested_as", "").lower().strip() == "health data access application":
            spe = self._spe_records(question)
        plan = QueryPlan(
            unit=unit, population=pop, encounter_filter=self.enc_filter if unit == "encounters" else None,
            group_by=group_by, measures=measures, spe_records=spe, patient_level_requested=self.patient_level,
        )
        for ln in range(len(self.defs)):
            if ln not in coverage and self.defs[ln] not in self.unparsed:
                coverage.setdefault(ln, [])
        res = ParseResult(plan=plan, unparsed=self.unparsed, notes=self.notes, coverage=coverage)
        res.unknown_terms = self.unknown_terms
        return res

    def _spe_records(self, question: str) -> list[SpeRecordType]:
        q = question.lower()
        recs = [SpeRecordType(table="patients")]
        if "condition" in q or "diagnos" in q:
            recs.append(SpeRecordType(table="conditions"))
        if "medication" in q or "prescription" in q or "drug" in q:
            recs.append(SpeRecordType(table="medications"))
        obs_codes = sorted({code for c in self.concepts.values() if c.kind == "observation" for code in c.codes
                            if _name_regex(c.name).search(q)})
        if obs_codes or "observation" in q or "lab" in q or "measurement" in q:
            recs.append(SpeRecordType(table="observations", codes=obs_codes))
        if "encounter" in q or "stay" in q or "visit" in q:
            recs.append(SpeRecordType(table="encounters"))
        return recs

    STOP = set("""patients patient people persons person individuals adults adult with without no not who have has having had a an the their them
        they of how many number numbers and or that share in % percent percentage proportion mean average value values active one two decimal decimals
        rounded at least stays stay visits visit encounters encounter size cohort total count counts is are on per any all each whose its
        what which for there among by group groups band bands region regions hospital hospitals sex currently receiving taking prescription
        prescribed diagnosis diagnosed""".split())

    def _leftover(self, item: str) -> list[str]:
        low = item.lower()
        for c in sorted(self.concepts.values(), key=lambda c: len(c.name), reverse=True):
            low = _name_regex(c.name).sub(" ", low)
        for term in sorted(TERMS, key=len, reverse=True):
            low = _name_regex(term).sub(" ", low)
        for r in db.domain("region") + db.domain("data_holder"):
            low = low.replace(r.lower(), " ")
        words = re.findall(r"[a-zäöüß][a-zäöüß0-9-]+", low)
        return [w for w in words if w not in self.STOP and _stem(w) not in self.STOP and not w.isdigit()]

    @staticmethod
    def _is_pct(item: str) -> bool:
        return bool(re.search(r"%|\bshare\b|\bpercent|\bproportion\b|\bprevalence\b|\brate\b|\banteil\b", item.lower()))

    @staticmethod
    def _key(m: Mention) -> tuple:
        c = m.concept
        return (c.kind, tuple(c.codes), c.age_min, c.age_max, c.sex, m.negated, m.value_op, m.value)


def parse(request: dict) -> ParseResult:
    try:
        return Parser(request).build()
    except Exception as e:  # a parse failure must never crash the pipeline; it routes to review instead
        return ParseResult(plan=None, unparsed=list(request.get("definitions", [])), notes=[f"parser error: {e}"], coverage={})
