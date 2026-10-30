"""Disclosure control: the single gate between raw statistics and any output.

Small-cell suppression, ROUND_HALF_UP rounding (in Decimal, never via float)
and a leak guard that is run on every disclosed table.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel

from .config import SMALL_CELL_THRESHOLD
from .models import CountMetric, RawCount, RawMean, RawPercent, RawTable

SMALL = f"<{SMALL_CELL_THRESHOLD}"
SUPPRESSED = "suppressed"

PATIENT_ID_PATTERN = re.compile(r"p-[0-9a-f]{8}")

CellValue = int | float | str


class LeakError(Exception):
    """Raised when an output would reveal a small count or a patient identifier."""


# --- Rounding ---------------------------------------------------------------


def round_half_up(value: Decimal, places: int = 1) -> Decimal:
    """Round to `places` decimals, ties away from zero (ROUND_HALF_UP)."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


# --- Cell disclosure --------------------------------------------------------


def _suppression_reason(cell: RawCount | RawPercent | RawMean) -> str | None:
    """Generic reason (never a raw number) if the cell must be suppressed, else None."""
    if isinstance(cell, RawCount):
        return f"count below {SMALL_CELL_THRESHOLD}" if cell.n < SMALL_CELL_THRESHOLD else None
    if isinstance(cell, RawPercent):
        if cell.num < SMALL_CELL_THRESHOLD:
            return f"numerator below {SMALL_CELL_THRESHOLD}"
        if cell.den < SMALL_CELL_THRESHOLD:
            return f"denominator below {SMALL_CELL_THRESHOLD}"
        return None
    if isinstance(cell, RawMean):
        return f"fewer than {SMALL_CELL_THRESHOLD} values" if cell.n < SMALL_CELL_THRESHOLD else None
    raise TypeError(f"unsupported cell type: {type(cell).__name__}")


def disclose_cell(cell: RawCount | RawPercent | RawMean) -> CellValue:
    """Apply the small-cell rule and rounding to one raw cell."""
    if _suppression_reason(cell) is not None:
        return SMALL if isinstance(cell, RawCount) else SUPPRESSED
    if isinstance(cell, RawCount):
        return cell.n
    if isinstance(cell, RawPercent):
        return float(round_half_up(Decimal(100 * cell.num) / Decimal(cell.den)))
    return float(round_half_up(cell.total / Decimal(cell.n)))


# --- Table disclosure -------------------------------------------------------


class DisclosedRow(BaseModel):
    group: dict[str, str]
    values: dict[str, CellValue]


class SuppressionNote(BaseModel):
    group: dict[str, str]
    metric: str
    reason: str


class DisclosedTable(BaseModel):
    dimensions: list[str]
    metrics: list[dict[str, str]]
    rows: list[DisclosedRow]
    notes: list[SuppressionNote]


def disclose_table(raw: RawTable) -> DisclosedTable:
    """Disclose every displayed metric of every group; hidden counts are dropped."""
    shown = [m for m in raw.metrics if not (isinstance(m, CountMetric) and not m.display)]
    rows: list[DisclosedRow] = []
    notes: list[SuppressionNote] = []
    for raw_row in raw.rows:
        values: dict[str, CellValue] = {}
        for metric in shown:
            cell = raw_row.cells[metric.name]
            values[metric.name] = disclose_cell(cell)
            reason = _suppression_reason(cell)
            if reason is not None:
                notes.append(SuppressionNote(group=dict(raw_row.group), metric=metric.name, reason=reason))
        rows.append(DisclosedRow(group=dict(raw_row.group), values=values))
    table = DisclosedTable(
        dimensions=list(raw.dimensions),
        metrics=[{"name": m.name, "label": m.label, "kind": m.kind} for m in shown],
        rows=rows,
        notes=notes,
    )
    assert_no_leak(table)
    return table


# --- Leak guard -------------------------------------------------------------


def assert_no_leak(obj: Any) -> None:
    """Raise LeakError if `obj` holds an int < threshold or a patient id (keys included)."""
    if isinstance(obj, BaseModel):
        assert_no_leak(obj.model_dump())
    elif isinstance(obj, dict):
        for key, value in obj.items():
            assert_no_leak(key)
            assert_no_leak(value)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            assert_no_leak(item)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, int):
        if obj < SMALL_CELL_THRESHOLD:
            raise LeakError("output contains a count below the small-cell threshold")
    elif isinstance(obj, str):
        if PATIENT_ID_PATTERN.search(obj):
            raise LeakError("output contains a patient identifier")
