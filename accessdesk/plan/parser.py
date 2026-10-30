"""Turns a request's plain-English definitions into a query plan.

The plan is a small, checkable description of the numbers to compute:
who is counted (unit and filters), how results are grouped and which
measures (count, percentage, mean) are reported. Nothing is written per
request: the same rules read every request.
"""
import re
import unicodedata

from . import terminology
from ..store import REFERENCE_DATE
from .model import QueryPlan

POPULATION_NOUNS = {
    "adults": ("age", {"min": 18}, "Adult"),
    "adult": ("age", {"min": 18}, "Adult"),
    "children": ("age", {"max": 17}, "Child"),
    "women": ("sex", {"value": "female"}, "Women"),
    "woman": ("sex", {"value": "female"}, "Women"),
    "men": ("sex", {"value": "male"}, "Men"),
}
GENERIC_NOUNS = r"(patients?|people|persons?|individuals?)"
NEGATIONS = {"no", "without", "not", "never", "none"}
NEW_ITEM_START = re.compile(
    r"^(the|their|its|that|this|these|mean|average|median|%|share|percentage|proportion|number|"
    r"how many|count|adults?|patients?|women|men|people|inpatient|stays|encounters)\b|^%"
)
ICD_RE = r"[A-Z]\d{2}(?:\.\d{1,2})?"
ATC_RE = r"[A-Z]\d{2}(?:[A-Z]{1,2}(?:\d{2})?)?"


class Plan(dict):
    """Plain dict, so it serialises to JSON for the staff view."""


def _clean(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("×", "x")).strip().rstrip(".").strip()


def _aliases(name):
    n = name.lower().strip()
    out = {n}
    if n.endswith("y") and not n.endswith("ay"):
        out.add(n[:-1] + "ies")
    elif not n.endswith("s"):
        out.add(n + "s")
    else:
        out.add(n[:-1])
    if n == "woman":
        out.add("women")
    if n == "women":
        out.add("woman")
    return out


def _years(text):
    t = text.lower()
    m = re.search(r"(?:between|from)\s+(\d{4})\s+(?:and|to|until)\s+(\d{4})", t) or \
        re.search(r"\b(\d{4})\s*(?:-|–|to)\s*(\d{4})\b", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return list(range(min(a, b), max(a, b) + 1))
    m = re.findall(r"\bin\s+(\d{4})\b", t)
    return sorted({int(y) for y in m}) or None


def _age_rule(body):
    b = body.lower()
    m = re.search(r"aged?\s+(\d+)\s*(?:-|–|to)\s*(\d+)", b)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    m = re.search(r"aged?\s+(\d+)\s+(?:or|and)\s+(?:older|over|above|more)", b) or \
        re.search(r"(?:at least|minimum)\s+(\d+)\s+years", b)
    if m:
        return {"min": int(m.group(1))}
    m = re.search(r"older than\s+(\d+)", b)
    if m:
        return {"min": int(m.group(1)) + 1}
    m = re.search(r"aged?\s+(\d+)\s+or\s+younger", b)
    if m:
        return {"max": int(m.group(1))}
    m = re.search(r"(?:under|younger than|below)\s+(\d+)", b)
    if m and "age" in b:
        return {"max": int(m.group(1)) - 1}
    return None


def _bands(text):
    """'18-49, 50-64, 65+' -> [{'label','min','max'}]; '10-year' -> 0-9 ... 90+."""
    t = text.lower()
    part = t.split(":", 1)[1] if ":" in t else t
    bands = []
    for tok in re.split(r",|;|\band\b", part):
        tok = tok.strip().rstrip(".")
        m = re.fullmatch(r"(\d+)\s*(?:-|–|to)\s*(\d+)", tok)
        if m:
            bands.append({"label": f"{m.group(1)}-{m.group(2)}", "min": int(m.group(1)), "max": int(m.group(2))})
            continue
        m = re.fullmatch(r"(\d+)\s*(?:\+|or older|and over|and older)", tok)
        if m:
            bands.append({"label": f"{m.group(1)}+", "min": int(m.group(1)), "max": None})
            continue
        m = re.fullmatch(r"(?:under|<)\s*(\d+)", tok)
        if m:
            bands.append({"label": f"<{m.group(1)}", "min": 0, "max": int(m.group(1)) - 1})
    if not bands and "10-year" in t:
        bands = [{"label": f"{a}-{a + 9}", "min": a, "max": a + 9} for a in range(0, 90, 10)]
        bands.append({"label": "90+", "min": 90, "max": None})
    return bands


class Parser:
    def __init__(self, request, store, ai_mapper=None):
        self.req = request
        self.store = store
        self.ai_mapper = ai_mapper
        self.concepts = {}
        self.order = []
        self.ratios = {}
        self.notes = []
        self.warnings = []
        self.unit = "patient"
        self.unit_years = None
        self.bands = None
        self.report = None
        self.active_rule = False
        self.patient_level = False
        self.referenced = set()

    # ---------- concepts ----------
    def add(self, name, kind, source, **spec):
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        cid = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_") or f"c{len(self.concepts)}"
        while cid in self.concepts and self.concepts[cid]["name"].lower() != name.lower():
            cid += "_"
        c = {"id": cid, "name": name, "kind": kind, "source": source, "aliases": sorted(_aliases(name)), **spec}
        self.concepts[cid] = c
        if cid not in self.order:
            self.order.append(cid)
        return c

    def parse(self):
        statements = []
        for d in self.req.get("definitions", []):
            for part in re.split(r";\s+", d):
                part = _clean(part)
                if part:
                    statements.append((part, d))
        last_obs = None
        for text, original in statements:
            low = text.lower()
            if low.startswith("report"):
                self.report = text
            elif "age band" in low or "age group" in low:
                self.bands = _bands(text)
            elif re.search(r"\bis active\b|\bactive on\b", low) and "=" not in text:
                self.active_rule = True
                self.notes.append("Active medication rule: start_date on or before 31 Dec 2025 and end_date empty or on/after that day.")
            elif low.startswith("use the latest") or low.startswith("use the most recent"):
                m = re.search(r"(?:latest|most recent)\s+(.+?)\s*\(loinc\s+([\d-]+)\)", text, re.I)
                if m:
                    last_obs = self.add(m.group(1).strip(), "observation", original, loinc=m.group(2), pick="latest")
            elif "left out" in low or "excluded" in low:
                self.notes.append(text)
            elif re.match(r"count (stays|encounters|visits|admissions)", low) or "(not patients)" in low:
                self.unit = "encounter"
                self.unit_years = _years(text)
            elif "=" in text:
                name, body = [s.strip() for s in text.split("=", 1)]
                self.define(name, body, original)
            else:
                self.warnings.append(f"Not understood: “{text}”")
        if self.report is None:
            self.warnings.append("No 'Report …' sentence found; counting the cohort per requested group.")
        return self.build()

    def define(self, name, body, original):
        b = body.lower()
        if " / " in body and re.search(r"(x|\*)\s*100|%|percent", b):
            num, den = body.split(" / ", 1)
            den = re.split(r"\s+(?:x|\*)\s*100", den)[0]
            self.ratios[name.lower()] = {"name": name, "num": _clean(num), "den": _clean(re.sub(r",.*$", "", den))}
            return
        if re.match(r"^(adults?|patients?|people|persons?|women|men|children)\b", b) or " who " in b:
            self.add(name, "composite", original, phrase=body)
            return
        has_icd = re.search(r"\bicd|primary_icd10", b) is not None
        if has_icd and ("primary_icd10" in b or "main diagnosis" in b or "encounter" in b or "stay" in b):
            codes = re.findall(ICD_RE, body.split("starting with")[-1]) if "starting with" in b else re.findall(ICD_RE, body)
            parent = self._encounter_parent(body)
            self.add(name, "encounter", original, enc_type=parent.get("enc_type") or _enc_type(b),
                     primary_prefixes=codes)
            return
        if has_icd:
            codes = re.findall(ICD_RE, body.split("with", 1)[-1])
            self.add(name, "condition", original, prefixes=codes)
            return
        if re.search(r"\batc\b", b):
            codes = re.findall(ATC_RE, body.split("with", 1)[-1])
            self.add(name, "medication", original, prefixes=codes)
            return
        if re.search(r"\bloinc\b", b):
            m = re.search(r"loinc\s+([\d-]+)", b)
            self.add(name, "observation", original, loinc=m.group(1), pick="latest")
            return
        if re.search(r"\bsex\b|\bgender\b", b):
            m = re.search(r"(female|male)", b)
            self.add(name, "sex", original, value=m.group(1) if m else "female")
            return
        if re.search(r"\baged?\b|\byears old\b|\bage\b", b):
            rule = _age_rule(body)
            if rule:
                self.add(name, "age", original, **rule)
                return
        if "encounter" in b or re.search(r"\b(inpatient|outpatient|emergency)\b", b):
            parent = self._encounter_parent(body)
            self.add(name, "encounter", original, enc_type=_enc_type(b) or parent.get("enc_type"),
                     primary_prefixes=parent.get("primary_prefixes", []))
            return
        if "length of stay" in name.lower() or ("end_date" in b and "start_date" in b):
            self.add(name, "los", original)
            return
        hits = terminology.find_terms(body)
        if hits:
            h = hits[0]
            kind = {"icd10": "condition", "atc": "medication", "loinc": "observation"}[h["system"]]
            spec = {"loinc": h["codes"][0], "pick": "latest"} if kind == "observation" else {"prefixes": h["codes"]}
            self.add(name, kind, original + "  [codes from code list]", **spec)
            return
        if self.ai_mapper:
            out = self.ai_mapper(name, body)
            if out:
                kind = {"icd10": "condition", "atc": "medication", "loinc": "observation"}[out["system"]]
                spec = {"loinc": out["codes"][0], "pick": "latest"} if kind == "observation" else {"prefixes": out["codes"]}
                note = str(out.get("note") or "").strip()
                source = f"AI mapping: {note}".rstrip()
                self.add(name, kind, source, **spec)
                return
        self.warnings.append(f"Definition not understood: “{name} = {body}”")

    def _encounter_parent(self, body):
        for c in self.concepts.values():
            if c["kind"] == "encounter" and any(a in body.lower() for a in c["aliases"]):
                return c
        return {}

    # ---------- phrases ----------
    def resolve(self, phrase, mark=True):
        """Find concept mentions in a phrase. Returns (terms, matched spans)."""
        p = " " + _clean(phrase).lower() + " "
        spans, terms = [], []

        def taken(a, b):
            return any(a < e and b > s for s, e in spans)

        alias_list = sorted(((a, cid) for cid, c in self.concepts.items() for a in c["aliases"]
                             if c["kind"] != "composite"), key=lambda x: -len(x[0]))
        for alias, cid in alias_list:
            for m in re.finditer(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", p):
                if taken(m.start(), m.end()):
                    continue
                spans.append((m.start(), m.end()))
                terms.append(self._term(cid, p, m.start(), m.end()))
        # composite concepts ("the cohort")
        for cid, c in self.concepts.items():
            if c["kind"] == "composite":
                for a in c["aliases"]:
                    m = re.search(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", p)
                    if m and not taken(m.start(), m.end()):
                        spans.append((m.start(), m.end()))
                        sub, _ = self.resolve(c["phrase"], mark)
                        terms.extend(sub)
                        if mark:
                            self.referenced.add(cid)
        # population nouns that were not defined
        for noun, (kind, spec, label) in POPULATION_NOUNS.items():
            for m in re.finditer(r"(?<![\w-])" + noun + r"(?![\w-])", p):
                if taken(m.start(), m.end()):
                    continue
                existing = [c for c in self.concepts.values() if c["kind"] == kind and
                            all(c.get(k) == v for k, v in spec.items())]
                c = existing[0] if existing else self.add(label, kind, "implicit (population noun)", **spec)
                spans.append((m.start(), m.end()))
                terms.append({"concept": c["id"], "neg": False})
        # code list fallback for medical terms the request did not define
        for h in terminology.find_terms(p):
            if taken(h["start"], h["end"]):
                continue
            kind = {"icd10": "condition", "atc": "medication", "loinc": "observation"}[h["system"]]
            spec = {"loinc": h["codes"][0], "pick": "latest"} if kind == "observation" else {"prefixes": h["codes"]}
            existing = [c for c in self.concepts.values() if c["kind"] == kind and
                        (c.get("prefixes") == spec.get("prefixes") if kind != "observation" else c.get("loinc") == spec["loinc"])]
            c = existing[0] if existing else self.add(h["label"], kind, f"code list (matched “{h['matched']}”)", **spec)
            spans.append((h["start"], h["end"]))
            terms.append(self._term(c["id"], p, h["start"], h["end"]))
        if mark:
            for t in terms:
                self.referenced.add(t["concept"])
        # remove duplicates, keep order
        seen, out = set(), []
        for t in terms:
            key = (t["concept"], t["neg"], t.get("active"), str(t.get("cmp")), str(t.get("years")))
            if key not in seen:
                seen.add(key)
                out.append(t)
        return out, spans

    def _term(self, cid, p, start, end):
        c = self.concepts[cid]
        before = p[max(0, start - 40):start].split()[-4:]
        after = p[end:end + 40]
        term = {"concept": cid, "neg": any(w in NEGATIONS for w in before)}
        if c["kind"] == "medication":
            explicit = "active" in before
            ever = re.search(r"\b(ever|any time|at any time)\b", p) is not None
            term["active"] = explicit or (self.active_rule and not ever)
        if c["kind"] in ("observation",):
            m = re.match(r"\s*(?:value\s*)?(?:of\s*)?(above|over|greater than|more than|higher than|>=|>|at least|below|under|less than|lower than|<=|<)\s*(\d+(?:\.\d+)?)", after)
            if m:
                op = {"above": ">", "over": ">", "greater than": ">", "more than": ">", "higher than": ">",
                      ">": ">", ">=": ">=", "at least": ">=", "below": "<", "under": "<", "less than": "<",
                      "lower than": "<", "<": "<", "<=": "<="}[m.group(1)]
                term["cmp"] = {"op": op, "value": float(m.group(2))}
        if c["kind"] == "encounter":
            yrs = _years(p[end:end + 40])
            if yrs:
                term["years"] = yrs
        return term

    # ---------- report sentence ----------
    def build(self):
        groups, items = [], []
        rep = self.report or ""
        low = rep.lower()
        m = re.match(r"report (?:per|by|for each)\s+(.+?):\s*(.+)$", rep, re.I)
        if re.search(r"for each patient|patient id|birth date", low):
            self.patient_level = True
            gm = re.search(r"in (" + "|".join(self.store.domains["region"]) + r")", rep)
            if gm:
                self.add(gm.group(1), "region", "report sentence", value=gm.group(1))
            items = ["patients"]
        elif m:
            groups = self._groups(m.group(1))
            items = self._split_items(m.group(2))
        elif re.search(r"size of the cohort|cohort size", low):
            items = ["cohort size"]
        elif ":" in rep:
            items = self._split_items(rep.split(":", 1)[1])
        else:
            q = self.req.get("question", "")
            gm = re.search(r"\bby ([\w\s'-]+?)(?:\?|$)", q)
            groups = self._groups(gm.group(1)) if gm else []
            items = ["patients"]

        measures = []
        last_count = None
        for raw in items:
            meas = self._measure(raw, measures, last_count)
            if meas is None:
                continue
            measures.append(meas)
            if meas["type"] == "count":
                last_count = meas

        for r in self.ratios.values():
            self.referenced.update(t["concept"] for t in self.resolve(r["num"])[0])
            self.referenced.update(t["concept"] for t in self.resolve(r["den"])[0])

        # Concepts defined but never mentioned in a measure describe the
        # cohort itself (e.g. "women with breast cancer"), so they filter everyone.
        population = []
        for cid in self.order:
            c = self.concepts[cid]
            if c["kind"] in ("age", "sex", "region"):
                population.append({"concept": cid, "neg": False})
            elif c["kind"] in ("condition", "medication", "observation", "encounter") and cid not in self.referenced:
                t = {"concept": cid, "neg": False}
                if c["kind"] == "medication":
                    t["active"] = self.active_rule
                population.append(t)
                self.notes.append(f"“{c['name']}” is not mentioned in the report sentence, so it is applied to the whole cohort.")

        cohort = None
        for cid, c in self.concepts.items():
            if c["kind"] == "composite" and c["name"].lower() in ("cohort", "study population", "population"):
                cohort, _ = self.resolve(c["phrase"])
        if cohort is None:
            sized = [mm for mm in measures if mm.get("cohort")]
            cohort = sized[0]["set"] if sized else (measures[0]["set"] if measures else [])

        enc_concept = None
        if self.unit == "encounter":
            enc = [t for mm in measures for t in mm.get("set", []) if self.concepts[t["concept"]]["kind"] == "encounter"]
            enc_concept = enc[0]["concept"] if enc else next(
                (cid for cid in self.order if self.concepts[cid]["kind"] == "encounter"), None)

        plan = Plan(
            unit=self.unit,
            unit_years=self.unit_years,
            encounter_concept=enc_concept,
            concepts={cid: self.concepts[cid] for cid in self.order},
            ratios=list(self.ratios.values()),
            population=population,
            groups=groups,
            measures=measures,
            cohort=cohort,
            patient_level_requested=self.patient_level,
            record_types=_record_types(self.req.get("question", ""), self.concepts),
            active_rule=self.active_rule,
            reference_date=REFERENCE_DATE,
            notes=self.notes,
            warnings=self.warnings,
        )
        return QueryPlan.model_validate(plan)

    def _groups(self, text):
        t = text.lower()
        out = []
        for tok in re.split(r"\band\b|,|\bx\b", t):
            tok = tok.strip()
            if not tok:
                continue
            if re.search(r"age band|band|age group", tok):
                bands = self.bands or _bands("10-year")
                out.append({"dim": "age_band", "bands": bands})
            elif re.search(r"region|federal state|state|bundesland", tok):
                out.append({"dim": "region"})
            elif re.search(r"hospital|data.holder|clinic|klinikum", tok):
                out.append({"dim": "data_holder"})
            elif re.search(r"\bsex\b|gender", tok):
                out.append({"dim": "sex"})
            elif re.search(r"\byear\b", tok):
                out.append({"dim": "year", "years": self.unit_years or [2023, 2024, 2025]})
            else:
                self.warnings.append(f"Unknown grouping “{tok}”")
        return out

    def _split_items(self, text):
        text = _clean(text)
        protected = {}
        for c in self.concepts.values():
            for a in c["aliases"]:
                if " and " in a or "," in a:
                    key = f"§{len(protected)}§"
                    protected[key] = a
                    text = re.sub(re.escape(a), key, text, flags=re.I)
        parts = []
        for chunk in text.split(", "):
            chunk = re.sub(r"^(and|or)\s+", "", chunk.strip())
            pieces = re.split(r"\s+and\s+", chunk)
            cur = pieces[0]
            for nxt in pieces[1:]:
                if NEW_ITEM_START.match(nxt.strip().lower()):
                    parts.append(cur)
                    cur = nxt
                else:
                    cur = f"{cur} and {nxt}"
            parts.append(cur)
        out = []
        for p in parts:
            for k, v in protected.items():
                p = p.replace(k, v)
            p = p.strip()
            if re.fullmatch(r"(with |to |rounded to )?(one|1) decimals?( place)?", p.lower()) or not p:
                continue
            out.append(p)
        return out

    def _measure(self, raw, measures, last_count):
        label = re.sub(r",?\s*(with |rounded to )?(one|1) decimals?( place)?$", "", raw, flags=re.I).strip()
        low = label.lower()
        relative = re.search(r"\b(of them|their|of these|among them|of those|these patients)\b", low) is not None
        ctx = last_count["set"] if (relative and last_count) else []
        key_base = re.sub(r"[^a-z0-9%]+", "_", low.replace("%", "pct")).strip("_")
        key_base = re.sub(r"^(number_of|how_many_of_them_have|how_many_of_them|how_many|of_them|their|that|the)_", "", key_base)

        # percentage defined in the definitions (e.g. "the prevalence")
        for rname, r in self.ratios.items():
            if rname in low:
                num, _ = self.resolve(r["num"])
                den, _ = self.resolve(r["den"])
                return {"key": re.sub(r"\W+", "_", rname) + "_pct", "label": label, "type": "pct",
                        "num_set": num, "den_set": den, "source": f"{r['name']} = {r['num']} / {r['den']} x 100"}

        if re.search(r"\b(mean|average)\b", low):
            terms, _ = self.resolve(low)
            value = next((t for t in terms if self.concepts[t["concept"]]["kind"] in ("observation", "los")), None)
            if value is None:
                obs = [c for c in self.concepts.values() if c["kind"] in ("observation", "los")]
                if not obs:
                    self.warnings.append(f"Mean of what? “{label}”")
                    return None
                value = {"concept": obs[0]["id"], "neg": False}
                self.referenced.add(obs[0]["id"])
            others = [t for t in terms if t["concept"] != value["concept"]]
            if last_count and any(t["concept"] == value["concept"] for t in last_count["set"]):
                base = last_count["set"]
            else:
                base = ctx + others
                if self.concepts[value["concept"]]["kind"] == "observation":
                    base = base + [{"concept": value["concept"], "neg": False}]
            return {"key": key_base, "label": label, "type": "mean", "set": _dedupe(base + others),
                    "value": value["concept"]}

        if "%" in low or re.search(r"\b(share|percentage|proportion|prevalence|rate)\b", low):
            terms, _ = self.resolve(low)
            if not terms and last_count is not None:
                parent = last_count.get("parent")
                den = parent["set"] if parent else (measures[0]["set"] if measures and measures[0]["type"] == "count" else [])
                return {"key": key_base, "label": label, "type": "pct", "num_set": last_count["set"], "den_set": den,
                        "source": f"{last_count['label']} / {(parent or {'label': 'all'})['label']} x 100"}
            den = last_count["set"] if last_count else []
            return {"key": key_base, "label": label, "type": "pct", "num_set": _dedupe(den + terms), "den_set": den,
                    "source": f"({last_count['label'] if last_count else 'all'} {('with ' + label.lstrip('% ')) if terms else ''}) / {last_count['label'] if last_count else 'all'} x 100"}

        if re.search(r"size of the cohort|cohort size", low):
            cohort = next((c for c in self.concepts.values() if c["kind"] == "composite"), None)
            terms = self.resolve(cohort["phrase"])[0] if cohort else []
            if cohort:
                self.referenced.add(cohort["id"])
            return {"key": "cohort_size", "label": "Cohort size", "type": "count", "set": terms, "cohort": True}

        terms, _ = self.resolve(low)
        meas = {"key": key_base or "patients", "label": label, "type": "count", "set": _dedupe(ctx + terms)}
        if relative and last_count:
            meas["parent"] = {"label": last_count["label"], "set": last_count["set"]}
        return meas


def _enc_type(b):
    m = re.search(r"\b(inpatient|outpatient|emergency)\b", b)
    return m.group(1) if m else None


def _dedupe(terms):
    seen, out = set(), []
    for t in terms:
        key = (t["concept"], t["neg"], t.get("active"), str(t.get("cmp")), str(t.get("years")))
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _record_types(question, concepts):
    q = question.lower()
    types = []
    if re.search(r"condition|diagnos", q):
        types.append({"table": "conditions"})
    if re.search(r"medication|prescription|drug", q):
        types.append({"table": "medications"})
    obs = []
    for h in terminology.find_terms(q, systems={"loinc"}):
        if h["codes"][0] not in obs:
            obs.append(h["codes"][0])
    if obs or re.search(r"observation|measurement|lab value", q):
        types.append({"table": "observations", "loinc": obs or None})
    if re.search(r"encounter|visit|stay|admission", q):
        types.append({"table": "encounters"})
    if re.search(r"demograph|birth date|date of birth|\bsex\b|region", q):
        types.append({"table": "patients"})
    if not types and "record" in q:
        types = [{"table": "conditions"}, {"table": "medications"}, {"table": "observations", "loinc": None}]
    return types


def parse(request, store, ai_mapper=None):
    return Parser(request, store, ai_mapper=ai_mapper).parse()
