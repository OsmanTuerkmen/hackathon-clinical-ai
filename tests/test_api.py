import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accessdesk.api import create_app


@pytest.fixture(scope="module")
def client(data_dir, tmp_path_factory):
    app = create_app(data_dir, runtime_dir=tmp_path_factory.mktemp("api-runtime"))
    with TestClient(app) as test_client:
        yield test_client


def _request(data_dir, request_id):
    path = Path(data_dir).parent / "requests" / f"{request_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _submit_body():
    return {
        "request": {
            "id": "client-selected",
            "applicant": {"name": "New Researcher", "organisation": "Local University", "country": "AT"},
            "requested_as": "health data request",
            "purpose": "Research on chronic kidney disease prevalence.",
            "question": "How many people have chronic kidney disease?",
            "definitions": ["Chronic kidney disease = ICD-10 code starting with N18."],
        },
        "login": "New Researcher",
    }


def test_system_and_staff_case_endpoints(client):
    health = client.get("/api/health")
    assert health.json() == {"ok": True}
    assert health.headers["content-type"] == "application/json; charset=utf-8"
    assert client.get("/openapi.json").headers["content-type"] == "application/json; charset=utf-8"
    info = client.get("/api/info").json()
    assert (info["patients"], info["opted_out"], info["mode"], info["version"]) == (
        20_000, 839, "central", "2.0",
    )
    assert info["counts"]["review_needed"] == 1
    assert client.get("/api/settings").json()["differencing_guard"] is True
    assert len(client.get("/api/identities").json()) == 14

    summaries = client.get("/api/cases").json()
    assert len(summaries) == 15
    detail = client.get("/api/cases/R01").json()
    assert detail["summary"]["id"] == "R01"
    assert set(detail["result"]["five_safes"]) == {
        "people", "projects", "data", "settings", "outputs",
    }
    assert client.get("/api/cases/missing").status_code == 404
    assert client.get("/api/cases/missing").headers["content-type"] == "application/json; charset=utf-8"


def test_precheck_shows_prohibited_evidence_without_releasing_values(client):
    before = client.get("/api/audit?limit=300").json()
    response = client.post("/api/precheck", json={
        "request": {
            "applicant": {"name": "Draft User", "organisation": "Health Marketing Agency", "country": "AT"},
            "requested_as": "health data request",
            "purpose": "We plan an advertising campaign for a new medicine.",
            "question": "How many people have asthma?",
            "definitions": ["Asthma = ICD-10 code starting with J45."],
        },
        "login": "Draft User",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["decision"]["decision"] == "REJECT"
    assert result["art54"][0]["category"] == "marketing"
    assert result["art54"][0]["evidence"]
    assert "released" not in result and "answer" not in result
    assert all(
        not isinstance(code["rows"], int) or code["rows"] >= 10
        for mapping in result["mappings"] for code in mapping["codes"]
    )
    assert client.get("/api/audit?limit=300").json() == before


def test_precheck_art54_evidence_drops_contained_phrases(client):
    result = client.post("/api/precheck", json={
        "request": {
            "applicant": {"name": "Draft User", "organisation": "Alpenland Insurance", "country": "AT"},
            "requested_as": "health data request",
            "purpose": "We want to align private health insurance premiums with actual risk.",
            "question": "What is the average HbA1c?",
            "definitions": ["HbA1c = LOINC 4548-4."],
        },
    }).json()
    phrases = [item["phrase"] for item in result["art54"][0]["evidence"]]
    assert "insurance premiums" in phrases
    assert "premiums" not in phrases


def test_submit_validates_and_persists_a_custom_case(client):
    invalid = client.post("/api/submit", json={"request": {"question": "?"}})
    assert invalid.status_code == 422

    response = client.post("/api/submit", json=_submit_body())
    assert response.status_code == 200
    assert response.json()["id"] == "U01"
    assert response.json()["summary"]["group"] == "custom"
    assert client.get("/api/cases/U01").json()["result"]["request"]["id"] == "U01"


def test_applicant_access_hides_held_results_and_checks_login(client):
    own = client.get("/api/applicant/cases?login=Dr. Nina Hofbauer").json()
    assert any(summary["id"] == "R09" for summary in own)

    allowed = client.get("/api/applicant/cases/R09?login=Dr. Nina Hofbauer")
    assert allowed.status_code == 200
    assert allowed.json()["visible"]
    assert allowed.json()["released"]

    assert client.get("/api/applicant/cases/R09?login=Someone Else").status_code == 403
    held = client.get("/api/applicant/cases/D04?login=Dr. Eva Lang").json()
    assert not held["visible"]
    assert "released" not in held and "funnel" not in held


def test_staff_review_audit_and_letter_routes(client):
    short = client.post("/api/cases/R01/review", json={
        "action": "hold", "reason": "too short", "reviewer": "Staff",
    })
    assert short.status_code == 422
    reviewed = client.post("/api/cases/R01/review", json={
        "action": "release",
        "reason": "The evidence has been reviewed and the result may be released.",
        "reviewer": "Staff reviewer",
    })
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "released"
    assert client.get("/api/cases/R01/audit").json()[0]["action"] == "case_reviewed"
    assert client.get("/api/audit/verify").json()["ok"]

    letter = client.get("/api/cases/R01/letter?lang=de").json()
    assert letter["header"]["reference"] == "HDAB-AT/2026/R01"
    assert letter["operative"].startswith("Ihrer Gesundheitsdatenanfrage")
    assert client.get("/api/cases/R01/letter?lang=fr").status_code == 422


def test_stateless_decision_and_public_register_are_privacy_safe(client, data_dir):
    decision = client.post("/api/decide", json=_request(data_dir, "R01")).json()
    assert decision["decision"] == "APPROVE_STATISTICAL"
    assert decision["answer"]["Wien"]["adults"] == 3247

    register = client.get("/api/register").json()
    payload = json.dumps(register, ensure_ascii=False)
    assert register["legal_basis"].startswith("Art. 57")
    assert "Lechner" not in payload
    assert "532" not in payload and "6.2" not in payload
    assert "p-" not in payload
    held = next(entry for entry in register["entries"] if entry["id"] == "D04")
    assert held["publication_status"] == "in_review"
    assert "decision" not in held
    r05 = next(entry for entry in register["entries"] if entry["id"] == "R05")
    assert any(
        item["label_en"] == "measurements (LOINC 4548-4 only)"
        for item in r05["permit"]["record_types"]
    )


def test_register_preserves_organisation_and_templates_are_served(client):
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "demo" / "requests" / "D03.json").read_text(encoding="utf-8"))
    register = client.get("/api/register").json()
    entry = next(item for item in register["entries"] if item["id"] == "D03")
    assert entry["organisation"] == source["applicant"]["organisation"]
    assert client.get("/api/templates").json() == json.loads(
        (root / "demo" / "templates.json").read_text(encoding="utf-8")
    )


def test_article_titles_use_official_short_titles():
    from accessdesk.safes.projects import ARTICLE_TITLES

    assert ARTICLE_TITLES == {
        "53": ("Purposes for secondary use", "Zwecke der Sekundärnutzung"),
        "54": ("Prohibited secondary use", "Unerlaubte Sekundärnutzung"),
        "57": ("Tasks of health data access bodies", "Aufgaben der Zugangsstellen für Gesundheitsdaten"),
        "61": ("Duties of health data users", "Pflichten der Gesundheitsdatennutzer"),
        "66": ("Data minimisation and purpose limitation", "Datenminimierung und Zweckbindung"),
        "67": ("Health data access applications", "Anträge auf Zugang zu Gesundheitsdaten"),
        "68": ("Data permit", "Datengenehmigung"),
        "69": ("Health data request", "Gesundheitsdatenanfrage"),
        "71": ("Right to opt out", "Recht zum Widerspruch"),
        "73": ("Secure processing environment", "Sichere Verarbeitungsumgebung"),
    }


def test_spe_authorization_query_download_and_export_review(client):
    manifest = client.get("/api/cases/R05").json()["result"]["spe"]
    permit = manifest["permit_id"]
    login = "Dr. Amir Hadžić"

    assert client.get(f"/api/spe/{permit}?login=Intruder").status_code == 403
    preview = client.get(f"/api/spe/{permit}?login={login}").json()
    assert preview["manifest"]["permit_id"] == permit

    query = client.post(f"/api/spe/{permit}/query", json={
        "sql": "SELECT patient_id FROM cohort LIMIT 2", "login": login,
    })
    assert query.status_code == 200
    denied = client.post(f"/api/spe/{permit}/query", json={
        "sql": "SELECT * FROM read_csv('C:/private.csv')", "login": login,
    })
    assert denied.status_code == 400
    blocked = client.get(f"/api/spe/{permit}/download")
    assert blocked.status_code == 403
    assert "Art. 73(2)" in blocked.json()["detail"]["en"]
    assert client.get(f"/api/spe/{permit}/export/raw").status_code == 403

    rejected = client.post(f"/api/spe/{permit}/exports", json={
        "sql": "SELECT patient_id FROM cohort LIMIT 2",
        "title": "Raw patients",
        "note": "",
        "login": login,
    }).json()
    assert rejected["status"] == "rejected_auto"
    assert client.post(f"/api/exports/{rejected['id']}/review", json={
        "action": "approve",
        "reason": "The records are safe and reviewed for release.",
        "reviewer": "Staff reviewer",
    }).status_code == 409
    small = client.post(f"/api/spe/{permit}/exports", json={
        "sql": "SELECT 5 AS count",
        "title": "Small count",
        "note": "",
        "login": login,
    }).json()
    assert small["status"] == "rejected_auto"
    oversized = client.post(f"/api/spe/{permit}/exports", json={
        "sql": "SELECT i AS value FROM range(1001) t(i)",
        "title": "Large record output",
        "note": "",
        "login": login,
    }).json()
    assert oversized["status"] == "rejected_auto"
    assert any(reason["code"] == "record_level" for reason in oversized["check"]["reasons"])

    export = client.post(f"/api/spe/{permit}/exports", json={
        "sql": "SELECT COUNT(*) AS n FROM cohort",
        "title": "Cohort size",
        "note": "Aggregate count for review.",
        "login": login,
    }).json()
    assert export["status"] == "pending_review"
    assert client.get(f"/api/exports/{export['id']}/download?login={login}").status_code == 403
    assert client.post(f"/api/exports/{export['id']}/review", json={
        "action": "approve",
        "reason": "This aggregate contains no personal or small-cell data.",
        "reviewer": "Staff reviewer",
    }).status_code == 200
    downloaded = client.get(f"/api/exports/{export['id']}/download?login={login}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("text/csv")
    assert downloaded.headers["content-disposition"].endswith(f"export_{export['id']}.csv\"")


def test_static_root_serves_the_build_or_fallback(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    if (Path(__file__).resolve().parents[1] / "web" / "dist").is_dir():
        assert '<div id="root"></div>' in response.text
    else:
        assert "Frontend not built" in response.text
