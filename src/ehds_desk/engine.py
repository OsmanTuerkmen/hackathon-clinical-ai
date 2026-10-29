"""Execute compiled queries against the Database and build typed raw tables."""

from __future__ import annotations

from decimal import Decimal

from .compiler import CompiledQuery, Scope, compile_cohort, compile_statistics
from .data import Database
from .models import (
    CountMetric,
    MeanMetric,
    PercentMetric,
    QuerySpec,
    RawCount,
    RawMean,
    RawPercent,
    RawRow,
    RawTable,
)


def run_statistics(spec: QuerySpec, db: Database) -> tuple[RawTable, CompiledQuery]:
    """Raw (unsuppressed, unrounded) cells for every metric and every group of the domain."""
    query = compile_statistics(spec, data_holders=db.data_holders)
    rows_sql = db.cursor().execute(query.sql, query.params).fetchall()
    n_dims = len(query.dimensions)
    rows: list[RawRow] = []
    for record in rows_sql:
        group = {kind: str(record[i]) for i, kind in enumerate(query.dimensions)}
        pos = n_dims
        counts: dict[str, int] = {}
        cells: dict[str, RawCount | RawPercent | RawMean] = {}
        for metric in spec.metrics:
            if isinstance(metric, CountMetric):
                cells[metric.name] = RawCount(n=int(record[pos]))
                counts[metric.name] = int(record[pos])
                pos += 1
            elif isinstance(metric, MeanMetric):
                cells[metric.name] = RawMean(total=Decimal(record[pos]), n=int(record[pos + 1]))
                pos += 2
        for metric in spec.metrics:
            if isinstance(metric, PercentMetric):
                cells[metric.name] = RawPercent(num=counts[metric.numerator], den=counts[metric.denominator])
        rows.append(RawRow(group=group, cells={m.name: cells[m.name] for m in spec.metrics}))
    table = RawTable(dimensions=list(query.dimensions), metrics=list(spec.metrics), rows=rows)
    return table, query


def cohort_patient_ids(spec: QuerySpec, db: Database, scope: Scope = "consented") -> list[str]:
    query = compile_cohort(spec, scope=scope)
    return [r[0] for r in db.cursor().execute(query.sql, query.params).fetchall()]


def opt_out_exclusions(spec: QuerySpec, db: Database) -> int:
    """Patients of the population that exist in the full data but are hidden by opt-out."""
    everyone = len(cohort_patient_ids(spec, db, scope="all"))
    consented = len(cohort_patient_ids(spec, db, scope="consented"))
    return everyone - consented
