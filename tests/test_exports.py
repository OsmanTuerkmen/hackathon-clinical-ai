from datetime import date

from accessdesk.safes.outputs import check_export


def _codes(result):
    return {reason["code"] for reason in result["reasons"]}


def test_export_check_passes_aggregated_counts():
    result = check_export(["region", "patients"], [["Wien", 120], ["Tirol", 25]])

    assert result == {"result": "pass", "reasons": []}


def test_export_check_rejects_identifiers_and_small_counts():
    result = check_export(
        ["patient_id", "count"],
        [["p-12345678", 4]],
    )

    assert result["result"] == "fail"
    assert {"identifier_column", "identifier_value", "small_count"} <= _codes(result)
    assert all(reason["de"] and reason["en"] for reason in result["reasons"])


def test_export_check_warns_when_population_size_cannot_be_verified():
    result = check_export(["region", "mean_bmi"], [["Wien", 27.5]])

    assert result["result"] == "warn"
    assert _codes(result) == {"no_count_column"}


def test_export_check_detects_record_level_and_dates():
    rows = [["e123456", date(2025, 1, 1)] for _ in range(1001)]
    result = check_export(["visit_type", "date"], rows)

    assert result["result"] == "fail"
    assert {"identifier_value", "record_level", "dates", "no_count_column"} <= _codes(result)
