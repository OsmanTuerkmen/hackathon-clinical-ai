import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch):
    monkeypatch.delenv("EHDS_LLM_BASE_URL", raising=False)


def load(rel):
    return json.loads((ROOT / rel).read_text())
