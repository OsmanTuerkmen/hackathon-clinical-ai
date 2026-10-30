"""Secure processing environment (SPE): isolated copy of the permitted records, blocked downloads, audit log.

Each permit gets its own directory ``<var_dir>/spe/<permit_id>/`` with

* ``spe.duckdb``    - separate DuckDB file with ``cohort`` and the requested record types,
* ``manifest.json`` - tables, row counts, exact patient count, articles (no timestamps: reproducible),
* ``audit.jsonl``   - append-only audit trail (Art. 73(1)(e)).

Rows are copied from the opt-out-filtered views, so patients who opted out (Art. 71) never enter an SPE.
Pseudonymised records may not leave the SPE (Art. 73(2)): every download attempt is refused and audited.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict

from .data import Database
from .engine import cohort_patient_ids
from .models import AccessRequest, QuerySpec

ARTICLES: list[str] = ["53", "66", "68", "73", "71"]
PREVIEW_MAX_ROWS = 20

_PERMIT_ID = re.compile(r"[A-Za-z0-9_-]+")
_COHORT_TMP = "spe_cohort_tmp"

# Whitelisted table -> source SELECT on the opt-out-filtered views (never the *_all views).
# `patients` omits opted_out (always false here) and the computed age column.
_SOURCES: dict[str, str] = {
    "patients": "SELECT patient_id, sex, birth_date, region, data_holder FROM pat",
    "conditions": "SELECT * FROM cond",
    "medications": "SELECT * FROM med",
    "observations": "SELECT * FROM obs",
    "encounters": "SELECT * FROM enc",
}
TABLE_WHITELIST: frozenset[str] = frozenset({"cohort", *_SOURCES})

_audit_lock = threading.Lock()
_provision_lock = threading.Lock()  # ATTACH aliases and files are instance-wide: provision one SPE at a time


class SpeNotFound(Exception):
    """No SPE has been provisioned for this permit."""


class InvalidPermitId(ValueError):
    """The permit id contains characters outside [A-Za-z0-9_-]."""


class SpeManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    permit_id: str
    request_id: str
    patient_count: int
    tables: dict[str, int]
    record_types: list[str]
    observation_codes: list[str]
    articles: list[str]


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: str
    permit_id: str
    actor: str
    action: Literal["provisioned", "preview", "download_blocked"]
    table: str | None
    detail: str


# --- paths and ids -----------------------------------------------------------


def permit_id_for(request: AccessRequest) -> str:
    """`<request id>-<8 hex of the request hash>`; identical requests always map to the same permit."""
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", request.id) or "request"
    return f"{safe_id}-{digest}"


def _check_permit_id(permit_id: str) -> str:
    if not isinstance(permit_id, str) or not _PERMIT_ID.fullmatch(permit_id):
        raise InvalidPermitId("permit id may only contain letters, digits, '_' and '-'")
    return permit_id


def _permit_dir(permit_id: str, var_dir: Path) -> Path:
    return Path(var_dir) / "spe" / _check_permit_id(permit_id)


def _check_table(manifest: SpeManifest, table: str) -> str:
    if table not in TABLE_WHITELIST:
        raise ValueError(f"unknown table '{table}'")
    if table not in manifest.tables:
        raise ValueError(f"table '{table}' is not part of this secure processing environment")
    return table


# --- audit -------------------------------------------------------------------


def _log(
    permit_id: str,
    var_dir: Path,
    action: Literal["provisioned", "preview", "download_blocked"],
    table: str | None,
    detail: str,
    actor: str = "applicant",
) -> AuditEvent:
    event = AuditEvent(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        permit_id=permit_id,
        actor=actor,
        action=action,
        table=table,
        detail=detail,
    )
    path = _permit_dir(permit_id, var_dir) / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _audit_lock, path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(event.model_dump_json() + "\n")
    return event


def audit_log(permit_id: str, var_dir: Path) -> list[AuditEvent]:
    path = _permit_dir(permit_id, var_dir) / "audit.jsonl"
    if not path.exists():
        return []
    with _audit_lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    return [AuditEvent.model_validate_json(line) for line in lines if line.strip()]


# --- provisioning ------------------------------------------------------------


def provision_spe(request: AccessRequest, spec: QuerySpec, db: Database, var_dir: Path) -> SpeManifest:
    """(Re-)create the SPE of this request: cohort plus the requested record types, no opted-out patients.

    Serialised by a module-level lock: ATTACH/DETACH act on the shared in-memory database, and the
    same permit must not be rebuilt by two threads at once.
    """
    permit_id = permit_id_for(request)
    directory = _permit_dir(permit_id, var_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with _provision_lock:
        manifest = _provision_locked(request, spec, db, permit_id, directory)
    _log(
        permit_id,
        var_dir,
        "provisioned",
        None,
        f"Secure processing environment provisioned for request {request.id}: {manifest.patient_count} patients, "
        f"tables {', '.join(manifest.tables)}.",
        actor="system",
    )
    return manifest


def _provision_locked(
    request: AccessRequest, spec: QuerySpec, db: Database, permit_id: str, directory: Path
) -> SpeManifest:
    db_file = directory / "spe.duckdb"
    # Remove the old SPE and its manifest first: a failed run must not leave a manifest that
    # describes a missing or half-built database. The audit log is deliberately kept.
    for stale in (db_file, directory / "spe.duckdb.wal", directory / "manifest.json"):
        stale.unlink(missing_ok=True)

    patient_ids = cohort_patient_ids(spec, db)
    record_types = list(dict.fromkeys(spec.record_types))
    observation_codes = list(spec.observation_codes.prefixes) if spec.observation_codes else []
    alias = "spe_" + uuid.uuid4().hex  # unique per call; ATTACH is instance-wide

    counts: dict[str, int] = {}
    con = db.cursor()
    try:
        con.execute(f"CREATE TEMP TABLE {_COHORT_TMP} (patient_id VARCHAR)")
        if patient_ids:
            con.executemany(f"INSERT INTO {_COHORT_TMP} VALUES (?)", [[pid] for pid in patient_ids])
        # Defence in depth: only patients visible in the opt-out-filtered view may enter the SPE.
        consented = f"patient_id IN (SELECT patient_id FROM pat) AND patient_id IN (SELECT patient_id FROM {_COHORT_TMP})"
        attach_path = str(db_file).replace("'", "''")
        con.execute(f"ATTACH '{attach_path}' AS {alias}")
        try:
            con.execute(f"CREATE TABLE {alias}.cohort AS SELECT patient_id FROM {_COHORT_TMP} WHERE patient_id IN (SELECT patient_id FROM pat) ORDER BY patient_id")
            counts["cohort"] = con.execute(f"SELECT count(*) FROM {alias}.cohort").fetchone()[0]
            for table in record_types:
                # `table` is validated by the QuerySpec Literal and looked up in the _SOURCES whitelist.
                sql = f"CREATE TABLE {alias}.{table} AS {_SOURCES[table]} WHERE {consented}"
                params: list[str] = []
                if table == "observations" and observation_codes:
                    sql += " AND (" + " OR ".join("starts_with(loinc, ?)" for _ in observation_codes) + ")"
                    params = observation_codes
                con.execute(sql, params)
                counts[table] = con.execute(f"SELECT count(*) FROM {alias}.{table}").fetchone()[0]
        finally:
            con.execute(f"DETACH {alias}")  # release the file lock (Windows)
    finally:
        try:
            con.execute(f"DROP TABLE IF EXISTS {_COHORT_TMP}")
        finally:
            con.close()

    manifest = SpeManifest(
        permit_id=permit_id,
        request_id=request.id,
        patient_count=counts["cohort"],
        tables=counts,
        record_types=record_types,
        observation_codes=observation_codes,
        articles=list(ARTICLES),
    )
    (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def load_manifest(permit_id: str, var_dir: Path) -> SpeManifest:
    path = _permit_dir(permit_id, var_dir) / "manifest.json"
    if not path.exists():
        raise SpeNotFound(f"no secure processing environment for permit '{permit_id}'")
    return SpeManifest.model_validate_json(path.read_text(encoding="utf-8"))


# --- access inside the SPE ---------------------------------------------------


def preview(permit_id: str, table: str, var_dir: Path, limit: int = PREVIEW_MAX_ROWS) -> list[dict]:
    """First rows of one SPE table (at most 20), read through a separate read-only connection."""
    manifest = load_manifest(permit_id, var_dir)
    _check_table(manifest, table)
    limit = max(0, min(int(limit), PREVIEW_MAX_ROWS))
    con = duckdb.connect(str(_permit_dir(permit_id, var_dir) / "spe.duckdb"), read_only=True)
    try:
        # `table` is whitelisted and present in the manifest; `limit` is a clamped int.
        cur = con.execute(f'SELECT * FROM "{table}" ORDER BY ALL LIMIT {limit}')
        columns = [d[0] for d in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        con.close()
    _log(permit_id, var_dir, "preview", table, f"Previewed {len(rows)} rows of table '{table}' inside the workspace.")
    return rows


def attempt_download(permit_id: str, table: str, var_dir: Path, actor: str = "applicant") -> AuditEvent:
    """Every download is refused (Art. 73(2)); the attempt is audited. Never returns data."""
    manifest = load_manifest(permit_id, var_dir)
    try:
        _check_table(manifest, table)
    except ValueError:
        # An attempt to fetch an unknown table is still a download attempt: audit it, then refuse.
        shown = table if table in TABLE_WHITELIST else None
        label = f"table '{shown}'" if shown else "an unknown table"
        _log(
            permit_id,
            var_dir,
            "download_blocked",
            shown,
            f"Download of {label} blocked: it is not part of this secure processing environment, and "
            f"pseudonymised records may not leave it (Art. 73(2)).",
            actor=actor,
        )
        raise
    return _log(
        permit_id,
        var_dir,
        "download_blocked",
        table,
        f"Download of table '{table}' blocked: pseudonymised records may not leave the secure processing "
        f"environment (Art. 73(2)).",
        actor=actor,
    )
