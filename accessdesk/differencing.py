"""Cross-request differencing protection for approved statistical outputs."""
import hashlib
import json
import threading
from pathlib import Path

from .atomic import write_json_atomic
from .safes.people import org_core, plain_name

MIN_DIFFERENCE = 1
MAX_DIFFERENCE = 9


class ReleaseLedger:
    def __init__(self, root):
        self.path = Path(root) / "release_ledger.json"
        self.lock = threading.RLock()
        self.entries = self._read()

    def _read(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @staticmethod
    def applicant_key(request):
        applicant = request.get("applicant") or {}
        return (
            plain_name(str(applicant.get("name") or ""))
            + "|"
            + org_core(str(applicant.get("organisation") or ""))
        )

    @staticmethod
    def _bitmap(store, unit, identifiers):
        index = store.patient_bits if unit == "patient" else store.encounter_bits
        bitmap = 0
        for identifier in identifiers:
            bit = index.get(identifier)
            if bit is not None:
                bitmap |= 1 << bit
        packed = bitmap.to_bytes(max(1, (bitmap.bit_length() + 7) // 8), "big")
        return bitmap, hashlib.sha256(packed).hexdigest(), packed

    def apply(self, released, cell_sets, request, request_id, store, unit):
        applicant_key = self.applicant_key(request)
        with self.lock:
            existing = [
                entry for entry in self.entries
                if not (entry["applicant_key"] == applicant_key and entry["request_id"] == request_id)
            ]
            measures = {item["key"]: item["type"] for item in released["measures"]}
            checked_cells = 0
            compared_entries = 0
            suppressed = []
            new_entries = []
            for row in released["rows"]:
                group = tuple(row["group"])
                for measure, value in list(row["values"].items()):
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        continue
                    checked_cells += 1
                    kind = measures[measure]
                    parts = {
                        "count": ["value"],
                        "pct": ["num", "den"],
                        "mean": ["patients"],
                    }[kind]
                    cell_suppressed = False
                    for part in parts:
                        identifiers = cell_sets.get((group, measure, part), set())
                        bitmap, fingerprint, packed = self._bitmap(store, unit, identifiers)
                        compared_fingerprints = set()
                        for old in existing:
                            if old["applicant_key"] != applicant_key or old["unit"] != unit:
                                continue
                            if old["request_id"] == request_id:
                                continue
                            fingerprint_key = (old["fingerprint"], tuple(old["group"]))
                            if fingerprint_key in compared_fingerprints:
                                continue
                            compared_fingerprints.add(fingerprint_key)
                            previous = int(old["bitmap"], 16)
                            difference = (bitmap ^ previous).bit_count()
                            compared_entries += 1
                            if MIN_DIFFERENCE <= difference <= MAX_DIFFERENCE:
                                cell_suppressed = True
                                suppressed.append({
                                    "group": list(group),
                                    "measure": measure,
                                    "part": part,
                                    "difference": difference,
                                    "against": {
                                        "request_id": old["request_id"],
                                        "group": old["group"],
                                        "measure": old["measure"],
                                        "part": old["part"],
                                    },
                                })
                        if not any(
                            item["group"] == list(group)
                            and item["measure"] == measure
                            and item["part"] == part
                            for item in suppressed
                        ):
                            new_entries.append({
                                "applicant_key": applicant_key,
                                "request_id": request_id,
                                "group": list(group),
                                "measure": measure,
                                "part": part,
                                "unit": unit,
                                "n": len(identifiers),
                                "fingerprint": fingerprint,
                                "bitmap": format(bitmap, "x"),
                            })
                    if cell_suppressed:
                        row["values"][measure] = "suppressed"
            self.entries = existing + new_entries
            write_json_atomic(self.path, self.entries)
            self._rebuild_answer(released)
            released["differencing"] = {
                "checked_cells": checked_cells,
                "compared_entries": compared_entries,
                "suppressed": suppressed,
            }
            return released

    @staticmethod
    def _rebuild_answer(released):
        answer = {}
        for row in released["rows"]:
            if not row["group"]:
                answer = dict(row["values"])
                continue
            node = answer
            for value in row["group"][:-1]:
                node = node.setdefault(value, {})
            node[row["group"][-1]] = row["values"]
        released["answer"] = answer
