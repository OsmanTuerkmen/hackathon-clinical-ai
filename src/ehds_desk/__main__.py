"""Command line: `python -m ehds_desk decide <file.json> [--staff]` and `python -m ehds_desk serve`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _decide(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from .models import AccessRequest
    from .pipeline import DeskService

    path = Path(args.file)
    try:
        request = AccessRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except OSError as exc:
        print(f"Cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    except (ValueError, ValidationError) as exc:  # invalid JSON or missing required fields
        print(f"{path} is not a valid access request: {exc}", file=sys.stderr)
        return 1
    result = DeskService().process(request)
    payload = result if args.staff else result.applicant
    print(payload.model_dump_json(indent=2))
    return 0


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        import ehds_desk.api  # noqa: F401  (imported only to check that the web app exists)
    except ImportError as exc:
        print(f"The web server is not available ({exc}). Install the dependencies and make sure ehds_desk.api exists.", file=sys.stderr)
        return 1
    uvicorn.run("ehds_desk.api:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ehds_desk", description="EHDS Access Desk")
    sub = parser.add_subparsers(dest="command", required=True)
    decide = sub.add_parser("decide", help="decide an access request given as a JSON file")
    decide.add_argument("file", help="path to the access request (JSON)")
    decide.add_argument("--staff", action="store_true", help="print the full result including the staff view")
    decide.set_defaults(func=_decide)
    serve = sub.add_parser("serve", help="start the web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
