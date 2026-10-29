"""The only path for statistical values to leave the access body."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import re

THRESHOLD = 10
LT = "<10"
SUPPRESSED = "suppressed"


def round1(value):
    return float(Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


class Gate:
    def __init__(self):
        self.log = {"cells": 0, "counts_hidden": 0, "pct_suppressed": 0, "means_suppressed": 0}

    def cell(self, raw):
        self.log["cells"] += 1
        cell_type = raw["type"]
        if cell_type == "count":
            value = int(raw["value"])
            if value < THRESHOLD:
                self.log["counts_hidden"] += 1
                return LT
            return value
        if cell_type == "pct":
            numerator, denominator = int(raw["num"]), int(raw["den"])
            if numerator < THRESHOLD or denominator < THRESHOLD:
                self.log["pct_suppressed"] += 1
                return SUPPRESSED
            return round1(Decimal(numerator) * 100 / Decimal(denominator))
        if cell_type == "mean":
            count, patients = int(raw["n"]), int(raw["patients"])
            if count == 0 or patients < THRESHOLD:
                self.log["means_suppressed"] += 1
                return SUPPRESSED
            return round1(Decimal(int(raw["sum10"])) / Decimal(10) / Decimal(count))
        raise ValueError(f"Unknown cell type {cell_type}")


def release(result, plan):
    gate = Gate()
    measures = plan.measures
    rows = [
        {"group": list(key), "values": {name: gate.cell(raw) for name, raw in cells.items()}}
        for key, cells in result["raw"].items()
    ]
    nested = {}
    for row in rows:
        if not row["group"]:
            nested = dict(row["values"])
            continue
        node = nested
        for group in row["group"][:-1]:
            node = node.setdefault(group, {})
        node[row["group"][-1]] = row["values"]
    return {
        "group_dims": [group.dim for group in plan.groups],
        "measures": [{"key": m.key, "label": m.label, "type": m.type} for m in measures],
        "rows": rows,
        "answer": nested,
        "gate": gate.log,
    }


def assert_no_leak(released):
    for row in released["rows"]:
        for value in row["values"].values():
            if isinstance(value, int) and value < THRESHOLD:
                raise AssertionError("count below threshold escaped the gate")
            if isinstance(value, str) and value.startswith("p-"):
                raise AssertionError("patient identifier in statistical answer")
            if isinstance(value, str) and value not in (LT, SUPPRESSED):
                raise AssertionError("unexpected text value in statistical answer")
        if any(str(group).startswith("p-") for group in row["group"]):
            raise AssertionError("patient identifier in statistical answer")
    return True


def protect_count(value):
    value = int(value)
    if value < THRESHOLD:
        return LT
    return int((Decimal(value) / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10)


COUNT_COLUMN = re.compile(r"^(?:n$|n_)|_n$|count|patients|persons|people|cases|anzahl|num", re.I)
IDENTIFIER_VALUE = re.compile(r"^(?:p-[0-9a-f]{8}|e\d{6})$")
IDENTIFIER_COLUMNS = {"patient_id", "encounter_id", "birth_date", "pseudonym"}
EXPORT_REASONS = {
    "identifier_column": (
        "Spalte enthält ein direkt identifizierendes Merkmal.",
        "A column contains a direct identifier.",
    ),
    "identifier_value": (
        "Ein Wert sieht wie eine Patienten- oder Aufenthaltskennung aus.",
        "A value looks like a patient or encounter identifier.",
    ),
    "small_count": (
        "Eine Zelle enthält eine Anzahl unter 10.",
        "A cell contains a count below 10.",
    ),
    "record_level": (
        "Der Export enthält mehr als 1.000 Zeilen.",
        "The export contains more than 1,000 rows.",
    ),
    "no_count_column": (
        "Keine Anzahlsspalte gefunden; mindestens 10 Personen je Zeile manuell prüfen.",
        "No count column found; staff must verify at least 10 people per row.",
    ),
    "dates": (
        "Datumsangaben können eine Re-Identifizierung erleichtern und müssen geprüft werden.",
        "Dates can support re-identification and require review.",
    ),
}


def check_export(columns, rows):
    names = [str(column) for column in columns]
    reasons = {}

    def add(code):
        if code not in reasons:
            de, en = EXPORT_REASONS[code]
            reasons[code] = {"code": code, "de": de, "en": en}

    count_columns = [
        index for index, name in enumerate(names)
        if COUNT_COLUMN.search(name)
    ]
    if not count_columns:
        add("no_count_column")
    if any(name.casefold() in IDENTIFIER_COLUMNS or name.casefold().endswith("_id") for name in names):
        add("identifier_column")
    if len(rows) > 1000:
        add("record_level")
    if any("date" in name.casefold() for name in names) or any(
        isinstance(value, (date, datetime)) for row in rows for value in row
    ):
        add("dates")

    for row in rows:
        for value in row:
            if isinstance(value, str) and IDENTIFIER_VALUE.fullmatch(value):
                add("identifier_value")
        for index in count_columns:
            if index < len(row):
                value = row[index]
                if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < THRESHOLD:
                    add("small_count")

    values = list(reasons.values())
    failed = any(
        code in reasons
        for code in ("identifier_column", "identifier_value", "small_count", "record_level")
    )
    return {
        "result": "fail" if failed else "warn" if values else "pass",
        "reasons": values,
    }
