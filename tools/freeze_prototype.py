"""Freezes the prototype's outputs as golden data for the regression test.

Runs the original prototype (../ehds-accessdesk, read-only) in a separate
process on the official requests, the demo cases and the own test requests,
and writes tests/golden/prototype.json: decision, articles, delivery status,
cohort size and the released rows (group + values in report order). The
prototype gets a temporary runtime folder, so its own folder is not touched.

Run: python tools/freeze_prototype.py --data ../TRACK-3-ehds/data
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTO = os.path.normpath(os.path.join(ROOT, "..", "ehds-accessdesk"))

CHILD = r"""
import json, os, sys, tempfile
proto, data_dir, files = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, proto)
os.environ["ACCESSDESK_AI"] = "off"
from accessdesk.pipeline import AccessDesk
root = tempfile.mkdtemp(prefix="proto-runtime-")
desk = AccessDesk(data_dir, root, os.path.join(proto, "demo", "registry.json"),
                  os.path.join(data_dir, "..", "requests", "expected.json"))
out = {}
for path in files:
    with open(path, encoding="utf-8") as f:
        req = json.load(f)
    try:
        res = desk.process(req, use_cache=False, actor="freeze")
    except Exception as e:
        out[req["id"]] = {"error": f"{type(e).__name__}: {e}"}
        continue
    rel = res.get("released")
    out[req["id"]] = {
        "decision": res["decision"]["decision"],
        "articles": res["decision"]["articles"],
        "delivery": res["delivery"]["status"],
        "cohort_size": (res.get("spe") or {}).get("cohort_size"),
        "rows": [{"group": r["group"], "values": list(r["values"].values())} for r in rel["rows"]] if rel else None,
        "warnings": res["plan"]["warnings"],
    }
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "..", "TRACK-3-ehds", "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "tests", "golden", "prototype.json"))
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data)
    files = (sorted(glob.glob(os.path.join(data_dir, "..", "requests", "R*.json")))
             + sorted(glob.glob(os.path.join(ROOT, "demo", "requests", "D*.json")))
             + sorted(glob.glob(os.path.join(ROOT, "tests", "oracle", "requests", "T*.json"))))
    if not any(os.path.basename(f).startswith("D") for f in files):
        files += sorted(glob.glob(os.path.join(PROTO, "demo", "requests", "D*.json")))
    proc = subprocess.run([sys.executable, "-c", CHILD, PROTO, data_dir, *[os.path.abspath(f) for f in files]],
                          capture_output=True, cwd=PROTO, check=True)
    out = json.loads(proc.stdout.decode("utf-8"))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(out)} prototype results to {os.path.relpath(args.out, ROOT)}")


if __name__ == "__main__":
    main()
