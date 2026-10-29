"""DuckDB data layer: typed CSV import and opt-out-filtered views.

Views without the ``_all`` suffix contain only patients who did NOT opt out (Art. 71).
Only the staff metric "opt-out exclusions" may use the ``*_all`` views.
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from .config import REFERENCE_DATE, Settings, load_settings

REGIONS: tuple[str, ...] = (
    "Burgenland",
    "Kärnten",
    "Niederösterreich",
    "Oberösterreich",
    "Salzburg",
    "Steiermark",
    "Tirol",
    "Vorarlberg",
    "Wien",
)
SEXES: tuple[str, ...] = ("female", "male")

# table -> (csv file, DuckDB column types). Order must match the CSV header.
_TABLES: dict[str, tuple[str, dict[str, str]]] = {
    "raw_patients": (
        "patients.csv",
        {
            "patient_id": "VARCHAR",
            "sex": "VARCHAR",
            "birth_date": "DATE",
            "region": "VARCHAR",
            "data_holder": "VARCHAR",
            "opted_out": "BOOLEAN",
        },
    ),
    "raw_conditions": (
        "conditions.csv",
        {
            "patient_id": "VARCHAR",
            "icd10": "VARCHAR",
            "description": "VARCHAR",
            "onset_date": "DATE",
        },
    ),
    "raw_medications": (
        "medications.csv",
        {
            "patient_id": "VARCHAR",
            "atc": "VARCHAR",
            "name": "VARCHAR",
            "start_date": "DATE",
            "end_date": "DATE",
        },
    ),
    "raw_observations": (
        "observations.csv",
        {
            "patient_id": "VARCHAR",
            "loinc": "VARCHAR",
            "name": "VARCHAR",
            "value": "DECIMAL(10,2)",
            "unit": "VARCHAR",
            "date": "DATE",
        },
    ),
    "raw_encounters": (
        "encounters.csv",
        {
            "encounter_id": "VARCHAR",
            "patient_id": "VARCHAR",
            "data_holder": "VARCHAR",
            "type": "VARCHAR",
            "start_date": "DATE",
            "end_date": "DATE",
            "primary_icd10": "VARCHAR",
        },
    ),
}

# child view name -> raw table (all child views are semi-joined to consented patients)
_CHILDREN = {
    "cond": "raw_conditions",
    "med": "raw_medications",
    "obs": "raw_observations",
    "enc": "raw_encounters",
}


class Database:
    """In-memory DuckDB holding the typed tables and the opt-out views."""

    def __init__(self, data_dir: Path):
        self._con = duckdb.connect(":memory:")
        self._lock = threading.Lock()
        csv_dir = Path(data_dir) / "data"
        for table, (filename, columns) in _TABLES.items():
            self._load_csv(table, csv_dir / filename, columns)
        self._create_views()
        self.data_holders: tuple[str, ...] = tuple(
            r[0]
            for r in self._con.execute(
                "SELECT DISTINCT data_holder FROM raw_patients ORDER BY data_holder"
            ).fetchall()
        )

    def _load_csv(self, table: str, path: Path, columns: dict[str, str]) -> None:
        # DuckDB opens non-ASCII Windows paths (e.g. "ü") fine; nothing is copied to disk.
        # Empty fields (end_date, primary_icd10) are read as NULL.
        # `table` and the column types come from the _TABLES constant, never from user input.
        rel = self._con.read_csv(
            str(path),
            header=True,
            columns=columns,
            date_format="%Y-%m-%d",
        )
        self._con.register("_csv_stage", rel)
        try:
            self._con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _csv_stage')
        finally:
            self._con.unregister("_csv_stage")

    def _create_views(self) -> None:
        con = self._con
        # REFERENCE_DATE.year is an int constant from config, not user input.
        con.execute(
            f"CREATE VIEW pat_all AS SELECT *, "
            f"{int(REFERENCE_DATE.year)} - CAST(year(birth_date) AS INTEGER) AS age "
            f"FROM raw_patients"
        )
        con.execute("CREATE VIEW pat AS SELECT * FROM pat_all WHERE NOT opted_out")
        for view, raw in _CHILDREN.items():
            con.execute(f"CREATE VIEW {view}_all AS SELECT * FROM {raw}")
            con.execute(
                f"CREATE VIEW {view} AS SELECT * FROM {raw} "
                f"WHERE patient_id IN (SELECT patient_id FROM pat)"
            )

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """A thread-safe cursor on the shared in-memory database."""
        with self._lock:
            return self._con.cursor()


_dbs: dict[Path, Database] = {}
_db_lock = threading.Lock()


def get_database(settings: Settings | None = None) -> Database:
    """Process-wide Database, cached per resolved data directory."""
    data_dir = Path((settings or load_settings()).data_dir).resolve()
    with _db_lock:
        if data_dir not in _dbs:
            _dbs[data_dir] = Database(data_dir)
        return _dbs[data_dir]
