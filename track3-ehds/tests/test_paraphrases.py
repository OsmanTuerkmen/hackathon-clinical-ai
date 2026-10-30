"""Robustness: paraphrased, reordered and re-cased versions of the supplied requests must give the same
answers as requests/expected.json (expected.json is read only here, to compare)."""
import copy
import json
import random
import re
import unittest
from pathlib import Path

from desk.evaluate import compare_answer
from desk.pipeline import Desk, answer_of

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = json.loads((ROOT / "requests" / "expected.json").read_text(encoding="utf-8"))


def load(rid):
    return json.loads((ROOT / "requests" / f"{rid}.json").read_text(encoding="utf-8"))


def variant(rid, **changes):
    r = copy.deepcopy(load(rid))
    r.update(changes)
    return r


PARAPHRASES = {
    "R01": [
        dict(definitions=["Adults = patients aged 18 years or older on 31 December 2025.",
                          "Type 2 diabetes = a diagnosis with an ICD-10 code beginning with E11.",
                          "Prevalence = adults with type 2 diabetes divided by all adults × 100, one decimal.",
                          "Report by region: number of adults, number of adults with type 2 diabetes and prevalence (%)."]),
        dict(definitions=["Report for each region: adults; adults with type 2 diabetes; % of adults with type 2 diabetes "
                          "(one decimal)."]),
        dict(definitions=["Adult = aged 18+ on 31 December 2025.", "T2D = ICD-10 code E11.",
                          "Report per Bundesland: adults, adults with T2D, share of adults with T2D in %."]),
        dict(definitions=["Adult = at least 18 years old on 31 December 2025.",
                          "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                          "Report per region: adults, adults with type 2 diabetes, prevalence of type 2 diabetes among "
                          "adults (%)."]),
    ],
    "R03": [
        dict(definitions=["Atrial fibrillation (AF) = any condition with ICD-10 code I48.",
                          "Age bands (age on 31 December 2025): 65–74, 75–84, 85 and older.",
                          "Oral anticoagulant (OAC) = ATC B01AA or B01AF.",
                          "A medication is active on 31 December 2025 if start_date is on or before that day and end_date "
                          "is empty or on or after that day.",
                          "Report per age band: patients with AF, of whom without an active OAC, and their share (%), one "
                          "decimal."]),
        dict(definitions=["Atrial fibrillation = any condition with an ICD-10 code starting with I48.",
                          "Age groups on 31 December 2025: 65-74, 75-84, 85+.",
                          "Oral anticoagulant = ATC code starting with B01AA or B01AF.",
                          "Report per age group: patients with atrial fibrillation, how many of them have no currently "
                          "active oral anticoagulant, and that share in %, one decimal."]),
    ],
    "R05": [
        dict(question="Please provide pseudonymised diagnoses, prescriptions and HbA1c measurements of adults with type 2 "
                      "diabetes and at least one HbA1c measurement.",
             definitions=["Adult = aged 18 or older on 31 December 2025.",
                          "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
                          "Cohort = adults with type 2 diabetes and at least one HbA1c value (LOINC 4548-4).",
                          "Report the size of the cohort."]),
    ],
    "R07": [
        dict(definitions=["Inpatient stay = an encounter of type inpatient.",
                          "Count encounters, not patients, that started in 2025.",
                          "Report per region of residence: inpatient stays."]),
        dict(definitions=["Hospital stay = encounter with type 'inpatient'.",
                          "Count stays (not patients) with a start_date between 2025-01-01 and 2025-12-31.",
                          "Report per patient region: hospital stays."]),
    ],
    "R08": [
        dict(definitions=["Breast cancer = ICD-10 code C50.", "Women = female patients.",
                          "Use the most recent BMI (LOINC 39156-5) for each patient; patients without a BMI value are "
                          "excluded.",
                          "Report per region: women with a BMI (count) and their mean BMI (one decimal)."]),
        dict(definitions=["Breast cancer = any condition with an ICD-10 code starting with C50.",
                          "Women = sex 'female'.",
                          "Use the latest BMI (LOINC 39156-5) per patient; patients without a BMI are left out.",
                          "Report per region: number of women with a BMI, average BMI, one decimal."]),
    ],
    "R09": [
        dict(definitions=["Adult = aged 18 or older on 31 December 2025.", "Hypertension = ICD-10 code I10.",
                          "ACE inhibitors = ATC codes starting with C09AA.", "ARBs = ATC codes starting with C09CA.",
                          "A medication is active on 31 December 2025 if start_date is on or before that day and end_date "
                          "is empty or on or after that day.",
                          "Age bands on 31 December 2025: 18-49, 50-64, 65+.",
                          "Report per age band: adults with hypertension, percentage with an active ACE inhibitor, "
                          "percentage with an active ARB (one decimal)."]),
    ],
}

REJECTIONS = {
    "R02": "We want to adjust private health insurance tariffs for diabetics according to their real risk.",
    "R04": "We plan a promotional campaign for doctors in the regions where SGLT2 inhibitors are prescribed most.",
    "R06": "HR wants to know which employees have depression so that we can decide on contract extensions.",
    "R10": "We develop flavoured nicotine products and want to know which age groups have COPD.",
}


class ParaphraseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desk = Desk()

    def check(self, rid, req, label):
        case = self.desk.process(req)
        exp = EXPECTED[rid]
        d = case["decision"]
        self.assertEqual((d["outcome"], set(d["articles"])), (exp["decision"], set(exp["articles"])), label)
        if exp["answer"] is not None:
            err = (case["fulfilment"].get("error") or {}).get("message")
            ours = answer_of(case)
            if ours and "cohort_size" not in ours:  # group labels keep the applicant's wording ("85 and older")
                ours = {re.sub(r"^(\d+) and older$", r"\1+", k): v for k, v in ours.items()}
            ok, problems = compare_answer(exp["answer"], ours)
            self.assertTrue(ok, f"{label}: {problems or err}")
        return case

    def test_paraphrased_definitions(self):
        for rid, variants in PARAPHRASES.items():
            for i, changes in enumerate(variants, 1):
                with self.subTest(request=rid, variant=i):
                    self.check(rid, variant(rid, **changes), f"{rid} paraphrase {i}")

    def test_spe_paraphrase_keeps_data_minimisation(self):
        case = self.check("R05", variant("R05", **PARAPHRASES["R05"][0]), "R05 paraphrase")
        self.assertEqual(case["result"]["tables"]["observations"]["filter"], {"loinc": ["4548-4"]})
        self.assertEqual(set(case["result"]["tables"]), {"conditions", "medications", "observations"})

    def test_definition_order_does_not_matter(self):
        rnd = random.Random(7)
        for rid in ("R01", "R03", "R05", "R07", "R08", "R09"):
            for k in range(3):
                req = copy.deepcopy(load(rid))
                defs = req["definitions"]
                req["definitions"] = list(reversed(defs)) if k == 0 else rnd.sample(defs, len(defs))
                with self.subTest(request=rid, order=k):
                    self.check(rid, req, f"{rid} order {k}")

    def test_letter_case_does_not_matter(self):
        for rid in ("R01", "R03", "R07", "R08", "R09"):
            for fn in (str.lower, str.upper):
                req = copy.deepcopy(load(rid))
                req["definitions"] = [fn(d) for d in req["definitions"]]
                with self.subTest(request=rid, case=fn.__name__):
                    self.check(rid, req, f"{rid} {fn.__name__}")

    def test_rephrased_prohibited_purposes(self):
        for rid, purpose in REJECTIONS.items():
            with self.subTest(request=rid):
                self.check(rid, variant(rid, purpose=purpose), f"{rid} rephrased")


if __name__ == "__main__":
    unittest.main()
