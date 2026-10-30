"""Command line: python3 -m desk [serve|evaluate|run FILE]"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "evaluate":
        from .evaluate import main as evaluate_main
        return evaluate_main(sys.argv[2:])
    ap = argparse.ArgumentParser(prog="python3 -m desk", description="Doccess - secure access to health data (hackathon simulation)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the web app (default)")
    s.add_argument("--host", default=None)
    s.add_argument("--port", type=int, default=None)
    r = sub.add_parser("run", help="process one request file and print the applicant answer")
    r.add_argument("file")
    r.add_argument("--staff", action="store_true", help="print the full staff view")
    sub.add_parser("evaluate", help="score R01-R10 against requests/expected.json (3 runs)")
    args = ap.parse_args()
    if args.cmd == "run":
        from .llm import from_environment
        from .pipeline import Desk, applicant_view, staff_view
        desk = Desk(planner=from_environment())
        with open(args.file, encoding="utf-8") as f:
            case = desk.process(f.read(), source="cli")
        view = staff_view(case, desk.spe) if args.staff else applicant_view(case)
        print(json.dumps(view, indent=2, ensure_ascii=False, default=str))
        return 0
    from .server import serve
    serve(getattr(args, "host", None), getattr(args, "port", None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
