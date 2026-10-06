"""values: the numbers ffman reads, and their text."""

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ffman.values import decimal, div_half_up, finite_decimal, round_half_up


@pytest.mark.parametrize(
    ("text", "shortest"),
    [
        ("57", "57"),
        ("057", "57"),
        ("57.50", "57.5"),
        ("00.0", "0"),
        ("0.05573", "0.05573"),
        ("1024", "1024"),
    ],
)
def test_decimal_is_the_shortest_exact_text(text: str, shortest: str) -> None:
    assert decimal(Fraction(text)) == shortest


@given(st.integers(-(10**12), 10**12), st.integers(0, 12), st.integers(0, 12))
def test_decimal_reads_back_exactly_and_ends_in_no_zero(n: int, twos: int, fives: int) -> None:
    value = Fraction(n) / (Fraction(2) ** twos * Fraction(5) ** fives)  # int ** int: Any
    text = decimal(value)
    assert Fraction(text) == value
    assert "." not in text or not text.endswith("0")


def test_a_fraction_without_a_finite_decimal_is_refused() -> None:
    with pytest.raises(ValueError, match="1/3 has no finite decimal"):
        _ = decimal(Fraction(1, 3))


@given(st.fractions(min_value=-(10**6), max_value=10**6))
def test_round_half_up_is_the_nearest_halves_up(x: Fraction) -> None:
    n = round_half_up(x)
    assert abs(x - n) < Fraction(1, 2) or n - x == Fraction(1, 2)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Fraction(3, 8), "0.375"),
        (Fraction(1, 3), None),
        (Fraction(7), "7"),
        (Fraction(-1, 20), "-0.05"),
    ],
)
def test_a_finite_decimal_when_its_denominator_is_twos_and_fives(
    value: Fraction, text: str | None
) -> None:
    assert finite_decimal(value) == text


@pytest.mark.parametrize(
    ("n", "d", "nearest"), [(14, 10, 1), (15, 10, 2), (-15, 10, -1), (-16, 10, -2), (0, 7, 0)]
)
def test_a_division_rounds_half_up(n: int, d: int, nearest: int) -> None:
    """(2n + d) // 2d: the floor of n/d + 1/2 -- a half up, negative or not."""
    assert div_half_up(n, d) == nearest == round_half_up(Fraction(n, d))
