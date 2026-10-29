"""The five Track 3 metrics on the 10 official requests must stay on target."""
import glob
import json
import os

from accessdesk import evaluation


def test_official_metrics_on_target(desk, data_dir):
    reqs = []
    for f in sorted(glob.glob(os.path.join(data_dir, "..", "requests", "R*.json"))):
        with open(f, encoding="utf-8") as fh:
            reqs.append(json.load(fh))
    assert len(reqs) == 10
    res = evaluation.run(desk, reqs, runs=3)
    s = res["summary"]
    assert s["correct_decisions"] == "10 / 10", res["rows"]
    assert s["correct_numbers"] == "6 / 6", res["rows"]
    assert s["privacy_leaks"] == 0, [(r["id"], r["leaks"]) for r in res["rows"]]
    assert s["consistency"] == "10 / 10", res["rows"]
    assert s["slowest_ms"] < 60_000
    assert res["opted_out_rows_in_store"] == 0
    assert s["targets_met"]
