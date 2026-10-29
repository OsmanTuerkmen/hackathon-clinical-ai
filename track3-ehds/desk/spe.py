"""Secure processing environment (SPE): one isolated SQLite database per data permit.

Only the selected (opted-in) patients and only the record types named in the application are copied
in, with their pseudonymous patient IDs. The workspace is never served over HTTP; every download
attempt is refused with HTTP 403 and written to the access log (Art. 73(1)(e), 73(2)).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
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


class SPEManager:
    def __init__(self, store: DataStore, base_dir: Path | str = SPE_DIR):
        self.store = store
        self.base = Path(base_dir)
        self.access_log: list[dict] = []
        self._lock = threading.Lock()

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
        with self._lock:
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
            manifest = {
                "workspace_id": wid,
                "request_id": request.get("id"),
                "permit": permit,
                "cohort_size": len(cohort_ids),
                "tables": tables,
                "storage": f"spe_workspaces/{wid}/workspace.sqlite (isolated database, one per permit)",
                "pseudonymisation": "patient IDs are the pseudonyms used by the data holders; no names or contact data",
                "download_policy": "blocked",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            }
            (wdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(wid, "workspace_created", "ok", f"{len(cohort_ids)} patients, tables {sorted(tables)}")
        return manifest

    def manifest(self, wid: str) -> dict:
        p = self.path(wid) / "manifest.json"
        if not p.exists():
            raise KeyError("unknown workspace")
        return json.loads(p.read_text(encoding="utf-8"))

    def log(self, wid: str, action: str, result: str, detail: str = "", actor: str = "system") -> dict:
        entry = {"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "workspace_id": wid,
                 "actor": actor, "action": action, "result": result, "detail": detail}
        self.access_log.append(entry)
        return entry

    def request_download(self, wid: str, table: str | None = None, actor: str = "applicant") -> tuple[int, dict]:
        """Every record download is refused; the attempt is logged."""
        self.manifest(wid)
        entry = self.log(wid, "download_records" + (f":{table}" if table else ""), "BLOCKED", BLOCK_MESSAGE, actor)
        return 403, {"error": "download_blocked", "status": 403, "message": BLOCK_MESSAGE, "logged": entry}

    def log_for(self, wid: str) -> list[dict]:
        return [e for e in self.access_log if e["workspace_id"] == wid]
