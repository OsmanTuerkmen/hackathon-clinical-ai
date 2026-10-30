"""DuckDB access. Opted-out patients (Art. 71) are removed at the lowest layer so no query can see them."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EHDS_DATA_DIR", ROOT / "track" / "data"))
REFERENCE_DATE = "2025-12-31"
TABLES = ["patients", "conditions", "medications", "observations", "encounters"]


@lru_cache(maxsize=1)
def connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("create schema raw")
    for t in TABLES:
        con.execute(f"create table raw.{t} as select * from read_csv('{DATA_DIR / (t + '.csv')}', all_varchar=true, header=true)")
    con.execute("create schema hdab")
    con.execute(
        f"""create view hdab.patients as
            select patient_id, sex, birth_date, region, data_holder,
                   {REFERENCE_DATE[:4]} - cast(substr(birth_date, 1, 4) as integer) as age
            from raw.patients where opted_out <> 'true'"""
    )
    keep = "patient_id in (select patient_id from hdab.patients)"
    con.execute(f"create view hdab.conditions as select * from raw.conditions where {keep}")
    con.execute(
        f"""create view hdab.medications as
            select patient_id, atc, name, start_date, nullif(end_date, '') as end_date
            from raw.medications where {keep}"""
    )
    con.execute(
        f"""create view hdab.observations as
            select patient_id, loinc, name, cast(value as double) as value, unit, date
            from raw.observations where {keep}"""
    )
    con.execute(
        f"""create view hdab.encounters as
            select encounter_id, patient_id, data_holder, type, start_date, end_date,
                   nullif(primary_icd10, '') as primary_icd10
            from raw.encounters where {keep}"""
    )
    return con


def query(sql: str, params: list | None = None):
    cur = connection().cursor()
    return cur.execute(sql, params or []).fetchdf()


@lru_cache(maxsize=None)
def domain(dim: str) -> tuple[str, ...]:
    """All values a group dimension can take, so empty groups are still reported."""
    col = {"region": "region", "data_holder": "data_holder", "sex": "sex"}[dim]
    df = query(f"select distinct {col} v from hdab.patients order by 1")
    return tuple(df["v"].tolist())
