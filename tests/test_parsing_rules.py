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
        # per metric, in report order (metric names differ from expected.json, positions do not)
        wanted = list(exp.values()) if isinstance(exp, dict) else [exp]
        assert groups[key] == wanted, (rid, key, groups[key], wanted)


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


# --- Fix round 1: jury-style wordings (review probes) ---------------------------------------------

D = "Diabetes = any condition with an ICD-10 code starting with E11."
H = "Hypertension = any condition with an ICD-10 code starting with I10."
INS = "Insulin = ATC code starting with A10A."


def parse(term, defs, question="How many patients?", **kw):
    return parse_rules(make_request(defs, question, **kw), term)


def all_criteria(spec):
    crit = list(spec.population)
    for m in spec.metrics:
        crit += list(getattr(m, "where", []))
    return crit


@pytest.mark.parametrize(
    ("defs", "question"),
    [
        ([D, "Report per region: smokers with diabetes."], None),
        ([D, "Report per sex: patients with diabetes treated at LKH Graz."], None),
        ([D, "Report per region: patients diagnosed with diabetes after 2020."], None),
        ([D, "Report per region: patients with diabetes diagnosed in 2024."], None),
        (["Report per region: median BMI of adults with diabetes."], None),
        (["Report per region: patients with an inpatient stay in the last 12 months."], None),
        (["Report per region: patients with at least two inpatient stays."], None),
        (["Report per hospital: readmissions within 30 days."], None),
        ([D, "Report per region: the total."], None),
        (["Report per region: patients with diabetes with HbA1c above 8%."], None),
        ([D, "Report per region: patients with diabetes, how many have an HbA1c value above 9 %."], None),
        (["Cohort = adults with diabetes who smoke.", D, "Report the size of the cohort."], None),
        (["Cohort = adults with diabetes and with retinopathy.", D, "Report the size of the cohort."], None),
        ([D, "Report per region: patients with diabetes and women."], None),
        ([D], "How many smokers have diabetes, by region?"),
        (["Asthma = any condition with an ICD-10 code starting with J45."], "How many patients have asthma, by municipality and region?"),
        ([D], "How many patients have diabetes, per hospital and per region and per year?"),
        (["Report per region: patients with type 1 or type 2 diabetes."], None),
        (["Asthma = any condition with an ICD-10 code starting with J45.", "Report per region: patients with asthma and their mean age."], None),
    ],
)
def test_residual_words_are_not_understood(term, defs, question):
    _spec, report = parse(term, defs, question or "How many patients?")
    assert not report.complete


@pytest.mark.parametrize(
    ("defs", "item_crit"),
    [
        ([D, INS, "Report per region: patients with diabetes, how many of them are not treated with insulin."], "where"),
        ([D, INS, "Report per region: patients with diabetes, how many of them never received insulin."], "where"),
        ([D, INS, "Report per region: patients with diabetes, how many of them lack insulin."], "where"),
        ([D, INS, "Report per region: patients with diabetes who have never been on insulin."], "population"),
        ([D, H, "Report per region: patients with diabetes excluding those with hypertension."], "population"),
        ([D, H, "Report per region: patients with diabetes except those with hypertension."], "population"),
        ([D, H, "Report per region: patients with diabetes but free of hypertension."], "population"),
        ([D, "Report per region: patients with diabetes other than those on insulin."], "population"),
        ([D, "Report per region: adults, how many of them are diabetes-free."], "where"),
    ],
)
def test_exclusion_wordings_negate(term, defs, item_crit):
    spec, report = parse(term, defs)
    assert report.complete, report.not_understood
    crit = spec.population if item_crit == "population" else [c for m in spec.metrics for c in getattr(m, "where", [])]
    negated = [c for c in crit if getattr(c, "negate", False)]
    assert len(negated) == 1
    assert negated[0].codes.prefixes in (["A10A"], ["I10"], ["E11"])


@pytest.mark.parametrize(
    "item",
    [
        "patients with diabetes but not hypertension",
        "adults, how many of them are non-diabetic",
    ],
)
def test_unhandled_exclusion_is_not_understood(term, item):
    _spec, report = parse(term, [D, f"Report per region: {item}."])
    assert not report.complete


@pytest.mark.parametrize(
    ("item", "values"),
    [
        ("patients in Vienna with diabetes", ["Wien"]),
        ("patients with diabetes in Steiermark or Wien", ["Steiermark", "Wien"]),
        ("patients with diabetes living in Upper Austria", ["Oberösterreich"]),
    ],
)
def test_region_filters(term, item, values):
    spec, report = parse(term, [D, f"Report per sex: {item}."])
    assert report.complete, report.not_understood
    assert [c.values for c in spec.population if c.kind == "region"] == [values]


@pytest.mark.parametrize("item", ["patients with diabetes not living in Wien", "patients with diabetes outside Wien"])
def test_negated_region_is_not_understood(term, item):
    _spec, report = parse(term, [D, f"Report per sex: {item}."])
    assert not report.complete


def test_main_diagnosis_from_defined_term(term):
    spec, report = parse(
        term,
        [
            "Hip fracture = main diagnosis (primary_icd10) starting with S72.",
            "Count inpatient stays in 2025.",
            "Report per hospital: inpatient stays with a main diagnosis of hip fracture.",
        ],
    )
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.types == ["inpatient"]
    assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]
    assert str(spec.encounter_scope.start_from) == "2025-01-01"
    assert [d.kind for d in spec.group_by] == ["data_holder"]
    assert spec.population == []


@pytest.mark.parametrize(
    "item",
    [
        "inpatient stays with a main diagnosis of hip fracture",
        "inpatient stays with main diagnosis hip fracture",
        "inpatient stays whose main diagnosis is hip fracture",
        "inpatient stays with primary_icd10 S72",
        "inpatient stays whose main diagnosis starts with S72",
    ],
)
def test_main_diagnosis_without_definition(term, item):
    spec, report = parse(term, ["Count inpatient stays in 2025.", f"Report per hospital: {item}."])
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.types == ["inpatient"]
    assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]
    assert spec.population == []


def test_main_diagnosis_in_count_sentence(term):
    spec, report = parse(
        term,
        [
            "Count inpatient stays whose main diagnosis (primary_icd10) starts with S72 and whose start_date is in 2025.",
            "Report per hospital: stays.",
        ],
    )
    assert report.complete, report.not_understood
    assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]
    assert spec.encounter_scope.types == ["inpatient"]


@pytest.mark.parametrize(
    ("defs", "types", "prefixes"),
    [
        (["Count emergency visits in 2024.", "Report per hospital: visits."], ["emergency"], None),
        (
            ["Fracture stay = inpatient stay whose main diagnosis starts with S72 or S82.", "Report per hospital: fracture stays."],
            ["inpatient"],
            ["S72", "S82"],
        ),
        (
            ["Hip fracture stay = inpatient stay with primary_icd10 S72.", "Report per hospital: hip fracture stays."],
            ["inpatient"],
            ["S72"],
        ),
        (
            ["Hospital stay = encounter with type 'inpatient' or 'emergency'.", "Report per hospital: hospital stays."],
            ["inpatient", "emergency"],
            None,
        ),
    ],
)
def test_encounter_wordings(term, defs, types, prefixes):
    spec, report = parse(term, defs)
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.types == types
    primary = spec.encounter_scope.primary_icd10
    assert (primary.prefixes if primary else None) == prefixes


@pytest.mark.parametrize(
    "defs",
    [
        ["Pneumonia = any condition with an ICD-10 code starting with J18.", "Count inpatient stays in 2024.",
         "Report per hospital: inpatient stays for pneumonia."],
        ["Pneumonia = any condition with an ICD-10 code starting with J18.", "Count inpatient stays in 2024.",
         "Report per hospital: inpatient stays with pneumonia."],
        ["Count inpatient stays in 2025.", "Report per hospital: inpatient stays for hip fracture."],
        ["Pneumonia stay = inpatient encounter with a diagnosis code starting with J18.",
         "Count stays (not patients) whose start_date is in 2024.", "Report per hospital: pneumonia stays."],
    ],
)
def test_condition_on_stays_without_main_diagnosis_is_not_understood(term, defs):
    _spec, report = parse(term, defs)
    assert not report.complete


@pytest.mark.parametrize(
    "sentence",
    [
        "Count stays (not patients) whose end_date is in 2024.",
        "Count stays (not patients) whose start_date is after 2023.",
        "Count stays (not patients) whose start_date is in 2024 or 2025.",
    ],
)
def test_unsupported_date_rules_are_not_understood(term, sentence):
    _spec, report = parse(
        term, ["Inpatient stay = encounter with type 'inpatient'.", sentence, "Report per hospital: inpatient stays."]
    )
    assert not report.complete
    assert sentence in report.not_understood


@pytest.mark.parametrize(
    ("definition", "item", "expected"),
    [
        ("Elderly diabetic = patient aged 65 or older with an ICD-10 code starting with E11.", "elderly diabetics",
         {("age", 65, None), ("condition", "E11")}),
        ("Female diabetic = female patient with an ICD-10 code starting with E11.", "female diabetics",
         {("sex", "female"), ("condition", "E11")}),
        ("Young = aged under 40.", "young patients", {("age", None, 39)}),
    ],
)
def test_definition_analysers_combine(term, definition, item, expected):
    spec, report = parse(term, [definition, f"Report per region: {item}."])
    assert report.complete, report.not_understood
    got = set()
    for c in spec.population:
        if c.kind == "age":
            got.add(("age", c.min, c.max))
        elif c.kind == "sex":
            got.add(("sex", c.value))
        else:
            got.add((c.kind, c.codes.prefixes[0]))
    assert got == expected


@pytest.mark.parametrize(
    "definition",
    [
        "Hypertension = any condition with an ICD-10 code starting with I10, excluding I15.",
        "Hypertension = any condition with an ICD-10 code starting with I10 recorded since 2020.",
        "Hypertension = BMI of 30 or more.",
        "Hypertension = HbA1c value of 8 or higher.",
        "Hypertension = high blood pressure requiring three drugs.",
        "Hypertension = type 2 diabetes mellitus diagnosed by a GP.",
    ],
)
def test_bad_definition_bodies_are_not_understood(term, definition):
    _spec, report = parse(term, [definition, "Report per region: patients with hypertension."])
    assert definition in report.not_understood


@pytest.mark.parametrize(
    ("item", "lo", "hi"),
    [
        ("patients between 18 and 64 with hypertension", 18, 64),
        ("patients aged 18 to 64 with hypertension", 18, 64),
        ("patients older than 70 with hypertension", 71, None),
        ("patients over 65 with hypertension", 66, None),
        ("patients younger than 18 with hypertension", None, 17),
        ("patients aged >= 65 with hypertension", 65, None),
        ("patients aged 65 and older with hypertension", 65, None),
    ],
)
def test_age_wordings(term, item, lo, hi):
    spec, report = parse(term, [f"Report per region: {item}."])
    assert report.complete, report.not_understood
    assert [(c.min, c.max) for c in spec.population if c.kind == "age"] == [(lo, hi)]


def test_threshold_is_not_an_age(term):
    _spec, report = parse(term, ["Report per region: patients with a BMI over 30."])
    assert not report.complete


@pytest.mark.parametrize(("body", "active"), [("an active prescription of atorvastatin", True), ("atorvastatin", False)])
def test_active_in_definition_body(term, body, active):
    spec, report = parse(term, [f"Statin = {body}.", D, "Report per region: patients with diabetes, % on a statin."])
    assert report.complete, report.not_understood
    meds = [c for c in all_criteria(spec) if c.kind == "medication"]
    assert [m.active_only for m in meds] == [active]


# --- Fix round 2: a negator binds to the next element only ----------------------------------------


def coded(criteria):
    return {(c.kind, tuple(c.codes.prefixes), c.negate) for c in criteria if hasattr(c, "codes")}


@pytest.mark.parametrize(
    ("defs", "where", "expected"),
    [
        ([D, H, "Report per region: patients without diabetes with hypertension."], "population",
         {("condition", ("E11",), True), ("condition", ("I10",), False)}),
        ([D, INS, "Report per region: patients not on insulin with diabetes."], "population",
         {("medication", ("A10A",), True), ("condition", ("E11",), False)}),
        ([D, H, INS, "Report per region: patients with diabetes, how many of them have no insulin but have hypertension."],
         "where", {("medication", ("A10A",), True), ("condition", ("I10",), False)}),
        ([D, INS, "Cohort = adults not on insulin with diabetes.", "Report the size of the cohort."], "population",
         {("medication", ("A10A",), True), ("condition", ("E11",), False)}),
        ([D, INS, "Report per region: adults, % not on insulin with diabetes."], "where",
         {("medication", ("A10A",), True), ("condition", ("E11",), False)}),
        (["Report per region: patients not on insulin with type 2 diabetes."], "population",
         {("medication", ("A10A",), True), ("condition", ("E11",), False)}),
    ],
)
def test_negator_binds_to_the_next_element_only(term, defs, where, expected):
    spec, report = parse(term, defs)
    assert report.complete, report.not_understood
    crit = spec.population if where == "population" else [c for m in spec.metrics for c in getattr(m, "where", [])]
    assert coded(crit) == expected


def test_negated_region_does_not_negate_the_next_term(term):
    spec, report = parse(term, [D, "Report per sex: patients not in Wien with diabetes."])
    assert not report.complete
    if spec is not None:
        assert ("condition", ("E11",), True) not in coded(all_criteria(spec))
        assert not any(c.kind == "region" for c in all_criteria(spec))


def test_negated_list_is_ambiguous(term):
    _spec, report = parse(term, [D, H, "Report per region: patients without diabetes and hypertension."])
    assert not report.complete


def test_person_item_in_a_stay_count_is_not_understood(term):
    spec, report = parse(
        term,
        ["Count stays (not patients) whose start_date is in 2024.", "Report per hospital: inpatient stays, number of patients."],
    )
    assert not report.complete
    assert "number of patients" in report.not_understood
    assert [m.label for m in spec.metrics] == ["Inpatient stays"]


@pytest.mark.parametrize(
    ("definition", "item", "system", "prefixes"),
    [
        ("Diabetes = E11.", "patients with diabetes", "icd10", ["E11"]),
        ("Hip fracture = ICD-10 S72.", "patients with hip fracture", "icd10", ["S72"]),
        ("Diabetes = ICD-10 E11.*", "patients with diabetes", "icd10", ["E11"]),
        ("Metformin = ATC A10BA02.", "patients on metformin", "atc", ["A10BA02"]),
    ],
)
def test_bare_codes_in_definitions(term, definition, item, system, prefixes):
    spec, report = parse(term, [definition, f"Report per region: {item}."])
    assert report.complete, report.not_understood
    assert [(c.codes.system, c.codes.prefixes) for c in spec.population] == [(system, prefixes)]


def test_conflicting_stay_types_are_not_understood(term):
    _spec, report = parse(
        term, ["Count emergency visits in 2024.", "Report per hospital: inpatient stays with main diagnosis S72."]
    )
    assert "Count emergency visits in 2024." in report.not_understood


def test_exactly_one_is_not_at_least_one(term):
    _spec, report = parse(term, ["Report per region: patients with one inpatient stay."])
    assert not report.complete


def test_region_list_with_and(term):
    spec, report = parse(term, [D, "Report per sex: patients in Wien and Tirol with diabetes."])
    assert report.complete, report.not_understood
    assert [c.values for c in spec.population if c.kind == "region"] == [["Wien", "Tirol"]]


# --- Fix round 3 --------------------------------------------------------------------------------

CNT = "Count stays (not patients) whose start_date is in 2024."


@pytest.mark.parametrize("defs", [[CNT], []])
def test_parenthetical_not_patients_in_item(term, defs):
    spec, report = parse(term, [*defs, "Report per hospital: inpatient stays (not patients) with main diagnosis S72."])
    assert report.complete, report.not_understood
    assert spec.unit == "encounter"
    assert spec.encounter_scope.types == ["inpatient"]
    assert spec.encounter_scope.primary_icd10.prefixes == ["S72"]


@pytest.mark.parametrize("defs", [[CNT, "Report per hospital: inpatient stays per patient."], ["Report per region: inpatient stays per patient."]])
def test_per_patient_ratio_is_not_understood(term, defs):
    _spec, report = parse(term, defs)
    assert not report.complete


def test_negated_question_term_does_not_join_population(term):
    question = "How many patients without hypertension with diabetes are there?"
    spec, report = parse(term, [D, H, "Report per region: patients with diabetes."], question)
    assert not report.complete
    assert question in report.not_understood
    assert ("condition", ("I10",), False) not in coded(spec.population if spec else [])


@pytest.mark.parametrize("item", ["how many of them with diabetes", "those with diabetes"])
def test_relative_condition_on_stays_is_not_understood(term, item):
    _spec, report = parse(term, [CNT, D, f"Report per hospital: inpatient stays, {item}."])
    assert not report.complete


def test_atc_code_must_have_an_atc_main_group(term):
    _spec, report = parse(term, ["Diabetes = ATC E11.", "Report per region: patients with diabetes."])
    assert "Diabetes = ATC E11." in report.not_understood


def test_unused_term_mentioned_in_failed_item_does_not_join_population(term):
    spec, report = parse(term, [D, "Report per region: patients, patients with diabetes treated at LKH Graz."])
    assert not report.complete
    assert spec is not None
    assert spec.population == []
