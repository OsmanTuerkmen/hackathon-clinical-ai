"""Append-only, hash-chained audit log (JSONL). Tampering with an entry breaks every later hash."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "cache" / "audit.jsonl"
_lock = threading.Lock()
_last_hash = "genesis"


def _init():
    global _last_hash
    if LOG.exists():
        lines = LOG.read_text().strip().splitlines()
        if lines:
            _last_hash = json.loads(lines[-1])["hash"]


def log(event: str, request_id: str | None = None, actor: str = "system", detail: str = "", **extra) -> dict:
    global _last_hash
    with _lock:
        if _last_hash == "genesis":
            _init()
        entry = {"id": "aud_" + uuid.uuid4().hex[:8], "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                 "event": event, "request_id": request_id, "actor": actor, "detail": detail, **extra, "prev": _last_hash}
        entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _last_hash = entry["hash"]
        return entry


def for_request(request_id: str) -> list[dict]:
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        e = json.loads(line)
        if e.get("request_id") == request_id:
            out.append(e)
    return out


def verify_chain() -> bool:
    if not LOG.exists():
        return True
    prev = None
    for line in LOG.read_text().splitlines():
        e = json.loads(line)
        h = e.pop("hash")
        if prev is not None and e["prev"] != prev:
            return False
        if hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16] != h:
            return False
        prev = h
    return True

