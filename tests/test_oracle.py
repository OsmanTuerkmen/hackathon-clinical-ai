"""Official, demo and own jury-style requests against the pandas oracle (strict).

tests/oracle/oracle.py computes every expected value directly with pandas and
first reproduces the official expected.json. Here the app must give exactly
the same decision, articles, groups and values (in report order), the same
cohort size and SPE contents, and the same cohort funnel where the oracle
lists one. No leaks are allowed either.
"""
import json
import os

import pytest

from accessdesk import evaluation

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "oracle", "expected.json"), encoding="utf-8") as f:
    ORACLE = json.load(f)


def _request(data_dir, rid):
    folder = {"R": os.path.join(data_dir, "..", "requests"),
              "D": os.path.join(ROOT, "demo", "requests"),
              "T": os.path.join(HERE, "oracle", "requests")}[rid[0]]
    with open(os.path.join(folder, rid + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("rid", sorted(ORACLE))
def test_matches_oracle(desk, data_dir, rid):
    res = desk.process(_request(data_dir, rid), use_cache=False, actor="oracle-test")
    problems = evaluation.compare_strict(res, ORACLE[rid], desk.root)
    problems += evaluation.leak_check(res, desk.store.opted_ids, desk.root)
    assert not problems, problems
