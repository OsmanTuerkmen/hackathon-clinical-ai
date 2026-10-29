"""Statistical disclosure control: exact half-up rounding and the small-cell rule.

All arithmetic is done on exact rationals (fractions.Fraction). Binary floats are refused so that
values such as 37.25 round to 37.3 (half up) and never to 37.2 (banker's rounding / float error).
"""
from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import Iterable, Union

from .config import SMALL_CELL_THRESHOLD

LT10 = "<10"
SUPPRESSED = "suppressed"

Exact = Union[int, str, Decimal, Fraction]


def to_fraction(value: Exact) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("binary floats are not accepted; pass int, str, Decimal or Fraction")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    if isinstance(value, int):
        return Fraction(value)
    return Fraction(Decimal(str(value).strip()))


def round_half_up(value: Exact, places: int = 1) -> Decimal:
    """Round to `places` decimals, ties away from zero ("halves up"), exactly."""
    x = to_fraction(value)
    scaled = x * (10 ** places)
    sign = -1 if scaled < 0 else 1
    q = math.floor(abs(scaled) + Fraction(1, 2))
    return Decimal(sign * q).scaleb(-places)


def is_small(n: int) -> bool:
    return n < SMALL_CELL_THRESHOLD


def count_cell(n: int):
    """Counts below the threshold, including 0, are shown as "<10"."""
    return LT10 if is_small(n) else int(n)


def percent_cell(numerator: int, denominator: int):
    """A percentage is suppressed if its numerator or denominator is below the threshold."""
    if is_small(numerator) or is_small(denominator):
        return SUPPRESSED
    return round_half_up(Fraction(numerator * 100, denominator), 1)


def mean_cell(values: Iterable[Fraction]):
    """A mean is suppressed if it is based on fewer patients than the threshold."""
    vals = list(values)
    if is_small(len(vals)):
        return SUPPRESSED
    return round_half_up(sum(vals, Fraction(0)) / len(vals), 1)


def median_cell(values: Iterable[Fraction]):
    vals = sorted(values)
    if is_small(len(vals)):
        return SUPPRESSED
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return round_half_up(med, 1)


def json_value(value):
    """JSON representation of a released cell: int, one-decimal number or a suppression marker."""
    if isinstance(value, Decimal):
        return float(value)
    return value
