import json
import urllib.error
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


def test_ai_explanation_requires_the_visible_applicant_and_returns_bilingual_text(
    tmp_path,
    data_dir,
    monkeypatch,
):
    app = create_app(data_dir, runtime_dir=tmp_path / "runtime")
    client = TestClient(app)
    desk = app.state.desk
    monkeypatch.setattr(desk.ai, "status", lambda: {
        "enabled": True, "model": "fake-model", "reason": None,
    })
    monkeypatch.setattr(desk.ai, "call", lambda *args: {
        "value": {"explanation_de": "Die Statistik ist anonymisiert.", "explanation_en": "The statistics are anonymous."},
        "reason": None, "model": "fake-model", "cached": False,
    })

    denied = client.post("/api/ai/explain/R01?login=Wrong Person")
    assert denied.status_code == 403
    response = client.post("/api/ai/explain/R01?login=Dr.%20Sophie%20Lechner")
    assert response.status_code == 200
    assert response.json()["explanation_en"] == "The statistics are anonymous."


def test_gemini_provider_selection_prefers_anthropic_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    assistant = Assistant(tmp_path)

    assert assistant.status()["provider"] == "gemini"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setattr(Assistant, "_anthropic_module", staticmethod(lambda: object()))
    assert assistant.status()["provider"] == "claude"

    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    assert assistant.status()["provider"] == "gemini"


def test_gemini_rest_request_parses_structured_output_and_uses_cache(tmp_path, monkeypatch):
    from accessdesk import ai

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assistant = Assistant(tmp_path)
    value = {"prohibited": False}
    response_body = {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(value)}]},
            "finishReason": "STOP",
        }],
    }
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(response_body).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    schema = {"type": "object", "properties": {"prohibited": {"type": "boolean"}}}

    first = assistant.call("purpose", "system prompt", "request text", schema)
    second = assistant.call("purpose", "system prompt", "request text", schema)

    assert first["value"] == value
    assert first["provider"] == "gemini"
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.8-flash:generateContent"
    )
    assert request.get_header("X-goog-api-key") == "test-gemini-key"
    assert "test-gemini-key" not in request.full_url
    body = json.loads(request.data)
    assert body["systemInstruction"]["parts"] == [{"text": "system prompt"}]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "request text"}]}]
    assert body["generationConfig"]["responseJsonSchema"] == schema
    assert timeout == 30


def test_gemini_quota_error_returns_a_clear_reason_without_raising(tmp_path, monkeypatch):
    from accessdesk import ai

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assistant = Assistant(tmp_path)

    def quota_error(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 429, "quota exhausted", {}, None,
        )

    monkeypatch.setattr(ai.urllib.request, "urlopen", quota_error)

    result = assistant.call("purpose", "system", "request", {"type": "object"})

    assert result["value"] is None
    assert result["provider"] == "gemini"
    assert result["reason"] == "quota_exhausted"


def test_gemini_draft_quota_is_a_clear_503(tmp_path, data_dir, monkeypatch):
    from accessdesk import ai

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(data_dir, runtime_dir=tmp_path / "runtime")

    def quota_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "quota exhausted", {}, None)

    monkeypatch.setattr(ai.urllib.request, "urlopen", quota_error)
    response = TestClient(app).post(
        "/api/ai/draft",
        json={"text": "How common is asthma?", "lang": "en"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["de"].startswith("Gemini-Kontingent erschöpft")
    assert response.json()["detail"]["en"].startswith("Gemini quota exhausted")


def test_startup_with_gemini_enabled_and_empty_cache_makes_no_network_calls(
    tmp_path, data_dir, monkeypatch,
):
    from accessdesk import ai
    from accessdesk.cases import CaseRegistry
    from accessdesk.config import build_desk

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls = []

    def fail_if_called(request, timeout):
        calls.append(request)
        raise AssertionError("startup attempted an AI network call")

    monkeypatch.setattr(ai.urllib.request, "urlopen", fail_if_called)
    desk = build_desk(data_dir, runtime_dir=tmp_path / "runtime")
    try:
        registry = CaseRegistry(desk, data_dir)
        assert len(registry.list()) == 15
        assert calls == []
    finally:
        desk.store.con.close()


def test_staff_ai_opinion_is_live_cached_and_holds_a_disagreement(
    tmp_path, data_dir, monkeypatch,
):
    from accessdesk import ai

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_response = {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps({
                "prohibited": True,
                "category": "jobs_insurance_credit",
                "allowed_purposes": [],
                "statistics_sufficient": True,
                "evidence_quote": "align private health insurance premiums",
                "explanation_en": "This purpose may discriminate.",
                "explanation_de": "Dieser Zweck kann diskriminieren.",
            })}]},
            "finishReason": "STOP",
        }],
    }
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(fake_response).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    app = create_app(data_dir, runtime_dir=tmp_path / "runtime")
    client = TestClient(app)

    response = client.post("/api/cases/R01/ai-opinion")

    assert response.status_code == 200
    detail = response.json()
    assert detail["result"]["ai"]["opinion"]["prohibited"] is True
    assert detail["summary"]["status"] == "review_needed"
    assert detail["result"]["delivery"]["status"] == "on_hold_review"
    assert len(calls) == 1


def test_gemini_quota_returns_a_localized_503_not_a_server_error(tmp_path, data_dir, monkeypatch):
    from accessdesk import ai

    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(data_dir, runtime_dir=tmp_path / "runtime")

    def quota_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "quota exhausted", {}, None)

    monkeypatch.setattr(ai.urllib.request, "urlopen", quota_error)
    response = TestClient(app).post(
        "/api/ai/draft",
        json={"text": "How common is asthma?", "lang": "en"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["de"].startswith("Gemini-Kontingent erschöpft")
    assert response.json()["detail"]["en"].startswith("Gemini quota exhausted")


def test_info_and_settings_report_the_selected_provider_and_model(tmp_path, data_dir, monkeypatch):
    monkeypatch.setenv("ACCESSDESK_AI", "on")
    monkeypatch.setenv("ACCESSDESK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(create_app(data_dir, runtime_dir=tmp_path / "runtime"))

    info = client.get("/api/info").json()["ai"]
    settings = client.get("/api/settings").json()["ai"]

    assert info["provider"] == settings["provider"] == "gemini"
    assert info["model"] == settings["model"] == "gemini-3.8-flash"
