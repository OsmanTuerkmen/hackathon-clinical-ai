import pytest

from ehds_desk.config import load_settings
from ehds_desk.data import get_database


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def db(settings):
    return get_database(settings)
