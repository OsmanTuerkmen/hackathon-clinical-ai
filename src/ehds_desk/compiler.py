"""Compile a typed QuerySpec into parameterised DuckDB SQL.

Every value that originates from a request (codes, dates, labels, domain values) is bound as a
positional ``?`` parameter. Only fixed identifiers (view names from a whitelist, generated column
aliases) are written into the SQL text. Parameters are collected in the exact textual order in
which their placeholders appear.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .config import REFERENCE_DATE
from .data import REGIONS, SEXES
from .models import (
    AgeCriterion,
    CodeSet,
    ConditionCriterion,
    CountMetric,
    DataHolderCriterion,
    Dimension,
    EncounterCriterion,
    MeanMetric,
    MedicationCriterion,
    ObservationCriterion,
    QuerySpec,
    RegionCriterion,
    SexCriterion,
)

Scope = Literal["consented", "all"]

_VIEWS = frozenset({"pat", "cond", "med", "obs", "enc"})


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: list[Any]
    dimensions: list[str]


class _Ctx:
    """Collects parameters and resolves view names for one compilation."""

    def __init__(self, scope: Scope):
        if scope not in ("consented", "all"):
            raise ValueError(f"unknown scope: {scope!r}")
        self.scope = scope
        self.params: list[Any] = []

    def view(self, name: str) -> str:
        if name not in _VIEWS:
            raise ValueError(f"unknown view: {name!r}")
        return f"{name}_all" if self.scope == "all" else name

    def p(self, value: Any) -> str:
        self.params.append(value)
        return "?"

    def text(self, value: str) -> str:
        """A VARCHAR parameter with an explicit type (needed inside CASE / VALUES)."""
        self.params.append(value)
        return "CAST(? AS VARCHAR)"


@dataclass(frozen=True)
class _Cols:
    """How to reference the patient columns of the current row source."""

    alias: str
    holder: str  # column holding the patient's data holder

    def __getitem__(self, column: str) -> str:
        return f"{self.alias}.{self.holder if column == 'data_holder' else column}"


def _prefix_match(ctx: _Ctx, column: str, codes: CodeSet) -> str:
    return "(" + " OR ".join(f"starts_with({column}, {ctx.p(prefix)})" for prefix in codes.prefixes) + ")"


def _in_list(ctx: _Ctx, column: str, values: list[str]) -> str:
    if not values:
        return "FALSE"
    return f"{column} IN ({', '.join(ctx.p(v) for v in values)})"


def _exists(ctx: _Ctx, view: str, cols: _Cols, conditions: list[str], negate: bool) -> str:
    where = " AND ".join([f"x.patient_id = {cols['patient_id']}", *conditions])
    return f"{'NOT ' if negate else ''}EXISTS (SELECT 1 FROM {ctx.view(view)} x WHERE {where})"


def _criterion_sql(ctx: _Ctx, crit: Any, cols: _Cols) -> str:
    if isinstance(crit, AgeCriterion):
        parts = []
        if crit.min is not None:
            parts.append(f"{cols['age']} >= {ctx.p(crit.min)}")
        if crit.max is not None:
            parts.append(f"{cols['age']} <= {ctx.p(crit.max)}")
        return "(" + " AND ".join(parts) + ")" if parts else "TRUE"
    if isinstance(crit, SexCriterion):
        return f"{cols['sex']} = {ctx.p(crit.value)}"
    if isinstance(crit, RegionCriterion):
        return _in_list(ctx, cols["region"], crit.values)
    if isinstance(crit, DataHolderCriterion):
        return _in_list(ctx, cols["data_holder"], crit.values)
    if isinstance(crit, ConditionCriterion):
        return _exists(ctx, "cond", cols, [_prefix_match(ctx, "x.icd10", crit.codes)], crit.negate)
    if isinstance(crit, MedicationCriterion):
        conds = [_prefix_match(ctx, "x.atc", crit.codes)]
        if crit.active_only:
            ref = REFERENCE_DATE
            conds.append(
                f"x.start_date <= {ctx.p(ref)} AND (x.end_date IS NULL OR x.end_date >= {ctx.p(ref)})"
            )
        return _exists(ctx, "med", cols, conds, crit.negate)
    if isinstance(crit, ObservationCriterion):
        return _exists(ctx, "obs", cols, [_prefix_match(ctx, "x.loinc", crit.codes)], crit.negate)
    if isinstance(crit, EncounterCriterion):
        conds = _encounter_filters(
            ctx, "x", crit.types, crit.start_from, crit.start_to, crit.primary_icd10, []
        )
        return _exists(ctx, "enc", cols, conds, crit.negate)
    raise TypeError(f"unsupported criterion: {type(crit).__name__}")


def _encounter_filters(ctx, alias, types, start_from, start_to, primary_icd10, data_holders) -> list[str]:
    conds: list[str] = []
    if types:
        conds.append(_in_list(ctx, f"{alias}.type", list(types)))
    if start_from is not None:
        conds.append(f"{alias}.start_date >= {ctx.p(start_from)}")
    if start_to is not None:
        conds.append(f"{alias}.start_date <= {ctx.p(start_to)}")
    if primary_icd10 is not None:
        conds.append(_prefix_match(ctx, f"{alias}.primary_icd10", primary_icd10))
    if data_holders:
        conds.append(_in_list(ctx, f"{alias}.data_holder", list(data_holders)))
    return conds


def _conjunction(ctx: _Ctx, criteria: list[Any], cols: _Cols) -> list[str]:
    return [_criterion_sql(ctx, c, cols) for c in criteria]


# --- Row source (units) -------------------------------------------------------


def _source(ctx: _Ctx, spec: QuerySpec) -> tuple[str, str]:
    """FROM clause and the encounter alias holding the unit's data holder."""
    if spec.unit == "encounter":
        return f"FROM {ctx.view('enc')} e JOIN {ctx.view('pat')} p ON e.patient_id = p.patient_id", "e"
    return f"FROM {ctx.view('pat')} p", "p"


def _where_clause(ctx: _Ctx, spec: QuerySpec) -> str:
    conds: list[str] = []
    if spec.unit == "encounter":
        scope = spec.encounter_scope
        assert scope is not None
        conds += _encounter_filters(ctx, "e", scope.types, scope.start_from, scope.start_to, scope.primary_icd10, scope.data_holders)
    cols = _Cols("p", "data_holder")
    conds += _conjunction(ctx, spec.population, cols)
    for dim in spec.group_by:
        if dim.kind == "age_band":
            bands = [AgeCriterion(kind="age", min=b.min, max=b.max) for b in dim.bands]
            conds.append("(" + " OR ".join(_criterion_sql(ctx, band, cols) for band in bands) + ")")
    return f"WHERE {' AND '.join(conds)}" if conds else ""


# --- Statistics -----------------------------------------------------------------


def _dim_expr(ctx: _Ctx, dim: Dimension, holder_alias: str) -> str:
    if dim.kind == "region":
        return "p.region"
    if dim.kind == "sex":
        return "p.sex"
    if dim.kind == "data_holder":
        return f"{holder_alias}.data_holder"
    whens = []
    for band in dim.bands:
        cond = f"p.age >= {ctx.p(band.min)}"
        if band.max is not None:
            cond += f" AND p.age <= {ctx.p(band.max)}"
        whens.append(f"WHEN {cond} THEN {ctx.text(band.label)}")
    return f"CASE {' '.join(whens)} END"


def _domain_values(dim: Dimension, data_holders: tuple[str, ...]) -> list[str]:
    if dim.kind == "region":
        return list(REGIONS)
    if dim.kind == "sex":
        return list(SEXES)
    if dim.kind == "data_holder":
        return list(data_holders)
    return [b.label for b in dim.bands]


def compile_statistics(
    spec: QuerySpec, *, data_holders: tuple[str, ...], scope: Scope = "consented"
) -> CompiledQuery:
    """SQL returning, per group of the cartesian domain: dims, then c_k per count metric and
    s_i, n_i per mean metric, in metric order. Percent metrics are derived by the engine."""
    ctx = _Ctx(scope)
    dims = spec.group_by
    from_sql, holder_alias = _source(ctx, spec)
    dim_names = [f"d_{i}" for i in range(len(dims))]

    # units CTE (parameter order: select list, then where)
    select = ["p.patient_id", "p.age", "p.sex", "p.region", "p.data_holder AS patient_holder"]
    select += [f"{_dim_expr(ctx, d, holder_alias)} AS {name}" for d, name in zip(dims, dim_names)]
    units = f"units AS (SELECT {', '.join(select)} {from_sql} {_where_clause(ctx, spec)})"

    ctes = [units]
    means = [(i, m) for i, m in enumerate(spec.metrics) if isinstance(m, MeanMetric)]
    for i, m in means:
        ctes.append(
            f"latest_{i} AS (SELECT patient_id, arg_max(value, date) AS v FROM {ctx.view('obs')} "
            f"WHERE {_prefix_match(ctx, 'loinc', m.codes)} GROUP BY patient_id)"
        )

    # agg CTE
    agg_cols = list(dim_names)
    final_cols: list[str] = []
    unit_cols = _Cols("units", "patient_holder")
    for i, m in enumerate(spec.metrics):
        if isinstance(m, CountMetric):
            if m.where:
                cond = " AND ".join(_conjunction(ctx, m.where, unit_cols))
                agg_cols.append(f"count(*) FILTER (WHERE {cond}) AS c_{i}")
            else:
                agg_cols.append(f"count(*) AS c_{i}")
            final_cols.append(f"coalesce(c_{i}, 0) AS c_{i}")
        elif isinstance(m, MeanMetric):
            agg_cols.append(f"sum(l_{i}.v) AS s_{i}")
            agg_cols.append(f"count(l_{i}.v) AS n_{i}")
            final_cols += [f"coalesce(s_{i}, 0) AS s_{i}", f"coalesce(n_{i}, 0) AS n_{i}"]
    joins = " ".join(f"LEFT JOIN latest_{i} l_{i} ON l_{i}.patient_id = units.patient_id" for i, _ in means)
    group = f" GROUP BY {', '.join(dim_names)}" if dims else ""
    if not agg_cols:
        agg_cols = ["count(*) AS _n"]
    ctes.append(f"agg AS (SELECT {', '.join(agg_cols)} FROM units {joins}{group})")

    if not dims:
        sql = f"WITH {', '.join(ctes)} SELECT {', '.join(final_cols) or '1 AS _n'} FROM agg"
        return CompiledQuery(sql=sql, params=ctx.params, dimensions=[])

    # domain CTE: cartesian product of the dimension domains with an ordering column each
    parts, ord_cols = [], []
    for i, (d, name) in enumerate(zip(dims, dim_names)):
        values = _domain_values(d, data_holders)
        rows = ", ".join(f"({ctx.text(v)}, {j})" for j, v in enumerate(values)) or "(CAST(NULL AS VARCHAR), 0)"
        parts.append(f"(VALUES {rows}) t{i}({name}, o_{i})")
        ord_cols.append(f"o_{i}")
    ctes.append(f"domain AS (SELECT * FROM {' CROSS JOIN '.join(parts)})")

    on = " AND ".join(f"domain.{n} = agg.{n}" for n in dim_names)
    sel = [f"domain.{n}" for n in dim_names] + final_cols
    order = ", ".join(f"domain.{o}" for o in ord_cols)
    sql = (
        f"WITH {', '.join(ctes)} SELECT {', '.join(sel)} FROM domain "
        f"LEFT JOIN agg ON {on} ORDER BY {order}"
    )
    return CompiledQuery(sql=sql, params=ctx.params, dimensions=[d.kind for d in dims])


def compile_cohort(spec: QuerySpec, *, scope: Scope = "consented") -> CompiledQuery:
    """Distinct, sorted patient ids of the population (for unit=encounter: of the scoped encounters)."""
    ctx = _Ctx(scope)
    from_sql, _ = _source(ctx, spec)
    sql = f"SELECT DISTINCT p.patient_id AS patient_id {from_sql} {_where_clause(ctx, spec)} ORDER BY patient_id"
    return CompiledQuery(sql=sql, params=ctx.params, dimensions=[])
