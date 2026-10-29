import json

import pytest

from ehds_desk import engine
from ehds_desk.disclosure import disclose_table
from ehds_desk.models import AccessRequest, Applicant, ConditionCriterion
from ehds_desk.parsing import ParseReport, parse_rules
from ehds_desk.terminology import Terminology


@pytest.fixture(scope="module")
def term(db):
    return Terminology(db)


def load(settings, rid: str) -> AccessRequest:
    path = settings.data_dir / "requests" / f"{rid}.json"
    return AccessRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def expected(settings) -> dict:
    return json.loads((settings.data_dir / "requests" / "expected.json").read_text(encoding="utf-8"))


def make_request(definitions: list[str], question: str = "How many patients?", **kw) -> AccessRequest:
    return AccessRequest(
        id="T1",
        applicant=Applicant(name="Test", organisation="Test University"),
        requested_as=kw.pop("requested_as", "health data request"),
        purpose=kw.pop("purpose", "Research."),
        question=question,
        definitions=definitions,
        **kw,
    )


@pytest.mark.parametrize("rid", ["R01", "R02", "R03", "R04", "R05", "R07", "R08", "R09", "R10"])
def test_track3_requests_parse_completely(settings, term, rid):
    spec, report = parse_rules(load(settings, rid), term)
    assert isinstance(report, ParseReport)
    assert report.complete, report.not_understood
    assert spec is not None
    req = load(settings, rid)
    # every definition sentence is accounted for
    accounted = " ".join(report.understood)
    for sentence in req.definitions:
        assert sentence.split(";")[0].strip()[:15] in accounted


@pytest.mark.parametrize("rid", ["R01", "R03", "R07", "R08", "R09"])
def test_parsed_numbers_match_expected(settings, db, term, rid):
    spec, report = parse_rules(load(settings, rid), term)
    assert spec is not None, report.not_understood
    raw, _ = engine.run_statistics(spec, db)
    table = disclose_table(raw)
    assert len(table.dimensions) == 1
    dim = table.dimensions[0]
    groups = {row.group[dim]: list(row.values.values()) for row in table.rows}
    answer = expected(settings)[rid]["answer"]
    assert set(answer) == set(groups)
    for key, exp in answer.items():
        wanted = list(exp.values()) if isinstance(exp, dict) else [exp]
        for value in wanted:
            assert value in groups[key], (rid, key, value, groups[key])


def test_r01_percent_comes_from_definition(settings, term):
    spec, _ = parse_rules(load(settings, "R01"), term)
    by_name = {m.name: m for m in spec.metrics}
    pct = [m for m in spec.metrics if m.kind == "percent"]
    assert [m.label for m in pct] == ["Prevalence"]
    assert [c.codes.prefixes for c in by_name[pct[0].numerator].where] == [["E11"]]
    assert by_name[pct[0].denominator].where == []


def test_r05_cohort_and_record_types(settings, db, term):
    spec, report = parse_rules(load(settings, "R05"), term)
    assert report.complete, report.not_understood
    assert spec.output == "cohort_size"
    assert len(engine.cohort_patient_ids(spec, db)) == 1152
    assert spec.record_types == ["conditions", "medications", "observations"]
    assert spec.observation_codes is not None
    assert spec.observation_codes.prefixes == ["4548-4"]


def test_r08_unused_condition_joins_population(settings, term):
    spec, _ = parse_rules(load(settings, "R08"), term)
    conds = [c for c in spec.population if isinstance(c, ConditionCriterion)]
    assert [c.codes.prefixes for c in conds] == [["C50"]]


def test_r06_patient_listing_not_understood(settings, term):
    spec, report = parse_rules(load(settings, "R06"), term)
    assert not report.complete
    assert any("patient ID" in s for s in report.not_understood)
    assert any("patient-level listing" in n for n in report.notes)


BANDS = "Age bands on 31 December 2025: 0-49, 50+."


@pytest.mark.parametrize(
    ("sentence", "dims"),
    [
        ("Report per hospital: patients with heart failure.", ["data_holder"]),
        ("Report by data holder: patients with heart failure.", ["data_holder"]),
        ("Report per sex and age band: patients with heart failure.", ["sex", "age_band"]),
        ("Report for each hospital and age band: patients with heart failure.", ["data_holder", "age_band"]),
        ("Report per federal state: patients with heart failure.", ["region"]),
    ],
)
def test_group_by_synonyms(term, sentence, dims):
    spec, report = parse_rules(make_request([BANDS, sentence]), term)
    assert report.complete, report.not_understood
    assert [d.kind for d in spec.group_by] == dims
    assert spec.population[0].codes.prefixes == ["I50"]


def test_primary_icd10_definition(db, term):
    req = make_request(
        [
            "Pneumonia stay = inpatient encounter whose main diagnosis (primary_icd10) starts with J18.",
            "Count stays (not patients) whose start_date is in 2024.",
            "Report per hospital: pneumonia stays.",
        ]
    )
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.primary_icd10.prefixes == ["J18"]
    assert spec.encounter_scope.types == ["inpatient"]
    assert str(spec.encounter_scope.start_from) == "2024-01-01"
    assert str(spec.encounter_scope.start_to) == "2024-12-31"
    assert [d.kind for d in spec.group_by] == ["data_holder"]
    assert any(m.table == "primary_icd10" for m in report.mappings)
    raw, _ = engine.run_statistics(spec, db)
    assert sum(r.cells[spec.metrics[0].name].n for r in raw.rows) > 0


def test_plain_text_without_codes(db, term):
    req = make_request(
        [
            "Asthma = a diagnosis of asthma.",
            "Inhaler = an active prescription of salmeterol/fluticasone.",
            "Report per region: patients with asthma, % with an active inhaler.",
        ]
    )
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    prefixes = {tuple(m.codes.prefixes): m.table for m in report.mappings}
    assert prefixes[("J45",)] == "conditions"
    assert prefixes[("R03AK06",)] == "medications"
    kinds = [m.kind for m in spec.metrics]
    assert kinds.count("percent") == 1
    engine.run_statistics(spec, db)


def test_unknown_term_is_not_understood(term):
    req = make_request(["Gout = any diagnosis of gout.", "Report per region: patients with gout."])
    _spec, report = parse_rules(req, term)
    assert not report.complete
    assert "Gout = any diagnosis of gout." in report.not_understood


def test_negation_and_active_from_text(term):
    req = make_request(
        [
            "Heart failure = any condition with an ICD-10 code starting with I50.",
            "Beta blocker = ATC code starting with C07.",
            "Report per region: patients with heart failure, how many of them have no active beta blocker and that share in %.",
        ]
    )
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    counts = [m for m in spec.metrics if m.kind == "count"]
    med = counts[1].where[0]
    assert med.kind == "medication" and med.negate and med.active_only
    pct = [m for m in spec.metrics if m.kind == "percent"][0]
    assert (pct.numerator, pct.denominator) == (counts[1].name, counts[0].name)


def test_question_fallback_grouping(term):
    req = make_request(
        ["COPD = any condition with an ICD-10 code starting with J44."],
        question="How many patients have COPD, by region?",
    )
    spec, report = parse_rules(req, term)
    assert spec is not None
    assert [d.kind for d in spec.group_by] == ["region"]


def test_primary_diagnosis_in_plain_text_without_count_sentence(term):
    req = make_request(
        [
            "Hip fracture = any condition with an ICD-10 code starting with S72.",
            "Hip fracture stay = inpatient stay with a main diagnosis of hip fracture.",
            "Report per hospital: hip fracture stays.",
        ]
    )
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.types == ["inpatient"]
    assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]
    assert spec.population == []  # the condition term is used by the stay definition


def test_several_with_phrases_and_lookup(term):
    req = make_request(["Report per region: patients with heart failure and hypertension without an active beta blocker."])
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    kinds = {(c.kind, tuple(c.codes.prefixes), getattr(c, "negate", False)) for c in spec.population}
    assert kinds == {("condition", ("I50",), False), ("condition", ("I10",), False), ("medication", ("C07",), True)}


def test_region_filter_and_clean_labels(term):
    req = make_request(["Report per sex: adults with asthma in Wien and their mean BMI with one decimal."])
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    assert any(c.kind == "region" and c.values == ["Wien"] for c in spec.population)
    assert [m.label for m in spec.metrics] == ["Adults with asthma in Wien", "Mean BMI"]


def test_undefined_encounter_phrase_is_a_patient_criterion(term):
    spec, report = parse_rules(make_request(["Report per region: patients with an inpatient stay."]), term)
    assert report.complete, report.not_understood
    assert spec.unit == "patient"
    assert [(c.kind, c.types) for c in spec.population] == [("encounter", ["inpatient"])]


def test_mean_before_any_count_keeps_its_population(term):
    req = make_request(["Report per region: average systolic blood pressure of adults with hypertension."])
    spec, report = parse_rules(req, term)
    assert report.complete, report.not_understood
    assert {c.kind for c in spec.population} == {"age", "condition"}
    assert spec.metrics[0].kind == "mean" and spec.metrics[0].codes.prefixes == ["8480-6"]


def test_no_metrics_returns_none(term):
    spec, report = parse_rules(make_request(["Something entirely different."], question="Tell me."), term)
    assert spec is None
    assert not report.complete
