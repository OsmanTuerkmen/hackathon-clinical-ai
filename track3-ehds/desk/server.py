"""Web server (Python standard library only): static UI + JSON API.

GET  /                         applicant and staff UI (web/index.html)
GET  /api/health               data load statistics
GET  /api/requests             supplied (R01-R10) and new (N..) example requests
GET  /api/requests/<id>        request JSON
POST /api/submit               process a request (body: request JSON) -> applicant view
GET  /api/cases                staff case list
GET  /api/cases/<case_id>      staff view of one case
GET  /api/spe/<workspace>      SPE manifest (record types, row counts - never records) and access log
GET|POST /api/spe/<workspace>/download   always 403: records cannot leave the SPE
POST /api/evaluate             run the evaluation harness (R01-R10 x 3) and return the metrics
"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import __version__
from .config import HOST, NEW_REQUESTS_DIR, PORT, REQUESTS_DIR, WEB_DIR
from .pipeline import Desk, applicant_view, staff_view
from .request_schema import MAX_BYTES

STATIC_TYPES = {".html", ".js", ".css", ".svg", ".png", ".ico", ".json"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def list_requests() -> list[dict]:
    out = []
    for group, folder in (("supplied", REQUESTS_DIR), ("new", NEW_REQUESTS_DIR)):
        for p in sorted(folder.glob("*.json")):
            if p.name == "expected.json":
                continue
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append({"id": r.get("id", p.stem), "file": p.name, "group": group,
                        "applicant": (r.get("applicant") or {}).get("organisation", ""),
                        "requested_as": r.get("requested_as", ""), "question": r.get("question", "")})
    return out


def request_text(rid: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", rid) or rid.lower() == "expected":
        return None
    for folder in (REQUESTS_DIR, NEW_REQUESTS_DIR):
        p = folder / f"{rid}.json"
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


class App:
    def __init__(self, desk: Desk | None = None, quiet: bool = False):
        self.desk = desk or Desk()
        self.quiet = quiet
        self.eval_lock = threading.Lock()
        self.last_evaluation: dict | None = None


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"HealthDataAccessDesk/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quieter console
            if not app.quiet:
                sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {self.command} {self.path} -> "
                                 f"{args[1] if len(args) > 1 else ''}\n")

        # -------------------------------------------------------------- helpers
        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload):
            self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _body(self) -> bytes | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BYTES:
                self._json(413, {"error": f"request body larger than {MAX_BYTES // 1024} KB"})
                return None
            return self.rfile.read(length) if length else b""

        def _static(self, rel: str):
            rel = rel or "index.html"
            root = WEB_DIR.resolve()
            path = (root / rel).resolve()
            if root not in path.parents or not path.is_file() or path.suffix not in STATIC_TYPES:
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, path.read_bytes(), ctype)

        # -------------------------------------------------------------- routes
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            desk = app.desk
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/health":
                return self._json(200, {"status": "ok", "version": __version__, "data": desk.store.stats,
                                        "simulation": True})
            if path == "/api/requests":
                return self._json(200, list_requests())
            m = re.fullmatch(r"/api/requests/([A-Za-z0-9_-]+)", path)
            if m:
                text = request_text(m.group(1))
                return self._send(200, text.encode("utf-8"), "application/json; charset=utf-8") if text \
                    else self._json(404, {"error": "unknown request"})
            if path == "/api/cases":
                return self._json(200, [case_summary(c) for c in reversed(desk.cases)])
            m = re.fullmatch(r"/api/cases/(C-\d{4,})", path)
            if m:
                case = desk.get_case(m.group(1))
                return self._json(200, staff_view(case, desk.spe)) if case else self._json(404, {"error": "unknown case"})
            m = re.fullmatch(r"/api/spe/([a-z0-9-]+)/download(?:/([a-z]+))?", path)
            if m:
                return self._download(m.group(1), m.group(2))
            m = re.fullmatch(r"/api/spe/([a-z0-9-]+)", path)
            if m:
                try:
                    manifest = desk.spe.manifest(m.group(1))
                except KeyError:
                    return self._json(404, {"error": "unknown workspace"})
                return self._json(200, {"manifest": manifest, "access_log": desk.spe.log_for(m.group(1))})
            if path == "/api/evaluation":
                return self._json(200, app.last_evaluation or {})
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            path = unquote(urlparse(self.path).path)
            if path == "/api/submit":
                body = self._body()
                if body is None:
                    return
                case = app.desk.process(body, source="web")
                status = 400 if case["status"] == "INVALID_REQUEST" else 200
                return self._json(status, applicant_view(case))
            m = re.fullmatch(r"/api/spe/([a-z0-9-]+)/download(?:/([a-z]+))?", path)
            if m:
                self._body()
                return self._download(m.group(1), m.group(2))
            if path == "/api/evaluate":
                self._body()
                from .evaluate import evaluate
                with app.eval_lock:
                    app.last_evaluation = evaluate(runs=3)
                return self._json(200, app.last_evaluation)
            return self._json(404, {"error": "not found"})

        def _download(self, wid: str, table: str | None):
            try:
                status, payload = app.desk.spe.request_download(wid, table, actor="applicant (web)")
            except KeyError:
                return self._json(404, {"error": "unknown workspace"})
            return self._json(status, payload)

    return Handler


def case_summary(c: dict) -> dict:
    req = c.get("request") or {}
    d = c.get("decision") or {}
    checks = c.get("privacy_checks") or []
    return {"case_id": c["case_id"], "request_id": req.get("id"), "received_at": c.get("received_at"),
            "applicant": (req.get("applicant") or {}).get("organisation", ""),
            "requested_as": req.get("requested_as"), "outcome": d.get("outcome") or c.get("status"),
            "articles": d.get("articles") or [], "fulfilment": (c.get("fulfilment") or {}).get("status"),
            "elapsed_ms": c.get("elapsed_ms"),
            "privacy": f"{sum(x['status'] == 'pass' for x in checks)}/{len(checks)}" if checks else "-"}


def serve(host: str | None = None, port: int | None = None) -> None:
    host, port = host or HOST, port or PORT
    print("Health Data Access Desk - HACKATHON SIMULATION, synthetic data only, not a real approval system")
    print("Loading synthetic data ...", flush=True)
    t0 = time.perf_counter()
    from .llm import from_environment
    planner = from_environment()
    app = App(Desk(planner=planner))
    s = app.desk.store.stats
    print(f"Loaded {s['patients_eligible']} patients ({s['patients_opted_out']} opted-out patients excluded) "
          f"in {time.perf_counter() - t0:.1f} s")
    print(f"Interpreter: deterministic rules" + (f" + {planner.label} as validated fallback" if planner else
                                                 " (no LLM configured; set DESK_LLM_PROVIDER to enable a fallback)"))
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Open http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
