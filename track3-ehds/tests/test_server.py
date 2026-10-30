"""HTTP API: SPE download blocking and static file safety (server runs in a thread on a free port)."""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from desk.datastore import DataStore
from desk.pipeline import Desk
from desk.server import App, make_handler
from tests.minidata import build

SPE_REQUEST = {
    "id": "S1", "applicant": {"name": "T", "organisation": "Uni", "country": "AT"},
    "requested_as": "health data access application", "requested_format": "pseudonymised records",
    "purpose": "We validate a prediction model. It needs individual-level histories; aggregates are not enough.",
    "question": "Provide pseudonymised conditions and medications for patients with atrial fibrillation.",
    "definitions": ["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                    "Cohort = patients with atrial fibrillation.", "Report the size of the cohort."],
}


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="desk-http-"))
        (cls.tmp / "data").mkdir()
        cls.desk = Desk(store=DataStore(build().write(cls.tmp / "data")), spe_dir=cls.tmp / "spe")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(cls.desk, quiet=True)))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.token = None
        cls.token = cls.sign_in("lena")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.desk.store.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def raw_call(cls, path, data=None, method=None, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        req = urllib.request.Request(cls.base + path, data=data, method=method or ("POST" if data else "GET"),
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read()

    @classmethod
    def sign_in(cls, person, state="s1"):
        """Simulated ID Austria flow: approve at the mock IdP, then exchange the one-time code for a session."""
        _, body = cls.raw_call("/idp-sim/approve", json.dumps({"person": person, "state": state,
                                                               "redirect_uri": "/"}).encode())
        code = parse_qs(urlparse(json.loads(body)["redirect"]).query)["code"][0]
        _, body = cls.raw_call("/api/auth/token", json.dumps({"code": code}).encode())
        return json.loads(body)["token"]

    def call(self, path, data=None, method=None):
        return self.raw_call(path, data, method, token=self.token if path == "/api/submit" else None)

    def test_submitting_requires_the_simulated_id_austria_sign_in(self):
        payload = json.dumps(SPE_REQUEST).encode()
        status, body = self.raw_call("/api/submit", payload)
        self.assertEqual(status, 401)
        self.assertIn("ID Austria", json.loads(body)["message"])
        status, body = self.call("/api/submit", payload)
        view = json.loads(body)
        self.assertEqual((status, view["submitted_by"]["name"]), (200, "Dr. Lena Gruber"))
        status, body = self.raw_call(f"/api/cases/{view['case_id']}")
        identity = json.loads(body)["identity"]
        self.assertEqual((identity["eidas_loa"], identity["method"]), ("high", "ID Austria (simulated)"))
        self.assertTrue(identity["bpk_gh"].startswith("GH:"))

    def test_id_austria_simulation_rejects_misuse(self):
        status, _ = self.raw_call("/idp-sim/approve", json.dumps({"person": "lena", "state": "x",
                                                                  "redirect_uri": "https://evil.example/"}).encode())
        self.assertEqual(status, 400, "open redirect")
        _, body = self.raw_call("/idp-sim/approve", json.dumps({"person": "lena", "state": "x",
                                                                "redirect_uri": "/"}).encode())
        code = parse_qs(urlparse(json.loads(body)["redirect"]).query)["code"][0]
        self.assertEqual(self.raw_call("/api/auth/token", json.dumps({"code": code}).encode())[0], 200)
        self.assertEqual(self.raw_call("/api/auth/token", json.dumps({"code": code}).encode())[0], 400, "code reuse")
        token = self.sign_in("sophie")
        self.assertEqual(self.raw_call("/api/auth/me", token=token)[0], 200)
        self.raw_call("/api/auth/logout", b"{}", token=token)
        self.assertEqual(self.raw_call("/api/auth/me", token=token)[0], 401)
        self.assertEqual(self.raw_call("/api/submit", json.dumps(SPE_REQUEST).encode(), token=token)[0], 401)

    def test_spe_download_is_blocked_and_logged(self):
        status, body = self.call("/api/submit", json.dumps(SPE_REQUEST).encode())
        view = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(view["decision"]["outcome"], "APPROVE_SPE")
        self.assertEqual(view["result"]["cohort_size"], 6)
        wid = view["result"]["workspace_id"]
        for method, path in (("GET", f"/api/spe/{wid}/download"), ("POST", f"/api/spe/{wid}/download"),
                             ("GET", f"/api/spe/{wid}/download/conditions")):
            status, body = self.call(path, data=b"" if method == "POST" else None, method=method)
            self.assertEqual(status, 403, path)
            self.assertEqual(json.loads(body)["error"], "download_blocked")
            self.assertNotRegex(body.decode(), r"p-[0-9a-f]{8}")
        status, body = self.call(f"/api/spe/{wid}")
        info = json.loads(body)
        self.assertEqual(info["manifest"]["download_policy"], "blocked")
        self.assertNotRegex(body.decode(), r"p-[0-9a-f]{8}", "manifest must not contain records")
        self.assertGreaterEqual(sum(e["result"] == "BLOCKED" for e in info["access_log"]), 3)

    def test_spe_analysis_needs_the_permit_token_and_masks_small_cells(self):
        status, body = self.call("/api/submit", json.dumps(SPE_REQUEST).encode())
        res = json.loads(body)["result"]
        wid, token = res["workspace_id"], res["permit_token"]
        q = json.dumps({"table": "conditions", "column": "icd10"}).encode()
        status, body = self.call(f"/api/spe/{wid}/analyse", q)
        self.assertEqual(status, 401)
        req = urllib.request.Request(self.base + f"/api/spe/{wid}/analyse", data=q, method="POST",
                                     headers={"X-Permit-Token": token})
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.loads(r.read())
        self.assertEqual({row["value"] for row in out["rows"]}, {"I48.0", "I48.2"})
        self.assertTrue(all(row["patients"] == "<10" for row in out["rows"]))
        self.assertNotRegex(json.dumps(out), r"p-[0-9a-f]{8}")
        bad = urllib.request.Request(self.base + f"/api/spe/{wid}/analyse", method="POST",
                                     data=json.dumps({"table": "conditions", "column": "patient_id"}).encode(),
                                     headers={"X-Permit-Token": token})
        try:
            urllib.request.urlopen(bad, timeout=10)
            self.fail("patient-level column accepted")
        except urllib.error.HTTPError as e:
            with e:
                self.assertEqual(e.code, 400)

    def test_case_register_and_access_log_survive_a_restart(self):
        state = self.tmp / "state"
        desk = Desk(store=self.desk.store, spe_dir=self.tmp / "spe", state_dir=state)
        case = desk.process(SPE_REQUEST)
        desk.spe.request_download(case["result"]["workspace_id"])
        again = Desk(store=self.desk.store, spe_dir=self.tmp / "spe", state_dir=state)
        self.assertEqual(again.get_case(case["case_id"])["fingerprint"], case["fingerprint"])
        self.assertTrue(any(e["result"] == "BLOCKED" for e in again.spe.log_for(case["result"]["workspace_id"])))
        self.assertNotRegex((state / "cases.jsonl").read_text(), r"p-[0-9a-f]{8}")

    def test_workspace_and_data_files_are_not_served(self):
        for path in ("/static/../spe_workspaces/x/workspace.sqlite", "/static/%2e%2e/data/patients.csv",
                     "/static/../desk/config.py", "/api/requests/expected", "/api/spe/../../data/download"):
            status, _ = self.call(path)
            self.assertEqual(status, 404, path)

    def test_malformed_http_input_gets_clean_errors(self):
        status, body = self.call("/api/submit", b"\xff\xfe\x00garbage")
        self.assertEqual(status, 400)
        self.assertIn("UTF-8", body.decode())
        status, body = self.call("/api/submit", b"x" * (70 * 1024))
        self.assertEqual(status, 413)
        req = urllib.request.Request(self.base + "/api/submit", data=b"{}", method="POST",
                                     headers={"Content-Length": "-5"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("negative Content-Length accepted")
        except urllib.error.HTTPError as e:
            with e:
                self.assertEqual(e.code, 400)
        status, _ = self.call("/api/does-not-exist")
        self.assertEqual(status, 404)

    def test_concurrent_submissions_are_consistent(self):
        from concurrent.futures import ThreadPoolExecutor
        stats = dict(SPE_REQUEST, requested_as="health data request", requested_format="anonymised statistics",
                     purpose="Research on atrial fibrillation care.",
                     definitions=["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                                  "Report per hospital: patients with atrial fibrillation."])
        payloads = [json.dumps(SPE_REQUEST if i % 2 else stats).encode() for i in range(24)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda p: self.call("/api/submit", p), payloads))
        self.assertTrue(all(s == 200 for s, _ in results))
        answers = set()
        for _, b in results:  # the per-permit token is a credential, not part of the answer
            res = {k: v for k, v in json.loads(b)["result"].items() if k != "permit_token"}
            answers.add(json.dumps(res, sort_keys=True))
        self.assertEqual(len(answers), 2, "identical requests must give identical answers under load")

    def test_statistical_answer_over_http(self):
        req = dict(SPE_REQUEST, requested_as="health data request", requested_format="anonymised statistics",
                   purpose="Research on atrial fibrillation care.",
                   definitions=["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                                "Report per hospital: patients with atrial fibrillation."])
        status, body = self.call("/api/submit", json.dumps(req).encode())
        view = json.loads(body)
        self.assertEqual(view["decision"]["outcome"], "APPROVE_STATISTICAL")
        cells = [r["cells"]["m1"] for r in view["result"]["rows"]]
        self.assertEqual(cells, ["<10", "<10", "<10"])
        self.assertNotRegex(body.decode(), r"p-[0-9a-f]{8}")


if __name__ == "__main__":
    unittest.main()
