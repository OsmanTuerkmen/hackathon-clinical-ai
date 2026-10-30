"""Loads the Track 3 CSVs into an in-memory DuckDB analysis database."""
import re
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import duckdb

REFERENCE_DATE = "2025-12-31"
REFERENCE_YEAR = 2025
REGIONS = [
    "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg",
    "Steiermark", "Tirol", "Vorarlberg", "Wien",
]

SCHEMAS = {
    "patients": {
        "patient_id": "VARCHAR", "sex": "VARCHAR", "birth_date": "DATE",
        "region": "VARCHAR", "data_holder": "VARCHAR", "opted_out": "BOOLEAN",
    },
    "conditions": {
        "patient_id": "VARCHAR", "icd10": "VARCHAR", "description": "VARCHAR",
        "onset_date": "DATE",
    },
    "medications": {
        "patient_id": "VARCHAR", "atc": "VARCHAR", "name": "VARCHAR",
        "start_date": "DATE", "end_date": "DATE",
    },
    "observations": {
        "patient_id": "VARCHAR", "loinc": "VARCHAR", "name": "VARCHAR",
        "value": "VARCHAR", "unit": "VARCHAR", "date": "DATE",
    },
    "encounters": {
        "encounter_id": "VARCHAR", "patient_id": "VARCHAR", "data_holder": "VARCHAR",
        "type": "VARCHAR", "start_date": "DATE", "end_date": "DATE",
        "primary_icd10": "VARCHAR",
    },
}
VALUE_RE = re.compile(r"-?\d+(?:\.\d)?$")


@dataclass
class Store:
    con: duckdb.DuckDBPyConnection
    data_dir: str
    total_patients: int
    opted_out: int
    opted_ids: frozenset
    domains: dict = field(default_factory=dict)
    descriptions: dict = field(default_factory=dict)
    patient_bits: dict = field(default_factory=dict)
    encounter_bits: dict = field(default_factory=dict)
    load_seconds: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock)


def _columns(schema):
    return "{" + ", ".join(f"'{name}': '{kind}'" for name, kind in schema.items()) + "}"


def _tenths(value):
    value = str(value).strip()
    if not VALUE_RE.fullmatch(value):
        raise ValueError(f"Invalid observation value: {value!r}")
    return int(Decimal(value) * 10)


def load(data_dir):
    started = time.perf_counter()
    data_dir = Path(data_dir).resolve()
    con = duckdb.connect()
    lock = threading.RLock()
    with lock:
        for table, schema in SCHEMAS.items():
            path = str(data_dir / f"{table}.csv").replace("'", "''")
            con.execute(
                f"CREATE TEMP TABLE _source_{table} AS "
                f"SELECT * FROM read_csv('{path}', columns={_columns(schema)}, "
                "header=true, encoding='utf-8', dateformat='%Y-%m-%d', nullstr='')"
            )

        total_patients, opted_out = con.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE opted_out) FROM _source_patients"
        ).fetchone()
        opted_ids = frozenset(
            row[0] for row in con.execute(
                "SELECT patient_id FROM _source_patients WHERE opted_out"
            ).fetchall()
        )
        con.execute(
            "CREATE TABLE patients AS SELECT patient_id, sex, birth_date, "
            "year(birth_date)::INTEGER AS birth_year, "
            f"{REFERENCE_YEAR} - year(birth_date)::INTEGER AS age, region, data_holder, "
            "false AS opted_out FROM _source_patients WHERE NOT opted_out"
        )
        con.execute(
            "CREATE TABLE conditions AS SELECT s.patient_id, s.icd10, s.description, s.onset_date "
            "FROM _source_conditions s JOIN patients p USING (patient_id)"
        )
        con.execute(
            "CREATE TABLE medications AS SELECT s.patient_id, s.atc, s.name, s.start_date, s.end_date "
            "FROM _source_medications s JOIN patients p USING (patient_id)"
        )
        observation_rows = con.execute(
            "SELECT s.patient_id, s.loinc, s.name, s.value, s.unit, s.date "
            "FROM _source_observations s JOIN patients p USING (patient_id)"
        ).fetchall()
        for row in observation_rows:
            _tenths(row[3])
        con.execute(
            "CREATE TABLE observations AS "
            "SELECT s.patient_id, s.loinc, s.name, s.value, "
            "CAST(CAST(trim(s.value) AS DECIMAL(38, 1)) * 10 AS INTEGER) AS value10, "
            "s.unit, s.date "
            "FROM _source_observations s JOIN patients p USING (patient_id)"
        )
        con.execute(
            "CREATE TABLE encounters AS SELECT s.encounter_id, s.patient_id, s.data_holder, s.type, "
            "s.start_date, s.end_date, s.primary_icd10, "
            "date_diff('day', s.start_date, s.end_date)::INTEGER AS los_days "
            "FROM _source_encounters s JOIN patients p USING (patient_id)"
        )
        con.execute("CREATE INDEX ix_conditions_patient ON conditions(patient_id)")
        con.execute("CREATE INDEX ix_conditions_icd10 ON conditions(icd10)")
        con.execute("CREATE INDEX ix_medications_patient ON medications(patient_id)")
        con.execute("CREATE INDEX ix_medications_atc ON medications(atc)")
        con.execute("CREATE INDEX ix_observations_patient_loinc_date ON observations(patient_id, loinc, date)")
        con.execute("CREATE INDEX ix_encounters_patient ON encounters(patient_id)")
        patient_bits = {
            patient_id: bit
            for bit, (patient_id,) in enumerate(
                con.execute("SELECT patient_id FROM patients ORDER BY patient_id").fetchall()
            )
        }
        encounter_bits = {
            encounter_id: bit
            for bit, (encounter_id,) in enumerate(
                con.execute("SELECT encounter_id FROM encounters ORDER BY encounter_id").fetchall()
            )
        }

        descriptions = {}
        for code, description in con.execute(
            "SELECT icd10, description FROM _source_conditions"
        ).fetchall():
            descriptions.setdefault(("icd10", code), description)
        for (code,) in con.execute(
            "SELECT DISTINCT primary_icd10 FROM _source_encounters WHERE primary_icd10 IS NOT NULL"
        ).fetchall():
            descriptions.setdefault(("icd10", code), None)
        for code, name in con.execute("SELECT atc, name FROM _source_medications").fetchall():
            descriptions.setdefault(("atc", code), name)
        for code, name in con.execute("SELECT loinc, name FROM _source_observations").fetchall():
            descriptions.setdefault(("loinc", code), name)

        regions = [row[0] for row in con.execute("SELECT DISTINCT region FROM _source_patients").fetchall()]
        holders = {row[0] for row in con.execute("SELECT DISTINCT data_holder FROM _source_patients").fetchall()}
        holders.update(row[0] for row in con.execute("SELECT DISTINCT data_holder FROM _source_encounters").fetchall())
        domains = {
            "region": REGIONS + sorted(set(regions) - set(REGIONS)),
            "data_holder": sorted(holders),
            "sex": ["female", "male"],
            "encounter_type": sorted(row[0] for row in con.execute(
                "SELECT DISTINCT type FROM _source_encounters"
            ).fetchall()),
        }
        for table in SCHEMAS:
            con.execute(f"DROP TABLE _source_{table}")
    return Store(
        con=con,
        data_dir=str(data_dir),
        total_patients=total_patients,
        opted_out=opted_out,
        opted_ids=opted_ids,
        domains=domains,
        descriptions=descriptions,
        patient_bits=patient_bits,
        encounter_bits=encounter_bits,
        load_seconds=round(time.perf_counter() - started, 2),
        lock=lock,
    )


def codes_in_data(store, system):
    return sorted(code for system_name, code in store.descriptions if system_name == system)
