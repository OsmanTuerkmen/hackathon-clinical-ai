"""Application paths and request loading."""
import json
import os
import sys
from pathlib import Path

from .pipeline import AccessDesk

ROOT = Path(__file__).resolve().parent.parent


def find_data_dir(cli_value):
    candidates = [
        cli_value,
        os.environ.get("ACCESSDESK_DATA"),
        ROOT.parent / "track3" / "data",
        ROOT.parent / "TRACK-3-ehds" / "data",
        ROOT / "data",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "patients.csv").exists():
            return str(Path(candidate).resolve())
    sys.exit("Track 3 data not found. Pass --data /path/to/TRACK-3-ehds/data")


def build_desk(data_dir, runtime_dir=None):
    data_dir = Path(data_dir).resolve()
    runtime_dir = Path(runtime_dir).resolve() if runtime_dir else ROOT / "runtime"
    registry_path = ROOT / "demo" / "registry.json"
    expected_path = data_dir.parent / "requests" / "expected.json"
    return AccessDesk(str(data_dir), str(runtime_dir), str(registry_path), str(expected_path))


def load_requests(data_dir):
    requests = []
    candidates = [
        ("test", sorted((Path(data_dir).resolve().parent / "requests").glob("R*.json"))),
        ("demo", sorted((ROOT / "demo" / "requests").glob("*.json"))),
    ]
    for group, paths in candidates:
        for path in paths:
            with path.open(encoding="utf-8") as stream:
                requests.append((group, json.load(stream)))
    return requests
