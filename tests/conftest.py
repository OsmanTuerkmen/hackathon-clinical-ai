import pytest

from ehds_desk.config import load_settings
from ehds_desk.data import get_database


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """A developer .env (loaded into os.environ by load_settings) must not leak into tests.

    TRACK3_DATA is intentionally left alone so data discovery keeps working.
    """
    for name in ("EHDS_LLM", "EHDS_VAR_DIR", "EHDS_LLM_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def db(settings):
    return get_database(settings)
