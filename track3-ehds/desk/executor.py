"""Compile a validated IR into parameterized SQL and compute released statistics.

1. Every atom used by the plan (condition / medication / observation / encounter filters) becomes one
   column of a single parameterized SELECT over the eligible patients (opted-out patients are not in
   the database at all). Encounter counts use a second parameterized SELECT.
2. Boolean expressions, grouping and aggregation are evaluated in Python with exact arithmetic.
3. Released cells go through disclosure.py; raw counts stay in the separate `Internal` object, which
   is only used by the privacy auditor and never serialised to a client.
"""
from __future__ import annotations

import itertools
import operator
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

from . import disclosure as D
from .config import REFERENCE_DATE, REFERENCE_YEAR
from .datastore import DataStore

CMP = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "=": operator.eq}
DIM_LABELS = {"region": "Region", "age_band": "Age band", "sex": "Sex", "data_holder": "Hospital (data holder)",
              "year": "Year"}
PICK_ORDER = {"latest": "o.date DESC", "earliest": "o.date ASC",
              "highest": "CAST(o.value AS REAL) DESC, o.date DESC", "lowest": "CAST(o.value AS REAL) ASC, o.date DESC"}


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@dataclass
class Internal:
    """Unreleased numbers, kept server-side for the privacy auditor only."""
    cells: list[dict] = field(default_factory=list)
    contributors: dict[str, set] = field(default_factory=dict)
    population_size: int = 0
    encounter_patients: dict[str, dict] = field(default_factory=dict)


class Executor:
    def __init__(self, store: DataStore, ir: dict):
        self.store = store
        self.ir = ir
        self.concepts = ir["concepts"]
        self.atoms: dict[tuple, dict] = {}
        self.sql: list[dict] = []
        self.active_date = (ir.get("active_rule") or {}).get("date") or REFERENCE_DATE
        self._rows: list[dict] | None = None

    # ------------------------------------------------------------------ atom collection
    def _collect(self, e: dict) -> None:
        op = e.get("op")
        if op in ("and", "or"):
            for a in e["args"]:
                self._collect(a)
        elif op == "not":
            self._collect(e["arg"])
        elif op == "ref":
            self._collect(self.concepts[e["id"]]["expr"])
        elif op == "has_condition":
            self._atom(("cond", e["id"]))
        elif op == "has_medication":
            self._atom(("med", e["id"], bool(e.get("active"))))
        elif op == "has_observation":
            self._atom(("obs_has", e["id"]))
        elif op == "observation_value":
            self._atom(("obs_val", e["id"]))
        elif op == "has_encounter":
            self._atom(("enc", e["id"]))

    def _atom(self, key: tuple) -> None:
        if key in self.atoms:
            return
        col = f"a{len(self.atoms) + 1}"
        kind, cid = key[0], key[1]
        c = self.concepts[cid]
        params: list = []
        if kind == "cond":
            clause, params = self._icd_clause("c.icd10", c["icd10"])
            sql = f"EXISTS (SELECT 1 FROM conditions c WHERE c.patient_id = p.patient_id AND {clause}"
            if c.get("onset_from"):
                sql += " AND c.onset_date >= ?"
                params.append(c["onset_from"])
            if c.get("onset_to"):
                sql += " AND c.onset_date <= ?"
                params.append(c["onset_to"])
            sql += ")"
        elif kind == "med":
            clause = " OR ".join("m.atc LIKE ? ESCAPE '\\'" for _ in c["atc"])
            params = [_like(a) for a in c["atc"]]
            sql = f"EXISTS (SELECT 1 FROM medications m WHERE m.patient_id = p.patient_id AND ({clause})"
            if key[2]:
                sql += " AND m.start_date <= ? AND (m.end_date IS NULL OR m.end_date >= ?)"
                params += [self.active_date, self.active_date]
            if c.get("start_from"):
                sql += " AND m.start_date >= ?"
                params.append(c["start_from"])
            if c.get("start_to"):
                sql += " AND m.start_date <= ?"
                params.append(c["start_to"])
            sql += ")"
        elif kind == "obs_has":
            sql = "EXISTS (SELECT 1 FROM observations o WHERE o.patient_id = p.patient_id AND o.loinc = ?)"
            params = [c["loinc"]]
        elif kind == "obs_val":
            order = PICK_ORDER[c["pick"]]
            sql = (f"(SELECT o.value FROM observations o WHERE o.patient_id = p.patient_id AND o.loinc = ? "
                   f"ORDER BY {order}, o.rowid DESC LIMIT 1)")
            params = [c["loinc"]]
        elif kind == "enc":
            where, params = self._encounter_where(c)
            sql = f"(SELECT COUNT(*) FROM encounters e WHERE e.patient_id = p.patient_id AND {where})"
        else:
            raise ValueError(kind)
        self.atoms[key] = {"col": col, "sql": sql, "params": params}

    @staticmethod
    def _icd_clause(column: str, items: list[dict]) -> tuple[str, list]:
        parts, params = [], []
        for it in items:
            if it["match"] == "prefix":
                parts.append(f"{column} LIKE ? ESCAPE '\\'")
                params.append(_like(it["code"]))
            else:
                parts.append(f"({column} = ? OR {column} LIKE ? ESCAPE '\\')")
                params += [it["code"], _like(it["code"] + ".")]
        return "(" + " OR ".join(parts) + ")", params

    def _encounter_where(self, c: dict) -> tuple[str, list]:
        types = c["types"]
        where = [f"e.type IN ({','.join('?' * len(types))})"]
        params: list = list(types)
        if c.get("start_from"):
            where.append("e.start_date >= ?")
            params.append(c["start_from"])
        if c.get("start_to"):
            where.append("e.start_date <= ?")
            params.append(c["start_to"])
        if c.get("primary_icd10"):
            clause, p = self._icd_clause("e.primary_icd10", [{"code": x, "match": "prefix"}
                                                             for x in c["primary_icd10"]])
            where.append(clause)
            params += p
        if c.get("data_holders"):
            where.append(f"e.data_holder IN ({','.join('?' * len(c['data_holders']))})")
            params += list(c["data_holders"])
        return " AND ".join(where), params

    # ------------------------------------------------------------------ patient features
    def patient_rows(self, exprs: list[dict]) -> list[dict]:
        for e in exprs:
            self._collect(e)
        cols = ["p.patient_id", "p.sex", "p.region", "p.data_holder", "? - p.birth_year AS age"]
        params: list = [REFERENCE_YEAR]
        for a in self.atoms.values():
            cols.append(f"{a['sql']} AS {a['col']}")
            params += a["params"]
        sql = "SELECT " + ",\n       ".join(cols) + "\nFROM patients p\nORDER BY p.patient_id"
        rows = self.store.query(sql, params, purpose="patient features")
        self.sql.append({"purpose": "Per-patient features (opted-out patients are not in the database)",
                         "sql": sql, "params": params, "rows": len(rows)})
        names = ["patient_id", "sex", "region", "data_holder", "age"] + [a["col"] for a in self.atoms.values()]
        self._rows = [dict(zip(names, r)) for r in rows]
        return self._rows

    def ev(self, e: dict, row: dict) -> bool:
        op = e["op"]
        if op == "all":
            return True
        if op == "and":
            return all(self.ev(a, row) for a in e["args"])
        if op == "or":
            return any(self.ev(a, row) for a in e["args"])
        if op == "not":
            return not self.ev(e["arg"], row)
        if op == "age":
            return CMP[e["cmp"]](row["age"], e["value"])
        if op == "age_between":
            return e["min"] <= row["age"] <= e["max"]
        if op == "attr":
            return row[e["field"]] in e["values"]
        if op == "ref":
            return self.ev(self.concepts[e["id"]]["expr"], row)
        if op == "has_condition":
            return row[self.atoms[("cond", e["id"])]["col"]] == 1
        if op == "has_medication":
            return row[self.atoms[("med", e["id"], bool(e.get("active")))]["col"]] == 1
        if op == "has_observation":
            return row[self.atoms[("obs_has", e["id"])]["col"]] == 1
        if op == "observation_value":
            v = row[self.atoms[("obs_val", e["id"])]["col"]]
            return v is not None and CMP[e["cmp"]](D.to_fraction(v), D.to_fraction(str(e["value"])))
        if op == "has_encounter":
            return row[self.atoms[("enc", e["id"])]["col"]] >= int(e.get("min_count") or 1)
        raise ValueError(op)

    def value(self, cid: str, row: dict) -> Fraction | None:
        v = row[self.atoms[("obs_val", cid)]["col"]]
        return None if v is None else D.to_fraction(v)

    # ------------------------------------------------------------------ grouping
    def _groups(self, dims: list[dict]) -> list[tuple]:
        lists = []
        for d in dims:
            if d["type"] == "age_band":
                lists.append([g["label"] for g in d["groups"]])
            else:
                lists.append(list(d["groups"]))
        return list(itertools.product(*lists)) if lists else [()]

    @staticmethod
    def _band(age: int, bands: list[dict]):
        for b in bands:
            if age >= b["min"] and (b["max"] is None or age <= b["max"]):
                return b["label"]
        return None

    def _key(self, dims: list[dict], prow: dict, enc: dict | None = None):
        key = []
        for d in dims:
            t = d["type"]
            if t == "age_band":
                k = self._band(prow["age"], d["groups"])
            elif t == "data_holder" and enc is not None:
                k = enc["data_holder"]
            elif t == "year":
                k = enc["year"] if enc is not None else None
            else:
                k = prow[t]
            if k is None:
                return None
            key.append(k)
        return tuple(key)

    # ------------------------------------------------------------------ statistics
    def run_statistics(self) -> tuple[dict, Internal]:
        ir = self.ir
        measures = ir["measures"]
        for d in ir["dimensions"]:
            if d["type"] == "year" and not d["groups"]:
                d["groups"] = self._years(measures)  # resolved on the plan itself so the auditor sees them
        dims = ir["dimensions"]
        exprs = [ir["population"]] + [m["set"] for m in measures if "set" in m]
        for m in measures:
            if m["type"] in ("mean", "median"):
                self._atom(("obs_val", m["observation"]))
        rows = self.patient_rows(exprs)
        groups = self._groups(dims)
        gindex = {g: i for i, g in enumerate(groups)}
        internal = Internal()
        counts = {m["id"]: [0] * len(groups) for m in measures if m["type"].startswith("count")}
        values = {m["id"]: [[] for _ in groups] for m in measures if m["type"] in ("mean", "median")}
        contributors = {m["id"]: set() for m in measures if m["type"] != "percent"}
        pop_rows = [r for r in rows if self.ev(ir["population"], r)]
        internal.population_size = len(pop_rows)
        by_id = {r["patient_id"]: r for r in pop_rows}

        pmeasures = [m for m in measures if m["type"] in ("count_patients", "mean", "median")]
        for r in pop_rows:
            k = self._key(dims, r)
            if k is None or k not in gindex:
                continue
            gi = gindex[k]
            for m in pmeasures:
                if not self.ev(m["set"], r):
                    continue
                if m["type"] == "count_patients":
                    counts[m["id"]][gi] += 1
                    contributors[m["id"]].add(r["patient_id"])
                else:
                    v = self.value(m["observation"], r)
                    if v is not None:
                        values[m["id"]][gi].append(v)
                        contributors[m["id"]].add(r["patient_id"])

        for m in measures:
            if m["type"] != "count_encounters":
                continue
            c = self.concepts[m["encounter"]]
            where, params = self._encounter_where(c)
            sql = ("SELECT e.encounter_id, e.patient_id, e.data_holder, substr(e.start_date, 1, 4) AS year\n"
                   f"FROM encounters e\nWHERE {where}\nORDER BY e.encounter_id")
            enc_rows = self.store.query(sql, params, purpose="encounters")
            self.sql.append({"purpose": f"Encounters for '{m['label']}'", "sql": sql, "params": params,
                             "rows": len(enc_rows)})
            distinct = [set() for _ in groups]
            for encounter_id, pid, holder, year in enc_rows:
                r = by_id.get(pid)
                if r is None or not self.ev(m["set"], r):
                    continue
                k = self._key(dims, r, {"data_holder": holder, "year": year})
                if k is None or k not in gindex:
                    continue
                counts[m["id"]][gindex[k]] += 1
                distinct[gindex[k]].add(pid)
                contributors[m["id"]].add(pid)
            internal.encounter_patients[m["id"]] = {"distinct_patients": [len(s) for s in distinct]}

        visible = [m for m in measures if m.get("visible")]
        out_rows = []
        for gi, g in enumerate(groups):
            cells, raw = {}, {}
            for m in measures:
                mid, t = m["id"], m["type"]
                if t.startswith("count"):
                    n = counts[mid][gi]
                    raw[mid] = {"n": n}
                    released = n if m.get("exact") else D.count_cell(n)
                elif t == "percent":
                    num, den = counts[m["numerator"]][gi], counts[m["denominator"]][gi]
                    raw[mid] = {"numerator": num, "denominator": den}
                    released = D.percent_cell(num, den)
                else:
                    vals = values[mid][gi]
                    raw[mid] = {"n": len(vals), "sum": str(sum(vals, Fraction(0)))}
                    released = D.mean_cell(vals) if t == "mean" else D.median_cell(vals)
                if m.get("visible"):
                    cells[mid] = released
            out_rows.append({"group": list(g), "label": " · ".join(str(x) for x in g) if g else "All patients",
                             "cells": cells})
            internal.cells.append({"group": list(g), "raw": raw})
        internal.contributors = contributors
        result = {
            "kind": "statistics",
            "dimensions": [{"type": d["type"], "label": DIM_LABELS[d["type"]]} for d in dims],
            "columns": [{"id": m["id"], "label": m["label"],
                         "type": "count" if m["type"].startswith("count") else m["type"],
                         "unit": "encounters" if m["type"] == "count_encounters" else "patients"}
                        for m in visible],
            "rows": out_rows,
        }
        return result, internal

    def _years(self, measures: list[dict]) -> list[str]:
        lo, hi = None, None
        for m in measures:
            if m["type"] == "count_encounters":
                c = self.concepts[m["encounter"]]
                lo = c.get("start_from") or lo
                hi = c.get("start_to") or hi
        years = [y for (y,) in self.store.query("SELECT DISTINCT substr(start_date, 1, 4) FROM encounters ORDER BY 1",
                                                purpose="domain")]
        return [y for y in years if (lo is None or y >= lo[:4]) and (hi is None or y <= hi[:4])]

    # ------------------------------------------------------------------ cohorts (SPE)
    def cohort_ids(self, cohort: dict) -> list[str]:
        exprs = [self.ir["population"], cohort]
        rows = self.patient_rows(exprs)
        return [r["patient_id"] for r in rows if self.ev(self.ir["population"], r) and self.ev(cohort, r)]


def released_json(result: dict) -> dict:
    """JSON-safe copy of a released statistics table (Decimals -> numbers)."""
    out = dict(result)
    out["rows"] = [{**r, "cells": {k: D.json_value(v) for k, v in r["cells"].items()}} for r in result["rows"]]
    return out


def display_value(v) -> str:
    if isinstance(v, Decimal):
        return f"{v:.1f}"
    return str(v)
