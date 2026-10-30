"""The shipped desk and direct workspace URLs expose the same local UI shell."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from ehds_desk.api import create_app
from ehds_desk.pipeline import DeskService


@pytest.fixture
def client(settings, tmp_path):
    service = DeskService(dataclasses.replace(settings, var_dir=tmp_path / "var", llm_mode="off", anthropic_api_key=None))
    return TestClient(create_app(service))


def test_desk_serves_html_shell(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="app"' in response.text


@pytest.mark.parametrize("path,content_type", [("/app.js", "javascript"), ("/styles.css", "text/css")])
def test_desk_assets_available(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.content


def test_workspace_direct_url_serves_ui_shell(client):
    response = client.get("/spe/R05-abcdef12")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="app"' in response.text
