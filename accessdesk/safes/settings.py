"""Per-permit DuckDB workspaces with a read-only SQL console."""
import datetime as dt
import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path

import duckdb

from ..plan.compiler import Compiler
from ..plan.model import QueryPlan

TABLE_COLUMNS = {
    "conditions": "patient_id, icd10, description, onset_date",
    "medications": "patient_id, atc, name, start_date, end_date",
    "observations": "patient_id, loinc, name, value, unit, date",
    "encounters": "encounter_id, patient_id, data_holder, type, start_date, end_date, primary_icd10",
    "patients": "patient_id, sex, birth_date, region, data_holder",
}
MAX_CONSOLE_ROWS = 200
MAX_EXPORT_ROWS = 1000
PERMIT_RE = re.compile(r"^DP-[A-Za-z0-9_-]{1,96}$")
LOINC_RE = re.compile(r"^\d{1,6}-\d$")


class ConsoleError(ValueError):
    pass


def create(request, plan, store, root, persons):
    if not isinstance(plan, QueryPlan):
        raise TypeError("SPE creation requires a validated QueryPlan")
    request_json = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    request_id = request["id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
        raise ValueError("Invalid request ID")
    permit_id = f"DP-{request_id}-{request_hash[:8]}"
    root_path = Path(root).resolve()
    folder = root_path / "spe" / permit_id
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as stream:
            return json.load(stream)

    temporary_path = folder / "workspace.duckdb.tmp"
    workspace_path = folder / "workspace.duckdb"
    temporary_path.unlink(missing_ok=True)
    workspace_path.unlink(missing_ok=True)
    compiler = Compiler(plan, store)
    cohort_sql = compiler.cohort_sql()
    with store.lock:
        store.con.execute("DROP TABLE IF EXISTS _spe_ids")
        store.con.execute(f"CREATE TEMP TABLE _spe_ids AS {cohort_sql}")
        cohort_size = store.con.execute("SELECT COUNT(*) FROM _spe_ids").fetchone()[0]
        escaped_path = temporary_path.resolve().as_posix().replace("'", "''")
        store.con.execute(f"ATTACH '{escaped_path}' AS spe")
        attached = True
        copied = []
        skipped = []
        wanted = {record.table: record for record in plan.record_types}
        try:
            store.con.execute(
                "CREATE TABLE spe.cohort (patient_id VARCHAR PRIMARY KEY)"
            )
            store.con.execute(
                "INSERT INTO spe.cohort SELECT patient_id FROM _spe_ids"
            )
            for table, columns in TABLE_COLUMNS.items():
                if table not in wanted:
                    skipped.append(table)
                    continue
                where = "patient_id IN (SELECT patient_id FROM _spe_ids)"
                note = None
                if table == "observations" and wanted[table].loinc:
                    codes = wanted[table].loinc
                    if any(not LOINC_RE.fullmatch(code) for code in codes):
                        raise ValueError("Invalid LOINC code in record-type request")
                    where += " AND loinc IN (" + ", ".join(f"'{code}'" for code in codes) + ")"
                    note = "only " + ", ".join(codes)
                store.con.execute(
                    f"CREATE TABLE spe.{table} AS SELECT {columns} FROM {table} WHERE {where}"
                )
                rows = store.con.execute(f"SELECT COUNT(*) FROM spe.{table}").fetchone()[0]
                copied.append({"table": table, "rows": rows, "note": note})
            store.con.execute("DETACH spe")
            attached = False
        finally:
            if attached:
                store.con.execute("DETACH spe")
            store.con.execute("DROP TABLE IF EXISTS _spe_ids")

    os.replace(temporary_path, workspace_path)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        issue_date = dt.date.fromisoformat(str(request.get("submitted", ""))[:10])
    except ValueError:
        issue_date = now.date()
    manifest = {
        "permit_id": permit_id,
        "request_id": request_id,
        "created": now.isoformat(),
        "expires": (issue_date + dt.timedelta(days=365)).isoformat(),
        "cohort_size": cohort_size,
        "persons_with_access": persons,
        "tables_copied": copied,
        "tables_not_copied": skipped,
        "cohort_sql": (
            "-- Cohort for the secure processing environment (opted-out patients excluded)\n"
            + cohort_sql
        ),
        "egress_rule": (
            "No download. Only aggregated results or model weights may leave, "
            "after review by the access body."
        ),
        "location": workspace_path.relative_to(root_path).as_posix(),
        "request_hash": request_hash,
    }
    with manifest_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=1)
    return manifest


def open_readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ConsoleError("SPE workspace does not exist")
    try:
        return duckdb.connect(
            str(path),
            read_only=True,
            config={
                "enable_external_access": "false",
                "autoload_known_extensions": "false",
                "autoinstall_known_extensions": "false",
                "allow_community_extensions": "false",
                "lock_configuration": "true",
            },
        )
    except duckdb.Error as exc:
        raise ConsoleError(f"Could not open SPE workspace read-only: {exc}") from exc


@contextmanager
def readonly(path):
    connection = open_readonly(path)
    try:
        yield connection
    finally:
        connection.close()


def _permit_folder(root, permit_id):
    if not PERMIT_RE.fullmatch(permit_id):
        raise ConsoleError("Invalid permit ID")
    root_path = Path(root).resolve()
    folder = (root_path / "spe" / permit_id).resolve()
    try:
        folder.relative_to(root_path / "spe")
    except ValueError as exc:
        raise ConsoleError("Invalid permit path") from exc
    return folder


def _strip_comments(sql):
    output, semicolons = [], []
    index, quote = 0, None
    while index < len(sql):
        char = sql[index]
        if quote:
            output.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    output.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            output.append(char)
        elif sql.startswith("--", index):
            output.append(" ")
            newline = sql.find("\n", index + 2)
            if newline < 0:
                break
            index = newline - 1
        elif sql.startswith("/*", index):
            output.append(" ")
            end = sql.find("*/", index + 2)
            if end < 0:
                raise ConsoleError("SQL contains an unterminated comment")
            index = end + 1
        else:
            if char == ";":
                semicolons.append(len(output))
            output.append(char)
        index += 1
    if quote:
        raise ConsoleError("SQL contains an unterminated string or identifier")
    raw = "".join(output)
    if semicolons:
        trailing = len(raw.rstrip()) - 1
        if len(semicolons) != 1 or semicolons[0] != trailing:
            raise ConsoleError("Only one SQL statement is allowed")
        raw = raw[:semicolons[0]] + raw[semicolons[0] + 1:]
    cleaned = raw.strip()
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        raise ConsoleError("Only SELECT and WITH queries are allowed")
    return cleaned


def console_query(root, permit_id, sql, limit=MAX_CONSOLE_ROWS):
    statement = _strip_comments(sql)
    try:
        limit = max(0, min(int(limit), MAX_EXPORT_ROWS))
    except (TypeError, ValueError) as exc:
        raise ConsoleError("Row limit must be an integer") from exc
    folder = _permit_folder(root, permit_id)
    manifest_path = folder / "manifest.json"
    workspace_path = folder / "workspace.duckdb"
    if not manifest_path.is_file() or not workspace_path.is_file():
        raise ConsoleError("SPE permit or workspace does not exist")
    try:
        with readonly(workspace_path) as con:
            timed_out = threading.Event()

            def interrupt():
                timed_out.set()
                try:
                    con.interrupt()
                except duckdb.Error:
                    pass

            timer = threading.Timer(5, interrupt)
            timer.daemon = True
            timer.start()
            try:
                cursor = con.execute(statement)
                rows = cursor.fetchmany(limit + 1)
                if timed_out.is_set():
                    raise ConsoleError("Query stopped after 5 s")
                truncated = len(rows) > limit
                rows = rows[:limit]
                columns = [description[0] for description in cursor.description or []]
            except ConsoleError:
                raise
            except duckdb.Error as exc:
                if timed_out.is_set():
                    raise ConsoleError("Query stopped after 5 s") from exc
                raise
            finally:
                timer.cancel()
    except ConsoleError:
        raise
    except duckdb.Error as exc:
        raise ConsoleError(f"Query rejected by the read-only SPE console: {exc}") from exc
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


def preview(root, permit_id, limit=6):
    folder = _permit_folder(root, permit_id)
    manifest_path = folder / "manifest.json"
    path = folder / "workspace.duckdb"
    if not path.exists() or not manifest_path.exists():
        return None
    with manifest_path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    tables = {}
    with readonly(path) as con:
        for record in manifest["tables_copied"]:
            table = record["table"]
            if table != "cohort" and table not in TABLE_COLUMNS:
                raise ConsoleError("Manifest names an unknown SPE table")
            cursor = con.execute(f"SELECT * FROM {table} LIMIT ?", [max(0, int(limit))])
            tables[table] = {
                "columns": [description[0] for description in cursor.description],
                "rows": cursor.fetchall(),
            }
    return {"manifest": manifest, "tables": tables}


def log_blocked_download(audit, request_id, actor="applicant", reason=None):
    audit.log(
        "download_blocked",
        request_id,
        actor,
        reason=reason or "Data may not leave the secure processing environment (Art. 73).",
    )
