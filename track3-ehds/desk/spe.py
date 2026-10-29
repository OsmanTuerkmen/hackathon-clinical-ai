"""Secure processing environment (SPE): one isolated SQLite database per data permit.

Only the selected (opted-in) patients and only the record types named in the application are copied
in, with their pseudonymous patient IDs. The workspace is never served over HTTP; every download
attempt is refused with HTTP 403 and written to the access log (Art. 73(1)(e), 73(2)).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sqlite3
import threading
from pathlib import Path

from .config import SPE_DIR
from .datastore import RECORD_COLUMNS, DataStore

WORKSPACE_RE = re.compile(r"^spe-[0-9a-f]{12}$")
ORDER = {"patients": "t.patient_id", "conditions": "t.patient_id, t.onset_date, t.icd10",
         "medications": "t.patient_id, t.start_date, t.atc", "observations": "t.patient_id, t.loinc, t.date",
         "encounters": "t.patient_id, t.start_date, t.encounter_id"}
BLOCK_MESSAGE = ("Download blocked. Under the data permit, pseudonymised records can only be processed inside the "
                 "secure processing environment (Art. 73). Only non-personal results, such as anonymised statistics "
                 "or model weights, may leave it after review by the health data access body (Art. 73(2)).")


ANALYSES = {("conditions", "icd10"), ("medications", "atc"), ("observations", "loinc"), ("encounters", "type"),
            ("encounters", "primary_icd10"), ("encounters", "data_holder"), ("patients", "sex"), ("patients", "region"),
            ("patients", "data_holder")}


class SPEManager:
    def __init__(self, store: DataStore, base_dir: Path | str = SPE_DIR):
        self.store = store
        self.base = Path(base_dir)
        self.lock = threading.RLock()
        self.log_file = self.base / "access_log.jsonl"
        self.access_log: list[dict] = []
        if self.log_file.exists():  # the access log survives restarts (Art. 73(1)(e))
            for line in self.log_file.read_text(encoding="utf-8").splitlines():
                try:
                    self.access_log.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def workspace_id(request: dict) -> str:
        keys = ("requested_as", "requested_format", "purpose", "question", "definitions")
        canonical = json.dumps({k: request.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
        return "spe-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def path(self, wid: str) -> Path:
        if not WORKSPACE_RE.match(wid or ""):
            raise KeyError("invalid workspace id")
        return self.base / wid

    def build(self, request: dict, record_types: list[dict], cohort_ids: list[str], permit: dict) -> dict:
        wid = self.workspace_id(request)
        wdir = self.path(wid)
        with self.lock:
            if wdir.exists():
                shutil.rmtree(wdir)
            wdir.mkdir(parents=True)
            db = wdir / "workspace.sqlite"
            with self.store.lock:
                conn = self.store.conn
                conn.execute("ATTACH DATABASE ? AS spe", (str(db),))
                try:
                    conn.execute("CREATE TABLE spe.cohort (patient_id TEXT PRIMARY KEY)")
                    conn.executemany("INSERT INTO spe.cohort VALUES (?)", [(pid,) for pid in sorted(cohort_ids)])
                    for rt in record_types:
                        table = rt["table"]
                        cols = ", ".join(f"t.{c}" for c in RECORD_COLUMNS[table])
                        where, params = "t.patient_id IN (SELECT patient_id FROM spe.cohort)", []
                        if table == "observations" and rt.get("loinc"):
                            where += f" AND t.loinc IN ({','.join('?' * len(rt['loinc']))})"
                            params += list(rt["loinc"])
                        conn.execute(f"CREATE TABLE spe.{table} AS SELECT {cols} FROM main.{table} t "
                                     f"WHERE {where} ORDER BY {ORDER[table]}", params)
                    conn.commit()
                finally:
                    conn.execute("DETACH DATABASE spe")
            tables = {}
            ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                for rt in record_types:
                    t = rt["table"]
                    rows = ro.execute(f"SELECT COUNT(*), COUNT(DISTINCT patient_id) FROM {t}").fetchone()
                    tables[t] = {"rows": rows[0], "patients": rows[1], "columns": RECORD_COLUMNS[t],
                                 "filter": ({"loinc": rt["loinc"]} if rt.get("loinc") else None)}
            finally:
                ro.close()
            token = secrets.token_urlsafe(18)
            manifest = {
                "workspace_id": wid,
                "request_id": request.get("id"),
                "permit": permit,
                "permit_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "cohort_size": len(cohort_ids),
                "tables": tables,
                "storage": f"spe_workspaces/{wid}/workspace.sqlite (isolated database, one per permit)",
                "pseudonymisation": "patient IDs are the pseudonyms used by the data holders; no names or contact data",
                "download_policy": "blocked",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
            (wdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(wid, "workspace_created", "ok", f"{len(cohort_ids)} patients, tables {sorted(tables)}")
        return {**manifest, "permit_token": token}

    def manifest(self, wid: str) -> dict:
        p = self.path(wid) / "manifest.json"
        if not p.exists():
            raise KeyError("unknown workspace")
        return json.loads(p.read_text(encoding="utf-8"))

    def log(self, wid: str, action: str, result: str, detail: str = "", actor: str = "system") -> dict:
        entry = {"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "workspace_id": wid,
                 "actor": actor, "action": action, "result": result, "detail": detail}
        with self.lock:
            self.access_log.append(entry)
            self.base.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def analyse(self, wid: str, token: str | None, table: str, column: str) -> tuple[int, dict]:
        """Aggregate analysis inside the SPE by the permit holder; the output passes the small-cell rule and is the
        only kind of result that may leave the environment (Art. 73(2))."""
        manifest = self.manifest(wid)
        if not token or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),
                                                manifest.get("permit_token_sha256", "")):
            self.log(wid, f"analysis:{table}.{column}", "DENIED", "missing or invalid permit token", "unknown")
            return 401, {"error": "permit_token_required",
                         "message": "Only the holder of the data permit can work inside this environment (Art. 73(1)(a))."}
        if (table, column) not in ANALYSES or table not in manifest["tables"]:
            return 400, {"error": "analysis_not_allowed", "message": f"{table}.{column} is not available in this SPE.",
                         "allowed": sorted(f"{t}.{c}" for t, c in ANALYSES if t in manifest["tables"])}
        from . import disclosure as D
        ro = sqlite3.connect(f"file:{self.path(wid) / 'workspace.sqlite'}?mode=ro", uri=True)
        try:
            rows = ro.execute(f"SELECT {column}, COUNT(DISTINCT patient_id) FROM {table} WHERE {column} IS NOT NULL "
                              f"GROUP BY {column} ORDER BY {column}").fetchall()
        finally:
            ro.close()
        out = [{"value": v, "patients": D.count_cell(n)} for v, n in rows]
        masked = sum(1 for r in out if r["patients"] == D.LT10)
        self.log(wid, f"analysis:{table}.{column}", "ok", f"{len(out)} groups, {masked} masked", "permit holder")
        return 200, {"table": table, "column": column, "rows": out,
                     "note": "Aggregated inside the SPE; counts below 10 are shown as <10. This output passed the "
                             "disclosure check and may be exported."}

    def request_download(self, wid: str, table: str | None = None, actor: str = "applicant") -> tuple[int, dict]:
        """Every record download is refused; the attempt is logged."""
        self.manifest(wid)
        entry = self.log(wid, "download_records" + (f":{table}" if table else ""), "BLOCKED", BLOCK_MESSAGE, actor)
        return 403, {"error": "download_blocked", "status": 403, "message": BLOCK_MESSAGE, "logged": entry}

    def log_for(self, wid: str) -> list[dict]:
        return [e for e in self.access_log if e["workspace_id"] == wid]
