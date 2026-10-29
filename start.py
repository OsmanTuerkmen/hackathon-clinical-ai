"""Start the local AccessDesk 2 API and open the frontend when available."""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from accessdesk.bootstrap import ROOT, ensure_runtime


def _free_port(host, requested):
    for port in range(requested, 8101):
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"No free port between {requested} and 8100.")


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", help="path to TRACK-3-ehds/data")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    ensure_runtime(__file__, sys.argv[1:])
    from accessdesk.api import create_app
    from accessdesk.config import find_data_dir
    import uvicorn

    try:
        data_dir = find_data_dir(args.data)
    except SystemExit as exc:
        raise SystemExit(f"{exc}\nPlace TRACK-3-ehds next to accessdesk2 or pass --data PATH.") from exc
    if not 1 <= args.port <= 8100:
        raise SystemExit("--port must be between 1 and 8100.")
    port = _free_port(args.host, args.port)
    if port != args.port:
        print(f"Port {args.port} is busy; using {port}.", flush=True)
    host_for_url = "localhost" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{host_for_url}:{port}"
    print(f"AccessDesk 2 is starting at {url}", flush=True)
    app = create_app(data_dir, runtime_dir=ROOT / "runtime")
    if not args.no_browser:
        def open_browser():
            time.sleep(0.5)
            webbrowser.open(url)

        app.add_event_handler(
            "startup",
            lambda: threading.Thread(target=open_browser, daemon=True).start(),
        )
    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
