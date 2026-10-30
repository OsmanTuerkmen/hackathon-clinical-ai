"""Secure processing environment: a separate DuckDB file per permit holding only the selected patients and record types."""
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb

from . import db
from .compiler import _prefixes, cohort_ids
from .plan import QueryPlan

SPE_DIR = Path(__file__).resolve().parents[2] / "spe"
CODE_COL = {"conditions": "icd10", "medications": "atc", "observations": "loinc", "encounters": "primary_icd10"}


def create(request_id: str, plan: QueryPlan) -> dict:
    SPE_DIR.mkdir(exist_ok=True)
    path = SPE_DIR / f"{request_id}.duckdb"
    path.unlink(missing_ok=True)
    ids = cohort_ids(plan)
    src = db.connection().cursor()
    src.execute("create or replace temp table spe_cohort (patient_id varchar)")
    src.executemany("insert into spe_cohort values (?)", [[i] for i in ids])
    out = duckdb.connect(str(path))
    copied = {}
    tables = {r.table: r for r in plan.spe_records} or {"patients": None}
    tables.setdefault("patients", None)
    for table, rec in tables.items():
        where = "patient_id in (select patient_id from spe_cohort)"
        if rec is not None and rec.codes and table in CODE_COL:
            col = CODE_COL[table]
            where += " and " + (f"{col} in ({', '.join(repr(c) for c in rec.codes)})" if table == "observations" else _prefixes(col, rec.codes))
        df = src.execute(f"select * from hdab.{table} where {where}").fetchdf()
        out.register("df", df)
        out.execute(f"create table {table} as select * from df")
        out.unregister("df")
        copied[table] = len(df)
    out.close()
    manifest = {"request_id": request_id, "cohort_size": len(ids), "tables": copied, "created": time.time(), "download": "blocked"}
    (SPE_DIR / f"{request_id}.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def manifest(request_id: str) -> dict | None:
    p = SPE_DIR / f"{request_id}.json"
    return json.loads(p.read_text()) if p.exists() else None
