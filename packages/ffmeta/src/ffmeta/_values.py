"""Numbers exactly: the one rounding ffmeta needs."""

from fractions import Fraction


def round_half_up(value: Fraction) -> int:
    """The nearest integer, halves up: the floor of ``value`` + 1/2, exactly -- (2n + d) // 2d."""
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)
