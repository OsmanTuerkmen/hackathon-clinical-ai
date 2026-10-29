"""Difficult data rules on a miniature dataset with known answers (see tests/minidata.py)."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from desk.datastore import DataStore
from desk.executor import Executor, released_json
from desk.ir import validate
from desk.parser import build_plan
from desk.pipeline import Desk
from desk.request_schema import parse_request
from tests.minidata import build

ACTIVE = ("A medication is active on 31 December 2025 if start_date is on or before that day and end_date is empty "
          "or on or after that day.")


def request(definitions, question="How many patients?", purpose="Research to improve care for patients.",
            requested_as="health data request", fmt="anonymised statistics"):
    return {"id": "T", "applicant": {"name": "Test", "organisation": "Test", "country": "AT"},
            "requested_as": requested_as, "requested_format": fmt, "purpose": purpose, "question": question,
            "definitions": definitions}


class MiniDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="desk-test-"))
        cls.mini = build()
        (cls.tmp / "data").mkdir()
        cls.store = DataStore(cls.mini.write(cls.tmp / "data"))
        cls.desk = Desk(store=cls.store, spe_dir=cls.tmp / "spe")

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_raw(self, req):
        plan = build_plan(parse_request(req), "statistics", self.desk.catalog)
        validate(plan)
        result, internal = Executor(self.store, plan).run_statistics()
        released = released_json(result)
        raw = {tuple(c["group"]): c["raw"] for c in internal.cells}
        rows = {tuple(r["group"]): r["cells"] for r in released["rows"]}
        return plan, released, raw, rows

    # ------------------------------------------------------------------ small cells and empty groups
    def test_zero_and_small_cells_and_empty_groups(self):
        req = request(["Adult = aged 18 or older on 31 December 2025.",
                       "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Report per region: adults with type 2 diabetes."])
        plan, released, raw, rows = self.run_raw(req)
        self.assertEqual(len(released["rows"]), 9, "all nine federal states must be listed")
        self.assertEqual(rows[("Tirol",)]["m1"], 12)
        self.assertEqual(rows[("Wien",)]["m1"], "<10")           # 9 patients
        self.assertEqual(rows[("Salzburg",)]["m1"], "<10")       # 0 patients, still shown
        self.assertEqual(raw[("Salzburg",)]["m1"]["n"], 0)

    # ------------------------------------------------------------------ opt-outs
    def test_opted_out_patients_excluded_everywhere(self):
        self.assertEqual(self.store.stats["patients_opted_out"], 7)
        opted = sorted(self.store.opted_out_ids)
        marks = ",".join("?" * len(opted))
        for table in ("patients", "conditions", "observations", "encounters", "medications"):
            n = self.store.query(f"SELECT COUNT(*) FROM {table} WHERE patient_id IN ({marks})", opted)[0][0]
            self.assertEqual(n, 0, f"opted-out rows found in {table}")
        req = request(["Adult = aged 18 or older on 31 December 2025.",
                       "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Report per region: adults with type 2 diabetes."])
        _, _, raw, rows = self.run_raw(req)
        self.assertEqual(raw[("Tirol",)]["m1"]["n"], 12)   # would be 17 with the five opted-out patients
        self.assertEqual(raw[("Wien",)]["m1"]["n"], 9)     # would be exactly 10 (and shown) with the opted-out one
        self.assertEqual(rows[("Wien",)]["m1"], "<10")

    # ------------------------------------------------------------------ latest observation + half-up mean
    def test_latest_observation_and_half_up_mean(self):
        req = request(["Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Use the latest BMI (LOINC 39156-5) per patient; patients without a BMI are left out.",
                       "Report per region: patients with type 2 diabetes and mean BMI, one decimal."],
                      question="What is the mean BMI of patients with type 2 diabetes by region?")
        _, _, raw, rows = self.run_raw(req)
        self.assertEqual(rows[("Tirol",)]["m1"], 12)              # the child without BMI is left out
        self.assertEqual(rows[("Tirol",)]["m2"], 27.3)            # latest values average 27.25 -> 27.3
        self.assertEqual(raw[("Tirol",)]["m2"]["sum"], "327")     # 6 x 27.0 + 6 x 27.5 (old 40.0 ignored)
        self.assertEqual(rows[("Wien",)]["m1"], "<10")
        self.assertEqual(rows[("Wien",)]["m2"], "suppressed")     # mean of 9 patients

    def test_earliest_value_rule_is_respected(self):
        req = request(["Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Use the earliest BMI (LOINC 39156-5) per patient.",
                       "Report per region: patients with type 2 diabetes who have a BMI and their mean BMI."])
        _, _, _, rows = self.run_raw(req)
        self.assertEqual(rows[("Tirol",)]["m2"], 40.0)

    # ------------------------------------------------------------------ active medications
    def test_active_medication_on_reference_date(self):
        req = request(["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                       "Oral anticoagulant = ATC code starting with B01AA or B01AF.", ACTIVE,
                       "Report per region: patients with atrial fibrillation and how many of them have an active "
                       "oral anticoagulant."])
        plan, _, raw, _ = self.run_raw(req)
        self.assertEqual(raw[("Steiermark",)]["m1"]["n"], 6)
        self.assertEqual(raw[("Steiermark",)]["m2"]["n"], 3)
        ex = Executor(self.store, plan)
        ids = set(ex.cohort_ids(plan["measures"][1]["set"]))
        af = self.mini.af
        self.assertEqual(ids, {af["active_open"], af["ends_on_ref"], af["starts_on_ref"]})

    def test_without_active_rule_any_prescription_counts(self):
        req = request(["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                       "Oral anticoagulant = ATC code starting with B01AA or B01AF.",
                       "Report per region: patients with atrial fibrillation and how many of them have an oral "
                       "anticoagulant."])
        _, _, raw, _ = self.run_raw(req)
        self.assertEqual(raw[("Steiermark",)]["m2"]["n"], 5)

    # ------------------------------------------------------------------ encounters vs patients, hospitals
    def test_encounter_versus_patient_counts_by_hospital(self):
        req = request(["Inpatient stay = encounter with type 'inpatient'.",
                       "Count stays (not patients) whose start_date is in 2025.",
                       "Report per hospital: inpatient stays and patients with an inpatient stay."],
                      question="How many inpatient stays and patients by hospital?")
        plan, released, raw, rows = self.run_raw(req)
        self.assertEqual([m["type"] for m in plan["measures"]], ["count_encounters", "count_patients"])
        self.assertEqual(raw[("Klinikum Nord",)]["m1"]["n"], 3)   # p1 has three stays (p5 opted out)
        self.assertEqual(raw[("Klinikum Nord",)]["m2"]["n"], 1)   # ... but is one patient
        self.assertEqual(raw[("Klinikum Süd",)]["m1"]["n"], 2)    # p2 and p6 (p3 is 2024)
        self.assertEqual(raw[("Klinikum West",)]["m1"]["n"], 0)
        self.assertEqual([r["group"][0] for r in released["rows"]], ["Klinikum Nord", "Klinikum Süd", "Klinikum West"])
        self.assertEqual(rows[("Klinikum West",)]["m1"], "<10")

    # ------------------------------------------------------------------ primary_icd10
    def test_primary_icd10_filter_on_inpatient_stays(self):
        for definition in ("Heart failure stay = inpatient stay whose primary_icd10 starts with I50.",
                           "Heart failure stay = inpatient stay with a main diagnosis of heart failure."):
            req = request(["Inpatient stay = encounter with type 'inpatient'.", definition,
                           "Count stays (not patients) whose start_date is in 2025.",
                           "Report per hospital: heart failure stays."],
                          question="How many heart failure stays by hospital?")
            plan, _, raw, _ = self.run_raw(req)
            hf = plan["concepts"][plan["measures"][0]["encounter"]]
            self.assertEqual(hf["primary_icd10"], ["I50"], definition)
            self.assertEqual(raw[("Klinikum Nord",)]["m1"]["n"], 2, definition)  # J18.9 stay excluded
            self.assertEqual(raw[("Klinikum Süd",)]["m1"]["n"], 1, definition)   # p6: HF in conditions, K35.8 stay

    # ------------------------------------------------------------------ percentages
    def test_percentage_suppression(self):
        req = request(["Adult = aged 18 or older on 31 December 2025.",
                       "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Use the latest BMI (LOINC 39156-5) per patient.",
                       "High BMI = latest BMI of 27.5 or higher.",
                       "Report per region: adults with type 2 diabetes, % with a BMI, % with high BMI, one decimal."])
        _, _, raw, rows = self.run_raw(req)
        self.assertEqual(rows[("Tirol",)]["m3"], 100.0)               # 12 / 12
        self.assertEqual(raw[("Tirol",)]["m5"], {"numerator": 6, "denominator": 12})
        self.assertEqual(rows[("Tirol",)]["m5"], "suppressed")        # numerator 6 < 10
        self.assertEqual(rows[("Wien",)]["m3"], "suppressed")         # denominator 9 < 10
        self.assertNotIn("m2", rows[("Tirol",)], "helper counts must stay internal")

    # ------------------------------------------------------------------ patient-level output is refused
    def test_patient_level_report_is_refused(self):
        case = self.desk.process(request(["Diabetes = any condition with an ICD-10 code starting with E11.",
                                          "Report for each patient: patient ID, birth date and onset date."]))
        self.assertEqual(case["decision"]["outcome"], "APPROVE_STATISTICAL")
        self.assertEqual(case["fulfilment"]["status"], "NOT_PRODUCED")
        self.assertIn("patient-level", case["fulfilment"]["error"]["message"])
        self.assertIsNone(case["result"])

    def test_released_statistics_contain_no_patient_records(self):
        texts = []
        for defs in (["Report per region: patients with type 2 diabetes."],
                     ["Inpatient stay = encounter with type 'inpatient'.", "Report per hospital: inpatient stays."]):
            case = self.desk.process(request(defs))
            self.assertEqual(case["fulfilment"]["status"], "RELEASED")
            texts.append(json.dumps(case["result"]))
        for t in texts:
            self.assertNotRegex(t, r"p-[0-9a-f]{8}")
            self.assertNotRegex(t, r"e\d{6}")

    # ------------------------------------------------------------------ secure processing environment
    def test_spe_contains_only_cohort_and_requested_record_types(self):
        req = request(["Adult = aged 18 or older on 31 December 2025.",
                       "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                       "Cohort = adults with type 2 diabetes who have at least one BMI value (LOINC 39156-5).",
                       "Report the size of the cohort you would make available."],
                      question="Provide pseudonymised conditions and BMI values for adults with type 2 diabetes.",
                      purpose="We train a prediction model; it needs individual-level histories, aggregates are not "
                              "enough.",
                      requested_as="health data access application", fmt="pseudonymised records")
        case = self.desk.process(req)
        self.assertEqual(case["decision"]["outcome"], "APPROVE_SPE")
        self.assertEqual(case["result"]["cohort_size"], 21)  # 12 Tirol + 9 Wien; child and opted-out excluded
        wid = case["result"]["workspace_id"]
        db = self.desk.spe.path(wid) / "workspace.sqlite"
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"cohort", "conditions", "observations"})
            cohort = {r[0] for r in con.execute("SELECT patient_id FROM cohort")}
            self.assertFalse(cohort & self.store.opted_out_ids)
            for t in ("conditions", "observations"):
                ids = {r[0] for r in con.execute(f"SELECT DISTINCT patient_id FROM {t}")}
                self.assertTrue(ids <= cohort, t)
            self.assertEqual({r[0] for r in con.execute("SELECT DISTINCT loinc FROM observations")}, {"39156-5"})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 33)
        finally:
            con.close()
        status, body = self.desk.spe.request_download(wid)
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "download_blocked")
        self.assertNotRegex(json.dumps(body), r"p-[0-9a-f]{8}")
        self.assertTrue(all(c["status"] == "pass" for c in case["privacy_checks"]), case["privacy_checks"])


if __name__ == "__main__":
    unittest.main()
