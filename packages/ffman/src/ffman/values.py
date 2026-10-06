"""The bash ffman's value checks, shared by every validator (stage A keeps them)."""

import re
from fractions import Fraction
from typing import Final

_UINT: Final = re.compile(r"[1-9][0-9]*")
_NUM: Final = re.compile(r"[0-9]+(\.[0-9]+)?")
# What ffmpeg's filter syntax cannot split: paths that go into filter arguments.
_SAFE_PATH: Final = re.compile(r"[A-Za-z0-9_./+@-]+")


def is_uint(text: str) -> bool:
    """A positive integer, no sign, no leading zero (bash ``is_uint``)."""
    return _UINT.fullmatch(text) is not None


def is_num(text: str) -> bool:
    """Digits with an optional fraction; no sign, no exponent, no ``.5`` (bash ``is_num``)."""
    return _NUM.fullmatch(text) is not None


def is_safe_path(path: str) -> bool:
    """Whether ``path`` can go into an ffmpeg filter argument as is (bash ``SAFE_PATH``)."""
    return _SAFE_PATH.fullmatch(path) is not None


def decimal(value: Fraction) -> str:
    """``value`` as the shortest decimal that is exactly it (``57.50`` is ``57.5``).

    Every number ffman reads is a decimal, so a terminating fraction; any other
    is refused (ValueError), never rounded.
    """
    text = finite_decimal(value)
    if text is None:
        msg = f"{value} has no finite decimal"
        raise ValueError(msg)
    return text


def finite_decimal(value: Fraction) -> str | None:
    """``value`` as the shortest decimal that is exactly it; None if it has none."""
    places = _places(value)
    if places is None:
        return None
    return f"{value:.{places}f}"  # exact: 10 ** places is a multiple of the denominator


def round_half_up(value: Fraction) -> int:
    """The nearest integer, halves up: the floor of ``value`` + 1/2, exactly."""
    return div_half_up(value.numerator, value.denominator)


def div_half_up(n: int, d: int) -> int:
    """``n / d`` (``d`` > 0) to the nearest integer, halves up -- in integers: (2n + d) // 2d."""
    return (2 * n + d) // (2 * d)


def _places(value: Fraction) -> int | None:
    """The decimal places that write ``value`` exactly; None if no finite number do.

    None when its denominator has a prime other than 2 and 5.
    """
    rest, twos, fives = value.denominator, 0, 0
    while rest % 2 == 0:
        rest, twos = rest // 2, twos + 1
    while rest % 5 == 0:
        rest, fives = rest // 5, fives + 1
    return max(twos, fives) if rest == 1 else None
