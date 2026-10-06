"""What a reader makes of a field: a number, exactly, or none; a time, in whole milliseconds.

One grammar, one rounding, every format: a time is read from its decimal text -- never
through a float -- and rounded half up to the millisecond. Reading is bounded: a text's
size or exponent cannot make it slow (``exact``).
"""

import re
import sys
from fractions import Fraction
from typing import Final

from subverter._values import round_half_up

__all__ = ["exact", "json_number", "ms", "number", "prefix", "time_ms"]

# a decimal, as jq's tonumber and awk read one: ASCII digits, a sign, a fraction, an exponent,
# blanks around (Python's float() also takes "1_000", other scripts' digits, "nan" and "inf")
_DECIMAL: Final = re.compile(
    r"\s*([-+]?)(?:([0-9]+)\.?([0-9]*)|\.([0-9]+))(?:[eE]([-+]?[0-9]+))?\s*", re.ASCII
)
_PREFIX: Final = re.compile(
    r"[ \t\n]*[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?", re.ASCII
)
_HIGHEST: Final = 308  # a double's largest power of ten: a first digit above it, no number
_LOWEST: Final = -400  # under a double's least (5e-324): zero, as a double underflows
_DIGITS: Final = 400  # significant digits read: more than any rounding of a time here looks at
_EXPONENT_DIGITS: Final = 6  # an exponent of 10**6 or more is far past either bound
_LONGEST: Final = Fraction(sys.float_info.max)  # a time past a double's range is none


def exact(text: str) -> Fraction | None:
    """A decimal text's value -- exactly, for every rounding here -- in bounded work; else None.

    A first significant digit past 10**308 is no number; one under 10**-400 is zero (as a
    double underflows). The first 400 significant digits are read, and nonzero digits past
    them as one more (a sticky 1): every boundary a time's rounding meets lies far above the
    400th digit, so the value falls on the same side of each as the text's own.
    """
    match = _DECIMAL.fullmatch(text)
    if match is None:
        return None
    sign, whole, fraction, only, exponent = match.groups()
    integral = whole or ""
    digits = integral + (fraction if whole is not None else only)
    significant = digits.lstrip("0")
    if not significant:
        return Fraction(0)
    if exponent and len(exponent.lstrip("+-").lstrip("0")) > _EXPONENT_DIGITS:
        return Fraction(0) if exponent.startswith("-") else None
    top = len(integral) - (len(digits) - len(significant)) - 1 + int(exponent or 0)
    if top > _HIGHEST:
        return None
    if top < _LOWEST:
        return Fraction(0)
    kept = significant[:_DIGITS]
    if significant[_DIGITS:].strip("0"):
        kept += "1"  # sticky: the rest is nonzero, below every boundary a rounding meets
    value = int(kept) * Fraction(10) ** (top - len(kept) + 1)
    return -value if sign == "-" else value


def number(value: object) -> Fraction | None:
    """A JSON number (its fraction read exactly, ``exact``) or a decimal string; else None."""
    if isinstance(value, bool):  # a JSON true is no number (Python's bool is an int)
        return None
    if isinstance(value, int | Fraction):
        return Fraction(value)
    if isinstance(value, str):
        return exact(value)
    return None  # a float: JSON's NaN, Infinity, or a number past a double -- no number


def json_number(text: str) -> Fraction | float:
    """``json.loads``'s ``parse_float``: the number exactly; past a double, the float JSON gave."""
    found = exact(text)
    return found if found is not None else float(text)


def prefix(text: str) -> Fraction | None:
    """A field's leading number, as awk reads it (``$1 + 0``), exactly; 0 if none, None if huge."""
    match = _PREFIX.match(text)
    return exact(match[0]) if match else Fraction(0)


def ms(value: Fraction | None, per_unit: int) -> int | None:
    """``value`` (of ``per_unit`` ms each) in whole ms, rounded half up; past a double, none."""
    if value is None:
        return None
    scaled = value * per_unit
    return round_half_up(scaled) if abs(scaled) <= _LONGEST else None


def time_ms(value: object, per_unit: int) -> int | None:
    """A field read as a time (``number``), in whole ms (``ms``); None if it is none."""
    return ms(number(value), per_unit)
