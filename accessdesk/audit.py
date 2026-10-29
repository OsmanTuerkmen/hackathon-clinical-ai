"""Append-only hash-chained audit log."""
import datetime as dt
import hashlib
import json
import os
import threading

GENESIS = "0" * 64


def _canonical(entry):
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _digest(entry):
    return hashlib.sha256(_canonical(entry)).hexdigest()


class Audit:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._seq, self._prev = 0, GENESIS
        if os.path.exists(path):
            with open(path, encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    self._seq, self._prev = entry["seq"], entry["hash"]

    def log(self, action, request_id=None, actor="system", **details):
        with self._lock:
            entry = {
                "seq": self._seq + 1,
                "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
                "actor": actor,
                "action": action,
                "request_id": request_id,
                "details": details,
                "prev": self._prev,
            }
            entry["hash"] = _digest(entry)
            with open(self.path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._seq, self._prev = entry["seq"], entry["hash"]
            return entry

    def tail(self, n=200):
        if n <= 0 or not os.path.exists(self.path):
            return []
        with self._lock, open(self.path, encoding="utf-8") as stream:
            entries = [json.loads(line) for line in stream if line.strip()]
        return list(reversed(entries[-n:]))

    def verify(self):
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "first_bad_seq": None, "reason": None}
        with self._lock, open(self.path, encoding="utf-8") as stream:
            lines = [line for line in stream if line.strip()]
        previous, expected_seq = GENESIS, 1
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return {
                    "ok": False, "entries": len(lines), "first_bad_seq": expected_seq,
                    "reason": "invalid JSON",
                }
            seq = entry.get("seq")
            if seq != expected_seq:
                return {
                    "ok": False, "entries": len(lines), "first_bad_seq": seq,
                    "reason": f"sequence mismatch: expected {expected_seq}, found {seq}",
                }
            if entry.get("prev") != previous:
                return {
                    "ok": False, "entries": len(lines), "first_bad_seq": seq,
                    "reason": "previous hash mismatch",
                }
            supplied_hash = entry.get("hash")
            unhashed = {key: value for key, value in entry.items() if key != "hash"}
            if supplied_hash != _digest(unhashed):
                return {
                    "ok": False, "entries": len(lines), "first_bad_seq": seq,
                    "reason": "entry hash mismatch",
                }
            previous = supplied_hash
            expected_seq += 1
        return {"ok": True, "entries": len(lines), "first_bad_seq": None, "reason": None}
