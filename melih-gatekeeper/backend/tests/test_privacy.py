from app.privacy import leak_check, publish_cell, round_half_up


def test_counts():
    assert [publish_cell({"kind": "count", "value": v}) for v in (0, 1, 9, 10, 11)] == ["<10", "<10", "<10", 10, 11]


def test_pct_suppression():
    assert publish_cell({"kind": "pct", "value": 50.0, "num": 9, "den": 18}) == "suppressed"
    assert publish_cell({"kind": "pct", "value": 100.0, "num": 10, "den": 9}) == "suppressed"
    assert publish_cell({"kind": "pct", "value": 100.0, "num": 10, "den": 10}) == 100.0
    assert publish_cell({"kind": "pct", "value": None, "num": 0, "den": 0}) == "suppressed"


def test_mean_suppression():
    assert publish_cell({"kind": "mean", "value": 27.0, "n": 9}) == "suppressed"
    assert publish_cell({"kind": "mean", "value": 27.04, "n": 10}) == 27.0


def test_round_half_up_not_bankers():
    assert round(0.125, 2) == 0.12  # Python's banker's rounding: the trap
    assert round_half_up(0.05) == 0.1
    assert round_half_up(6.25) == 6.3
    assert round_half_up(6.249999) == 6.2
    assert round_half_up(0.15) == 0.2


def test_leak_check():
    assert leak_check({"Wien": {"a": 12, "b": "<10", "c": 7.5}}) == []
    assert leak_check({"Wien": {"a": 9}})
    assert leak_check({"x": "p-1234abcd"})
    assert leak_check({"rows": [1, 2]})
