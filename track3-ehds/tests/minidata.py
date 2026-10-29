"""Hand-made miniature dataset with known answers for the difficult rules.

Every number the tests expect can be checked by reading this file. Ages are 2025 - birth year.
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

HEADERS = {
    "patients": ["patient_id", "sex", "birth_date", "region", "data_holder", "opted_out"],
    "conditions": ["patient_id", "icd10", "description", "onset_date"],
    "medications": ["patient_id", "atc", "name", "start_date", "end_date"],
    "observations": ["patient_id", "loinc", "name", "value", "unit", "date"],
    "encounters": ["encounter_id", "patient_id", "data_holder", "type", "start_date", "end_date", "primary_icd10"],
}


class MiniData:
    def __init__(self):
        self.rows = {k: [] for k in HEADERS}
        self._enc = 0

    def patient(self, pid, sex="female", birth_year=1960, region="Wien", holder="Klinikum Nord", opted_out=False):
        self.rows["patients"].append([pid, sex, f"{birth_year}-06-15", region, holder, "true" if opted_out else "false"])
        return pid

    def condition(self, pid, icd, onset="2020-01-01"):
        self.rows["conditions"].append([pid, icd, "test", onset])

    def medication(self, pid, atc, start, end=""):
        self.rows["medications"].append([pid, atc, "test", start, end])

    def observation(self, pid, loinc, value, date):
        self.rows["observations"].append([pid, loinc, "test", value, "u", date])

    def encounter(self, pid, holder, typ, start, primary=""):
        self._enc += 1
        self.rows["encounters"].append([f"e{self._enc:06d}", pid, holder, typ, start, start, primary])

    def write(self, directory: Path | None = None) -> Path:
        d = Path(directory or tempfile.mkdtemp(prefix="desk-mini-"))
        for table, header in HEADERS.items():
            with (d / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(self.rows[table])
        return d


def build() -> MiniData:
    m = MiniData()
    # --- Type 2 diabetes by region: Tirol 12 (shown), Wien 9 (<10), Salzburg 0 (<10, still listed).
    # Opted-out patients would push Tirol to 17 and Wien to exactly 10 if they leaked in.
    for i in range(12):
        pid = m.patient(f"p-a000{i:04x}", region="Tirol", birth_year=1950 + i, sex="female" if i % 2 else "male")
        m.condition(pid, "E11.9")
        # latest BMI: six patients 27.0 and six 27.5 -> mean 27.25 -> 27.3 (half up); old 40.0 must be ignored
        m.observation(pid, "39156-5", "40.0", "2023-02-01")
        m.observation(pid, "39156-5", "27.0" if i < 6 else "27.5", "2025-03-01")
    for i in range(9):
        pid = m.patient(f"p-b000{i:04x}", region="Wien", birth_year=1955)
        m.condition(pid, "E11.65")
        m.observation(pid, "39156-5", "30.0", "2025-01-10")
    for i in range(5):
        pid = m.patient(f"p-c000{i:04x}", region="Tirol", birth_year=1950, opted_out=True)
        m.condition(pid, "E11.9")
        m.observation(pid, "39156-5", "50.0", "2025-05-05")
    pid = m.patient("p-c0000100", region="Wien", birth_year=1950, opted_out=True)
    m.condition(pid, "E11.9")
    # a child with E11 (age 10) must not count as adult
    pid = m.patient("p-d0000001", region="Tirol", birth_year=2015)
    m.condition(pid, "E11.9")

    # --- Active anticoagulants on 31 Dec 2025 (atrial fibrillation patients in Steiermark, age 70)
    af = {}
    for name, start, end in [("active_open", "2020-01-01", ""),        # active
                             ("ends_on_ref", "2020-01-01", "2025-12-31"),  # active (end on the day)
                             ("ended_before", "2020-01-01", "2025-12-30"),  # not active
                             ("starts_on_ref", "2025-12-31", ""),     # active (start on the day)
                             ("starts_after", "2026-01-05", "")]:      # not active
        pid = m.patient(f"p-e{len(af):07x}", region="Steiermark", birth_year=1955, holder="Klinikum Süd")
        m.condition(pid, "I48.0")
        m.medication(pid, "B01AF01", start, end)
        af[name] = pid
    pid = m.patient("p-e00000ff", region="Steiermark", birth_year=1955, holder="Klinikum Süd")
    m.condition(pid, "I48.2")
    m.medication(pid, "C09AA05", "2020-01-01", "")  # an ACE inhibitor is not an anticoagulant
    af["no_oac"] = pid

    # --- Encounters: stays versus patients, hospital grouping, primary_icd10
    p1 = m.patient("p-f0000001", region="Kärnten", holder="Klinikum Nord")
    for prim in ("I50.9", "I50.9", "J18.9"):
        m.encounter(p1, "Klinikum Nord", "inpatient", "2025-02-01", prim)
    p2 = m.patient("p-f0000002", region="Kärnten", holder="Klinikum Süd")
    m.encounter(p2, "Klinikum Süd", "inpatient", "2025-07-01", "I50.1")
    p3 = m.patient("p-f0000003", region="Kärnten", holder="Klinikum Süd")
    m.encounter(p3, "Klinikum Süd", "inpatient", "2024-07-01", "I50.9")  # wrong year
    p4 = m.patient("p-f0000004", region="Kärnten", holder="Klinikum Nord")
    m.encounter(p4, "Klinikum Nord", "outpatient", "2025-03-01")         # wrong type
    p5 = m.patient("p-f0000005", region="Kärnten", holder="Klinikum Nord", opted_out=True)
    m.encounter(p5, "Klinikum Nord", "inpatient", "2025-03-01", "I50.9")  # opted out
    m.encounter(p5, "Klinikum Nord", "inpatient", "2025-04-01", "I50.9")
    p6 = m.patient("p-f0000006", region="Kärnten", holder="Klinikum Süd")
    m.condition(p6, "I50.9")                                            # HF diagnosis in conditions ...
    m.encounter(p6, "Klinikum Süd", "inpatient", "2025-05-01", "K35.8")  # ... but the stay is appendicitis
    m.af = af
    return m
