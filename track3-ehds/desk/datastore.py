"""Central data store: loads the five CSV files into an in-memory SQLite database.

Opted-out patients (Art. 71) are removed at load time: their rows are never inserted into the
queryable database, so no query plan and no secure processing environment can ever contain them.
Only their pseudonymous IDs are kept in memory, for the privacy auditor.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .config import DATA_DIR

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMA = """
CREATE TABLE patients (
  patient_id TEXT PRIMARY KEY, sex TEXT NOT NULL, birth_date TEXT NOT NULL,
  birth_year INTEGER NOT NULL, region TEXT NOT NULL, data_holder TEXT NOT NULL);
CREATE TABLE conditions (
  patient_id TEXT NOT NULL REFERENCES patients(patient_id), icd10 TEXT NOT NULL,
  description TEXT, onset_date TEXT);
CREATE TABLE medications (
  patient_id TEXT NOT NULL REFERENCES patients(patient_id), atc TEXT NOT NULL, name TEXT,
  start_date TEXT, end_date TEXT);
CREATE TABLE observations (
  patient_id TEXT NOT NULL REFERENCES patients(patient_id), loinc TEXT NOT NULL, name TEXT,
  value TEXT NOT NULL, unit TEXT, date TEXT NOT NULL);
CREATE TABLE encounters (
  encounter_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  data_holder TEXT NOT NULL, type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT,
  primary_icd10 TEXT);
CREATE INDEX ix_cond ON conditions(patient_id, icd10);
CREATE INDEX ix_med ON medications(patient_id, atc);
CREATE INDEX ix_obs ON observations(patient_id, loinc, date);
CREATE INDEX ix_enc_patient ON encounters(patient_id, type, start_date);
CREATE INDEX ix_enc_type ON encounters(type, start_date);
"""

TABLE_COLUMNS = {
    "patients": ["patient_id", "sex", "birth_date", "region", "data_holder", "opted_out"],
    "conditions": ["patient_id", "icd10", "description", "onset_date"],
    "medications": ["patient_id", "atc", "name", "start_date", "end_date"],
    "observations": ["patient_id", "loinc", "name", "value", "unit", "date"],
    "encounters": ["encounter_id", "patient_id", "data_holder", "type", "start_date", "end_date",
                   "primary_icd10"],
}

# Columns of each record type as they are exposed in a secure processing environment.
RECORD_COLUMNS = {
    "patients": ["patient_id", "sex", "birth_date", "region", "data_holder"],
    "conditions": ["patient_id", "icd10", "description", "onset_date"],
    "medications": ["patient_id", "atc", "name", "start_date", "end_date"],
    "observations": ["patient_id", "loinc", "name", "value", "unit", "date"],
    "encounters": ["encounter_id", "patient_id", "data_holder", "type", "start_date", "end_date",
                   "primary_icd10"],
}


class DataError(Exception):
    pass


def _read_csv(path: Path, expected: list[str]) -> list[dict]:
    if not path.exists():
        raise DataError(f"missing data file: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in expected if c not in (reader.fieldnames or [])]
        if missing:
            raise DataError(f"{path.name}: missing columns {missing}")
        return list(reader)


def _blank_to_none(v: str):
    v = (v or "").strip()
    return v or None


class DataStore:
    def __init__(self, data_dir: Path | str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.query_log: list[dict] = []
        self.stats: dict = {}
        self.opted_out_ids: frozenset[str] = frozenset()
        self._load()

    # ------------------------------------------------------------------ loading
    def _load(self) -> None:
        d = self.data_dir
        patients = _read_csv(d / "patients.csv", TABLE_COLUMNS["patients"])
        opted_out, eligible = set(), []
        for p in patients:
            flag = p["opted_out"].strip().lower()
            if flag not in ("true", "false"):
                raise DataError(f"patients.csv: invalid opted_out value {p['opted_out']!r}")
            if not DATE_RE.match(p["birth_date"].strip()):
                raise DataError(f"patients.csv: invalid birth_date {p['birth_date']!r}")
            if flag == "true":
                opted_out.add(p["patient_id"].strip())
            else:
                eligible.append(p)
        self.opted_out_ids = frozenset(opted_out)
        eligible_ids = {p["patient_id"].strip() for p in eligible}
        stats = {"patients_total": len(patients), "patients_opted_out": len(opted_out),
                 "patients_eligible": len(eligible), "tables": {}}

        with self.lock:
            cur = self.conn.cursor()
            cur.executemany(
                "INSERT INTO patients VALUES (?,?,?,?,?,?)",
                [(p["patient_id"].strip(), p["sex"].strip().lower(), p["birth_date"].strip(),
                  int(p["birth_date"][:4]), p["region"].strip(), p["data_holder"].strip())
                 for p in eligible])
            stats["tables"]["patients"] = {"loaded": len(eligible), "excluded_opted_out": len(opted_out)}

            def load(table, rows, convert):
                kept = [convert(r) for r in rows if r["patient_id"].strip() in eligible_ids]
                unknown = [r for r in rows if r["patient_id"].strip() not in eligible_ids
                           and r["patient_id"].strip() not in opted_out]
                if unknown:
                    raise DataError(f"{table}.csv: {len(unknown)} rows reference unknown patients")
                marks = ",".join("?" * len(kept[0])) if kept else ""
                if kept:
                    cur.executemany(f"INSERT INTO {table} VALUES ({marks})", kept)
                stats["tables"][table] = {"loaded": len(kept), "excluded_opted_out": len(rows) - len(kept)}

            def obs_value(v: str) -> str:
                try:
                    Decimal(v.strip())
                except InvalidOperation as exc:
                    raise DataError(f"observations.csv: non-numeric value {v!r}") from exc
                return v.strip()

            load("conditions", _read_csv(d / "conditions.csv", TABLE_COLUMNS["conditions"]),
                 lambda r: (r["patient_id"].strip(), r["icd10"].strip().upper(), r["description"],
                            _blank_to_none(r["onset_date"])))
            load("medications", _read_csv(d / "medications.csv", TABLE_COLUMNS["medications"]),
                 lambda r: (r["patient_id"].strip(), r["atc"].strip().upper(), r["name"],
                            _blank_to_none(r["start_date"]), _blank_to_none(r["end_date"])))
            load("observations", _read_csv(d / "observations.csv", TABLE_COLUMNS["observations"]),
                 lambda r: (r["patient_id"].strip(), r["loinc"].strip(), r["name"], obs_value(r["value"]),
                            r["unit"], r["date"].strip()))
            load("encounters", _read_csv(d / "encounters.csv", TABLE_COLUMNS["encounters"]),
                 lambda r: (r["encounter_id"].strip(), r["patient_id"].strip(), r["data_holder"].strip(),
                            r["type"].strip().lower(), r["start_date"].strip(), _blank_to_none(r["end_date"]),
                            _blank_to_none((r["primary_icd10"] or "").upper())))
            self.conn.commit()
        self.stats = stats

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # ------------------------------------------------------------------ querying
    def query(self, sql: str, params: list | tuple = (), purpose: str = "") -> list[tuple]:
        """Run a parameterized, read-only query against the eligible (opted-in) data."""
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise ValueError("only read-only SELECT queries are allowed")
        with self.lock:
            rows = self.conn.execute(sql, list(params)).fetchall()
        self.query_log.append({"purpose": purpose, "rows": len(rows)})
        return rows

    def distinct_values(self, table: str, column: str) -> list[str]:
        if table not in TABLE_COLUMNS or column not in TABLE_COLUMNS[table]:
            raise ValueError("unknown column")
        rows = self.query(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY 1",
                          purpose="domain")
        return [r[0] for r in rows]

    def code_catalog(self) -> dict:
        """Codes present in the data (no patient information), used to validate interpretations."""
        return {
            "icd10": self.distinct_values("conditions", "icd10"),
            "primary_icd10": self.distinct_values("encounters", "primary_icd10"),
            "atc": self.distinct_values("medications", "atc"),
            "loinc": self.distinct_values("observations", "loinc"),
            "encounter_type": self.distinct_values("encounters", "type"),
            "region": self.distinct_values("patients", "region"),
            "data_holder": self.distinct_values("patients", "data_holder"),
            "sex": self.distinct_values("patients", "sex"),
        }


_STORE: DataStore | None = None
_STORE_LOCK = threading.Lock()


def get_store(data_dir: Path | str | None = None) -> DataStore:
    """Process-wide store for the default data directory (tests pass their own directory)."""
    global _STORE
    if data_dir is not None:
        return DataStore(data_dir)
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = DataStore(DATA_DIR)
        return _STORE
