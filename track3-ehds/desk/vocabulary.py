"""Plain-English -> code vocabulary (ICD-10, ATC, LOINC, encounter types) and reference domains.

Explicit codes in a request's definitions always win. The vocabulary is used when a definition or a
report line names a condition, drug class or measurement without giving its code, and to show staff
which codes a term stands for. Category prefixes follow the WHO ICD-10 and WHO ATC hierarchies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .text import MentionIndex


@dataclass(frozen=True)
class VocabEntry:
    kind: str  # condition | medication | observation | encounter
    label: str
    terms: tuple[str, ...]
    codes: tuple[str, ...] = field(default_factory=tuple)
    unit: str = ""


def _c(label, terms, codes):
    return VocabEntry("condition", label, tuple(terms), tuple(codes))


def _m(label, terms, codes):
    return VocabEntry("medication", label, tuple(terms), tuple(codes))


def _o(label, terms, code, unit):
    return VocabEntry("observation", label, tuple(terms), (code,), unit)


def _e(label, terms, types):
    return VocabEntry("encounter", label, tuple(terms), tuple(types))


CONDITIONS = [
    _c("Type 2 diabetes mellitus", ["type 2 diabetes", "type 2 diabetes mellitus", "diabetes type 2",
                                    "type ii diabetes", "t2d", "t2dm", "non-insulin-dependent diabetes"], ["E11"]),
    _c("Type 1 diabetes mellitus", ["type 1 diabetes", "type 1 diabetes mellitus", "diabetes type 1", "t1d",
                                    "t1dm"], ["E10"]),
    _c("Diabetes mellitus (any type)", ["diabetes", "diabetes mellitus"], ["E10", "E11", "E12", "E13", "E14"]),
    _c("Obesity", ["obesity"], ["E66"]),
    _c("Depression", ["depression", "depressive episode", "depressive disorder", "major depression"],
       ["F32", "F33"]),
    _c("Hypertensive diseases", ["hypertension", "high blood pressure", "arterial hypertension"],
       ["I10", "I11", "I12", "I13", "I15"]),
    _c("Essential (primary) hypertension", ["essential hypertension", "primary hypertension"], ["I10"]),
    _c("Atrial fibrillation and flutter", ["atrial fibrillation", "afib", "atrial fibrillation or flutter"], ["I48"]),
    _c("Heart failure", ["heart failure", "cardiac failure", "congestive heart failure"], ["I50"]),
    _c("Stroke", ["stroke"], ["I60", "I61", "I62", "I63", "I64"]),
    _c("Cerebral infarction", ["cerebral infarction", "ischaemic stroke", "ischemic stroke"], ["I63"]),
    _c("Chronic obstructive pulmonary disease", ["copd", "chronic obstructive pulmonary disease",
                                                 "chronic obstructive lung disease"], ["J44"]),
    _c("Asthma", ["asthma"], ["J45", "J46"]),
    _c("Chronic kidney disease", ["chronic kidney disease", "ckd", "chronic renal disease",
                                  "chronic renal failure"], ["N18"]),
    _c("Malignant neoplasm of breast", ["breast cancer", "malignant neoplasm of breast", "breast carcinoma"],
       ["C50"]),
    _c("Pneumonia", ["pneumonia"], ["J12", "J13", "J14", "J15", "J16", "J17", "J18"]),
    _c("Appendicitis", ["appendicitis", "acute appendicitis"], ["K35", "K36", "K37"]),
    _c("Urinary tract infection", ["urinary tract infection", "uti"], ["N39.0"]),
    _c("Hip fracture", ["hip fracture", "femoral neck fracture", "fracture of the femoral neck",
                        "fracture of neck of femur", "femur neck fracture"], ["S72.0", "S72.1", "S72.2"]),
    _c("Fracture of femur", ["femur fracture", "femoral fracture", "fracture of femur", "fracture of the femur"],
       ["S72"]),
]

MEDICATIONS = [
    _m("Insulins and analogues", ["insulin", "insulin therapy"], ["A10A"]),
    _m("Insulin glargine", ["insulin glargine", "glargine"], ["A10AE04"]),
    _m("Metformin", ["metformin"], ["A10BA02"]),
    _m("Biguanides", ["biguanide"], ["A10BA"]),
    _m("GLP-1 receptor agonists", ["glp-1 receptor agonist", "glp-1 agonist", "glp-1 analogue", "glp-1 ra",
                                   "glp1 receptor agonist", "glp-1 analog"], ["A10BJ"]),
    _m("Semaglutide", ["semaglutide"], ["A10BJ06"]),
    _m("SGLT2 inhibitors", ["sglt2 inhibitor", "sglt-2 inhibitor", "sglt2i", "gliflozin"], ["A10BK"]),
    _m("Empagliflozin", ["empagliflozin"], ["A10BK03"]),
    _m("Blood glucose lowering drugs, excl. insulins", ["oral antidiabetic", "oral antidiabetic drug",
                                                        "blood glucose lowering drug",
                                                        "oral glucose-lowering drug"], ["A10B"]),
    _m("Drugs used in diabetes", ["antidiabetic drug", "antidiabetic medication", "glucose-lowering drug",
                                  "glucose-lowering medication", "diabetes medication"], ["A10"]),
    _m("Oral anticoagulants", ["oral anticoagulant", "oac", "oral anticoagulation"], ["B01AA", "B01AE", "B01AF"]),
    _m("Vitamin K antagonists", ["vitamin k antagonist", "vka"], ["B01AA"]),
    _m("Phenprocoumon", ["phenprocoumon"], ["B01AA04"]),
    _m("Direct oral anticoagulants", ["direct oral anticoagulant", "doac", "noac"], ["B01AE", "B01AF"]),
    _m("Direct factor Xa inhibitors", ["factor xa inhibitor", "direct factor xa inhibitor"], ["B01AF"]),
    _m("Rivaroxaban", ["rivaroxaban"], ["B01AF01"]),
    _m("Apixaban", ["apixaban"], ["B01AF02"]),
    _m("Anticoagulants", ["anticoagulant", "anticoagulation"], ["B01AA", "B01AB", "B01AE", "B01AF", "B01AX"]),
    _m("Antithrombotic agents", ["antithrombotic", "antithrombotic agent", "blood thinner"], ["B01A"]),
    _m("Loop diuretics", ["loop diuretic", "high-ceiling diuretic"], ["C03C"]),
    _m("Furosemide", ["furosemide"], ["C03CA01"]),
    _m("Diuretics", ["diuretic"], ["C03"]),
    _m("Beta blocking agents", ["beta blocker", "beta-blocker", "beta blocking agent", "beta-blocking agent"],
       ["C07"]),
    _m("Bisoprolol", ["bisoprolol"], ["C07AB07"]),
    _m("Calcium channel blockers", ["calcium channel blocker", "calcium antagonist"], ["C08"]),
    _m("Amlodipine", ["amlodipine"], ["C08CA01"]),
    _m("ACE inhibitors", ["ace inhibitor", "ace-inhibitor", "acei", "angiotensin-converting enzyme inhibitor",
                          "angiotensin converting enzyme inhibitor"], ["C09A", "C09B"]),
    _m("Ramipril", ["ramipril"], ["C09AA05"]),
    _m("Angiotensin II receptor blockers", ["arb", "angiotensin receptor blocker", "angiotensin ii receptor blocker",
                                            "angiotensin ii receptor antagonist", "sartan",
                                            "angiotensin receptor antagonist"], ["C09C", "C09D"]),
    _m("Candesartan", ["candesartan"], ["C09CA06"]),
    _m("Statins", ["statin", "hmg coa reductase inhibitor", "hmg-coa reductase inhibitor"], ["C10AA"]),
    _m("Atorvastatin", ["atorvastatin"], ["C10AA05"]),
    _m("Lipid modifying agents", ["lipid-lowering drug", "lipid lowering drug", "lipid-lowering medication",
                                  "lipid modifying agent"], ["C10"]),
    _m("SSRIs", ["ssri", "selective serotonin reuptake inhibitor"], ["N06AB"]),
    _m("Sertraline", ["sertraline"], ["N06AB06"]),
    _m("Antidepressants", ["antidepressant"], ["N06A"]),
    _m("ICS/LABA combinations", ["ics/laba", "ics-laba", "laba/ics", "salmeterol/fluticasone",
                                 "fluticasone/salmeterol", "salmeterol and fluticasone"], ["R03AK"]),
    _m("Long-acting muscarinic antagonists", ["lama", "long-acting muscarinic antagonist",
                                              "anticholinergic inhaler"], ["R03BB"]),
    _m("Tiotropium", ["tiotropium"], ["R03BB04"]),
    _m("Drugs for obstructive airway diseases", ["inhaler", "drug for obstructive airway disease"], ["R03"]),
    _m("Antihypertensives", ["antihypertensive", "antihypertensive drug", "antihypertensive medication",
                             "blood pressure lowering drug"], ["C02", "C03", "C07", "C08", "C09"]),
]

OBSERVATIONS = [
    _o("HbA1c", ["hba1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "glycated haemoglobin",
                 "a1c"], "4548-4", "%"),
    _o("BMI", ["bmi", "body mass index"], "39156-5", "kg/m2"),
    _o("Systolic blood pressure", ["systolic blood pressure", "systolic bp", "sbp"], "8480-6", "mm[Hg]"),
    _o("eGFR", ["egfr", "estimated glomerular filtration rate", "glomerular filtration rate", "gfr",
                "kidney function"], "62238-1", "mL/min/{1.73_m2}"),
]

ENCOUNTERS = [
    _e("Inpatient stay", ["inpatient stay", "inpatient encounter", "inpatient admission", "inpatient episode",
                          "hospital stay", "hospitalisation", "hospitalization", "hospital admission",
                          "admission", "inpatient"], ["inpatient"]),
    _e("Outpatient visit", ["outpatient visit", "outpatient encounter", "outpatient contact", "outpatient"],
       ["outpatient"]),
    _e("Emergency visit", ["emergency visit", "emergency encounter", "emergency department visit", "ed visit",
                           "emergency room visit", "emergency"], ["emergency"]),
    _e("Encounter (any type)", ["encounter", "visit", "hospital contact"], ["inpatient", "outpatient", "emergency"]),
]

ALL_ENTRIES = CONDITIONS + MEDICATIONS + OBSERVATIONS + ENCOUNTERS

# Federal states of Austria (data/README.md: "Federal state where the patient lives").
REGIONS = ["Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg", "Steiermark",
           "Tirol", "Vorarlberg", "Wien"]
REGION_ALIASES = {
    "burgenland": "Burgenland", "karnten": "Kärnten", "kaernten": "Kärnten", "carinthia": "Kärnten",
    "niederosterreich": "Niederösterreich", "niederoesterreich": "Niederösterreich",
    "lower austria": "Niederösterreich", "oberosterreich": "Oberösterreich",
    "oberoesterreich": "Oberösterreich", "upper austria": "Oberösterreich", "salzburg": "Salzburg",
    "steiermark": "Steiermark", "styria": "Steiermark", "tirol": "Tirol", "tyrol": "Tirol",
    "vorarlberg": "Vorarlberg", "wien": "Wien", "vienna": "Wien",
}

# Hospitals listed in data/README.md (column data_holder).
DATA_HOLDERS = ["Klinikum Nord", "Klinikum Süd", "Klinikum West"]
DATA_HOLDER_ALIASES = {"klinikum nord": "Klinikum Nord", "klinikum sud": "Klinikum Süd",
                       "klinikum sued": "Klinikum Süd", "klinikum west": "Klinikum West"}

SEXES = ["female", "male"]
ENCOUNTER_TYPES = ["inpatient", "outpatient", "emergency"]


def build_index(kinds: tuple[str, ...] = ("condition", "medication", "observation", "encounter")) -> MentionIndex:
    idx = MentionIndex()
    for entry in ALL_ENTRIES:
        if entry.kind in kinds:
            for term in entry.terms:
                idx.add(term, entry)
    return idx


def entries_for_code(kind: str, code: str) -> list[VocabEntry]:
    """Vocabulary entries whose code set covers `code` (used to label explicit codes for staff)."""
    out = []
    for e in ALL_ENTRIES:
        if e.kind == kind and any(code.upper().startswith(c.upper()) or c.upper().startswith(code.upper())
                                  for c in e.codes):
            out.append(e)
    return out


def observation_by_loinc(code: str) -> VocabEntry | None:
    return next((e for e in OBSERVATIONS if e.codes[0] == code), None)
