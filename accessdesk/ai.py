"""Optional structured AI operations with a local content-addressed cache."""
import hashlib
import importlib
import json
import os
import threading
from pathlib import Path

from . import ai_spec
from .atomic import write_json_atomic

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Assistant:
    def __init__(self, runtime_root):
        self.root = Path(runtime_root)
        self.cache_path = self.root / "ai_cache.json"
        self.lock = threading.RLock()

    def _api_key(self):
        key = os.environ.get("ANTHROPIC_API_KEY")
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
            name, value = line.split("=", 1)
            if name.strip() == "ANTHROPIC_API_KEY":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                return value or None
        return None

    @staticmethod
    def _anthropic_module():
        try:
            return importlib.import_module("anthropic")
        except ImportError:
            return None

    def status(self):
        enabled_by_config = os.environ.get("ACCESSDESK_AI", "").strip().casefold() != "off"
        if not enabled_by_config:
            reason = "disabled"
        elif not self._api_key():
            reason = "no_api_key"
        elif self._anthropic_module() is None:
            reason = "anthropic_not_installed"
        else:
            reason = None
        return {"enabled": reason is None, "model": ai_spec.MODEL, "reason": reason}

    def call(self, task, system, user, schema):
        status = self.status()
        result = {
            "value": None,
            "reason": status["reason"],
            "model": status["model"],
            "cached": False,
        }
        if not status["enabled"]:
            return result
        key = self._api_key()
        anthropic = self._anthropic_module()
        cache_key = hashlib.sha256(json.dumps(
            [task, ai_spec.MODEL, system, user, schema],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with self.lock:
            cache = self._read_cache()
            if cache_key in cache:
                return {**result, "value": cache[cache_key], "cached": True}
            try:
                response = anthropic.Anthropic(api_key=key).messages.create(
                    model=ai_spec.MODEL,
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
                return {**result, "reason": "api_error"}
            stop_reason = getattr(response, "stop_reason", None)
            if stop_reason in ("refusal", "max_tokens"):
                return {**result, "reason": stop_reason}
            try:
                block = next(
                    item for item in response.content
                    if getattr(item, "type", None) == "text"
                )
                value = json.loads(block.text)
                if not isinstance(value, dict):
                    raise ValueError("Expected a JSON object")
            except (AttributeError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
                return {**result, "reason": "invalid_json"}
            cache[cache_key] = value
            write_json_atomic(self.cache_path, cache)
            return {**result, "value": value, "reason": None}

    def _read_cache(self):
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


def status():
    return Assistant(PROJECT_ROOT / "runtime").status()
