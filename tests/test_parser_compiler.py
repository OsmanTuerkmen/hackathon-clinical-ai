import json
from pathlib import Path

import pytest

from accessdesk.plan import compiler, parser
from accessdesk.plan.model import Comparison, Concept, Term


def _request(data_dir, request_id):
    path = Path(data_dir).parent / "requests" / f"{request_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def test_official_requests_parse_to_expected_groups_and_measure_types(data_dir, desk):
    expected = {
        "R01": (["region"], ["count", "count", "pct"]),
        "R02": (["age_band"], ["count", "mean"]),
        "R03": (["age_band"], ["count", "count", "pct"]),
        "R04": (["region"], ["count"]),
        "R05": ([], ["count"]),
        "R06": ([], ["count"]),
        "R07": (["region"], ["count"]),
        "R08": (["region"], ["count", "mean"]),
        "R09": (["age_band"], ["count", "pct", "pct"]),
        "R10": (["region", "age_band"], ["count"]),
    }
    for request_id, (groups, measures) in expected.items():
        plan = parser.parse(_request(data_dir, request_id), desk.store)
        assert [group.dim for group in plan.groups] == groups
        assert [measure.type for measure in plan.measures] == measures


def test_demo_requests_parse_without_warnings(desk):
    root = Path(__file__).resolve().parents[1] / "demo" / "requests"
    for path in sorted(root.glob("D*.json")):
        with path.open(encoding="utf-8") as stream:
            plan = parser.parse(json.load(stream), desk.store)
        assert not plan.warnings, path.name


def test_sql_rechecks_opt_out_filter_and_materializes_all_requested_groups(data_dir, desk):
    plan = parser.parse(_request(data_dir, "R10"), desk.store)
    result = compiler.run(plan, desk.store)

    assert "p.opted_out = false" in result["sql"]
    assert len(result["raw"]) == 90
    assert all(next(iter(cells.values()))["type"] == "count" for cells in result["raw"].values())


def test_compiler_rejects_unsafe_codes_values_bands_and_comparators(data_dir, desk):
    condition_plan = parser.parse(_request(data_dir, "R01"), desk.store)
    condition_id = next(
        key for key, concept in condition_plan.concepts.items()
        if concept.kind == "condition"
    )
    unsafe_code = condition_plan.model_copy(deep=True)
    unsafe_code.concepts[condition_id] = unsafe_code.concepts[condition_id].model_copy(
        update={"prefixes": ["E11'; DROP TABLE patients; --"]}
    )
    with pytest.raises(compiler.PlanError):
        compiler.run(unsafe_code, desk.store)

    unsafe_value = condition_plan.model_copy(deep=True)
    unsafe_value.concepts["injected_region"] = Concept(
        id="injected_region", name="Region", kind="region", source="test",
        value="Wien'; DROP TABLE patients; --",
    )
    with pytest.raises(compiler.PlanError):
        compiler.run(unsafe_value, desk.store)

    age_plan = parser.parse(_request(data_dir, "R10"), desk.store)
    unsafe_band = age_plan.model_copy(deep=True)
    first_group = unsafe_band.groups[1]
    unsafe_band.groups[1] = first_group.model_copy(update={
        "bands": [
            first_group.bands[0].model_copy(update={"label": "0-9'; DROP TABLE patients; --"}),
            *first_group.bands[1:],
        ]
    })
    with pytest.raises(compiler.PlanError):
        compiler.run(unsafe_band, desk.store)

    observation_plan = parser.parse(_request(data_dir, "R02"), desk.store)
    unsafe_comparator = observation_plan.model_copy(deep=True)
    observation_id = next(
        key for key, concept in unsafe_comparator.concepts.items()
        if concept.kind == "observation"
    )
    bad_term = Term(concept=observation_id, cmp=Comparison(op=">", value=8))
    bad_term = bad_term.model_copy(update={
        "cmp": bad_term.cmp.model_copy(update={"op": ">; DROP TABLE patients; --"})
    })
    unsafe_comparator.measures[0] = unsafe_comparator.measures[0].model_copy(
        update={"set": [bad_term]}
    )
    with pytest.raises(compiler.PlanError):
        compiler.run(unsafe_comparator, desk.store)


def test_compiler_requires_a_validated_query_plan(desk):
    with pytest.raises(compiler.PlanError):
        compiler.Compiler({}, desk.store)
