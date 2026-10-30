"""Optional structured AI operations with a local content-addressed cache."""
import hashlib
import importlib
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import ai_spec
from .atomic import write_json_atomic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
# Verified 2026-10-30: stable model and free-tier tokens per
# https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash and
# https://ai.google.dev/gemini-api/docs/pricing.


class Assistant:
    def __init__(self, runtime_root):
        self.root = Path(runtime_root)
        self.cache_path = self.root / "ai_cache.json"
        self.lock = threading.RLock()

    @staticmethod
    def _configured_key(name):
        key = os.environ.get(name)
        if key and key.strip():
            return key.strip()
        env_path = PROJECT_ROOT / ".env"
        if not env_path.is_file():
            return None
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key_name, value = line.split("=", 1)
            if key_name.strip() == name:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                return value or None
        return None

    def _api_key(self):
        return self._configured_key("ANTHROPIC_API_KEY")

    def _gemini_key(self):
        return self._configured_key("GEMINI_API_KEY")

    def _provider(self):
        configured = os.environ.get("ACCESSDESK_AI_PROVIDER", "").strip().casefold()
        if configured in ("claude", "anthropic"):
            return "claude"
        if configured == "gemini":
            return "gemini"
        if configured:
            return configured
        if self._api_key():
            return "claude"
        if self._gemini_key():
            return "gemini"
        return "claude"

    @staticmethod
    def _model(provider):
        override = os.environ.get("ACCESSDESK_AI_MODEL", "").strip()
        if override:
            return override
        return GEMINI_MODEL if provider == "gemini" else ai_spec.MODEL

    @staticmethod
    def _anthropic_module():
        try:
            return importlib.import_module("anthropic")
        except ImportError:
            return None

    def status(self):
        provider = self._provider()
        model = self._model(provider)
        enabled_by_config = os.environ.get("ACCESSDESK_AI", "").strip().casefold() != "off"
        if not enabled_by_config:
            reason = "disabled"
        elif provider not in ("claude", "gemini"):
            reason = "invalid_provider"
        elif provider == "claude" and not self._api_key():
            reason = "no_api_key"
        elif provider == "gemini" and not self._gemini_key():
            reason = "no_api_key"
        elif provider == "claude" and self._anthropic_module() is None:
            reason = "anthropic_not_installed"
        else:
            reason = None
        return {
            "enabled": reason is None,
            "provider": provider,
            "model": model,
            "reason": reason,
        }

    def call(self, task, system, user, schema, cache_only=False):
        status = self.status()
        result = {
            "value": None,
            "reason": status["reason"],
            "model": status["model"],
            "provider": status["provider"],
            "cached": False,
        }
        if not status["enabled"]:
            return result
        provider = status["provider"]
        key = self._api_key() if provider == "claude" else self._gemini_key()
        cache_key = hashlib.sha256(json.dumps(
            [provider, status["model"], task, system, user, schema],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with self.lock:
            cache = self._read_cache()
            if cache_key in cache:
                return {**result, "value": cache[cache_key], "cached": True}
            if cache_only:
                return {**result, "reason": "cache_miss"}
            try:
                if provider == "claude":
                    value, reason = self._call_claude(
                        key, task, status["model"], system, user, schema,
                    )
                else:
                    value, reason = self._call_gemini(
                        key, task, status["model"], system, user, schema,
                    )
            except Exception:
                return {**result, "reason": "api_error"}
            if reason:
                return {**result, "reason": reason}
            cache[cache_key] = value
            write_json_atomic(self.cache_path, cache)
            return {**result, "value": value, "reason": None}

    def _call_claude(self, key, task, model, system, user, schema):
        anthropic = self._anthropic_module()
        try:
            response = anthropic.Anthropic(api_key=key).messages.create(
                model=model,
                max_tokens=ai_spec.MAX_TOKENS[task],
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": ai_spec.EFFORT[task],
                    "format": {"type": "json_schema", "schema": schema},
                },
                timeout=30,
            )
        except Exception:
            return None, "api_error"
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason in ("refusal", "max_tokens"):
            return None, stop_reason
        try:
            block = next(
                item for item in response.content
                if getattr(item, "type", None) == "text"
            )
            value = json.loads(block.text)
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
        except (AttributeError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
            return None, "invalid_json"
        return value, None

    @staticmethod
    def _call_gemini(key, task, model, system, user, schema):
        url = f"{GEMINI_ENDPOINT}/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": ai_spec.MAX_TOKENS[task],
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return None, "quota_exhausted"
            if exc.code in (401, 403):
                return None, "authentication_error"
            return None, "api_error"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None, "api_error"
        try:
            candidate = body["candidates"][0]
            finish_reason = candidate.get("finishReason")
            if finish_reason == "MAX_TOKENS":
                return None, "max_tokens"
            if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST"):
                return None, "refusal"
            text = next(
                part["text"]
                for part in candidate["content"]["parts"]
                if isinstance(part.get("text"), str)
            )
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
        except (KeyError, IndexError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
            return None, "invalid_json"
        return value, None

    def _read_cache(self):
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


def status():
    return Assistant(PROJECT_ROOT / "runtime").status()
