"""Validator for the query-plan intermediate representation (IR).

Every plan - whether produced by the deterministic parser or proposed by an optional LLM - must pass
this validator before any patient data is touched.

IR outline:
  concepts:   id -> {kind: condition|medication|observation|encounter|set|ratio, ...codes/filters}
  population: boolean expression over patients
  dimensions: [{type: region|age_band|sex|data_holder|year, groups: [...]}]
  measures:   [{id, type: count_patients|count_encounters|percent|mean|median, ...}]
  spe:        {cohort: expression, record_types: [{table, loinc?}]}   (secure processing only)
Expressions: and/or/not/all, age, age_between, attr, ref, has_condition, has_medication,
             has_observation, observation_value, has_encounter.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

ICD = re.compile(r"^[A-Z]\d{0,2}(\.[0-9A-Z]{0,4})?$")
ATC = re.compile(r"^[A-Z](\d{2}([A-Z]([A-Z](\d{2})?)?)?)?$")
LOINC = re.compile(r"^\d{1,7}-\d$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KINDS = {"condition", "medication", "observation", "encounter", "set", "ratio", "derived"}
OPS = {"and", "or", "not", "all", "age", "age_between", "attr", "ref", "has_condition", "has_medication",
       "has_observation", "observation_value", "has_encounter"}
DERIVED = {("patient", "age"), ("encounter", "duration_days")}
CMPS = {"<", "<=", ">", ">=", "="}
DIMS = {"region", "age_band", "sex", "data_holder", "year"}
MEASURES = {"count_patients", "count_encounters", "percent", "mean", "median"}
TABLES = {"patients", "conditions", "medications", "observations", "encounters"}
ENC_TYPES = {"inpatient", "outpatient", "emergency"}
PICKS = {None, "latest", "earliest", "highest", "lowest"}


class PlanValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate(ir: dict) -> None:
    errs: list[str] = []
    if not isinstance(ir, dict):
        raise PlanValidationError(["plan must be an object"])
    if ir.get("version") != 1:
        errs.append("version must be 1")
    if ir.get("mode") not in ("statistics", "spe"):
        errs.append("mode must be 'statistics' or 'spe'")
    concepts = ir.get("concepts")
    if not isinstance(concepts, dict) or len(concepts) > 100:
        raise PlanValidationError(errs + ["concepts must be an object with at most 100 entries"])

    def date_ok(v, where):
        if v is not None and (not isinstance(v, str) or not DATE.match(v)):
            errs.append(f"{where}: invalid date {v!r}")

    for cid, c in concepts.items():
        w = f"concept {cid}"
        if not isinstance(c, dict) or c.get("kind") not in KINDS:
            errs.append(f"{w}: unknown kind")
            continue
        k = c["kind"]
        if k == "condition":
            items = c.get("icd10")
            if not isinstance(items, list) or not items:
                errs.append(f"{w}: icd10 list required")
            else:
                for it in items:
                    if not isinstance(it, dict) or not ICD.match(str(it.get("code", ""))) or \
                            it.get("match") not in ("prefix", "category"):
                        errs.append(f"{w}: invalid ICD-10 item {it!r}")
            date_ok(c.get("onset_from"), w)
            date_ok(c.get("onset_to"), w)
        elif k == "medication":
            atc = c.get("atc")
            if not isinstance(atc, list) or not atc or not all(isinstance(a, str) and ATC.match(a) for a in atc):
                errs.append(f"{w}: invalid ATC prefixes {atc!r}")
            date_ok(c.get("start_from"), w)
            date_ok(c.get("start_to"), w)
        elif k == "observation":
            if not LOINC.match(str(c.get("loinc", ""))):
                errs.append(f"{w}: invalid LOINC {c.get('loinc')!r}")
            if c.get("pick") not in PICKS:
                errs.append(f"{w}: invalid value selection {c.get('pick')!r}")
        elif k == "encounter":
            types = c.get("types")
            if not isinstance(types, list) or not types or not set(types) <= ENC_TYPES:
                errs.append(f"{w}: invalid encounter types {types!r}")
            for code in c.get("primary_icd10") or []:
                if not isinstance(code, str) or not ICD.match(code):
                    errs.append(f"{w}: invalid primary_icd10 {code!r}")
            date_ok(c.get("start_from"), w)
            date_ok(c.get("start_to"), w)
            if c.get("data_holders") is not None and not all(isinstance(h, str) for h in c["data_holders"]):
                errs.append(f"{w}: invalid data_holders")
        elif k == "derived":
            if (c.get("of"), c.get("formula")) not in DERIVED:
                errs.append(f"{w}: unsupported derived value {c.get('of')}/{c.get('formula')}")
        elif k == "set":
            _expr(c.get("expr"), concepts, errs, w, 0)
        elif k == "ratio":
            _expr(c.get("numerator"), concepts, errs, w, 0)
            _expr(c.get("denominator"), concepts, errs, w, 0)

    _expr(ir.get("population"), concepts, errs, "population", 0)
    _ref_cycles(concepts, errs)

    dims = ir.get("dimensions")
    if not isinstance(dims, list) or len(dims) > len(DIMS) or len({d.get("type") for d in dims if isinstance(d, dict)}) < len(dims):
        errs.append(f"dimensions must be a list of at most {len(DIMS)} different groupings")
        dims = []
    total = 1
    for d in dims:
        if not isinstance(d, dict) or d.get("type") not in DIMS:
            errs.append(f"invalid dimension {d!r}")
            continue
        groups = d.get("groups")
        if not isinstance(groups, list):
            errs.append(f"dimension {d['type']}: groups must be a list")
            continue
        if d["type"] == "age_band":
            prev_max = -1
            labels = set()
            for g in sorted(groups, key=lambda g: g.get("min", 0) if isinstance(g, dict) else 0):
                if not isinstance(g, dict) or not isinstance(g.get("min"), int) or \
                        (g.get("max") is not None and not isinstance(g.get("max"), int)):
                    errs.append(f"invalid age band {g!r}")
                    continue
                if g["min"] <= prev_max:
                    errs.append(f"age bands overlap at {g.get('label')}")
                if g["label"] in labels:
                    errs.append(f"duplicate age band {g['label']}")
                labels.add(g["label"])
                prev_max = g["max"] if g["max"] is not None else 10 ** 6
            if not groups:
                errs.append("age band dimension without bands")
        total *= max(1, len(groups))
    if total > 2000:
        errs.append("too many groups (more than 2000 cells per measure)")

    measures = ir.get("measures")
    if not isinstance(measures, list) or not measures or len(measures) > 40:
        errs.append("measures must be a non-empty list (at most 40)")
        measures = []
    seen: dict[str, dict] = {}
    for m in measures:
        if not isinstance(m, dict) or m.get("type") not in MEASURES or not isinstance(m.get("id"), str):
            errs.append(f"invalid measure {m!r}")
            continue
        w = f"measure {m['id']}"
        if m["id"] in seen:
            errs.append(f"{w}: duplicate id")
        t = m["type"]
        if t in ("count_patients", "count_encounters", "mean", "median"):
            _expr(m.get("set"), concepts, errs, w, 0)
        if t == "count_encounters" and concepts.get(m.get("encounter"), {}).get("kind") != "encounter":
            errs.append(f"{w}: 'encounter' must reference an encounter concept")
        if t in ("mean", "median"):
            if m.get("derived"):
                dv = concepts.get(m["derived"], {})
                if dv.get("kind") != "derived":
                    errs.append(f"{w}: 'derived' must reference a derived-value concept")
                elif dv.get("of") == "encounter" and concepts.get(m.get("encounter"), {}).get("kind") != "encounter":
                    errs.append(f"{w}: an encounter-level value needs an 'encounter' concept")
            else:
                obs = concepts.get(m.get("observation"), {})
                if obs.get("kind") != "observation":
                    errs.append(f"{w}: 'observation' must reference an observation concept")
                elif not obs.get("pick"):
                    errs.append(f"{w}: observation '{m.get('observation')}' has no per-patient value rule")
        if t == "percent":
            for key in ("numerator", "denominator"):
                ref = seen.get(m.get(key))
                if not ref or ref["type"] not in ("count_patients", "count_encounters"):
                    errs.append(f"{w}: {key} must reference an earlier count measure")
        seen[m["id"]] = m
    if measures and not any(m.get("visible") for m in measures if isinstance(m, dict)):
        errs.append("no visible measure")
    if any(d.get("type") == "year" for d in dims if isinstance(d, dict)):
        if any(m.get("type") not in ("count_encounters", "percent") and not m.get("encounter")
               for m in measures if m.get("visible")):
            errs.append("year grouping is only allowed for encounter counts and encounter-level values")

    if ir.get("mode") == "spe":
        spe = ir.get("spe")
        if not isinstance(spe, dict):
            errs.append("spe section required in spe mode")
        else:
            _expr(spe.get("cohort"), concepts, errs, "spe cohort", 0)
            rts = spe.get("record_types")
            if not isinstance(rts, list) or not rts:
                errs.append("spe record_types required")
            else:
                for rt in rts:
                    if not isinstance(rt, dict) or rt.get("table") not in TABLES:
                        errs.append(f"invalid record type {rt!r}")
                    elif rt.get("loinc") is not None and not all(LOINC.match(x) for x in rt["loinc"]):
                        errs.append(f"invalid LOINC filter in record type {rt!r}")
    if errs:
        raise PlanValidationError(errs)


def _expr(e, concepts, errs, where, depth):
    if depth > 12:
        errs.append(f"{where}: expression nested too deeply")
        return
    if not isinstance(e, dict) or e.get("op") not in OPS:
        errs.append(f"{where}: invalid expression {e!r}")
        return
    op = e["op"]
    if op in ("and", "or"):
        args = e.get("args")
        if not isinstance(args, list) or not args:
            errs.append(f"{where}: '{op}' needs arguments")
            return
        for a in args:
            _expr(a, concepts, errs, where, depth + 1)
    elif op == "not":
        _expr(e.get("arg"), concepts, errs, where, depth + 1)
    elif op == "age":
        if e.get("cmp") not in CMPS or not isinstance(e.get("value"), int) or not 0 <= e["value"] <= 130:
            errs.append(f"{where}: invalid age condition {e!r}")
    elif op == "age_between":
        if not isinstance(e.get("min"), int) or not isinstance(e.get("max"), int) or e["min"] > e["max"]:
            errs.append(f"{where}: invalid age range {e!r}")
    elif op == "attr":
        if e.get("field") not in ("sex", "region", "data_holder") or not isinstance(e.get("values"), list) or \
                not e["values"] or not all(isinstance(v, str) for v in e["values"]):
            errs.append(f"{where}: invalid attribute condition {e!r}")
    elif op != "all":
        c = concepts.get(e.get("id"))
        need = {"ref": "set", "has_condition": "condition", "has_medication": "medication",
                "has_observation": "observation", "observation_value": "observation",
                "has_encounter": "encounter"}[op]
        if not c or c.get("kind") != need:
            errs.append(f"{where}: '{op}' must reference a {need} concept (got {e.get('id')!r})")
            return
        if op == "observation_value":
            if e.get("cmp") not in CMPS:
                errs.append(f"{where}: invalid comparison {e.get('cmp')!r}")
            try:
                Decimal(str(e.get("value")))
            except InvalidOperation:
                errs.append(f"{where}: invalid number {e.get('value')!r}")
            if not c.get("pick"):
                errs.append(f"{where}: observation '{e['id']}' has no per-patient value rule")
        if op == "has_medication" and not isinstance(e.get("active", False), bool):
            errs.append(f"{where}: 'active' must be true/false")
        if op == "has_encounter" and e.get("min_count") is not None and \
                (not isinstance(e["min_count"], int) or e["min_count"] < 1):
            errs.append(f"{where}: invalid min_count")


def _ref_cycles(concepts: dict, errs: list[str]) -> None:
    def refs(e, out):
        if isinstance(e, dict):
            if e.get("op") == "ref":
                out.add(e.get("id"))
            for v in e.values():
                refs(v, out)
        elif isinstance(e, list):
            for v in e:
                refs(v, out)
        return out

    graph = {cid: refs(c.get("expr"), set()) for cid, c in concepts.items() if c.get("kind") == "set"}
    state: dict[str, int] = {}

    def visit(n):
        if state.get(n) == 1:
            errs.append(f"cyclic definition involving {n}")
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in graph.get(n, ()):
            visit(m)
        state[n] = 2

    for n in graph:
        visit(n)
