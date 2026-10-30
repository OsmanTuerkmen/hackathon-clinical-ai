from conftest import load
from fastapi.testclient import TestClient

from app.api import app

c = TestClient(app)


def test_flow_and_spe_download_blocked():
    assert c.get("/api/health").json()["ok"]
    r = c.post("/api/requests", json=load("track/requests/R05.json") | {"id": "apiR05"})
    assert r.status_code == 202
    d = c.get("/api/requests/apiR05").json()
    assert d["status"] == "decided" and d["decision"]["outcome"] == "APPROVE_SPE"
    ws = c.get("/api/spe/spe_apiR05").json()
    assert ws["cohort_size"] == 1152
    dl = c.get("/api/spe/spe_apiR05/download")
    assert dl.status_code == 403 and dl.json()["article"] == "73"
    events = [e["event"] for e in c.get("/api/requests/apiR05").json()["audit"]]
    assert "spe.download_blocked" in events
    assert c.get("/api/health").json()["audit_chain_valid"]


def test_suppressed_cells_never_reach_client():
    c.post("/api/requests", json=load("track/requests/R08.json") | {"id": "apiR08"})
    d = c.get("/api/requests/apiR08").json()
    for row in d["result"]["rows"]:
        for k, v in row.items():
            if isinstance(v, dict) and v.get("display") in ("<10", "suppressed"):
                assert v["value"] is None


def test_validation_and_override():
    assert c.post("/api/requests", json={"requested_as": "nope"}).status_code == 422
    c.post("/api/requests", json=load("track/requests/R01.json") | {"id": "apiR01"})
    assert c.post("/api/requests/apiR01/override", json={"decision": "REJECT"}).status_code == 422  # needs a reason
    r = c.post("/api/requests/apiR01/override", json={"decision": "REJECT", "note": "phone check", "actor": "staff:test"})
    assert r.json()["decision"]["outcome"] == "REJECT" and r.json()["flags"]["overridden"]
