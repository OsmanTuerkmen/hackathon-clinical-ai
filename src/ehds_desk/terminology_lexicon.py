"""Plain-English synonyms -> code prefixes (ICD-10, ATC, LOINC). Pure data, no logic.

Synonyms are matched whole-word after normalisation (see ``terminology.normalise``), so
plural forms, case and punctuation need not be listed. Order matters only for ties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LexEntry:
    synonyms: tuple[str, ...]
    system: Literal["icd10", "atc", "loinc"]
    prefixes: tuple[str, ...]
    label: str


# A lexicon hit directly preceded by one of these (normalised) tokens names a different
# condition ("pulmonary hypertension", "hemorrhagic stroke", "drug-induced depression").
# lookup() then returns None so the term goes to manual review instead of a wrong mapping.
QUALIFIER_EXCLUSIONS: frozenset[str] = frozenset(
    {
        "pulmonary",
        "hemorrhagic",
        "haemorrhagic",
        "gestational",
        "respiratory",
        "secondary",
        "portal",
        "intracranial",
        "intracerebral",
        "subarachnoid",
        "ocular",
        "neonatal",
        "induced",  # drug-induced / steroid-induced
    }
)

LEXICON: list[LexEntry] = [
    # --- ICD-10 -------------------------------------------------------------------------
    LexEntry(
        (
            "type 2 diabetes",
            "type 2 diabetes mellitus",
            "diabetes mellitus type 2",
            "diabetes type 2",
            "type 2 diabetic",
            "t2dm",
            "t2d",
            "adult onset diabetes",
        ),
        "icd10",
        ("E11",),
        "type 2 diabetes mellitus",
    ),
    LexEntry(
        (
            "type 1 diabetes",
            "type 1 diabetes mellitus",
            "diabetes mellitus type 1",
            "diabetes type 1",
            "type 1 diabetic",
            "t1dm",
            "t1d",
            "juvenile diabetes",
            "insulin dependent diabetes",
        ),
        "icd10",
        ("E10",),
        "type 1 diabetes mellitus",
    ),
    LexEntry(
        (
            "hypertension",
            "high blood pressure",
            "elevated blood pressure",
            "arterial hypertension",
            "essential hypertension",
        ),
        "icd10",
        ("I10",),
        "essential hypertension",
    ),
    LexEntry(
        ("atrial fibrillation", "afib"),
        "icd10",
        ("I48",),
        "atrial fibrillation",
    ),
    LexEntry(
        ("heart failure", "cardiac failure", "congestive heart failure", "chf"),
        "icd10",
        ("I50",),
        "heart failure",
    ),
    LexEntry(
        (
            "stroke",
            "cerebral infarction",
            "ischemic stroke",
            "ischaemic stroke",
            "cerebrovascular accident",
        ),
        "icd10",
        ("I63",),
        "cerebral infarction",
    ),
    LexEntry(
        (
            "copd",
            "chronic obstructive pulmonary disease",
            "chronic obstructive lung disease",
        ),
        "icd10",
        ("J44",),
        "chronic obstructive pulmonary disease",
    ),
    LexEntry(
        ("asthma", "bronchial asthma"),
        "icd10",
        ("J45",),
        "asthma",
    ),
    LexEntry(
        (
            "depression",
            "depressive disorder",
            "depressive episode",
            "major depression",
            "major depressive disorder",
        ),
        "icd10",
        ("F32", "F33"),
        "depression",
    ),
    LexEntry(
        (
            "breast cancer",
            "breast carcinoma",
            "carcinoma of the breast",
            "malignant neoplasm of breast",
        ),
        "icd10",
        ("C50",),
        "malignant neoplasm of breast",
    ),
    LexEntry(
        ("obesity", "obese"),
        "icd10",
        ("E66",),
        "obesity",
    ),
    LexEntry(
        (
            "chronic kidney disease",
            "kidney disease",
            "ckd",
            "chronic renal insufficiency",
            "renal failure",
        ),
        "icd10",
        ("N18",),
        "chronic kidney disease",
    ),
    LexEntry(
        ("pneumonia",),
        "icd10",
        ("J12", "J13", "J14", "J15", "J16", "J17", "J18"),
        "pneumonia",
    ),
    LexEntry(
        (
            "hip fracture",
            "femur fracture",
            "femoral fracture",
            "fracture of the femur",
            "femoral neck fracture",
            "fractured hip",
            "broken hip",
        ),
        "icd10",
        ("S72",),
        "hip/femur fracture",
    ),
    LexEntry(
        ("appendicitis", "acute appendicitis"),
        "icd10",
        ("K35",),
        "appendicitis",
    ),
    LexEntry(
        ("urinary tract infection", "uti"),
        "icd10",
        ("N39.0",),
        "urinary tract infection",
    ),
    LexEntry(
        (
            "myocardial infarction",
            "myocardial infarct",
            "acute myocardial infarction",
            "heart attack",
        ),
        "icd10",
        ("I21",),
        "myocardial infarction",
    ),
    # --- ATC ----------------------------------------------------------------------------
    LexEntry(
        (
            "antidiabetic",
            "antidiabetic drug",
            "antidiabetic medication",
            "diabetes medication",
            "diabetes drug",
            "blood glucose lowering drug",
        ),
        "atc",
        ("A10",),
        "antidiabetics",
    ),
    LexEntry(
        ("insulin", "insulin therapy"),
        "atc",
        ("A10A",),
        "insulins and analogues",
    ),
    LexEntry(("metformin",), "atc", ("A10BA02",), "metformin"),
    LexEntry(
        (
            "glp 1",
            "glp1",
            "glp 1 receptor agonist",
            "glucagon like peptide 1",
        ),
        "atc",
        ("A10BJ",),
        "GLP-1 receptor agonists",
    ),
    LexEntry(
        ("sglt2", "sglt 2", "sglt2 inhibitor", "gliflozin"),
        "atc",
        ("A10BK",),
        "SGLT2 inhibitors",
    ),
    LexEntry(
        ("vitamin k antagonist", "vka", "coumarin"),
        "atc",
        ("B01AA",),
        "vitamin K antagonists",
    ),
    LexEntry(
        (
            "doac",
            "noac",
            "direct oral anticoagulant",
            "novel oral anticoagulant",
            "factor xa inhibitor",
        ),
        "atc",
        ("B01AF",),
        "direct oral anticoagulants (DOAC)",
    ),
    LexEntry(
        (
            "oral anticoagulant",
            "oral anticoagulation",
            "anticoagulant",
            "anticoagulation",
            "blood thinner",
        ),
        "atc",
        ("B01AA", "B01AF"),
        "oral anticoagulants",
    ),
    LexEntry(("loop diuretic",), "atc", ("C03C",), "loop diuretics"),
    LexEntry(
        ("beta blocker", "betablocker", "beta adrenergic blocker"),
        "atc",
        ("C07",),
        "beta blockers",
    ),
    LexEntry(
        ("calcium channel blocker", "ccb", "calcium antagonist"),
        "atc",
        ("C08",),
        "calcium channel blockers",
    ),
    LexEntry(
        ("ace inhibitor", "angiotensin converting enzyme inhibitor"),
        "atc",
        ("C09AA",),
        "ACE inhibitors",
    ),
    LexEntry(
        (
            "arb",
            "angiotensin receptor blocker",
            "angiotensin ii receptor blocker",
            "sartan",
        ),
        "atc",
        ("C09CA",),
        "angiotensin receptor blockers",
    ),
    LexEntry(
        ("statin", "hmg coa reductase inhibitor"),
        "atc",
        ("C10AA",),
        "statins",
    ),
    LexEntry(
        ("ssri", "selective serotonin reuptake inhibitor"),
        "atc",
        ("N06AB",),
        "SSRIs",
    ),
    LexEntry(("antidepressant",), "atc", ("N06A",), "antidepressants"),
    LexEntry(
        ("ics laba", "laba ics", "ics laba inhaler", "inhaled corticosteroid laba"),
        "atc",
        ("R03AK",),
        "ICS/LABA inhalers",
    ),
    LexEntry(
        ("lama", "tiotropium", "long acting muscarinic antagonist"),
        "atc",
        ("R03BB",),
        "LAMA inhalers",
    ),
    # --- LOINC --------------------------------------------------------------------------
    LexEntry(
        (
            "hba1c",
            "a1c",
            "hemoglobin a1c",
            "haemoglobin a1c",
            "glycated hemoglobin",
            "glycated haemoglobin",
            "glycosylated hemoglobin",
            "glycosylated haemoglobin",
        ),
        "loinc",
        ("4548-4",),
        "HbA1c",
    ),
    LexEntry(
        ("bmi", "body mass index"),
        "loinc",
        ("39156-5",),
        "body mass index",
    ),
    LexEntry(
        ("systolic blood pressure", "systolic bp", "systolic pressure"),
        "loinc",
        ("8480-6",),
        "systolic blood pressure",
    ),
    LexEntry(
        ("egfr", "glomerular filtration rate", "kidney function", "renal function"),
        "loinc",
        ("62238-1",),
        "eGFR (kidney function)",
    ),
]
