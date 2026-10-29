import pytest

from accessdesk.config import build_desk, find_data_dir


@pytest.fixture(scope="session")
def data_dir():
    try:
        return find_data_dir(None)
    except SystemExit:
        pytest.skip("Track 3 data not found")


@pytest.fixture(scope="session")
def desk(data_dir, tmp_path_factory):
    instance = build_desk(data_dir, runtime_dir=tmp_path_factory.mktemp("accessdesk-runtime"))
    try:
        yield instance
    finally:
        instance.store.con.close()
