"""Our own new requests (new_requests/N01-N07) checked against an independent brute-force calculation.

The reference below reads the CSV files with the csv module and applies the rules directly; it shares
no code with the desk's parser or executor.
"""
import csv
import unittest
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from desk.pipeline import Desk, answer_of

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ["Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg", "Steiermark", "Tirol",
           "Vorarlberg", "Wien"]
HOLDERS = ["Klinikum Nord", "Klinikum Süd", "Klinikum West"]


def rows(name):
    with (ROOT / "data" / f"{name}.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cnt(n):
    return "<10" if n < 10 else n


def pct(a, b):
    if a < 10 or b < 10:
        return "suppressed"
    return float((Decimal(a) * 100 / Decimal(b)).quantize(Decimal("0.1"), ROUND_HALF_UP))


class Reference:
    def __init__(self):
        pts = [p for p in rows("patients") if p["opted_out"] == "false"]
        self.p = {p["patient_id"]: p for p in pts}
        self.age = {k: 2025 - int(v["birth_date"][:4]) for k, v in self.p.items()}
        self.cond = [c for c in rows("conditions") if c["patient_id"] in self.p]
        self.med = [m for m in rows("medications") if m["patient_id"] in self.p]
        self.obs = [o for o in rows("observations") if o["patient_id"] in self.p]
        self.enc = [e for e in rows("encounters") if e["patient_id"] in self.p]

    def has_condition(self, prefix):
        return {c["patient_id"] for c in self.cond if c["icd10"].startswith(prefix)}


class NewRequestsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desk = Desk()
        cls.ref = Reference()

    def process(self, rid):
        return self.desk.process((ROOT / "new_requests" / f"{rid}.json").read_text(encoding="utf-8"))

    def test_n01_primary_icd10_by_hospital(self):
        case = self.process("N01")
        self.assertEqual(case["decision"]["outcome"], "APPROVE_STATISTICAL")
        exp = defaultdict(int)
        for e in self.ref.enc:
            if e["type"] == "inpatient" and e["start_date"].startswith("2025") and e["primary_icd10"].startswith("I50"):
                exp[e["data_holder"]] += 1
        self.assertEqual(answer_of(case), {h: [cnt(exp[h])] for h in HOLDERS})

    def test_n02_stays_versus_distinct_patients(self):
        case = self.process("N02")
        stays, pats = defaultdict(int), defaultdict(set)
        for e in self.ref.enc:
            if e["type"] == "inpatient" and e["start_date"].startswith("2025"):
                stays[e["data_holder"]] += 1
                pats[e["data_holder"]].add(e["patient_id"])
        self.assertEqual(answer_of(case), {h: [cnt(stays[h]), cnt(len(pats[h]))] for h in HOLDERS})
        self.assertTrue(any(stays[h] != len(pats[h]) for h in HOLDERS))

    def test_n03_spe_cohort(self):
        case = self.process("N03")
        self.assertEqual(case["decision"]["outcome"], "APPROVE_SPE")
        hf = self.ref.has_condition("I50")
        stay = {e["patient_id"] for e in self.ref.enc if e["type"] == "inpatient"}
        cohort = {p for p in hf & stay if self.ref.age[p] >= 18}
        self.assertEqual(case["result"]["cohort_size"], len(cohort))
        self.assertEqual(set(case["result"]["tables"]), {"encounters", "conditions", "medications"})

    def test_n04_credit_scoring_rejected(self):
        case = self.process("N04")
        self.assertEqual((case["decision"]["outcome"], case["decision"]["articles"]), ("REJECT", ["54"]))

    def test_n05_latest_egfr_threshold_by_sex_and_band(self):
        case = self.process("N05")
        latest = {}
        for o in self.ref.obs:
            if o["loinc"] == "62238-1" and (o["patient_id"] not in latest or o["date"] > latest[o["patient_id"]][0]):
                latest[o["patient_id"]] = (o["date"], Decimal(o["value"]))
        ckd = self.ref.has_condition("N18")
        bands = [("0-64", 0, 64), ("65-79", 65, 79), ("80+", 80, 999)]
        exp = {}
        for sex in ("female", "male"):
            for label, lo, hi in bands:
                grp = [p for p in ckd if p in latest and self.ref.p[p]["sex"] == sex and lo <= self.ref.age[p] <= hi]
                low = [p for p in grp if latest[p][1] < 45]
                exp[f"{sex} · {label}"] = [cnt(len(grp)), cnt(len(low)), pct(len(low), len(grp))]
        self.assertEqual(answer_of(case), exp)

    def test_n06_vocabulary_only_terms(self):
        case = self.process("N06")
        t2d = {p for p in self.ref.has_condition("E11") if self.ref.age[p] >= 18}
        statin = {m["patient_id"] for m in self.ref.med if m["atc"].startswith("C10AA")
                  and m["start_date"] <= "2025-12-31" and (not m["end_date"] or m["end_date"] >= "2025-12-31")}
        exp = {}
        for r in REGIONS:
            grp = [p for p in t2d if self.ref.p[p]["region"] == r]
            on = [p for p in grp if p in statin]
            exp[r] = [cnt(len(grp)), cnt(len(on)), pct(len(on), len(grp))]
        self.assertEqual(answer_of(case), exp)

    def test_n07_length_of_stay_mean_and_median(self):
        import datetime as dt
        case = self.process("N07")
        self.assertEqual(case["fulfilment"]["status"], "RELEASED")
        exp = {}
        for h in HOLDERS:
            stays = [e for e in self.ref.enc if e["type"] == "inpatient" and e["start_date"].startswith("2025")
                     and e["data_holder"] == h]
            days = sorted((dt.date.fromisoformat(e["end_date"]) - dt.date.fromisoformat(e["start_date"])).days
                          for e in stays)
            mid = len(days) // 2
            median = Decimal(days[mid]) if len(days) % 2 else (Decimal(days[mid - 1]) + Decimal(days[mid])) / 2
            r1 = lambda x: float(Decimal(x).quantize(Decimal("0.1"), ROUND_HALF_UP))
            exp[h] = [cnt(len(stays)), r1(Decimal(sum(days)) / len(days)), r1(median)]
        self.assertEqual(answer_of(case), exp)

    def test_n08_maximum_is_refused_for_privacy(self):
        case = self.process("N08")
        self.assertEqual(case["decision"]["outcome"], "APPROVE_STATISTICAL")
        self.assertEqual(case["fulfilment"]["status"], "NOT_PRODUCED")
        self.assertIn("single patient", case["fulfilment"]["error"]["message"])
        self.assertIsNone(case["result"])


if __name__ == "__main__":
    unittest.main()
