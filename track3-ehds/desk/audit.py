"""Independent privacy checks, run on every answer before it is released."""
from __future__ import annotations

import json
import re
import sqlite3
from fractions import Fraction

from . import disclosure as D
from .datastore import DataStore

PATIENT_ID = re.compile(r"\bp-[0-9a-f]{8}\b")
ENCOUNTER_ID = re.compile(r"\be\d{6}\b")
ISO_DATE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "status": "pass" if ok else "fail", "detail": detail}


def eligible_ids(store: DataStore) -> set[str]:
    return {r[0] for r in store.query("SELECT patient_id FROM patients", purpose="audit")}


def audit_statistics(released: dict, internal, ir: dict, store: DataStore) -> list[dict]:
    checks = []
    text = json.dumps(released, ensure_ascii=False)
    leaks = PATIENT_ID.findall(text) + ENCOUNTER_ID.findall(text) + ISO_DATE.findall(text)
    checks.append(_check("No patient-level records in the answer", not leaks,
                         "only aggregated cells are released" if not leaks else f"found {leaks[:3]}"))

    measures = {m["id"]: m for m in ir["measures"]}
    visible = [m for m in ir["measures"] if m.get("visible")]
    small_bad = pct_bad = mean_bad = 0
    small_n = pct_n = mean_n = 0
    for row, raw_cell in zip(released["rows"], internal.cells):
        raw = raw_cell["raw"]
        for m in visible:
            mid = m["id"]
            val = row["cells"][mid]
            if m["type"].startswith("count"):
                n = raw[mid]["n"]
                if n < 10:
                    small_n += 1
                    small_bad += val != D.LT10
                else:
                    small_bad += val != n
            elif m["type"] == "percent":
                num, den = raw[mid]["numerator"], raw[mid]["denominator"]
                if num < 10 or den < 10:
                    pct_n += 1
                    pct_bad += val != D.SUPPRESSED
                else:
                    expect = float(D.round_half_up(Fraction(num * 100, den), 1))
                    pct_bad += val != expect
            else:
                n, k = raw[mid]["n"], raw[mid].get("k", raw[mid]["n"])  # n = distinct patients, k = values
                if n < 10:
                    mean_n += 1
                    mean_bad += val != D.SUPPRESSED
                elif m["type"] == "mean":
                    expect = float(D.round_half_up(Fraction(raw[mid]["sum"]) / k, 1))
                    mean_bad += val != expect
    checks.append(_check("Counts below 10 (including 0) shown as \"<10\"", small_bad == 0,
                         f"{small_n} small cell(s) masked" if small_bad == 0 else f"{small_bad} cell(s) wrong"))
    checks.append(_check("Percentages with numerator or denominator below 10 suppressed", pct_bad == 0,
                         f"{pct_n} percentage(s) suppressed; others rounded half-up to one decimal"
                         if pct_bad == 0 else f"{pct_bad} percentage(s) wrong"))
    checks.append(_check("Means and medians based on fewer than 10 patients suppressed", mean_bad == 0,
                         f"{mean_n} mean(s) suppressed" if mean_bad == 0 else f"{mean_bad} mean(s) wrong"))

    opted = store.opted_out_ids
    contributing = set().union(*internal.contributors.values()) if internal.contributors else set()
    in_db = eligible_ids(store) & opted
    checks.append(_check("Opted-out patients excluded (Art. 71)", not (contributing & opted) and not in_db,
                         f"{len(opted)} opted-out patients are not loaded; 0 of {len(contributing)} contributing "
                         "patients opted out" if not (contributing & opted) and not in_db
                         else "opted-out patients found"))

    expected_groups = 1
    for d in released["dimensions"]:
        dim = next(x for x in ir["dimensions"] if x["type"] == d["type"])
        expected_groups *= max(1, len(dim["groups"]))
    checks.append(_check("Every requested group shown, even if empty", len(released["rows"]) == expected_groups,
                         f"{len(released['rows'])} of {expected_groups} groups present"))
    cols_ok = [c["id"] for c in released["columns"]] == [m["id"] for m in visible]
    checks.append(_check("Only requested statistics released", cols_ok,
                         f"{len(visible)} requested column(s); helper counts stay internal"))
    enc_notes = []
    for mid, info in internal.encounter_patients.items():
        for row, n_pat, raw_cell in zip(released["rows"], info["distinct_patients"], internal.cells):
            if raw_cell["raw"][mid]["n"] >= 10 and n_pat < 10:
                enc_notes.append(row["label"])
    if internal.encounter_patients:
        checks.append({"check": "Encounter counts from fewer than 10 distinct patients (staff note)",
                       "status": "pass" if not enc_notes else "note",
                       "detail": "none" if not enc_notes else "review: " + ", ".join(enc_notes)})
    return checks


def audit_spe(manifest: dict, cohort_ids: list[str], record_types: list[dict], store: DataStore,
              db_path, download_status: int) -> list[dict]:
    checks = []
    cohort = set(cohort_ids)
    ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {"cohort"} | {rt["table"] for rt in record_types}
        checks.append(_check("Only the requested record types were copied", tables == expected,
                             ", ".join(sorted(tables - {"cohort"}))))
        foreign = 0
        for t in tables:
            ids = {r[0] for r in ro.execute(f"SELECT DISTINCT patient_id FROM {t}")}
            foreign += len(ids - cohort)
            if t == "cohort":
                cohort_db = ids
        checks.append(_check("Only selected patients copied (pseudonymous IDs kept)", foreign == 0 and cohort_db == cohort,
                             f"{len(cohort)} patients; {foreign} rows outside the cohort"))
        checks.append(_check("Opted-out patients excluded (Art. 71)", not (cohort & store.opted_out_ids),
                             f"0 of {len(cohort)} cohort patients opted out"
                             if not (cohort & store.opted_out_ids) else "opted-out patients in cohort"))
        for rt in record_types:
            if rt["table"] == "observations" and rt.get("loinc"):
                codes = {r[0] for r in ro.execute("SELECT DISTINCT loinc FROM observations")}
                checks.append(_check("Observations limited to the requested measurements",
                                     codes <= set(rt["loinc"]), "LOINC " + ", ".join(sorted(codes)) if codes else "none"))
    finally:
        ro.close()
    checks.append(_check("Exact cohort size reported", manifest["cohort_size"] == len(cohort),
                         f"{len(cohort)} patients"))
    checks.append(_check("Record download blocked (Art. 73)", download_status == 403,
                         f"download endpoint answers HTTP {download_status}"))
    return checks
