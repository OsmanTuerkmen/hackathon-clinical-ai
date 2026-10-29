import pytest

from ehds_desk.config import load_settings
from ehds_desk.data import get_database


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Shield tests from the developer's shell environment for the optional settings.

    Tests never read a .env file (they call `load_settings(env_file=None)`), so only variables
    exported in the shell could leak; those four are removed. TRACK3_DATA is intentionally left
    alone so data discovery keeps working.
    """
    for name in ("EHDS_LLM", "EHDS_VAR_DIR", "EHDS_LLM_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def settings():
    return load_settings(env_file=None)


@pytest.fixture(scope="session")
def db(settings):
    return get_database(settings)
