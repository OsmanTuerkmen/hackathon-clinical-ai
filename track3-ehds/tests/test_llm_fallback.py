"""Optional LLM fallback: only request text is sent, and every proposal is validated before any query."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from desk.datastore import DataStore
from desk.llm import LLMPlanner
from desk.pipeline import Desk
from tests.minidata import build

# The rule-based parser cannot read "people suffering from" + an undefined disease name -> fallback is used.
REQUEST = {
    "id": "L1", "applicant": {"name": "Secret Name", "organisation": "Secret Org", "country": "AT"},
    "requested_as": "health data request", "requested_format": "anonymised statistics",
    "purpose": "Research on atrial fibrillation care.",
    "question": "How many people suffering from AF are there per hospital?",
    "definitions": ["Report per hospital: people suffering from AF-type arrhythmia."],
}
VALID_PLAN = {
    "version": 1, "mode": "statistics",
    "concepts": {"af": {"kind": "condition", "label": "Atrial fibrillation", "icd10": [{"code": "I48", "match": "prefix"}]}},
    "population": {"op": "all"},
    "dimensions": [{"type": "data_holder", "groups": []}],
    "measures": [{"id": "m1", "type": "count_patients", "label": "Patients with AF",
                  "set": {"op": "has_condition", "id": "af"}, "visible": True}],
}


class FakeModel:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, system, user):
        self.calls.append(user)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


class LLMFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="desk-llm-"))
        (cls.tmp / "data").mkdir()
        cls.store = DataStore(build().write(cls.tmp / "data"))

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def desk(self, reply):
        model = FakeModel(reply)
        return Desk(store=self.store, spe_dir=self.tmp / "spe", planner=LLMPlanner(model, "fake-llm")), model

    def test_valid_proposal_is_validated_and_executed(self):
        desk, model = self.desk(VALID_PLAN)
        case = desk.process(REQUEST)
        self.assertEqual(case["fulfilment"]["status"], "RELEASED")
        self.assertTrue(case["planner"]["llm_used"])
        self.assertEqual([r["cells"]["m1"] for r in case["result"]["rows"]], ["<10", "<10", "<10"])
        sent = json.loads(model.calls[0])
        self.assertEqual(set(sent["request"]), {"requested_as", "requested_format", "purpose", "question", "definitions"})
        self.assertNotIn("Secret", model.calls[0])
        self.assertNotRegex(model.calls[0], r"p-[0-9a-f]{8}")

    def test_invalid_proposal_is_refused(self):
        bad = json.loads(json.dumps(VALID_PLAN))
        bad["concepts"]["af"]["icd10"] = [{"code": "I48' OR 1=1 --", "match": "prefix"}]
        desk, _ = self.desk(bad)
        case = desk.process(REQUEST)
        self.assertEqual(case["fulfilment"]["status"], "NOT_PRODUCED")
        self.assertIn("failed validation", case["fulfilment"]["error"]["message"])

    def test_model_may_decline(self):
        desk, _ = self.desk({"error": "the request is ambiguous"})
        case = desk.process(REQUEST)
        self.assertEqual(case["fulfilment"]["status"], "NOT_PRODUCED")
        self.assertIn("declined", case["fulfilment"]["error"]["message"])

    def test_model_not_called_when_rules_succeed(self):
        desk, model = self.desk(VALID_PLAN)
        ok = dict(REQUEST, definitions=["Report per hospital: patients with atrial fibrillation."])
        case = desk.process(ok)
        self.assertEqual(case["fulfilment"]["status"], "RELEASED")
        self.assertEqual(model.calls, [])

    def test_decision_is_never_delegated(self):
        desk, model = self.desk(VALID_PLAN)
        case = desk.process(dict(REQUEST, purpose="We set insurance premiums for customers with heart disease."))
        self.assertEqual(case["decision"]["outcome"], "REJECT")
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
