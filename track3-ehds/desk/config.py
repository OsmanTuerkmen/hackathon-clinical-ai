"""Paths and fixed parameters. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DESK_DATA_DIR", ROOT / "data"))
REQUESTS_DIR = Path(os.environ.get("DESK_REQUESTS_DIR", ROOT / "requests"))
NEW_REQUESTS_DIR = ROOT / "new_requests"
WEB_DIR = ROOT / "web"
SPE_DIR = Path(os.environ.get("DESK_SPE_DIR", ROOT / "spe_workspaces"))
STATE_DIR = Path(os.environ.get("DESK_STATE_DIR", ROOT / "state"))  # persistent case register (no patient data)
REPORTS_DIR = ROOT / "reports"

# data/README.md: "The data runs until 31 December 2025. Use that date as the reference date
# for ages and for deciding which medications are active. Age = 2025 minus birth year."
REFERENCE_DATE = "2025-12-31"
REFERENCE_YEAR = 2025

# Small-cell rule from the challenge README.
SMALL_CELL_THRESHOLD = 10

HOST = os.environ.get("DESK_HOST", "127.0.0.1")
PORT = int(os.environ.get("DESK_PORT", "8000"))
