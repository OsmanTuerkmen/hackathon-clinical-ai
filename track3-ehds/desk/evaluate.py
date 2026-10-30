"""Evaluation harness: runs R01-R10 three times and scores them against requests/expected.json.

expected.json is read ONLY here, after the answers were produced, to compare them. No runtime code
path imports this module's data.

Usage:
  python3 -m desk evaluate                 # in-process, fresh data load per run
  python3 -m desk evaluate --url http://127.0.0.1:8000   # through the running web server (HTTP)
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from .config import REPORTS_DIR, REQUESTS_DIR

ALLOWED_EXTRA_ARTICLES = {"67", "71"}
PATIENT_ID = re.compile(r"\bp-[0-9a-f]{8}\b")


def _same(a, b) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    return Decimal(str(a)) == Decimal(str(b))


def compare_answer(expected, ours) -> tuple[bool, list[str]]:
    """README rule: every expected value appears under its group (layout does not matter)."""
    problems: list[str] = []
    if expected is None:
        return ours is None, ([] if ours is None else ["unexpected answer"])
    if ours is None:
        return False, ["no answer"]
    if "cohort_size" in expected:
        ok = ours.get("cohort_size") == expected["cohort_size"]
        return ok, [] if ok else [f"cohort_size {ours.get('cohort_size')} != {expected['cohort_size']}"]
    for group, exp_vals in expected.items():
        vals = list(exp_vals.values()) if isinstance(exp_vals, dict) else [exp_vals]
        got = list(ours.get(group, []))
        if group not in ours:
            problems.append(f"group '{group}' missing")
            continue
        pool = list(got)
        for v in vals:
            hit = next((i for i, g in enumerate(pool) if _same(v, g)), None)
            if hit is None:
                problems.append(f"{group}: expected {v!r}, got {got!r}")
            else:
                pool.pop(hit)
    return not problems, problems


def leak_scan(view: dict) -> list[str]:
    """Independent scan of what the applicant receives for a statistical answer."""
    leaks = []
    res = view.get("result") or {}
    if res.get("kind") != "statistics":
        return leaks
    text = json.dumps(res, ensure_ascii=False)
    if PATIENT_ID.search(text):
        leaks.append("patient identifier in answer")
    for row in res["rows"]:
        for col in res["columns"]:
            v = row["cells"][col["id"]]
            if col["type"] == "count" and isinstance(v, (int, float)) and not isinstance(v, bool) and v < 10:
                leaks.append(f"count below 10 shown in {row['label']}")
    return leaks


class InProcessClient:
    def __init__(self):
        from .config import DATA_DIR
        from .datastore import DataStore
        from .pipeline import Desk
        self.desk = Desk(store=DataStore(DATA_DIR))

    def submit(self, text: str):
        from .pipeline import applicant_view, staff_view
        t0 = time.perf_counter()
        case = self.desk.process(text, source="evaluation")
        ms = (time.perf_counter() - t0) * 1000
        return applicant_view(case), staff_view(case, self.desk.spe), ms

    def download(self, wid: str) -> int:
        return self.desk.spe.request_download(wid, actor="evaluation")[0]


class HttpClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def _call(self, path: str, data: bytes | None = None):
        req = urllib.request.Request(self.url + path, data=data, method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def submit(self, text: str):
        t0 = time.perf_counter()
        status, view = self._call("/api/submit", text.encode("utf-8"))
        ms = (time.perf_counter() - t0) * 1000
        _, staff = self._call(f"/api/cases/{view['case_id']}")
        return view, staff, ms

    def download(self, wid: str) -> int:
        return self._call(f"/api/spe/{wid}/download")[0]


def evaluate(runs: int = 3, url: str | None = None, request_dir: Path = REQUESTS_DIR) -> dict:
    expected = json.loads((request_dir / "expected.json").read_text(encoding="utf-8"))
    ids = sorted(expected)
    per_run: list[dict] = []
    for run in range(1, runs + 1):
        client = HttpClient(url) if url else InProcessClient()
        results = {}
        for rid in ids:
            text = (request_dir / f"{rid}.json").read_text(encoding="utf-8")
            view, staff, ms = client.submit(text)
            d = view.get("decision") or {}
            ours = _answer(view)
            exp = expected[rid]
            arts = set(d.get("articles") or [])
            decision_ok = d.get("outcome") == exp["decision"] and \
                set(exp["articles"]) <= arts <= set(exp["articles"]) | ALLOWED_EXTRA_ARTICLES
            numbers_ok, problems = (None, [])
            if exp["decision"] != "REJECT":
                numbers_ok, problems = compare_answer(exp["answer"], ours)
            leaks = leak_scan(view)
            checks = staff.get("privacy_checks") or []
            leaks += [f"privacy check failed: {c['check']}" for c in checks if c["status"] == "fail"]
            if exp["answer"] and not ("cohort_size" in exp["answer"]) and ours:
                for group, vals in exp["answer"].items():
                    ev = list(vals.values()) if isinstance(vals, dict) else [vals]
                    for e_val, o_val in zip(ev, ours.get(group, [])):
                        if e_val in ("<10", "suppressed") and o_val != e_val:
                            leaks.append(f"{group}: value {o_val!r} should be {e_val!r}")
            download = None
            res = view.get("result") or {}
            if res.get("kind") == "spe":
                download = client.download(res["workspace_id"])
                if download != 403:
                    leaks.append(f"SPE download answered HTTP {download}")
            results[rid] = {"decision": d.get("outcome"), "articles": sorted(arts, key=int),
                            "decision_ok": decision_ok, "numbers_ok": numbers_ok, "problems": problems,
                            "leaks": leaks, "ms": round(ms, 1), "fingerprint": staff.get("fingerprint"),
                            "download_status": download, "fulfilment": (view.get("fulfilment") or {}).get("status")}
        per_run.append(results)
        if isinstance(client, InProcessClient):
            client.desk.store.close()

    summary = {}
    for rid in ids:
        rs = [r[rid] for r in per_run]
        summary[rid] = {**rs[0], "consistent": len({r["fingerprint"] for r in rs}) == 1,
                        "ms_max": max(r["ms"] for r in rs), "leaks": sorted({x for r in rs for x in r["leaks"]})}
    approved = [rid for rid in ids if expected[rid]["decision"] != "REJECT"]
    statistical = [rid for rid in ids if expected[rid]["decision"] == "APPROVE_STATISTICAL"]
    metrics = {
        "correct_decisions": sum(all(r[rid]["decision_ok"] for r in per_run) for rid in ids),
        "decisions_total": len(ids),
        "correct_numbers": sum(all(r[rid]["numbers_ok"] for r in per_run) for rid in approved),
        "numbers_total": len(approved),
        "correct_statistical_numbers": sum(all(r[rid]["numbers_ok"] for r in per_run) for rid in statistical),
        "statistical_total": len(statistical),
        "privacy_leaks": sum(len(summary[rid]["leaks"]) > 0 for rid in ids),
        "consistent": sum(summary[rid]["consistent"] for rid in ids),
        "runs": runs,
        "slowest_ms": max(summary[rid]["ms_max"] for rid in ids),
        "slowest_request": max(ids, key=lambda rid: summary[rid]["ms_max"]),
        "mode": f"HTTP {url}" if url else "in-process (fresh data load per run)",
    }
    return {"metrics": metrics, "requests": summary}


def _answer(view: dict):
    res = view.get("result")
    if not res:
        return None
    if res["kind"] == "spe":
        return {"cohort_size": res["cohort_size"]}
    return {r["label"]: [r["cells"][c["id"]] for c in res["columns"]] for r in res["rows"]}


def render(report: dict) -> str:
    m = report["metrics"]
    lines = ["Health Data Access Desk - evaluation on the 10 supplied requests", f"mode: {m['mode']}, runs: {m['runs']}",
             "", f"{'req':4} {'decision':20} {'articles':14} {'dec':4} {'numbers':8} {'leaks':6} {'consistent':10} "
                 f"{'max ms':>8}",
             "-" * 82]
    for rid, r in report["requests"].items():
        num = "-" if r["numbers_ok"] is None else ("OK" if r["numbers_ok"] else "FAIL")
        lines.append(f"{rid:4} {r['decision'] or '-':20} {','.join(r['articles']):14} "
                     f"{'OK' if r['decision_ok'] else 'FAIL':4} {num:8} {len(r['leaks']):<6} "
                     f"{'yes' if r['consistent'] else 'NO':10} {r['ms_max']:>8.1f}")
        for p in r["problems"] + r["leaks"]:
            lines.append(f"     ! {p}")
    lines += ["", "Metrics",
              f"  Correct decisions : {m['correct_decisions']}/{m['decisions_total']}",
              f"  Correct numbers   : {m['correct_numbers']}/{m['numbers_total']} approved requests "
              f"({m['correct_statistical_numbers']}/{m['statistical_total']} statistical + SPE cohort size)",
              f"  Privacy leaks     : {m['privacy_leaks']}",
              f"  Consistency       : {m['consistent']}/{m['decisions_total']} identical across {m['runs']} runs",
              f"  Slowest answer    : {m['slowest_ms']:.1f} ms ({m['slowest_request']})"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--url", help="evaluate through a running server, e.g. http://127.0.0.1:8000")
    ap.add_argument("--save", action="store_true", help="write reports/evaluation.{json,txt}")
    args = ap.parse_args(argv)
    report = evaluate(args.runs, args.url)
    text = render(report)
    print(text)
    if args.save:
        REPORTS_DIR.mkdir(exist_ok=True)
        (REPORTS_DIR / "evaluation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (REPORTS_DIR / "evaluation.txt").write_text(text + "\n", encoding="utf-8")
    m = report["metrics"]
    ok = (m["correct_decisions"] == m["decisions_total"] and m["correct_numbers"] == m["numbers_total"]
          and m["privacy_leaks"] == 0 and m["consistent"] == m["decisions_total"] and m["slowest_ms"] < 60000)
    return 0 if ok else 1
