import json
from pathlib import Path

from accessdesk.config import build_desk, load_requests
from accessdesk.plan import compiler, parser


def _request_map(data_dir):
    requests = {request["id"]: request for _, request in load_requests(data_dir)}
    oracle = Path(__file__).resolve().parent / "oracle" / "requests"
    for path in sorted(oracle.glob("T*.json")):
        requests[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return requests


def test_cell_sets_match_raw_counts_for_oracle_requests(data_dir, tmp_path):
    desk = build_desk(data_dir, runtime_dir=tmp_path / "runtime")
    requests = _request_map(data_dir)
    try:
        for request_id, request in requests.items():
            plan = parser.parse(request, desk.store)
            raw = compiler.run(plan, desk.store)["raw"]
            sets = compiler.cell_sets(plan, desk.store)
            for group, measures in raw.items():
                for key, cell in measures.items():
                    if cell["type"] == "count":
                        assert len(sets.get((group, key, "value"), set())) == cell["value"], request_id
                    elif cell["type"] == "pct":
                        assert len(sets.get((group, key, "num"), set())) == cell["num"], request_id
                        assert len(sets.get((group, key, "den"), set())) == cell["den"], request_id
                    else:
                        assert len(sets.get((group, key, "patients"), set())) == cell["patients"], request_id
    finally:
        desk.store.con.close()


def test_followup_request_suppresses_only_small_differences(data_dir, tmp_path):
    requests = _request_map(data_dir)
    desk = build_desk(data_dir, runtime_dir=tmp_path / "paired")
    try:
        desk.process(requests["R01"], use_cache=False, differencing=True)
        result = desk.process(requests["D05"], use_cache=False, differencing=True)
        expected = {
            "Burgenland": [522, 33, 6.3],
            "Kärnten": [867, 71, 8.2],
            "Niederösterreich": [2691, 227, 8.4],
            "Oberösterreich": [2439, 173, 7.1],
            "Salzburg": [896, 75, 8.4],
            "Steiermark": [2021, 164, 8.1],
            "Tirol": [1221, 110, 9.0],
            "Vorarlberg": ["suppressed", 36, "suppressed"],
            "Wien": [3201, 263, 8.2],
        }
        measures = [measure["key"] for measure in result["released"]["measures"]]
        actual = {
            row["group"][0]: [row["values"][key] for key in measures]
            for row in result["released"]["rows"]
        }
        assert actual == expected
        suppressed = result["released"]["differencing"]["suppressed"]
        assert len(suppressed) == 2
        assert {item["group"][0] for item in suppressed} == {"Vorarlberg"}
        assert {item["difference"] for item in suppressed} == {8}
        assert {item["against"]["request_id"] for item in suppressed} == {"R01"}
        assert {(item["measure"], item["part"]) for item in suppressed} == {
            ("adults", "value"),
            ("prevalence_pct", "den"),
        }
        assert result["five_safes"]["outputs"]["status"] == "warn"
    finally:
        desk.store.con.close()


def test_followup_without_previous_release_and_identical_releases(data_dir, tmp_path):
    requests = _request_map(data_dir)
    alone = build_desk(data_dir, runtime_dir=tmp_path / "alone")
    repeated = build_desk(data_dir, runtime_dir=tmp_path / "repeated")
    try:
        alone_result = alone.process(requests["D05"], use_cache=False, differencing=True)
        row = next(row for row in alone_result["released"]["rows"] if row["group"] == ["Vorarlberg"])
        measures = [measure["key"] for measure in alone_result["released"]["measures"]]
        assert [row["values"][key] for key in measures] == [631, 36, 5.7]
        assert alone_result["released"]["differencing"]["suppressed"] == []

        results = [
            repeated.process(requests["R01"], use_cache=False, differencing=True)
            for _ in range(3)
        ]
        assert all(item["released"]["differencing"]["suppressed"] == [] for item in results)
    finally:
        alone.store.con.close()
        repeated.store.con.close()
