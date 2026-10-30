"""Official metrics (track README) + our extra suites. Used by the API scoreboard and scripts/eval.py."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from . import pipeline, privacy

ROOT = Path(__file__).resolve().parents[2]
RUNS: dict[str, dict] = {}
ALLOWED_EXTRA_ARTICLES = {"67", "71"}


def values_match(expected, got) -> bool:
    """Every expected value appears under its group; layout and measure names do not matter."""
    if isinstance(expected, dict):
        if not isinstance(got, dict):
            return False
        if all(not isinstance(v, dict) for v in expected.values()):
            if all(k in got for k in expected) and all(not isinstance(got[k], dict) for k in expected):
                return all(expected[k] == got[k] for k in expected)
            flat = [v for v in got.values() if not isinstance(v, dict)]
            if any(k in got and isinstance(got[k], dict) for k in expected):
                return all(k in got and values_match(v, got[k]) for k, v in expected.items())
            return _multiset_in(list(expected.values()), flat)
        return all(k in got and values_match(v, got[k]) for k, v in expected.items())
    if isinstance(got, dict):
        return expected in got.values()
    return expected == got


def _multiset_in(needles: list, hay: list) -> bool:
    hay = list(hay)
    for n in needles:
        if n in hay:
            hay.remove(n)
        else:
            return False
    return True


def count_values(e) -> int:
    return sum(count_values(v) for v in e.values()) if isinstance(e, dict) else 1


def articles_ok(expected: list[str], got: list[str]) -> bool:
    return set(expected) <= set(got) <= set(expected) | ALLOWED_EXTRA_ARTICLES


def _load_suite(include_custom: bool) -> list[tuple[dict, dict]]:
    exp = json.loads((ROOT / "track/requests/expected.json").read_text())
    suite = [(json.loads((ROOT / f"track/requests/{k}.json").read_text()), v) for k, v in exp.items()]
    if include_custom:
        for folder in ("custom", "adversarial"):
            for f in sorted((ROOT / "fixtures" / folder).glob("*.json")):
                if f.name.endswith(".expected.json"):
                    continue
                e = f.with_name(f.stem + ".expected.json")
                suite.append((json.loads(f.read_text()), json.loads(e.read_text()) if e.exists() else {}))
    return suite


def new_run() -> str:
    rid = "m_" + uuid.uuid4().hex[:6]
    RUNS[rid] = {"status": "running", "summary": {}, "rows": [], "custom": []}
    return rid


def execute(run_id: str, runs: int = 3, include_custom: bool = True) -> dict:
    out = RUNS.setdefault(run_id, {"status": "running", "summary": {}, "rows": [], "custom": []})
    rows, custom = [], []
    for req, exp in _load_suite(include_custom):
        official = req["id"].startswith("R")
        per = []
        for r in range(runs):
            q = {**req, "id": f"{req['id']}-{run_id[-4:]}-{r + 1}"}
            t = time.time()
            try:
                d = pipeline.run_sync(q)
                pipeline.STORE.pop(q["id"], None)  # evaluation runs stay out of the staff queue
            except pipeline.RequestError as e:
                per.append({"decision": "INVALID", "error": str(e), "ms": int((time.time() - t) * 1000), "answer": None, "leaks": 0,
                            "articles_ok": exp.get("decision") == "INVALID", "numbers_ok": None, "needs_review": False, "review": []})
                continue
            ms = int((time.time() - t) * 1000)
            dec = d.get("decision") or {}
            ans = (d.get("result") or {}).get("answer")
            leaks = len(privacy.leak_check(ans)) if ans and (d.get("result") or {}).get("kind") == "table" else 0
            e_ans = exp.get("answer")
            per.append({
                "decision": dec.get("outcome"), "articles": dec.get("articles"),
                "articles_ok": (dec.get("outcome") == exp.get("decision") and articles_ok(exp.get("articles", []), dec.get("articles", [])))
                if exp.get("articles") else dec.get("outcome") == exp.get("decision") if exp.get("decision") else None,
                "numbers_ok": values_match(e_ans, ans) if e_ans else ((ans is None) if ("answer" in exp and exp.get("decision", "").startswith("APPROVE_STAT")) else None),
                "leaks": leaks, "ms": ms, "answer": ans, "needs_review": dec.get("needs_review", False),
                "review": [x["code"] for x in dec.get("review_reasons", [])],
            })
        consistent = len({json.dumps([p["decision"], p.get("articles"), p["answer"]], sort_keys=True, ensure_ascii=False) for p in per}) == 1
        row = {"id": req["id"], "expected": exp.get("decision"), "expect_review": exp.get("needs_review"), "runs": per, "consistent": consistent,
               "values_total": count_values(exp["answer"]) if exp.get("answer") else 0, "title": (req.get("applicant") or {}).get("organisation", "")}
        (rows if official else custom).append(row)
        out["rows"], out["custom"] = rows, custom
    approved = [r for r in rows if r["expected"] != "REJECT"]
    out["summary"] = {
        "decisions_correct": sum(all(p["articles_ok"] for p in r["runs"]) for r in rows), "decisions_total": len(rows),
        "numbers_correct": sum(all(p["numbers_ok"] for p in r["runs"]) for r in approved), "numbers_total": len(approved),
        "privacy_leaks": sum(p["leaks"] for r in rows + custom for p in r["runs"]),
        "consistent": sum(r["consistent"] for r in rows), "consistent_total": len(rows),
        "slowest_ms": max((p["ms"] for r in rows for p in r["runs"]), default=0), "threshold_ms": 60000,
        "custom_correct": sum(all((p["articles_ok"] is not False) and (p["numbers_ok"] is not False) and
                                  (r["expect_review"] is None or p["needs_review"] == r["expect_review"]) for p in r["runs"]) for r in custom),
        "custom_total": len(custom),
    }
    out["status"] = "done"
    return out
