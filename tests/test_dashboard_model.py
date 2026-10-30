"""Pure chart and CSV logic behind the Doccess dashboard, exercised in Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] / "web" / "dashboard.js").as_posix()
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def metric(name, kind, label=None):
    return {"name": name, "label": label or name, "kind": kind}


TABLE = {
    "dimensions": ["region"],
    "metrics": [metric("adults", "count", "Adults"), metric("t2d", "count", "Adults with type 2 diabetes"), metric("prevalence", "percent", "Prevalence")],
    "rows": [
        {"group": {"region": "Burgenland"}, "values": {"adults": 532, "t2d": 33, "prevalence": 6.2}},
        {"group": {"region": "Niederösterreich"}, "values": {"adults": 2740, "t2d": 227, "prevalence": 8.3}},
        {"group": {"region": "Tirol"}, "values": {"adults": 1240, "t2d": 110, "prevalence": 8.9}},
        {"group": {"region": "Wien"}, "values": {"adults": "<10", "t2d": "<10", "prevalence": "suppressed"}},
    ],
}
NESTED = {
    "dimensions": ["region", "sex"],
    "metrics": [metric("patients", "count", "Patients")],
    "rows": [{"group": {"region": r, "sex": s}, "values": {"patients": n}} for r, s, n in [("Wien", "female", 40), ("Wien", "male", "<10"), ("Tirol", "female", 20), ("Tirol", "male", 12)]],
}


def run(expression, **values):
    script = f"const m = require({json.dumps(SCRIPT)}); const v = {json.dumps(values)}; process.stdout.write(JSON.stringify({expression}));"
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(done.stdout)


def test_default_metric_prefers_the_last_percentage():
    assert run("m.defaultMetric(v.table)", table=TABLE) == "prevalence"


def test_default_metric_falls_back_to_the_first_count():
    assert run("m.defaultMetric(v.table)", table=NESTED) == "patients"


def test_masked_cells_stay_masked_and_never_enter_the_scale():
    model = run("m.chartModel(v.table, 'prevalence')", table=TABLE)
    wien = model["bars"][3]
    assert wien["masked"] is True and wien["value"] is None and wien["display"] == "suppressed"
    assert max(bar["heightPct"] for bar in model["bars"] if not bar["masked"]) == 100
    assert model["bars"][2]["heightPct"] == 100


def test_small_values_keep_a_minimum_height():
    table = {"dimensions": ["region"], "metrics": [metric("n", "count")], "rows": [{"group": {"region": "A"}, "values": {"n": 1}}, {"group": {"region": "B"}, "values": {"n": 1000}}]}
    assert run("m.chartModel(v.table, 'n')", table=table)["bars"][0]["heightPct"] == 6


def test_every_masked_bar_has_the_same_height():
    table = {"dimensions": ["region"], "metrics": [metric("n", "count")], "rows": [{"group": {"region": r}, "values": {"n": "<10"}} for r in "AB"] + [{"group": {"region": "C"}, "values": {"n": 50}}]}
    bars = run("m.chartModel(v.table, 'n')", table=table)["bars"]
    assert bars[0]["heightPct"] == bars[1]["heightPct"]


def test_percentages_keep_one_decimal():
    table = {"dimensions": ["region"], "metrics": [metric("p", "percent")], "rows": [{"group": {"region": "A"}, "values": {"p": 8}}]}
    assert run("m.chartModel(v.table, 'p')", table=table)["bars"][0]["display"] == "8.0"


def test_counts_use_a_thousands_separator():
    assert run("m.chartModel(v.table, 'adults')", table=TABLE)["bars"][1]["display"] == "2,740"


def test_short_label_is_three_characters_and_keeps_the_full_label():
    bar = run("m.chartModel(v.table, 'prevalence')", table=TABLE)["bars"][1]
    assert bar["shortLabel"] == "Nie" and bar["label"] == "Niederösterreich"


def test_more_than_twelve_groups_switch_to_horizontal():
    rows = [{"group": {"region": f"R{i}"}, "values": {"n": i + 10}} for i in range(13)]
    table = {"dimensions": ["region"], "metrics": [metric("n", "count")], "rows": rows}
    assert run("m.chartModel(v.table, 'n')", table=table)["horizontal"] is True
    assert run("m.chartModel(v.table, 'adults')", table=TABLE)["horizontal"] is False


def test_further_dimensions_become_filters():
    model = run("m.chartModel(v.table, 'patients')", table=NESTED)
    assert model["axis"] == "region"
    assert model["filters"] == [{"dimension": "sex", "options": ["female", "male"], "selected": "female"}]
    assert [bar["label"] for bar in model["bars"]] == ["Wien", "Tirol"]


def test_filter_selection_changes_the_bars():
    model = run("m.chartModel(v.table, 'patients', {sex: 'male'})", table=NESTED)
    assert [bar["display"] for bar in model["bars"]] == ["<10", "12"]


def test_summary_names_the_highest_value_when_all_is_shown():
    table = {**TABLE, "rows": TABLE["rows"][:3]}
    assert run("m.summary(m.chartModel(v.table, 'prevalence'))", table=table) == "Highest: Tirol (8.9%). All 3 groups are shown in full."


def test_summary_explains_hidden_groups():
    assert run("m.summary(m.chartModel(v.table, 'prevalence'))", table=TABLE) == "1 of 4 groups is partly hidden because fewer than 10 patients were involved."


def test_fully_shown_counts_groups_without_any_masked_cell():
    assert run("m.fullyShown(v.table)", table=TABLE) == {"shown": 3, "total": 4}


def test_protected_cells_are_counted_across_the_table():
    assert run("m.protectedCells(v.table)", table=TABLE) == 3


def test_csv_contains_exactly_the_released_values():
    assert run("m.toCsv(v.table)", table=TABLE).split("\r\n") == [
        "region,Adults,Adults with type 2 diabetes,Prevalence (%)",
        "Burgenland,532,33,6.2",
        "Niederösterreich,2740,227,8.3",
        "Tirol,1240,110,8.9",
        "Wien,<10,<10,suppressed",
        "",
    ]


def test_csv_quotes_separators_and_neutralises_formulas():
    table = {"dimensions": ["group"], "metrics": [metric("n", "count", "=SUM(A1)")], "rows": [{"group": {"group": 'a,"b'}, "values": {"n": 10}}, {"group": {"group": "@cmd"}, "values": {"n": 11}}]}
    lines = run("m.toCsv(v.table)", table=table).split("\r\n")
    assert lines[0] == "group,'=SUM(A1)"
    assert lines[1] == '"a,""b",10'
    assert lines[2] == "'@cmd,11"


def test_csv_keeps_negative_numbers_numeric():
    table = {"dimensions": ["group"], "metrics": [metric("m", "mean", "Mean change"), metric("n", "count", "Patients")], "rows": [{"group": {"group": "A"}, "values": {"m": -3.2, "n": 12}}]}
    assert run("m.toCsv(v.table)", table=table).split("\r\n")[1] == "A,-3.2,12"


def test_csv_writes_missing_values_as_empty_cells():
    table = {"dimensions": ["group"], "metrics": [metric("n", "count", "Patients")], "rows": [{"group": {"group": "A"}, "values": {"n": None}}]}
    assert run("m.toCsv(v.table)", table=table).split("\r\n")[1] == "A,"


def test_csv_still_neutralises_negative_looking_text():
    assert run("m.csvCell('-1+1')") == "'-1+1"


def test_summary_handles_an_empty_table():
    table = {**TABLE, "rows": []}
    assert run("m.summary(m.chartModel(v.table, 'prevalence'))", table=table) == "No groups to show."


def test_default_metric_handles_a_table_without_metrics():
    assert run("m.defaultMetric(v.table)", table={"dimensions": [], "metrics": [], "rows": []}) is None


def test_filters_accept_non_string_group_values():
    table = {"dimensions": ["region", "year"], "metrics": [metric("n", "count")], "rows": [{"group": {"region": "A", "year": y}, "values": {"n": n}} for y, n in [(2024, 11), (2025, 22)]]}
    model = run("m.chartModel(v.table, 'n', {year: '2025'})", table=table)
    assert [bar["display"] for bar in model["bars"]] == ["22"]


def test_export_filename_keeps_only_safe_characters():
    assert run("m.exportName('../R 01')") == "doccess-R01-statistics.csv"
