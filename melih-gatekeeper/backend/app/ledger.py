"""Query ledger against differencing ("tracker") attacks.

For each applicant we keep the patient sets behind every released group. A new release whose group differs
from an earlier released group by 1..9 patients would let the applicant subtract one from the other and learn
about fewer than 10 people, so it is flagged for review (Denning, Denning & Schwartz 1979).
"""
from __future__ import annotations

import threading

from .privacy import THRESHOLD

_lock = threading.Lock()
_released: dict[str, list[tuple[str, str, frozenset]]] = {}  # applicant -> [(request_id, group label, patient ids)]


def applicant_key(request: dict) -> str:
    a = request.get("applicant") or {}
    return (str(a.get("organisation", "")).strip().lower() or str(a.get("name", "")).strip().lower() or "anonymous")


def check(applicant: str, request_id: str, groups: dict[str, frozenset]) -> list[dict]:
    findings = []
    with _lock:
        previous = [p for p in _released.get(applicant, []) if p[0] != request_id]
    for label, ids in groups.items():
        if len(ids) < THRESHOLD:
            continue  # already suppressed by the small-cell rule
        for rid, plabel, pids in previous:
            diff = len(ids ^ pids)
            if 0 < diff < THRESHOLD:
                findings.append({"group": label, "other_request": rid, "other_group": plabel, "difference": diff})
    return findings


def record(applicant: str, request_id: str, groups: dict[str, frozenset]):
    with _lock:
        lst = _released.setdefault(applicant, [])
        lst[:] = [p for p in lst if p[0] != request_id]
        lst.extend((request_id, label, ids) for label, ids in groups.items() if len(ids) >= THRESHOLD)


def reset():
    with _lock:
        _released.clear()
