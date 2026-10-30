"""Hand-written reference plans for R01-R10 (ground truth for compiler tests and LLM-parser tests)."""
import json, pathlib
OUT = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "plans"
D = "2025-12-31"
T2D = {"source": "condition", "codes": ["E11"], "label": "Type 2 diabetes"}
HBA1C = {"source": "observation", "codes": ["4548-4"], "label": "has HbA1c"}
def med(codes, label): return {"source": "medication", "codes": codes, "active_on": D, "label": label}
P = {
 "R01": {"population": {"age_min": 18}, "group_by": [{"dim": "region"}], "measures": [
    {"name": "adults", "kind": "count"},
    {"name": "type2_diabetes", "kind": "count", "criteria": [T2D]},
    {"name": "prevalence_pct", "kind": "pct", "numerator": "type2_diabetes", "denominator": "adults"}]},
 "R02": {"population": {"age_min": 18, "criteria": [T2D, HBA1C]},
    "group_by": [{"dim": "age_band", "bands": ["18-29","30-39","40-49","50-59","60-69","70-79","80+"]}],
    "measures": [{"name": "patients_with_hba1c", "kind": "count"}, {"name": "mean_hba1c", "kind": "mean", "loinc": "4548-4"}]},
 "R03": {"population": {"age_min": 65, "criteria": [{"source": "condition", "codes": ["I48"], "label": "Atrial fibrillation"}]},
    "group_by": [{"dim": "age_band", "bands": ["65-74","75-84","85+"]}],
    "measures": [{"name": "af_patients", "kind": "count"},
      {"name": "without_oac", "kind": "count", "criteria": [dict(med(["B01AA","B01AF"], "active oral anticoagulant"), negate=True)]},
      {"name": "share_without_oac_pct", "kind": "pct", "numerator": "without_oac", "denominator": "af_patients"}]},
 "R04": {"population": {"criteria": [med(["A10BK"], "active SGLT2 inhibitor")]}, "group_by": [{"dim": "region"}],
    "measures": [{"name": "patients_active_sglt2", "kind": "count"}]},
 "R05": {"population": {"age_min": 18, "criteria": [T2D, HBA1C]}, "measures": [{"name": "cohort_size", "kind": "count"}],
    "spe_records": [{"table": "patients"}, {"table": "conditions"}, {"table": "medications"}, {"table": "observations", "codes": ["4548-4"]}]},
 "R06": {"population": {"age_min": 18, "regions": ["Oberösterreich"], "criteria": [{"source": "condition", "codes": ["F32"], "label": "Depression"}]},
    "measures": [{"name": "patients", "kind": "count"}], "spe_records": [{"table": "patients"}, {"table": "conditions", "codes": ["F32"]}]},
 "R07": {"unit": "encounters", "encounter_filter": {"types": ["inpatient"], "start_from": "2025-01-01", "start_to": "2025-12-31"},
    "group_by": [{"dim": "region"}], "measures": [{"name": "inpatient_stays", "kind": "count"}]},
 "R08": {"population": {"sex": "female", "criteria": [{"source": "condition", "codes": ["C50"], "label": "Breast cancer"},
      {"source": "observation", "codes": ["39156-5"], "label": "has BMI"}]}, "group_by": [{"dim": "region"}],
    "measures": [{"name": "women_with_bmi", "kind": "count"}, {"name": "mean_bmi", "kind": "mean", "loinc": "39156-5"}]},
 "R09": {"population": {"age_min": 18, "criteria": [{"source": "condition", "codes": ["I10"], "label": "Hypertension"}]},
    "group_by": [{"dim": "age_band", "bands": ["18-49","50-64","65+"]}],
    "measures": [{"name": "adults_with_hypertension", "kind": "count"},
      {"name": "ace", "kind": "count", "criteria": [med(["C09AA"], "active ACE inhibitor")]},
      {"name": "arb", "kind": "count", "criteria": [med(["C09CA"], "active ARB")]},
      {"name": "ace_inhibitor_pct", "kind": "pct", "numerator": "ace", "denominator": "adults_with_hypertension"},
      {"name": "arb_pct", "kind": "pct", "numerator": "arb", "denominator": "adults_with_hypertension"}],
    "spe_records": [{"table": "patients"}, {"table": "conditions"}, {"table": "medications"}]},
 "R10": {"population": {"criteria": [{"source": "condition", "codes": ["J44"], "label": "COPD"}]},
    "group_by": [{"dim": "region"}, {"dim": "age_band", "bands": ["0-9","10-19","20-29","30-39","40-49","50-59","60-69","70-79","80-89","90+"]}],
    "measures": [{"name": "patients_with_copd", "kind": "count"}]},
}
OUT.mkdir(parents=True, exist_ok=True)
for k, v in P.items():
    (OUT / f"{k}.json").write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n")
print("wrote", len(P))
