"""Run the official metrics (+ custom/adversarial suites) and write docs/METRICS.md and metrics.json.

Usage: .venv/bin/python scripts/eval.py [--runs 3] [--official-only]
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import llm, metrics  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--official-only", action="store_true")
    a = ap.parse_args()
    run_id = metrics.new_run()
    res = metrics.execute(run_id, a.runs, not a.official_only)
    s = res["summary"]
    cfg = llm.config()
    lines = [
        "# Metrics", "",
        f"AI profile: {'`' + cfg['model'] + '` at ' + str(cfg['endpoint_host']) if cfg['enabled'] else 'off (rules only)'}; runs per request: {a.runs}", "",
        "| Metric | Result | Target |", "|---|---|---|",
        f"| Correct decisions | {s['decisions_correct']} of {s['decisions_total']} | 10 of 10 |",
        f"| Correct numbers | {s['numbers_correct']} of {s['numbers_total']} | 6 of 6 |",
        f"| Privacy leaks | {s['privacy_leaks']} | 0 |",
        f"| Consistency (3 runs) | {s['consistent']} of {s['consistent_total']} | 10 of 10 |",
        f"| Time to answer (slowest) | {s['slowest_ms'] / 1000:.2f} s | under 60 s |",
    ]
    if s.get("custom_total"):
        lines.append(f"| Extra suites (hidden-style + adversarial) | {s['custom_correct']} of {s['custom_total']} | all |")
    lines += ["", "## Per request", "", "| ID | Expected | Got | Articles OK | Numbers OK | Review | Max ms |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"] + res["custom"]:
        p = r["runs"][0]
        lines.append(f"| {r['id']} | {r['expected'] or '–'} | {p['decision']} | {p['articles_ok']} | {p['numbers_ok']} | "
                     f"{', '.join(p['review']) or '–'} | {max(x['ms'] for x in r['runs'])} |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "METRICS.md").write_text("\n".join(lines) + "\n")
    (ROOT / "metrics.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print("\n".join(lines[:12]))
    fails = [r["id"] for r in res["rows"] + res["custom"] if any(p["articles_ok"] is False or p["numbers_ok"] is False for p in r["runs"])
             or (r.get("expect_review") is not None and any(p["needs_review"] != r["expect_review"] for p in r["runs"]))]
    print("failing:", fails or "none")


if __name__ == "__main__":
    main()
