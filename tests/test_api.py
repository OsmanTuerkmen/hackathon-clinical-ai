"""HTTP contracts and privacy boundaries, using real local services and isolated SPE storage."""

import dataclasses
import importlib
import importlib.util
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import quote

import duckdb

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ehds_desk.disclosure import PATIENT_ID_PATTERN, LeakError
from ehds_desk.pipeline import DeskService


@pytest.fixture
def service(settings, tmp_path):
    return DeskService(dataclasses.replace(settings, var_dir=tmp_path / "var", llm_mode="off", anthropic_api_key=None))


def client_for(service):
    # A missing module is an explicit red assertion, rather than a collection error.
    assert importlib.util.find_spec("ehds_desk.api") is not None, "Task 11 HTTP API is missing"
    module = importlib.import_module("ehds_desk.api")
    return TestClient(module.create_app(service), raise_server_exceptions=False)


def provision(client):
    response = client.post("/api/process/R05")
    assert response.status_code == 200
    return response.json()["applicant"]["spe"]["permit_id"]


def test_health(service):
    client = client_for(service)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "patients": 19161, "llm": "off"}


def test_health_reads_actual_pat_count(service):
    client = client_for(service)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE TABLE pat AS SELECT 1 AS sentinel")
        service.db = SimpleNamespace(cursor=connection.cursor)
        assert client.get("/api/health").json()["patients"] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("mode,key,want", [("auto", None, "off"), ("auto", "fake-key", "available"), ("off", "fake-key", "off")])
def test_health_reports_configuration_without_exposing_key(service, mode, key, want):
    service.settings = dataclasses.replace(service.settings, llm_mode=mode, anthropic_api_key=key)
    response = client_for(service).get("/api/health")
    assert response.json()["llm"] == want
    assert "fake-key" not in response.text


def test_list_requests_has_track3_ids(service):
    response = client_for(service).get("/api/requests")
    assert response.status_code == 200
    assert {f"R{i:02d}" for i in range(1, 11)} <= {r["id"] for r in response.json()}
    assert not PATIENT_ID_PATTERN.search(response.text)


def test_get_request_r05_keeps_unicode(service):
    response = client_for(service).get("/api/requests/R05")
    assert response.status_code == 200
    assert response.json()["applicant"]["name"] == "Dr. Amir Hadžić"


def test_process_by_id_r01(service):
    response = client_for(service).post("/api/process/R01")
    assert response.status_code == 200
    applicant = response.json()["applicant"]
    assert applicant["decision"] == "APPROVE_STATISTICAL"
    assert len(applicant["statistics"]["rows"]) == 9
    assert not PATIENT_ID_PATTERN.search(response.text)


def test_process_minimal_request(service):
    payload = service.get_request("R01").model_dump(mode="json")
    payload.pop("submitted")
    payload.pop("requested_format")
    payload["applicant"].pop("country")
    payload["optional_extra"] = "accepted"
    response = client_for(service).post("/api/process", json=payload)
    assert response.status_code == 200
    assert response.json()["applicant"]["decision"] == "APPROVE_STATISTICAL"


@pytest.mark.parametrize("content", ['{"invalid":', '{}', '{"id":"p-1234abcd"}'])
def test_process_invalid_json_is_422(service, content):
    response = client_for(service).post("/api/process", content=content, headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert not PATIENT_ID_PATTERN.search(response.text)


def test_process_r05_unicode(service):
    client = client_for(service)
    request = client.get("/api/requests/R05").json()
    assert "Hadžić" in request["applicant"]["name"]
    response = client.post("/api/process", json=request)
    assert response.status_code == 200
    assert response.json()["applicant"]["spe"]["patient_count"] == 1152
    assert not PATIENT_ID_PATTERN.search(response.text)


@pytest.mark.parametrize("method,path", [("get", "/api/requests/UNKNOWN"), ("post", "/api/process/UNKNOWN")])
def test_unknown_request_is_404(service, method, path):
    assert getattr(client_for(service), method)(path).status_code == 404


def test_law_catalogue(service):
    response = client_for(service).get("/api/law")
    assert response.status_code == 200
    assert set(response.json()) == {"53", "54", "66", "67", "68", "69", "71", "73"}
    assert response.json()["73"]["title"] == "Secure processing environment"
    assert response.json()["73"]["summary"]


def test_spe_manifest(service):
    client = client_for(service)
    permit = provision(client)
    response = client.get(f"/api/spe/{permit}")
    assert response.status_code == 200
    assert response.json()["patient_count"] == 1152
    assert set(response.json()["tables"]) == {"cohort", "conditions", "medications", "observations"}
    assert not PATIENT_ID_PATTERN.search(response.text)


def test_spe_preview_serialises_dates_and_decimal_and_is_audited(service):
    client = client_for(service)
    permit = provision(client)
    response = client.get(f"/api/spe/{permit}/preview/observations")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 20
    assert PATIENT_ID_PATTERN.fullmatch(rows[0]["patient_id"])
    assert all(row["loinc"] == "4548-4" for row in rows)
    assert date.fromisoformat(rows[0]["date"])
    assert Decimal(str(rows[0]["value"])) > 0
    audit = client.get(f"/api/spe/{permit}/audit").json()
    assert any(e["action"] == "preview" and e["table"] == "observations" for e in audit)


@pytest.mark.parametrize("table", ["cohort", "patients", "raw_patients", "p-1234abcd", "observations;DROP TABLE cohort", "../spe.duckdb"])
def test_spe_download_blocked_403_and_audited(service, table):
    client = client_for(service)
    permit = provision(client)
    response = client.get(f"/api/spe/{permit}/download/{quote(table, safe='')}")
    assert response.status_code == 403
    assert response.json() == {
        "blocked": True,
        "article": "73",
        "reason": "Downloads of pseudonymised records are blocked. Only anonymised results reviewed by the access body may leave the secure processing environment (Art. 73(2)).",
    }
    audit = client.get(f"/api/spe/{permit}/audit")
    assert audit.status_code == 200
    assert any(e["action"] == "provisioned" for e in audit.json())
    assert audit.json()[-1]["action"] == "download_blocked"
    assert not PATIENT_ID_PATTERN.search(response.text + audit.text)


@pytest.mark.parametrize("table", ["patients", "raw_patients", "missing", 'cohort";DROP TABLE cohort;--'])
def test_spe_preview_rejects_unpermitted_tables(service, table):
    client = client_for(service)
    permit = provision(client)
    response = client.get(f"/api/spe/{permit}/preview/{table}")
    assert response.status_code in (400, 404)
    assert not PATIENT_ID_PATTERN.search(response.text)
    assert client.get(f"/api/spe/{permit}/preview/cohort").status_code == 200


@pytest.mark.parametrize("suffix", ["", "/preview/cohort", "/audit", "/download/cohort"])
def test_spe_unknown_404(service, suffix):
    assert client_for(service).get(f"/api/spe/UNKNOWN{suffix}").status_code == 404
    assert not (service.settings.var_dir / "spe" / "UNKNOWN").exists()


@pytest.mark.parametrize("permit", ["..%2Fx", "..%5Cx", "bad.id", "p%3Ainvalid"])
@pytest.mark.parametrize("suffix", ["", "/audit", "/preview/cohort", "/download/cohort"])
def test_spe_path_traversal_rejected(service, permit, suffix):
    response = client_for(service).get(f"/api/spe/{permit}{suffix}")
    assert response.status_code in (400, 404)
    assert not service.settings.var_dir.exists()


@pytest.mark.parametrize("path,payload", [("/api/process/R01", None), ("/api/process", "R01")])
def test_leak_error_is_generic_without_patient_data(service, monkeypatch, path, payload):
    client = client_for(service)
    def unsafe_process(request):
        raise LeakError("Internal patient p-1234abcd has raw count 7")
    monkeypatch.setattr(service, "process", unsafe_process)
    body = service.get_request(payload).model_dump(mode="json") if payload else None
    response = client.post(path, json=body)
    assert response.status_code == 500
    assert "p-1234abcd" not in response.text and "raw count" not in response.text
    assert response.json()["detail"]


def test_static_mount_is_optional_and_never_serves_var(service, monkeypatch, tmp_path):
    client = client_for(service)
    module = importlib.import_module("ehds_desk.api")
    root = tmp_path / "site"
    root.mkdir()
    monkeypatch.setattr(module, "REPO_ROOT", root)
    assert TestClient(module.create_app(service)).get("/").status_code == 404
    web = root / "web"
    web.mkdir()
    (web / "index.html").write_text('<main id="app">API fixture</main>', encoding="utf-8")
    (web / "app.js").write_text("/* test asset */", encoding="utf-8")
    (root / "var").mkdir()
    (root / "var" / "secret.txt").write_text("p-1234abcd", encoding="utf-8")
    client = TestClient(module.create_app(service))
    assert 'id="app"' in client.get("/").text
    assert 'id="app"' in client.get("/spe/R05-abcdef12").text
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/UNKNOWN").status_code == 404
    for path in ("/var/secret.txt", "/spe/R05-abcdef12/spe.duckdb", "/..%2Fvar%2Fsecret.txt"):
        assert client.get(path).status_code == 404
        assert "p-1234abcd" not in client.get(path).text


def test_module_exports_cli_app(service):
    client_for(service)
    assert isinstance(importlib.import_module("ehds_desk.api").app, FastAPI)
