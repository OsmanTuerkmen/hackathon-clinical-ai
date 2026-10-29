"""Persistent export submissions and staff decisions."""
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .safes.outputs import check_export


class ExportConflict(ValueError):
    pass


class ExportRegistry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / "exports.json"
        self._lock = threading.RLock()
        if self.path.exists():
            with self.path.open(encoding="utf-8") as stream:
                self._exports = json.load(stream)
        else:
            self._exports = []
        ids = [
            int(match.group(1))
            for record in self._exports
            if (match := re.fullmatch(r"X(\d+)", record.get("id", "")))
        ]
        self._next_id = max(ids, default=0) + 1

    def list(self, status=None, permit_id=None):
        with self._lock:
            records = list(self._exports)
        if status:
            records = [record for record in records if record["status"] == status]
        if permit_id:
            records = [record for record in records if record["permit_id"] == permit_id]
        return list(reversed(records))

    def get(self, export_id):
        with self._lock:
            return next((record for record in self._exports if record["id"] == export_id), None)

    def create(
        self, permit_id, request_id, title, note, sql, columns, rows, requested_by,
        truncated=False,
    ):
        with self._lock:
            check_rows = [*rows, *([[]] if truncated else [])]
            record = {
                "id": f"X{self._next_id:02d}",
                "permit_id": permit_id,
                "request_id": request_id,
                "title": title,
                "note": note,
                "sql": sql,
                "columns": list(columns),
                "rows": [list(row) for row in rows],
                "created": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "requested_by": requested_by,
                "check": check_export(columns, check_rows),
                "status": "pending_review",
            }
            if record["check"]["result"] == "fail":
                record["status"] = "rejected_auto"
            self._exports.append(record)
            self._next_id += 1
            write_json_atomic(self.path, self._exports)
            return record

    def review(self, export_id, action, reason, reviewer):
        action = action.strip()
        reason, reviewer = reason.strip(), reviewer.strip()
        if action not in ("approve", "reject"):
            raise ValueError("action must be approve or reject")
        if len(reason) < 20:
            raise ValueError("reason must contain at least 20 characters")
        if not 2 <= len(reviewer) <= 80:
            raise ValueError("reviewer must contain 2 to 80 characters")
        with self._lock:
            record = next((item for item in self._exports if item["id"] == export_id), None)
            if record is None:
                return None
            if record["status"] == "rejected_auto" and action == "approve":
                raise ExportConflict("An automatically failed export cannot be approved")
            if record["status"] != "pending_review":
                raise ExportConflict("Export is no longer pending review")
            record["status"] = "approved" if action == "approve" else "rejected"
            record["review"] = {
                "action": action,
                "reason": reason,
                "reviewer": reviewer,
                "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            }
            write_json_atomic(self.path, self._exports)
            return record
