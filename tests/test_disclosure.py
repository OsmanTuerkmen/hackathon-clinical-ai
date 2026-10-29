from decimal import Decimal

import pytest

from ehds_desk.disclosure import (
    SMALL,
    SUPPRESSED,
    DisclosedRow,
    DisclosedTable,
    LeakError,
    SuppressionNote,
    assert_no_leak,
    disclose_cell,
    disclose_table,
    round_half_up,
)
from ehds_desk.models import (
    CodeSet,
    CountMetric,
    MeanMetric,
    PercentMetric,
    RawCount,
    RawMean,
    RawPercent,
    RawRow,
    RawTable,
)


def test_constants():
    assert SMALL == "<10"
    assert SUPPRESSED == "suppressed"


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("0.05"), Decimal("0.1")),
        (Decimal("0.15"), Decimal("0.2")),
        (Decimal("0.25"), Decimal("0.3")),
        (Decimal("2.45"), Decimal("2.5")),
        (Decimal("37.037"), Decimal("37.0")),
        (Decimal("-0.05"), Decimal("-0.1")),
    ],
)
def test_round_half_up(value, expected):
    result = round_half_up(value)
    assert result == expected
    assert result.as_tuple().exponent == -1


def test_round_half_up_places():
    assert round_half_up(Decimal("1.005"), 2) == Decimal("1.01")
    assert round_half_up(Decimal("2.5"), 0) == Decimal("3")


@pytest.mark.parametrize("n, expected", [(0, "<10"), (9, "<10"), (10, 10), (3247, 3247)])
def test_counts(n, expected):
    out = disclose_cell(RawCount(n=n))
    assert out == expected
    assert type(out) is type(expected)


@pytest.mark.parametrize(
    "num, den, expected",
    [
        (9, 100, "suppressed"),
        (10, 9, "suppressed"),
        (0, 50, "suppressed"),
        (30, 81, 37.0),
        (10, 10, 100.0),
        (227, 2740, 8.3),
        (1, 8, "suppressed"),
    ],
)
def test_percent(num, den, expected):
    out = disclose_cell(RawPercent(num=num, den=den))
    assert out == expected
    assert type(out) is type(expected)


@pytest.mark.parametrize(
    "total, n, expected",
    [
        (Decimal("408.0"), 15, 27.2),
        (Decimal("90.0"), 9, "suppressed"),
        (Decimal("0"), 0, "suppressed"),
    ],
)
def test_mean(total, n, expected):
    out = disclose_cell(RawMean(total=total, n=n))
    assert out == expected
    assert type(out) is type(expected)


def _table() -> RawTable:
    loinc = CodeSet(system="loinc", prefixes=["4548-4"], label="HbA1c", source="explicit")
    metrics = [
        CountMetric(kind="count", name="total", label="Patients"),
        CountMetric(kind="count", name="hidden", label="Hidden", display=False),
        PercentMetric(kind="percent", name="share", label="Share", numerator="hidden", denominator="total"),
        MeanMetric(kind="mean", name="avg", label="Mean HbA1c", codes=loinc),
    ]
    return RawTable(
        dimensions=["region"],
        metrics=metrics,
        rows=[
            RawRow(
                group={"region": "North"},
                cells={
                    "total": RawCount(n=120),
                    "hidden": RawCount(n=30),
                    "share": RawPercent(num=30, den=81),
                    "avg": RawMean(total=Decimal("408.0"), n=15),
                },
            ),
            RawRow(
                group={"region": "South"},
                cells={
                    "total": RawCount(n=0),
                    "hidden": RawCount(n=0),
                    "share": RawPercent(num=0, den=0),
                    "avg": RawMean(total=Decimal("0"), n=0),
                },
            ),
        ],
    )


def test_table_keeps_every_group_and_hides_hidden_counts():
    out = disclose_table(_table())
    assert isinstance(out, DisclosedTable)
    assert out.dimensions == ["region"]
    assert out.metrics == [
        {"name": "total", "label": "Patients", "kind": "count"},
        {"name": "share", "label": "Share", "kind": "percent"},
        {"name": "avg", "label": "Mean HbA1c", "kind": "mean"},
    ]
    assert [r.group for r in out.rows] == [{"region": "North"}, {"region": "South"}]
    assert all(isinstance(r, DisclosedRow) for r in out.rows)
    north, south = out.rows
    assert north.values == {"total": 120, "share": 37.0, "avg": 27.2}
    assert south.values == {"total": "<10", "share": "suppressed", "avg": "suppressed"}
    assert "hidden" not in north.values and "hidden" not in south.values

    assert all(isinstance(n, SuppressionNote) for n in out.notes)
    assert {(n.group["region"], n.metric) for n in out.notes} == {
        ("South", "total"),
        ("South", "share"),
        ("South", "avg"),
    }
    for note in out.notes:
        assert not any(ch.isdigit() for ch in note.reason.replace("10", ""))
        assert "10" in note.reason or "fewer" in note.reason


def test_notes_reasons_are_generic():
    out = disclose_table(_table())
    reasons = {n.metric: n.reason for n in out.notes}
    assert reasons["total"] == "count below 10"
    assert reasons["share"] == "numerator below 10"
    assert reasons["avg"] == "fewer than 10 values"


def test_percent_note_denominator():
    t = RawTable(
        dimensions=[],
        metrics=[
            CountMetric(kind="count", name="a", label="A"),
            CountMetric(kind="count", name="b", label="B"),
            PercentMetric(kind="percent", name="p", label="P", numerator="a", denominator="b"),
        ],
        rows=[RawRow(group={}, cells={"a": RawCount(n=50), "b": RawCount(n=5), "p": RawPercent(num=50, den=5)})],
    )
    out = disclose_table(t)
    assert [(n.metric, n.reason) for n in out.notes] == [
        ("b", "count below 10"),
        ("p", "denominator below 10"),
    ]


def test_disclosed_table_is_leak_free_and_serialisable():
    out = disclose_table(_table())
    assert_no_leak(out)
    assert_no_leak(out.model_dump())


def test_assert_no_leak():
    with pytest.raises(LeakError):
        assert_no_leak({"a": {"x": 5}})
    with pytest.raises(LeakError):
        assert_no_leak(["p-1234abcd"])
    assert_no_leak({"x": 10, "y": "<10", "z": True, "w": 37.0})


def test_assert_no_leak_more_cases():
    with pytest.raises(LeakError):
        assert_no_leak({"k": [({"deep": 0},)]})
    with pytest.raises(LeakError):
        assert_no_leak({"note": "patient p-0a1b2c3d matched"})
    with pytest.raises(LeakError):
        assert_no_leak({"p-0a1b2c3d": 50})
    with pytest.raises(LeakError):
        assert_no_leak(RawCount(n=3))
    assert_no_leak({"note": "p-123 and p-zzzzzzzz are not ids"})
    assert_no_leak(None)
    assert_no_leak(RawCount(n=3247))
    assert_no_leak({"flag": False, "ok": [10, 11, "text"]})
