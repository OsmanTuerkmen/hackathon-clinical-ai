"""Code list: plain-English terms -> ICD-10 / ATC / LOINC code prefixes.

Requests usually define their codes ("ICD-10 code starting with E11"). When a
request only names a condition, drug or measurement in words, this code list
supplies the code. Every mapping is shown to staff so they can check it.
"""
import re

# (system, code prefix, label, synonyms)
CODEBOOK = [
    # ICD-10 diagnoses found in conditions.csv
    ("icd10", "C50", "Breast cancer", ["breast cancer", "malignant neoplasm of breast", "breast carcinoma", "mammary carcinoma"]),
    ("icd10", "E11", "Type 2 diabetes", ["type 2 diabetes", "type ii diabetes", "t2d", "t2dm", "diabetes mellitus type 2", "type 2 diabetes mellitus", "diabetes"]),
    ("icd10", "E66", "Obesity", ["obesity", "obese", "adiposity"]),
    ("icd10", "F32", "Depression", ["depression", "depressive episode", "depressive disorder", "depressed"]),
    ("icd10", "I10", "Hypertension", ["hypertension", "high blood pressure", "essential hypertension"]),
    ("icd10", "I48", "Atrial fibrillation", ["atrial fibrillation", "afib", "a-fib", "af"]),
    ("icd10", "I50", "Heart failure", ["heart failure", "cardiac failure", "chf"]),
    ("icd10", "I63", "Stroke (cerebral infarction)", ["stroke", "cerebral infarction", "ischaemic stroke", "ischemic stroke"]),
    ("icd10", "J44", "COPD", ["copd", "chronic obstructive pulmonary disease", "smokers' lung", "smokers lung"]),
    ("icd10", "J45", "Asthma", ["asthma"]),
    ("icd10", "N18", "Chronic kidney disease", ["chronic kidney disease", "ckd", "kidney disease", "renal insufficiency"]),
    # ICD-10 codes that only appear as main diagnosis of an inpatient stay
    ("icd10", "K35", "Acute appendicitis", ["appendicitis", "acute appendicitis"]),
    ("icd10", "N39", "Urinary tract infection", ["urinary tract infection", "uti"]),
    ("icd10", "J18", "Pneumonia", ["pneumonia"]),
    ("icd10", "S72", "Fracture of femur (incl. hip fracture)", ["hip fracture", "femur fracture", "fracture of femur", "femoral fracture", "fractured hip"]),
    # ATC drug classes and substances found in medications.csv
    ("atc", "A10A", "Insulins", ["insulin", "insulins"]),
    ("atc", "A10AE04", "Insulin glargine", ["insulin glargine", "glargine"]),
    ("atc", "A10B", "Blood glucose lowering drugs (excl. insulins)", ["oral antidiabetic", "oral antidiabetics", "glucose-lowering drug", "glucose lowering drug"]),
    ("atc", "A10BA02", "Metformin", ["metformin"]),
    ("atc", "A10BJ", "GLP-1 receptor agonists", ["glp-1 receptor agonist", "glp-1 agonist", "glp-1", "semaglutide"]),
    ("atc", "A10BK", "SGLT2 inhibitors", ["sglt2 inhibitor", "sglt-2 inhibitor", "sglt2", "empagliflozin", "gliflozin"]),
    ("atc", "B01AA", "Vitamin K antagonists", ["vitamin k antagonist", "vka", "phenprocoumon", "coumarin"]),
    ("atc", "B01AF", "Direct factor Xa inhibitors", ["direct factor xa inhibitor", "doac", "noac", "rivaroxaban", "apixaban"]),
    ("atc", "B01AA|B01AF", "Oral anticoagulants", ["oral anticoagulant", "oral anticoagulants", "oac", "anticoagulant", "blood thinner", "blood thinners"]),
    ("atc", "C03CA", "Loop diuretics", ["loop diuretic", "furosemide"]),
    ("atc", "C07", "Beta blockers", ["beta blocker", "beta-blocker", "bisoprolol"]),
    ("atc", "C08CA", "Dihydropyridine calcium channel blockers", ["calcium channel blocker", "amlodipine"]),
    ("atc", "C09AA", "ACE inhibitors", ["ace inhibitor", "ace-inhibitor", "ramipril"]),
    ("atc", "C09CA", "Angiotensin II receptor blockers (ARB)", ["arb", "angiotensin receptor blocker", "angiotensin ii receptor blocker", "sartan", "candesartan"]),
    ("atc", "C10AA", "Statins", ["statin", "statins", "atorvastatin"]),
    ("atc", "N06AB", "SSRIs", ["ssri", "selective serotonin reuptake inhibitor", "sertraline"]),
    ("atc", "N06A", "Antidepressants", ["antidepressant", "antidepressants"]),
    ("atc", "R03AK", "Inhaled combination (beta-agonist + corticosteroid)", ["salmeterol/fluticasone", "combination inhaler"]),
    ("atc", "R03BB", "Inhaled anticholinergics", ["tiotropium", "lama", "inhaled anticholinergic"]),
    ("atc", "R03", "Drugs for obstructive airway diseases", ["inhaler", "inhalers", "asthma medication", "copd medication"]),
    # LOINC measurements found in observations.csv
    ("loinc", "4548-4", "HbA1c", ["hba1c", "glycated haemoglobin", "glycated hemoglobin", "a1c", "long-term blood sugar"]),
    ("loinc", "39156-5", "BMI", ["bmi", "body mass index"]),
    ("loinc", "8480-6", "Systolic blood pressure", ["systolic blood pressure", "systolic bp", "blood pressure"]),
    ("loinc", "62238-1", "eGFR", ["egfr", "estimated glomerular filtration rate", "kidney function", "glomerular filtration rate"]),
]


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text)


def find_terms(text: str, systems=None):
    """Return code list entries mentioned in text, longest synonyms first,
    without overlapping matches."""
    t = _norm(text)
    hits, taken = [], []
    candidates = []
    for system, code, label, syns in CODEBOOK:
        if systems and system not in systems:
            continue
        for s in syns:
            candidates.append((len(s), s, system, code, label))
    for _, s, system, code, label in sorted(candidates, reverse=True):
        for m in re.finditer(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", t):
            if any(m.start() < e and m.end() > b for b, e in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append({"system": system, "codes": code.split("|"), "label": label,
                         "matched": s, "start": m.start(), "end": m.end()})
    return sorted(hits, key=lambda h: h["start"])


def label_for(system: str, code: str):
    for sys_, c, label, _ in CODEBOOK:
        if sys_ == system and c == code:
            return label
    return None


def allowed_codes(system: str):
    """Codes the AI helper may choose from. It cannot invent new codes."""
    return sorted({c for sys_, code, _, _ in CODEBOOK if sys_ == system for c in code.split("|")})
