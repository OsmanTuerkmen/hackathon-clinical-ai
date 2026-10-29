import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from accessdesk import ai_spec
from accessdesk.ai import Assistant
from accessdesk.api import create_app
from accessdesk.config import load_requests


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeAnthropic:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def response(value, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(value))],
    )


def fake_assistant(tmp_path, monkeypatch, reply):
    monkeypatch.setenv("ACCESSDESK_AI", "on")
    assistant = Assistant(tmp_path)
    client = FakeAnthropic(reply)
    monkeypatch.setattr(assistant, "_api_key", lambda: "test-secret")
    monkeypatch.setattr(
        assistant,
        "_anthropic_module",
        lambda: SimpleNamespace(Anthropic=lambda **kwargs: client),
    )
    return assistant, client


def test_structured_response_is_cached_without_a_second_client_call(tmp_path, monkeypatch):
    value = {"prohibited": False}
    assistant, client = fake_assistant(tmp_path, monkeypatch, response(value))

    first = assistant.call("purpose", "system prompt", "user prompt", {"type": "object"})
    second = assistant.call("purpose", "system prompt", "user prompt", {"type": "object"})

    assert first["value"] == value
    assert first["cached"] is False
    assert second["value"] == value
    assert second["cached"] is True
    assert len(client.messages.calls) == 1
    assert client.messages.calls[0]["output_config"]["effort"] == "low"


def test_refusal_is_returned_as_no_answer(tmp_path, monkeypatch):
    assistant, _ = fake_assistant(
        tmp_path,
        monkeypatch,
        response({"prohibited": False}, stop_reason="refusal"),
    )

    outcome = assistant.call("purpose", "system prompt", "user prompt", {"type": "object"})

    assert outcome["value"] is None
    assert outcome["reason"] == "refusal"


def test_purpose_disagreement_holds_delivery_and_flags_unverified_quote(desk, data_dir, monkeypatch):
    request = next(
        request for group, request in load_requests(data_dir)
        if request["id"] == "R01"
    )
    monkeypatch.setattr(desk.ai, "status", lambda: {
        "enabled": True, "model": "fake-model", "reason": None,
    })
    monkeypatch.setattr(desk.ai, "call", lambda *args: {
        "value": {
            "prohibited": True,
            "evidence_quote": "fabricated quote",
        },
        "reason": None,
        "model": "fake-model",
        "cached": False,
    })

    result = desk.process(request, use_cache=False, login="Dr. Sophie Lechner")

    assert result["decision"]["decision"] == "APPROVE_STATISTICAL"
    assert result["decision"]["articles"] == ["53", "69"]
    assert result["ai"]["agrees"] is False
    assert result["ai"]["opinion"]["evidence_quote_verified"] is False
    assert result["delivery"]["status"] == "on_hold_review"


def test_ai_term_mapping_rejects_unknown_or_empty_codes(desk, monkeypatch):
    monkeypatch.setattr(desk.ai, "call", lambda *args: {
        "value": {"system": "icd10", "codes": ["ZZZ99"], "note": "not in data"},
        "reason": None, "model": "fake-model", "cached": False,
    })
    assert desk._map_term("unknown condition", "unsupported condition") is None
    with desk.store.lock:
        present = {
            row[0] for row in desk.store.con.execute(
                "SELECT DISTINCT icd10 FROM conditions"
            ).fetchall()
        }
    no_row_code = next(
        code for code in ai_spec.allowed_codes(desk.store)
        if not any(value.startswith(code) for value in present)
    )
    monkeypatch.setattr(desk.ai, "call", lambda *args: {
        "value": {"system": "icd10", "codes": [no_row_code], "note": "no matching rows"},
        "reason": None, "model": "fake-model", "cached": False,
    })
    assert desk._map_term("missing condition", "no rows") is None


def test_ai_draft_is_disabled_or_returns_precheck(tmp_path, data_dir, monkeypatch):
    app = create_app(data_dir, runtime_dir=tmp_path / "runtime")
    client = TestClient(app)
    body = {"text": "How common is asthma?", "lang": "en", "login": "Dr. Sophie Lechner"}
    response = client.post("/api/ai/draft", json=body)
    assert response.status_code == 503
    assert response.json()["detail"]["en"] == "AI is not active (no API key)."

    monkeypatch.setattr(app.state.desk.ai, "status", lambda: {
        "enabled": True, "model": "fake-model", "reason": None,
    })
    monkeypatch.setattr(app.state.desk.ai, "call", lambda *args: {
        "value": {
            "requested_as": "health data request",
            "purpose": "Scientific research on asthma.",
            "question": "How many adults have asthma?",
            "definitions": ["Asthma = any condition with an ICD-10 code starting with J45."],
            "assumptions": [],
            "unsupported": [],
        },
        "reason": None, "model": "fake-model", "cached": True,
    })
    response = client.post("/api/ai/draft", json=body)
    assert response.status_code == 200
    assert response.json()["draft"]["question"] == "How many adults have asthma?"
    assert response.json()["precheck"]["mappings"]
    assert response.json()["model"] == "fake-model"
