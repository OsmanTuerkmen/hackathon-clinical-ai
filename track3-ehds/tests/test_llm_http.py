"""LLM fallback over real HTTP: a local server speaking the Anthropic Messages and OpenAI Chat Completions
wire formats checks headers, request bodies and response parsing end to end (no API key needed)."""
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from desk.datastore import DataStore
from desk.llm import from_environment
from desk.pipeline import Desk
from tests.minidata import build
from tests.test_llm_fallback import REQUEST, VALID_PLAN


class FakeProvider(BaseHTTPRequestHandler):
    calls: list = []
    fail = False

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeProvider.calls.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                   "body": body})
        if FakeProvider.fail:
            self.send_response(500)
            self.end_headers()
            return
        plan = json.dumps(VALID_PLAN)
        if self.path == "/v1/messages":
            out = {"content": [{"type": "text", "text": f"Here is the plan:\n{plan}"}]}
        else:
            out = {"choices": [{"message": {"content": plan}}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class LLMOverHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="desk-llm-http-"))
        (cls.tmp / "data").mkdir()
        cls.store = DataStore(build().write(cls.tmp / "data"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        FakeProvider.calls = []
        FakeProvider.fail = False

    def run_with(self, provider, key_var):
        env = {"DESK_LLM_PROVIDER": provider, "DESK_LLM_MODEL": "test-model", key_var: "test-key",
               "DESK_LLM_BASE_URL": self.base}
        with mock.patch.dict(os.environ, env):
            desk = Desk(store=self.store, spe_dir=self.tmp / "spe", planner=from_environment())
        return desk.process(REQUEST)

    def test_anthropic_wire_format(self):
        case = self.run_with("anthropic", "ANTHROPIC_API_KEY")
        self.assertEqual(case["fulfilment"]["status"], "RELEASED")
        self.assertTrue(case["planner"]["llm_used"])
        call = FakeProvider.calls[0]
        self.assertEqual(call["path"], "/v1/messages")
        self.assertEqual(call["headers"]["x-api-key"], "test-key")
        self.assertEqual(call["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual((call["body"]["model"], call["body"]["temperature"]), ("test-model", 0))
        sent = json.loads(call["body"]["messages"][0]["content"])
        self.assertEqual(set(sent["request"]), {"requested_as", "requested_format", "purpose", "question", "definitions"})
        self.assertNotIn("Secret", json.dumps(call["body"]))

    def test_openai_wire_format(self):
        case = self.run_with("openai", "OPENAI_API_KEY")
        self.assertEqual(case["fulfilment"]["status"], "RELEASED")
        call = FakeProvider.calls[0]
        self.assertEqual(call["path"], "/v1/chat/completions")
        self.assertEqual(call["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(call["body"]["response_format"], {"type": "json_object"})
        self.assertEqual([m["role"] for m in call["body"]["messages"]], ["system", "user"])

    def test_provider_failure_fails_closed(self):
        FakeProvider.fail = True
        case = self.run_with("anthropic", "ANTHROPIC_API_KEY")
        self.assertEqual(case["fulfilment"]["status"], "NOT_PRODUCED")
        self.assertIn("unavailable", case["fulfilment"]["error"]["message"])
        self.assertIsNone(case["result"])


if __name__ == "__main__":
    unittest.main()
