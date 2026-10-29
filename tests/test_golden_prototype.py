"""Regression: the new architecture gives exactly the prototype's results.

tests/golden/prototype.json was written by tools/freeze_prototype.py from the
original prototype (../ehds-accessdesk). For the official requests and the
demo cases, decision, articles, delivery status, cohort size and every
released value must be identical. For the own test requests T01-T15 the
pandas oracle is the reference (test_oracle.py): the prototype approves the
disguised prohibited purposes T05-T07, which is what those tests are for.
"""
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "golden", "prototype.json"), encoding="utf-8") as f:
    GOLDEN = json.load(f)
IDS = sorted(k for k in GOLDEN if k[0] in "RD")


def _request(data_dir, rid):
    folder = os.path.join(data_dir, "..", "requests") if rid[0] == "R" else os.path.join(ROOT, "demo", "requests")
    with open(os.path.join(folder, rid + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("rid", IDS)
def test_identical_to_prototype(desk, data_dir, rid):
    g = GOLDEN[rid]
    res = desk.process(_request(data_dir, rid), use_cache=False, actor="golden-test")
    assert res["decision"]["decision"] == g["decision"]
    assert sorted(res["decision"]["articles"]) == sorted(g["articles"])
    assert res["delivery"]["status"] == g["delivery"]
    assert (res.get("spe") or {}).get("cohort_size") == g["cohort_size"]
    if g["rows"] is None:
        assert res.get("released") is None
    else:
        got = {tuple(r["group"]): list(r["values"].values()) for r in res["released"]["rows"]}
        want = {tuple(r["group"]): r["values"] for r in g["rows"]}
        assert got == want
