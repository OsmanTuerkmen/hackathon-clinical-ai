"""QueryPlan -> SQL (one row per unit) -> grouped raw aggregates. Deterministic, no LLM."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from . import db
from .plan import Criterion, GroupBy, QueryPlan

_CODE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TEXT = re.compile(r"^[\w .\-äöüÄÖÜß]{1,60}$")


def _code(c: str) -> str:
    if not _CODE.match(c):
        raise ValueError(f"invalid code {c!r}")
    return c


def _date(d: str) -> str:
    if not _DATE.match(d):
        raise ValueError(f"invalid date {d!r}")
    return d


def _text(t: str) -> str:
    if not _TEXT.match(t):
        raise ValueError(f"invalid value {t!r}")
    return t.replace("'", "''")


def _prefixes(col: str, codes: list[str]) -> str:
    if not codes:
        return "true"
    return "(" + " or ".join(f"{col} like '{_code(c)}%'" for c in codes) + ")"


def _in(col: str, values: list[str]) -> str:
    return f"{col} in (" + ", ".join(f"'{_text(v)}'" for v in values) + ")"


def criterion_sql(c: Criterion, pid: str = "p.patient_id") -> str:
    if c.source == "condition":
        body = f"select 1 from hdab.conditions x where x.patient_id = {pid} and {_prefixes('x.icd10', c.codes)}"
    elif c.source == "medication":
        cond = _prefixes("x.atc", c.codes)
        if c.active_on:
            d = _date(c.active_on)
            cond += f" and x.start_date <= '{d}' and (x.end_date is null or x.end_date >= '{d}')"
        body = f"select 1 from hdab.medications x where x.patient_id = {pid} and {cond}"
    elif c.source == "observation":
        loincs = ", ".join(f"'{_code(l)}'" for l in c.codes)
        val = f" and x.value {c.value_op} {float(c.value)}" if c.value_op and c.value is not None else ""
        if c.pick == "latest":
            body = (
                f"select 1 from (select value, row_number() over (partition by loinc order by date desc) rn "
                f"from hdab.observations where patient_id = {pid} and loinc in ({loincs})) x where x.rn = 1{val}"
            )
        else:
            body = f"select 1 from hdab.observations x where x.patient_id = {pid} and x.loinc in ({loincs}){val}"
    elif c.source == "encounter":
        conds = [f"x.patient_id = {pid}"]
        if c.encounter_types:
            conds.append(_in("x.type", c.encounter_types))
        if c.codes:
            conds.append(_prefixes("x.primary_icd10", c.codes))
        if c.start_from:
            conds.append(f"x.start_date >= '{_date(c.start_from)}'")
        if c.start_to:
            conds.append(f"x.start_date <= '{_date(c.start_to)}'")
        body = "select 1 from hdab.encounters x where " + " and ".join(conds)
    else:  # pragma: no cover
        raise ValueError(c.source)
    return f"{'not ' if c.negate else ''}exists ({body})"


def _band_bounds(band: str) -> tuple[int, int | None]:
    band = band.strip()
    if band.endswith("+"):
        return int(band[:-1]), None
    lo, hi = band.split("-")
    return int(lo), int(hi)


def _band_case(bands: list[str]) -> str:
    whens = []
    for b in bands:
        lo, hi = _band_bounds(b)
        cond = f"p.age >= {lo}" + (f" and p.age <= {hi}" if hi is not None else "")
        whens.append(f"when {cond} then '{b}'")
    return "case " + " ".join(whens) + " else null end"


def _dim_sql(g: GroupBy, plan: QueryPlan) -> str:
    if g.dim == "age_band":
        return _band_case(g.bands)
    if g.dim == "data_holder" and plan.unit == "encounters":
        return "e.data_holder"
    return f"p.{g.dim}"


def population_where(plan: QueryPlan) -> list[str]:
    pop = plan.population
    w = []
    if pop.age_min is not None:
        w.append(f"p.age >= {int(pop.age_min)}")
    if pop.age_max is not None:
        w.append(f"p.age <= {int(pop.age_max)}")
    if pop.sex:
        w.append(f"p.sex = '{_text(pop.sex)}'")
    if pop.regions:
        w.append(_in("p.region", pop.regions))
    if pop.data_holders:
        w.append(_in("p.data_holder", pop.data_holders))
    w += [criterion_sql(c) for c in pop.criteria]
    for g in plan.group_by:  # units outside every requested band are not part of the question
        if g.dim == "age_band":
            w.append(f"({_band_case(g.bands)}) is not null")
    return w


def compile_sql(plan: QueryPlan) -> str:
    cols = [f"{_dim_sql(g, plan)} as g{i}" for i, g in enumerate(plan.group_by)]
    for m in plan.measures:
        if m.kind == "count":
            expr = " and ".join(criterion_sql(c) for c in m.criteria) if m.criteria else "true"
            cols.append(f"({expr}) as \"{m.name}\"")
        elif m.kind == "mean":
            cols.append(
                f"(select o.value from hdab.observations o where o.patient_id = p.patient_id "
                f"and o.loinc = '{_code(m.loinc)}' order by o.date desc limit 1) as \"{m.name}\""
            )
    where = population_where(plan)
    if plan.unit == "encounters":
        f = plan.encounter_filter
        frm = "hdab.encounters e join hdab.patients p on p.patient_id = e.patient_id"
        if f:
            if f.types:
                where.append(_in("e.type", f.types))
            if f.start_from:
                where.append(f"e.start_date >= '{_date(f.start_from)}'")
            if f.start_to:
                where.append(f"e.start_date <= '{_date(f.start_to)}'")
            if f.end_from:
                where.append(f"e.end_date >= '{_date(f.end_from)}'")
            if f.end_to:
                where.append(f"e.end_date <= '{_date(f.end_to)}'")
            if f.primary_icd10:
                where.append(_prefixes("e.primary_icd10", f.primary_icd10))
            if f.data_holders:
                where.append(_in("e.data_holder", f.data_holders))
        unit_id = "e.encounter_id"
    else:
        frm = "hdab.patients p"
        unit_id = "p.patient_id"
    sql = f"select {unit_id} as unit_id" + "".join(f",\n       {c}" for c in cols) + f"\nfrom {frm}"
    if where:
        sql += "\nwhere " + "\n  and ".join(where)
    return sql


@dataclass
class RawResult:
    """Exact, unsuppressed numbers. Never leaves the backend: only privacy.publish() output does."""

    groups: list[tuple[str, ...]]
    values: dict[tuple[str, ...], dict[str, dict]]  # group -> measure -> {"value": x, "n": .., "num": .., "den": ..}
    sql: str
    unit_count: int
    group_ids: dict = None  # group -> frozenset of unit ids (for the differencing ledger only)


def group_domains(plan: QueryPlan) -> list[tuple[str, ...]]:
    from itertools import product

    domains = [tuple(g.bands) if g.dim == "age_band" else db.domain(g.dim) for g in plan.group_by]
    return list(product(*domains)) if domains else [()]


def run(plan: QueryPlan) -> RawResult:
    sql = compile_sql(plan)
    df: pd.DataFrame = db.query(sql)
    gcols = [f"g{i}" for i in range(len(plan.group_by))]
    groups = group_domains(plan)
    out: dict[tuple[str, ...], dict[str, dict]] = {}
    ids: dict[tuple[str, ...], frozenset] = {}
    grouped = {k if isinstance(k, tuple) else (k,): v for k, v in df.groupby(gcols, dropna=True)} if gcols else {(): df}
    for g in groups:
        sub = grouped.get(g, df.iloc[0:0])
        ids[g] = frozenset(sub["unit_id"].tolist())
        res: dict[str, dict] = {}
        for m in plan.measures:
            if m.kind == "count":
                n = int(len(sub)) if not m.criteria else int(sub[m.name].astype(bool).sum())
                res[m.name] = {"kind": "count", "value": n}
            elif m.kind == "mean":
                vals = sub[m.name].dropna()
                res[m.name] = {"kind": "mean", "value": float(vals.mean()) if len(vals) else None, "n": int(len(vals))}
        for m in plan.measures:
            if m.kind == "pct":
                num, den = res[m.numerator]["value"], res[m.denominator]["value"]
                res[m.name] = {"kind": "pct", "value": (100.0 * num / den) if den else None, "num": num, "den": den}
        out[g] = {m.name: res[m.name] for m in plan.measures}
    return RawResult(groups=groups, values=out, sql=sql, unit_count=int(len(df)), group_ids=ids)


def cohort_ids(plan: QueryPlan) -> list[str]:
    """Patient IDs selected by the plan's population (used for SPE)."""
    where = population_where(plan)
    sql = "select p.patient_id from hdab.patients p" + (" where " + " and ".join(where) if where else "") + " order by 1"
    return db.query(sql)["patient_id"].tolist()
