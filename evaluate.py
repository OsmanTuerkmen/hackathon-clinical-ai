"""Prints the five Track 3 metrics for the 10 official requests (3 runs each).

Run:  python evaluate.py --data ../TRACK-3-ehds/data
      python evaluate.py --suite all    # also the demo cases and the own test requests,
                                        # checked strictly against the pandas oracle (tests/oracle)
      python evaluate.py --json         # full result as JSON
Exit code 0 only if every target is met.
"""
import argparse
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from accessdesk import evaluation                       # noqa: E402
from accessdesk.config import build_desk, find_data_dir  # noqa: E402


def _load(pattern):
    out = []
    for f in sorted(glob.glob(pattern)):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="path to TRACK-3-ehds/data")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--suite", choices=["official", "all"], default="official")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args()

    data_dir = find_data_dir(args.data)
    desk = build_desk(data_dir, runtime_dir=tempfile.mkdtemp(prefix="accessdesk-eval-"))
    official = _load(os.path.join(data_dir, "..", "requests", "R*.json"))
    res = evaluation.run(desk, official, runs=args.runs)

    own = None
    if args.suite == "all":
        with open(os.path.join(ROOT, "tests", "oracle", "expected.json"), encoding="utf-8") as f:
            oracle = json.load(f)
        extra = (_load(os.path.join(ROOT, "demo", "requests", "D*.json"))
                 + _load(os.path.join(ROOT, "tests", "oracle", "requests", "T*.json")))
        own = evaluation.run_strict(desk, official + extra, oracle)

    if args.json:
        print(json.dumps({"official": res, "own": own}, indent=1, ensure_ascii=False))
    else:
        mark = lambda v: "-" if v is None else ("ok" if v else "NO")   # noqa: E731
        print(f"{'ID':<5}{'decision':<22}{'expected':<22}{'dec':<5}{'num':<6}{'leaks':<7}{'same':<6}{'max ms':>8}")
        for r in res["rows"]:
            print(f"{r['id']:<5}{r['decision']:<22}{r['expected_decision'] or '':<22}{mark(r['decision_ok']):<5}"
                  f"{mark(r['numbers_ok']):<6}{len(r['leaks']):<7}{mark(r['consistent']):<6}{r['max_ms']:>8}")
        s = res["summary"]
        print()
        print(f"Correct decisions : {s['correct_decisions']}   (target 10 / 10)")
        print(f"Correct numbers   : {s['correct_numbers']}   (target 6 / 6)")
        print(f"Privacy leaks     : {s['privacy_leaks']}        (target 0)")
        print(f"Consistency       : {s['consistency']}   (target 10 / 10, {s['runs_per_request']} runs each)")
        print(f"Slowest answer    : {s['slowest_ms']} ms (target < 60 s)")
        if own is not None:
            print()
            print("Strict check against the independent pandas oracle (groups, values in order, cohort, SPE, funnel):")
            for o in own:
                print(f"  {o['id']:<5}{o['decision']:<22}{o['expected']:<22}{'ok' if o['ok'] else 'NO'}"
                      + ("" if o["ok"] else "  " + "; ".join(o["problems"])[:160]))
            print(f"Own and official requests, strict: {sum(o['ok'] for o in own)} / {len(own)}")
    ok = res["summary"]["targets_met"] and (own is None or all(o["ok"] for o in own))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
