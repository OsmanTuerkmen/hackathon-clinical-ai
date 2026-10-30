"""Small-cell rule. The only path from raw numbers to anything an applicant sees."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .compiler import RawResult

THRESHOLD = 10
LT = "<10"
SUPPRESSED = "suppressed"


def round_half_up(x: float, places: int = 1) -> float:
    q = Decimal(1).scaleb(-places)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def publish_cell(cell: dict):
    kind, v = cell["kind"], cell["value"]
    if kind == "count":
        return LT if v < THRESHOLD else int(v)
    if kind == "pct":
        if cell["num"] < THRESHOLD or cell["den"] < THRESHOLD or v is None:
            return SUPPRESSED
        return round_half_up(v)
    if kind == "mean":
        if cell["n"] < THRESHOLD or v is None:
            return SUPPRESSED
        return round_half_up(v)
    raise ValueError(kind)


def publish(raw: RawResult, hidden: set[str] = frozenset()) -> dict:
    """Nested {group_level_1: {group_level_2: {measure: value}}}; flat {measure: value} when ungrouped."""
    out: dict = {}
    for g in raw.groups:
        cells = {name: publish_cell(c) for name, c in raw.values[g].items() if name not in hidden}
        if not g:
            return cells
        node = out
        for key in g[:-1]:
            node = node.setdefault(key, {})
        node[g[-1]] = cells
    return out


def leak_check(published, raw_unit_count: int | None = None) -> list[str]:
    """Independent audit of a published answer: returns a list of violations (empty = clean)."""
    problems: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and k.startswith("p-"):
                    problems.append(f"patient id in output at {path}")
                walk(v, path + [k])
        elif isinstance(node, list):
            problems.append(f"list (possible record dump) at {path}")
        elif isinstance(node, bool):
            pass
        elif isinstance(node, int) and node < THRESHOLD:
            problems.append(f"count {node} < {THRESHOLD} at {path}")
        elif isinstance(node, str) and node.startswith("p-"):
            problems.append(f"patient id at {path}")

    walk(published, [])
    return problems
