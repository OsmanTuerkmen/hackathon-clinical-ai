"""Definitions -> IR, vocabulary mapping, conservative failure and IR validation."""
import copy
import json
import unittest
from pathlib import Path

from desk.ir import PlanValidationError, validate
from desk.parser import InterpretationError, build_plan
from desk.request_schema import parse_request

ROOT = Path(__file__).resolve().parent.parent


def load(rid):
    return parse_request((ROOT / "requests" / f"{rid}.json").read_text(encoding="utf-8"))


def req(definitions, question="How many patients?"):
    return parse_request({"id": "T", "requested_as": "health data request", "requested_format": "anonymised statistics",
                          "purpose": "Research.", "question": question, "definitions": definitions})


class SuppliedPlansTest(unittest.TestCase):
    def test_r09_percentages_use_hidden_numerators(self):
        plan = build_plan(load("R09"), "statistics")
        validate(plan)
        types = [(m["type"], m["visible"]) for m in plan["measures"]]
        self.assertEqual(types, [("count_patients", True), ("count_patients", False), ("percent", True),
                                 ("count_patients", False), ("percent", True)])
        self.assertEqual([plan["measures"][2]["denominator"], plan["measures"][4]["denominator"]], ["m1", "m1"])
        atc = sorted(c["atc"][0] for c in plan["concepts"].values() if c["kind"] == "medication")
        self.assertEqual(atc, ["C09AA", "C09CA"])
        self.assertEqual(plan["active_rule"]["date"], "2025-12-31")

    def test_r08_population_from_question(self):
        plan = build_plan(load("R08"), "statistics")
        kinds = {c["label"]: c["kind"] for c in plan["concepts"].values()}
        self.assertEqual(kinds["Breast cancer"], "condition")
        self.assertIn("Breast cancer", json.dumps(plan["population_reasons"]))
        bmi = next(c for c in plan["concepts"].values() if c["kind"] == "observation")
        self.assertEqual((bmi["loinc"], bmi["pick"]), ("39156-5", "latest"))

    def test_r07_counts_encounters_in_2025(self):
        plan = build_plan(load("R07"), "statistics")
        m = plan["measures"][0]
        self.assertEqual(m["type"], "count_encounters")
        enc = plan["concepts"][m["encounter"]]
        self.assertEqual((enc["types"], enc["start_from"], enc["start_to"]), (["inpatient"], "2025-01-01", "2025-12-31"))

    def test_r05_spe_record_types(self):
        plan = build_plan(load("R05"), "spe")
        self.assertEqual(plan["spe"]["record_types"], [{"table": "conditions"}, {"table": "medications"},
                                                       {"table": "observations", "loinc": ["4548-4"]}])


class VocabularyTest(unittest.TestCase):
    def test_plain_english_terms_map_to_codes(self):
        plan = build_plan(req(["Report per region: adults aged 18 or older with heart failure and an active statin."]),
                          "statistics")
        concepts = {c["label"]: c for c in plan["concepts"].values()}
        self.assertEqual([x["code"] for x in concepts["Heart failure"]["icd10"]], ["I50"])
        self.assertEqual(concepts["Statins"]["atc"], ["C10AA"])
        self.assertEqual(concepts["Heart failure"]["source"], "vocabulary")

    def test_measurement_without_code_uses_vocabulary(self):
        plan = build_plan(req(["Use the latest systolic blood pressure per patient.",
                               "Report per sex: patients with a systolic blood pressure and their mean systolic "
                               "blood pressure."]), "statistics")
        obs = next(c for c in plan["concepts"].values() if c["kind"] == "observation")
        self.assertEqual(obs["loinc"], "8480-6")


class ConservativeFailureTest(unittest.TestCase):
    def assertFails(self, definitions, fragment, question="How many patients?"):
        with self.assertRaises(InterpretationError) as ctx:
            build_plan(req(definitions, question), "statistics")
        self.assertIn(fragment, ctx.exception.message)

    def test_unknown_terms_are_not_ignored(self):
        self.assertFails(["Report per region: patients with frobnitis."], "frobnitis")
        self.assertFails(["Diabetes = any condition with an ICD-10 code starting with E11 except E11.9.",
                          "Report per region: patients with diabetes."], "except")

    def test_unsupported_grouping(self):
        self.assertFails(["Report per municipality: patients."], "municipality")

    def test_patient_level_output(self):
        self.assertFails(["Report for each patient: patient ID and birth date."], "patient-level")

    def test_mean_needs_a_value_rule(self):
        self.assertFails(["Report per region: patients with an HbA1c value and their mean HbA1c."], "which HbA1c")

    def test_unused_definition_is_ambiguous(self):
        self.assertFails(["Obesity = any condition with an ICD-10 code starting with E66.",
                          "Report per region: patients with asthma."], "Obesity")

    def test_overlapping_age_bands(self):
        self.assertFails(["Age bands on 31 December 2025: 18-50, 50-64.", "Report per band: patients."], "overlap")

    def test_band_report_needs_bands(self):
        self.assertFails(["Report per age band: patients."], "no age bands")


class NegationScopeTest(unittest.TestCase):
    def measure_set(self, line, question="How many patients?", extra=()):
        plan = build_plan(req(list(extra) + [line], question), "statistics")
        return plan["measures"][0]["set"]

    def test_without_a_or_b_means_neither(self):
        s = self.measure_set("Report per sex: patients without asthma or COPD.")
        self.assertEqual(s["op"], "not")
        self.assertEqual(s["arg"]["op"], "or")

    def test_neither_nor_and_explicit_forms(self):
        for line in ("Report per sex: patients with neither asthma nor COPD.",
                     "Report per sex: patients without asthma and without COPD."):
            s = self.measure_set(line)
            self.assertEqual([a["op"] for a in s["args"]], ["not", "not"], line)
        s = self.measure_set("Report per sex: patients without asthma and with COPD.")
        self.assertEqual([a["op"] for a in s["args"]], ["not", "has_condition"])

    def test_ambiguous_negation_is_refused(self):
        with self.assertRaises(InterpretationError) as ctx:
            self.measure_set("Report per sex: patients without asthma and COPD.")
        self.assertIn("ambiguous", ctx.exception.message)

    def test_negated_mention_in_question_is_not_used_as_filter(self):
        with self.assertRaises(InterpretationError) as ctx:
            self.measure_set("Report per region: patients with hypertension.",
                             question="How many patients with hypertension but without diabetes are there?",
                             extra=["Diabetes = any condition with an ICD-10 code starting with E11."])
        self.assertIn("negated", ctx.exception.message)

    def test_words_that_would_be_silently_dropped_are_refused(self):
        for line in ("Report per sex: patients whose first diagnosis is asthma.",
                     "Report per sex: patients with the most visits."):
            with self.assertRaises(InterpretationError, msg=line):
                self.measure_set(line)


class ValidatorTest(unittest.TestCase):
    def test_validator_rejects_malformed_plans(self):
        plan = build_plan(load("R04"), "statistics")
        validate(plan)
        bad = copy.deepcopy(plan)
        next(c for c in bad["concepts"].values() if c["kind"] == "medication")["atc"] = ["A10BK'; DROP TABLE x;--"]
        with self.assertRaises(PlanValidationError):
            validate(bad)
        bad = copy.deepcopy(plan)
        bad["measures"][0]["set"] = {"op": "has_condition", "id": "does_not_exist"}
        with self.assertRaises(PlanValidationError):
            validate(bad)
        bad = copy.deepcopy(plan)
        bad["population"] = {"op": "raw_sql", "sql": "SELECT * FROM patients"}
        with self.assertRaises(PlanValidationError):
            validate(bad)


if __name__ == "__main__":
    unittest.main()
