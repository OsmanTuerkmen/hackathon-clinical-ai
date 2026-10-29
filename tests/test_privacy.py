from decimal import Decimal

import pytest

from accessdesk.safes.outputs import (
    Gate,
    LT,
    SUPPRESSED,
    assert_no_leak,
    protect_count,
    round1,
)


def test_rounds_half_up():
    assert round1(Decimal("37.25")) == 37.3


@pytest.mark.parametrize(("value", "expected"), [(0, LT), (9, LT), (10, 10)])
def test_counts_below_threshold_are_hidden(value, expected):
    assert Gate().cell({"type": "count", "value": value}) == expected


@pytest.mark.parametrize(
    ("num", "den", "expected"),
    [(9, 100, SUPPRESSED), (10, 9, SUPPRESSED), (30, 81, 37.0)],
)
def test_percentages_require_safe_numerator_and_denominator(num, den, expected):
    assert Gate().cell({"type": "pct", "num": num, "den": den}) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"type": "mean", "sum10": 900, "n": 9, "patients": 9}, SUPPRESSED),
        ({"type": "mean", "sum10": 0, "n": 0, "patients": 10}, SUPPRESSED),
        ({"type": "mean", "sum10": 2720, "n": 10, "patients": 10}, 27.2),
    ],
)
def test_means_require_ten_patients_and_a_value(raw, expected):
    assert Gate().cell(raw) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, LT), (9, LT), (10, 10), (14, 10), (15, 20), (1152, 1150), (1155, 1160)],
)
def test_applicant_estimates_round_to_nearest_ten_half_up(value, expected):
    assert protect_count(value) == expected


@pytest.mark.parametrize(
    ("released", "message"),
    [
        ({"rows": [{"group": [], "values": {"n": 9}}]}, "count below threshold"),
        ({"rows": [{"group": [], "values": {"n": "private"}}]}, "unexpected text"),
        ({"rows": [{"group": ["p-001"], "values": {}}]}, "patient identifier"),
    ],
)
def test_leak_assertion_rejects_unsafe_release(released, message):
    with pytest.raises(AssertionError, match=message):
        assert_no_leak(released)
