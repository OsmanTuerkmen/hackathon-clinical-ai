"""Closed terminology catalog: every code the data actually contains, plus main-diagnosis codes without descriptions.

The LLM must choose codes from here, so it cannot invent codes that match nothing.
"""
from __future__ import annotations

from functools import lru_cache

from . import db

# primary_icd10 codes in encounters.csv that never appear in conditions.csv (no description in the data)
EXTRA_ICD10 = {
    "K35": "Acute appendicitis",
    "N39": "Other disorders of urinary system (N39.0 urinary tract infection)",
    "J18": "Pneumonia, organism unspecified",
    "S72": "Fracture of femur (incl. hip fracture)",
}


@lru_cache(maxsize=1)
def catalog() -> dict:
    conds = db.query("select icd10, any_value(description) d, count(distinct patient_id) n from raw.conditions group by 1 order by 1")
    meds = db.query("select atc, any_value(name) d, count(distinct patient_id) n from raw.medications group by 1 order by 1")
    obs = db.query("select loinc, any_value(name) d, any_value(unit) u from raw.observations group by 1 order by 1")
    prim = db.query("select distinct substr(primary_icd10, 1, 3) c from raw.encounters where primary_icd10 <> '' order by 1")
    known3 = {c[:3] for c in conds["icd10"]}
    return {
        "conditions_icd10": [{"code": r.icd10, "description": r.d} for r in conds.itertuples()],
        "medications_atc": [{"code": r.atc, "name": r.d} for r in meds.itertuples()],
        "observations_loinc": [{"code": r.loinc, "name": r.d, "unit": r.u} for r in obs.itertuples()],
        "encounter_primary_icd10_prefixes": [
            {"code": c, "description": EXTRA_ICD10.get(c, "see conditions")} for c in prim["c"] if c not in known3 or c in EXTRA_ICD10
        ] + [{"code": c, "description": "same as conditions"} for c in prim["c"] if c in known3],
        "regions": list(db.domain("region")),
        "data_holders": list(db.domain("data_holder")),
        "encounter_types": ["inpatient", "outpatient", "emergency"],
        "reference_date": db.REFERENCE_DATE,
    }


def unknown_codes(plan) -> list[str]:
    """Codes in the plan that match nothing in the data (a sign the translation is wrong)."""
    cat = catalog()
    pools = {
        "condition": [c["code"] for c in cat["conditions_icd10"]],
        "medication": [c["code"] for c in cat["medications_atc"]],
        "observation": [c["code"] for c in cat["observations_loinc"]],
        "encounter": [c["code"] for c in cat["encounter_primary_icd10_prefixes"]],
    }
    crits = list(plan.population.criteria) + [c for m in plan.measures for c in m.criteria]
    bad = []
    for c in crits:
        for code in c.codes:
            pool = pools[c.source]
            hit = code in pool if c.source == "observation" else any(p.startswith(code) or code.startswith(p) for p in pool)
            if not hit:
                bad.append(f"{c.source}:{code}")
    if plan.encounter_filter:
        for code in plan.encounter_filter.primary_icd10:
            if not any(p.startswith(code[:3]) for p in pools["encounter"]):
                bad.append(f"primary_icd10:{code}")
    return bad
