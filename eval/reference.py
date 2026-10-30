"""Independent CSV reference computations. Standard library only; never prints patient rows.

Run directly: python eval/reference.py [--data PATH]. Task 14 can register new
calculations in EXTRA_REFERENCES; expected values always come from external JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DATE = "2025-12-31"


def find_data_dir() -> Path:
    configured = os.environ.get("TRACK3_DATA", "").strip()
    if configured:
        return Path(configured)
    for ancestor in (ROOT, *ROOT.parents):
        candidate = ancestor / "track3"
        if (candidate / "requests" / "expected.json").is_file():
            return candidate
    raise FileNotFoundError("Set TRACK3_DATA to the external directory containing data/ and requests/.")


class ReferenceData:
    """CSV strings and simple indexes; no application parser, SQL, or disclosure code."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.tables: dict[str, list[dict[str, str]]] = {}
        for name in ("patients", "conditions", "medications", "observations", "encounters"):
            with (self.directory / "data" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.tables[name] = list(csv.DictReader(stream))
        self.regions = sorted({p["region"] for p in self.tables["patients"]})
        self.patients = {p["patient_id"]: p for p in self.tables["patients"]
                         if p["opted_out"].lower() != "true"}
        self.opted_out_ids = {p["patient_id"] for p in self.tables["patients"]
                              if p["opted_out"].lower() == "true"}

    def age(self, patient_id: str) -> int:
        return 2025 - int(self.patients[patient_id]["birth_date"][:4])

    def diagnosed(self, prefix: str) -> set[str]:
        return {r["patient_id"] for r in self.tables["conditions"]
                if r["patient_id"] in self.patients and r["icd10"].startswith(prefix)}

    def active(self, *prefixes: str) -> set[str]:
        return {r["patient_id"] for r in self.tables["medications"]
                if r["patient_id"] in self.patients and r["atc"].startswith(prefixes)
                and r["start_date"] <= REFERENCE_DATE
                and (not r["end_date"] or r["end_date"] >= REFERENCE_DATE)}

    def latest(self, code: str) -> dict[str, Decimal]:
        latest: dict[str, tuple[str, Decimal]] = {}
        for r in self.tables["observations"]:
            pid = r["patient_id"]
            if pid in self.patients and r["loinc"] == code:
                if pid not in latest or r["date"] > latest[pid][0]:
                    latest[pid] = (r["date"], Decimal(r["value"]))
        return {pid: pair[1] for pid, pair in latest.items()}


def _data(data: ReferenceData | None) -> ReferenceData:
    return data if data is not None else ReferenceData(find_data_dir())


def count(n: int) -> int | str:
    return "<10" if n < 10 else n


def rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def percent(num: int, den: int) -> float | str:
    return "suppressed" if min(num, den) < 10 else rounded(Decimal(num) * 100 / Decimal(den))


def r01(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    diabetes = data.diagnosed("E11")
    result = {}
    for region in data.regions:
        adults = {pid for pid, p in data.patients.items() if p["region"] == region and data.age(pid) >= 18}
        cases = adults & diabetes
        result[region] = {"adults": count(len(adults)), "type2_diabetes": count(len(cases)),
                          "prevalence_pct": percent(len(cases), len(adults))}
    return result


def r03(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    af = data.diagnosed("I48")
    oac = data.active("B01AA", "B01AF")
    result = {}
    for label, lo, hi in (("65-74", 65, 74), ("75-84", 75, 84), ("85+", 85, 999)):
        cohort = {pid for pid in af if lo <= data.age(pid) <= hi}
        without = cohort - oac
        result[label] = {"af_patients": count(len(cohort)), "without_oac": count(len(without)),
                         "share_without_oac_pct": percent(len(without), len(cohort))}
    return result


def r05_patient_ids(data: ReferenceData) -> set[str]:
    return {pid for pid in data.diagnosed("E11") & data.latest("4548-4").keys() if data.age(pid) >= 18}


def r05(data: ReferenceData | None = None) -> dict:
    return {"cohort_size": len(r05_patient_ids(_data(data)))}


def r07(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    totals = dict.fromkeys(data.regions, 0)
    for r in data.tables["encounters"]:
        if r["patient_id"] in data.patients and r["type"] == "inpatient" and "2025-01-01" <= r["start_date"] <= REFERENCE_DATE:
            totals[data.patients[r["patient_id"]]["region"]] += 1
    return {region: count(n) for region, n in totals.items()}


def r08(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    cancer = data.diagnosed("C50")
    bmi = data.latest("39156-5")
    result = {}
    for region in data.regions:
        values = [bmi[pid] for pid in cancer & bmi.keys()
                  if data.patients[pid]["region"] == region and data.patients[pid]["sex"] == "female"]
        result[region] = {"women_with_bmi": count(len(values)),
                          "mean_bmi": "suppressed" if len(values) < 10 else rounded(sum(values, Decimal(0)) / len(values))}
    return result


def r09(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    hypertension = data.diagnosed("I10")
    ace, arb = data.active("C09AA"), data.active("C09CA")
    result = {}
    for label, lo, hi in (("18-49", 18, 49), ("50-64", 50, 64), ("65+", 65, 999)):
        cohort = {pid for pid in hypertension if lo <= data.age(pid) <= hi}
        result[label] = {"adults_with_hypertension": count(len(cohort)),
                         "ace_inhibitor_pct": percent(len(cohort & ace), len(cohort)),
                         "arb_pct": percent(len(cohort & arb), len(cohort))}
    return result


def _holder_domain(data: ReferenceData, *, encounters: bool = False) -> list[str]:
    holders = {p["data_holder"] for p in data.tables["patients"]}
    if encounters:
        holders.update(r["data_holder"] for r in data.tables["encounters"])
    return sorted(holders)


def n01(data: ReferenceData | None = None) -> dict:
    """Inpatient J18 stays starting in 2024-2025, grouped by the stay's hospital."""
    data = _data(data)
    totals = dict.fromkeys(_holder_domain(data, encounters=True), 0)
    for row in data.tables["encounters"]:
        if (row["patient_id"] in data.patients and row["type"] == "inpatient"
                and "2024-01-01" <= row["start_date"] <= REFERENCE_DATE
                and row["primary_icd10"].startswith("J18")):
            totals[row["data_holder"]] += 1
    return {holder: count(n) for holder, n in totals.items()}


def _egfr_groups(data: ReferenceData, diagnosis: str, dimension: str) -> dict:
    cohort = data.diagnosed(diagnosis)
    latest = data.latest("62238-1")
    domain = _holder_domain(data) if dimension == "data_holder" else data.regions
    result = {}
    for group in domain:
        values = [latest[pid] for pid in cohort & latest.keys()
                  if data.patients[pid][dimension] == group]
        result[group] = {
            "patients_with_egfr": count(len(values)),
            "mean_egfr": "suppressed" if len(values) < 10 else rounded(sum(values, Decimal(0)) / len(values)),
        }
    return result


def n02(data: ReferenceData | None = None) -> dict:
    """Distinct heart-failure patients with latest eGFR, by the patient's hospital."""
    return _egfr_groups(_data(data), "I50", "data_holder")


def n03(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    asthma = data.diagnosed("J45")
    combination = data.active("R03AK06")
    result = {}
    for region in data.regions:
        cohort = {pid for pid in asthma if data.patients[pid]["region"] == region}
        result[region] = {"asthma_patients": count(len(cohort)),
                          "active_combination_pct": percent(len(cohort & combination), len(cohort))}
    return result


def n05(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    copd = data.diagnosed("J44")
    return {region: count(sum(data.patients[pid]["region"] == region for pid in copd))
            for region in data.regions}


def n06_patient_ids(data: ReferenceData) -> set[str]:
    """Heart-failure cohort; encounters are the only requested SPE record type."""
    return data.diagnosed("I50")


def n06(data: ReferenceData | None = None) -> dict:
    return {"cohort_size": len(n06_patient_ids(_data(data)))}


def n07(data: ReferenceData | None = None) -> dict:
    data = _data(data)
    stroke = data.diagnosed("I63")
    bands = [(f"{low}-{low + 4}", low, low + 4) for low in range(0, 90, 5)] + [("90+", 90, 999)]
    result = {}
    for region in data.regions:
        for sex in sorted({p["sex"] for p in data.tables["patients"]}):
            for label, low, high in bands:
                n = sum(data.patients[pid]["region"] == region and data.patients[pid]["sex"] == sex
                        and low <= data.age(pid) <= high for pid in stroke)
                result[f"{region} / {sex} / {label}"] = count(n)
    return result


def n08(data: ReferenceData | None = None) -> dict:
    return _egfr_groups(_data(data), "N18", "region")


def n10(data: ReferenceData | None = None) -> dict:
    """Count stays (including repeated stays), never condition rows or unique people."""
    data = _data(data)
    bands = [("0-49", 0, 49), ("50-64", 50, 64), ("65-79", 65, 79), ("80+", 80, 999)]
    sexes = sorted({p["sex"] for p in data.tables["patients"]})
    totals = {f"{sex} / {label}": 0 for sex in sexes for label, _low, _high in bands}
    for row in data.tables["encounters"]:
        pid = row["patient_id"]
        if pid not in data.patients or row["type"] != "inpatient" or not row["primary_icd10"].startswith("S72"):
            continue
        for label, low, high in bands:
            if low <= data.age(pid) <= high:
                totals[f"{data.patients[pid]['sex']} / {label}"] += 1
    return {group: count(n) for group, n in totals.items()}


REFERENCES: dict[str, Callable[[ReferenceData], dict]] = {
    "R01": r01, "R03": r03, "R05": r05, "R07": r07, "R08": r08, "R09": r09,
}
# Task 14 extension point: independent functions, never application-generated values.
EXTRA_REFERENCES: dict[str, Callable[[ReferenceData], dict]] = {
    "N01": n01, "N02": n02, "N03": n03, "N05": n05, "N06": n06, "N07": n07, "N08": n08, "N10": n10,
}


def compare_references(data: ReferenceData, expected: dict, references: dict | None = None) -> dict[str, bool]:
    functions = REFERENCES if references is None else references
    return {request_id: request_id in expected and function(data) == expected[request_id]["answer"]
            for request_id, function in functions.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path)
    args = parser.parse_args()
    data = ReferenceData(args.data or find_data_dir())
    expected = json.loads((data.directory / "requests" / "expected.json").read_text(encoding="utf-8"))
    checks = compare_references(data, expected)
    print("Request | independent CSV reference matches expected")
    for request_id, matches in checks.items():
        print(f"{request_id} | {'PASS' if matches else 'FAIL'}")
    extra_expected = ROOT / "requests" / "extra" / "expected.json"
    if extra_expected.is_file():
        extra = json.loads(extra_expected.read_text(encoding="utf-8"))
        extra_checks = compare_references(data, extra, EXTRA_REFERENCES)
        missing = {key for key, value in extra.items() if value.get("answer") is not None} - extra_checks.keys()
        for key in sorted(missing):
            extra_checks[key] = False
        checks.update(extra_checks)
        for request_id, matches in extra_checks.items():
            print(f"{request_id} | {'PASS' if matches else 'FAIL (reference missing or mismatched)'}")
    else:
        print("Extra requests: not present (Task 14 pending).")
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
