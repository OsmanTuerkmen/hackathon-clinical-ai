"""Print the rule-based decision for one request JSON file."""
import argparse
import json
import os
import sys
from pathlib import Path

from accessdesk.bootstrap import ROOT, ensure_runtime


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="path to request JSON")
    parser.add_argument("--data", help="path to TRACK-3-ehds/data")
    parser.add_argument("--login", help="simulated eID name")
    args = parser.parse_args()
    ensure_runtime(__file__, sys.argv[1:])
    from accessdesk.api import decide_response
    from accessdesk.config import build_desk, find_data_dir

    data_dir = find_data_dir(args.data)
    with Path(args.request).open(encoding="utf-8") as stream:
        request = json.load(stream)
    desk = build_desk(data_dir, runtime_dir=ROOT / "runtime")
    try:
        result = desk.process(request, use_cache=False, login=args.login, actor="jury:decide")
        print(json.dumps(decide_response(result), ensure_ascii=False, indent=2, default=str))
    finally:
        desk.store.con.close()


if __name__ == "__main__":
    main()
