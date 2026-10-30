"""The ten supplied requests on the real synthetic data (expected.json is used only to compare)."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from desk.evaluate import compare_answer
from desk.pipeline import Desk, answer_of

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = json.loads((ROOT / "requests" / "expected.json").read_text(encoding="utf-8"))


def load(rid):
    return json.loads((ROOT / "requests" / f"{rid}.json").read_text(encoding="utf-8"))


class SuppliedRequestsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desk = Desk()

    def test_decisions_articles_and_numbers(self):
        """Matches requests/expected.json (compared only after the answers were produced)."""
        for rid, exp in EXPECTED.items():
            case = self.desk.process(load(rid))
            d = case["decision"]
            self.assertEqual(d["outcome"], exp["decision"], rid)
            self.assertEqual(set(d["articles"]), set(exp["articles"]), rid)
            if exp["answer"] is not None:
                ok, problems = compare_answer(exp["answer"], answer_of(case))
                self.assertTrue(ok, f"{rid}: {problems}")
                self.assertTrue(all(c["status"] != "fail" for c in case["privacy_checks"]), rid)

    def test_rejections_query_no_patient_data(self):
        for rid in ("R02", "R04", "R06", "R10"):
            before = len(self.desk.store.query_log)
            case = self.desk.process(load(rid))
            self.assertEqual(case["decision"]["outcome"], "REJECT")
            self.assertEqual(len(self.desk.store.query_log), before, f"{rid} touched the database")
            self.assertFalse(case["patient_data_queried"])
            self.assertIsNone(case["result"])

    def test_not_classified_by_id_or_applicant(self):
        for rid in ("R01", "R02", "R05", "R09"):
            original = self.desk.process(load(rid))
            disguised = copy.deepcopy(load(rid))
            disguised["id"] = "ZZ99"
            disguised["applicant"] = {"name": "Anonymous", "organisation": "Unknown", "country": "XX"}
            other = self.desk.process(disguised)
            self.assertEqual(other["decision"]["outcome"], original["decision"]["outcome"], rid)
            self.assertEqual(answer_of(other), answer_of(original), rid)

    def test_deterministic_results(self):
        for rid in EXPECTED:
            a = self.desk.process(load(rid))["fingerprint"]
            b = self.desk.process(load(rid))["fingerprint"]
            self.assertEqual(a, b, rid)

    def test_runtime_never_reads_expected_answers(self):
        for p in (ROOT / "desk").glob("*.py"):
            if p.name == "evaluate.py":
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                if "expected" in line and any(k in line for k in ("open(", "read_text", "json.load")):
                    self.fail(f"{p.name} reads expected answers: {line.strip()}")

    def test_supplied_files_unchanged(self):
        for line in (ROOT / "challenge.sha256").read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            actual = hashlib.sha256((ROOT / name.strip()).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, f"{name} was modified")


if __name__ == "__main__":
    unittest.main()
