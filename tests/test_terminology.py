import pytest

from ehds_desk.models import CodeSet
from ehds_desk.terminology import CodeMatch, Terminology, TermMapping


@pytest.fixture(scope="module")
def term(db):
    return Terminology(db)


@pytest.mark.parametrize(
    ("text", "system", "prefixes"),
    [
        ("type 2 diabetes", "icd10", ["E11"]),
        ("Type II diabetes mellitus", "icd10", ["E11"]),
        ("atrial fibrillation", "icd10", ["I48"]),
        ("breast cancer", "icd10", ["C50"]),
        ("hip fracture", "icd10", ["S72"]),
        ("oral anticoagulants", "atc", ["B01AA", "B01AF"]),
        ("ACE inhibitor", "atc", ["C09AA"]),
        ("angiotensin receptor blockers", "atc", ["C09CA"]),
        ("SGLT2 inhibitor", "atc", ["A10BK"]),
        ("HbA1c", "loinc", ["4548-4"]),
        ("body mass index", "loinc", ["39156-5"]),
        ("diabetes type 2", "icd10", ["E11"]),
        ("diabetes type II", "icd10", ["E11"]),
        ("type II diabetes", "icd10", ["E11"]),
        ("T2DM", "icd10", ["E11"]),
        ("diabetes type 1", "icd10", ["E10"]),
        ("diabetes type I", "icd10", ["E10"]),
        ("oral anticoagulation", "atc", ["B01AA", "B01AF"]),
        ("anticoagulation", "atc", ["B01AA", "B01AF"]),
        ("myocardial infarct", "icd10", ["I21"]),
        ("heart attack", "icd10", ["I21"]),
        ("fractured hip", "icd10", ["S72"]),
        ("femoral neck fracture", "icd10", ["S72"]),
        ("kidney disease", "icd10", ["N18"]),
        ("renal failure", "icd10", ["N18"]),
        ("CKD", "icd10", ["N18"]),
        ("high blood pressure", "icd10", ["I10"]),
        ("elevated blood pressure", "icd10", ["I10"]),
        ("essential hypertension", "icd10", ["I10"]),
        ("glycated haemoglobin", "loinc", ["4548-4"]),
        ("glycated hemoglobin", "loinc", ["4548-4"]),
    ],
)
def test_lookup_lexicon(term, text, system, prefixes):
    cs = term.lookup(text)
    assert isinstance(cs, CodeSet)
    assert cs.system == system
    assert cs.prefixes == prefixes
    assert cs.source == "lexicon"


def test_lookup_whole_word_only(term):
    # "insulin" inside another word must not match the insulin synonym
    assert term.lookup("insulinoma", system="atc") is None
    assert term.lookup("insulin pump", system="atc").prefixes == ["A10A"]


def test_lookup_respects_system(term):
    assert term.lookup("insulin") is not None
    assert term.lookup("insulin", system="loinc") is None


def test_lookup_data_match(term):
    cs = term.lookup("Salmeterol/fluticasone")
    assert cs is not None
    assert cs.system == "atc"
    assert cs.prefixes == ["R03AK06"]
    assert cs.source == "data_match"


@pytest.mark.parametrize(
    "text",
    [
        "pulmonary hypertension",
        "pulmonary arterial hypertension",
        "hemorrhagic stroke",
        "haemorrhagic stroke",
        "respiratory depression",
        "gestational diabetes mellitus type 2",
        "drug-induced depression",
        "secondary hypertension",
    ],
)
def test_lookup_qualifier_guard(term, text):
    assert term.lookup(text) is None


def test_lookup_borderline_data_match_rejected(term):
    # Jaccard exactly 0.5 against "Systolic blood pressure", not a subset -> must not narrow.
    assert term.lookup("diastolic blood pressure") is None


def test_lookup_subset_data_match_accepted(term):
    cs = term.lookup("fluticasone")
    assert cs is not None
    assert cs.prefixes == ["R03AK06"]
    assert cs.source == "data_match"


def test_lookup_ambiguous_subset_data_match_rejected(term):
    # "diabetes" is a subset of both E11.65 and E11.9 descriptions: must not pick one.
    assert term.lookup("diabetes") is None


def test_lookup_longest_synonym_wins(term):
    assert term.lookup("direct oral anticoagulants").prefixes == ["B01AF"]
    assert term.lookup("oral anticoagulants").prefixes == ["B01AA", "B01AF"]


def test_verify_system_mismatch_warns(term):
    cs = CodeSet(system="atc", prefixes=["A10"], label="antidiabetics", source="lexicon")
    m = term.verify("antidiabetics", cs, "conditions")
    assert m.matches == []
    assert m.warning and "icd10" in m.warning


def test_lookup_unknown(term):
    assert term.lookup("gout") is None


def test_verify_reports_matches(term):
    cs = CodeSet(system="icd10", prefixes=["E11"], label="type 2 diabetes", source="lexicon")
    m = term.verify("type 2 diabetes", cs, "conditions")
    assert isinstance(m, TermMapping)
    assert m.table == "conditions"
    assert m.warning is None
    assert [x.code for x in m.matches] == ["E11.65", "E11.9"]
    assert all(isinstance(x, CodeMatch) for x in m.matches)
    # opt-out-filtered counts (cond view); unfiltered would be 297 / 910
    assert [x.rows for x in m.matches] == [283, 869]
    assert m.matches[0].description == "Type 2 diabetes mellitus with hyperglycaemia"


def test_verify_pneumonia_in_primary(term):
    prefixes = ["J12", "J13", "J14", "J15", "J16", "J17", "J18"]
    cs = CodeSet(system="icd10", prefixes=prefixes, label="pneumonia", source="lexicon")
    m = term.verify("pneumonia", cs, "primary_icd10")
    assert m.table == "primary_icd10"
    assert [x.code for x in m.matches] == ["J18.9"]
    assert m.matches[0].rows == 230
    assert m.matches[0].description  # lexicon label for primary-only codes


def test_verify_warns_without_matches(term):
    cs = CodeSet(system="icd10", prefixes=["I21"], label="myocardial infarction", source="lexicon")
    m = term.verify("heart attack", cs, "conditions")
    assert m.matches == []
    assert m.warning


def test_verify_medications_and_observations(term):
    cs = CodeSet(
        system="atc", prefixes=["B01AA", "B01AF"], label="oral anticoagulant", source="lexicon"
    )
    m = term.verify("anticoagulants", cs, "medications")
    assert [x.code for x in m.matches] == ["B01AA04", "B01AF01", "B01AF02"]
    obs = CodeSet(system="loinc", prefixes=["4548-4"], label="HbA1c", source="lexicon")
    assert [x.code for x in term.verify("hba1c", obs, "observations").matches] == ["4548-4"]


def test_catalogue(term):
    cat = term.catalogue()
    assert set(cat) == {"icd10", "atc", "loinc"}
    assert ("E11.9", "Type 2 diabetes mellitus without complications") in cat["icd10"]
    assert any(code == "J18.9" for code, _ in cat["icd10"])
    assert ("A10BA02", "Metformin") in cat["atc"]
    assert any(code == "4548-4" for code, _ in cat["loinc"])
