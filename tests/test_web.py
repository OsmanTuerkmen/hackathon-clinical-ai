"""The shipped desk and direct workspace URLs expose the same local UI shell."""
import dataclasses
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ehds_desk.api import create_app
from ehds_desk.pipeline import DeskService

WEB = Path(__file__).resolve().parents[1] / "web"
FONTS = (
    "instrument-sans-latin-wght-normal.woff2",
    "instrument-sans-latin-ext-wght-normal.woff2",
    "ibm-plex-mono-latin-400-normal.woff2",
    "ibm-plex-mono-latin-ext-400-normal.woff2",
    "ibm-plex-mono-latin-500-normal.woff2",
    "ibm-plex-mono-latin-ext-500-normal.woff2",
)


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


def test_shell_carries_the_doccess_brand(client):
    html = client.get("/").text
    assert "<title>Doccess</title>" in html
    assert 'href="/assets/favicon.svg"' in html
    assert 'href="/assets/fonts/fonts.css"' in html
    assert "EHDS Access Desk" not in html


def test_favicon_is_a_local_svg(client):
    response = client.get("/assets/favicon.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]


@pytest.mark.parametrize("font", FONTS)
def test_fonts_are_served_locally(client, font):
    response = client.get(f"/assets/fonts/{font}")
    assert response.status_code == 200
    assert response.content[:4] == b"wOF2"


def test_font_stylesheet_only_references_shipped_files(client):
    css = client.get("/assets/fonts/fonts.css").text
    assert sorted(re.findall(r"url\(\.?/?([^)]+\.woff2)\)", css)) == sorted(FONTS)


@pytest.mark.parametrize("licence", ["OFL-InstrumentSans.txt", "OFL-IBMPlexMono.txt"])
def test_font_licences_ship_with_the_fonts(licence):
    assert "SIL Open Font License" in (WEB / "assets" / "fonts" / licence).read_text(encoding="utf-8")


def test_ui_loads_nothing_from_external_hosts():
    sources = [WEB / "index.html", WEB / "app.js", WEB / "styles.css", WEB / "assets" / "fonts" / "fonts.css", WEB / "assets" / "favicon.svg"]
    for path in sources:
        hosts = set(re.findall(r"https?://([^/\"')\s]+)", path.read_text(encoding="utf-8")))
        assert hosts <= {"www.w3.org"}, path.name

