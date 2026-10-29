"""The only path for statistical values to leave the access body."""
from decimal import Decimal, ROUND_HALF_UP

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
