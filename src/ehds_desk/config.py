"""Settings and global constants (reference date, small-cell threshold)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

REFERENCE_DATE: date = date(2025, 12, 31)
SMALL_CELL_THRESHOLD = 10

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LLM_MODEL = "claude-sonnet-5-5"
_MARKER = Path("track3") / "requests" / "expected.json"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    var_dir: Path
    llm_mode: Literal["auto", "off"]
    anthropic_api_key: str | None
    llm_model: str


def _find_data_dir() -> Path:
    """First ancestor of the repo root that contains track3/requests/expected.json."""
    for parent in (REPO_ROOT, *REPO_ROOT.parents):
        if (parent / _MARKER).is_file():
            return parent / "track3"
    raise FileNotFoundError(
        "Could not locate the track3 data directory. Set TRACK3_DATA to the folder "
        "that contains data/ and requests/."
    )


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    data_env = os.environ.get("TRACK3_DATA", "").strip()
    var_env = os.environ.get("EHDS_VAR_DIR", "").strip()
    mode = os.environ.get("EHDS_LLM", "auto").strip().lower() or "auto"
    if mode not in ("auto", "off"):
        raise ValueError(f"EHDS_LLM must be 'auto' or 'off', got {mode!r}")
    return Settings(
        data_dir=Path(data_env) if data_env else _find_data_dir(),
        var_dir=Path(var_env) if var_env else REPO_ROOT / "var",
        llm_mode=mode,  # type: ignore[arg-type]
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None,
        llm_model=os.environ.get("EHDS_LLM_MODEL", "").strip() or DEFAULT_LLM_MODEL,
    )
