"""readers.fields: a decimal read exactly, in bounded work; a time in whole milliseconds."""

import time
from fractions import Fraction

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from subverter.readers.fields import exact, ms, number, prefix


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1.0005", Fraction("1.0005")),
        (" -12.5e1 ", Fraction(-125)),
        ("1e999999999", None),  # past a double: decided from the exponent, no 10**999999999 built
        ("1e" + "9" * 5000, None),
        ("9" * 5000, None),
        ("1e-999999999", Fraction(0)),  # under a double: zero, as a double underflows
        ("-1e-500", Fraction(0)),
        ("0e999999999", Fraction(0)),
        ("1e400", None),
        ("x", None),
    ],
)
def test_a_decimal_in_bounded_work(text: str, value: Fraction | None) -> None:
    began = time.monotonic()
    assert exact(text) == value
    assert time.monotonic() - began < 1  # no huge integer built (a Fraction of the text: minutes)


def test_long_digits_round_as_the_text() -> None:
    """400 digits read, the rest sticky: 0.1111... s (5000 ones) is 111 ms, and a half past it 112."""
    assert ms(exact("0." + "1" * 5000), 1000) == 111
    assert ms(exact("0.1115" + "0" * 5000 + "1"), 1000) == 112
    assert ms(exact("-0.0005" + "0" * 5000 + "1"), 1000) == -1  # a hair past the half, down


def _decimal(sign: str, whole: int, frac: int, tail: int | None, exp: int | None) -> str:
    """A decimal text: a half-ms boundary when ``frac`` ends in 5; a sticky 1 ``tail`` zeros on."""
    sticky = "" if tail is None else "0" * tail + "1"
    exponent = "" if exp is None else f"e{exp}"
    return f"{sign}{whole}.{frac:04d}{sticky}{exponent}"


_DECIMALS = st.one_of(
    st.builds(  # any decimal
        _decimal,
        st.sampled_from(["", "-", "+"]),
        st.integers(0, 10**15),
        st.integers(0, 9999),
        st.one_of(st.none(), st.integers(0, 50), st.integers(380, 600)),
        st.one_of(st.none(), st.integers(-430, 330)),
    ),
    st.builds(  # on a half-ms boundary, its tail past the 400 digits read: where sticky matters
        _decimal,
        st.sampled_from(["-", ""]),
        st.integers(0, 10**6),
        st.integers(0, 999).map(lambda n: n * 10 + 5),
        st.integers(400, 600),
        st.none(),
    ),
)


@given(_DECIMALS)
@example("-0.0005" + "0" * 500 + "1")  # past the 400 digits read, a hair beyond a half: sticky
def test_exact_rounds_as_the_fraction_of_its_text(text: str) -> None:
    """Every rounding a time meets (ms, 10 ms units, seconds): as the unbounded Fraction's."""
    truth, read = Fraction(text), exact(text)
    for per_unit in (1, 10, 1000):
        assert ms(read, per_unit) == ms(truth, per_unit) or (
            read is None and ms(truth, per_unit) is None
        )


def test_a_number_is_a_json_number_or_a_decimal_string() -> None:
    assert (number(7), number(Fraction(1, 2)), number("1.5")) == (7, Fraction(1, 2), Fraction(3, 2))
    true: object = True  # a JSON true is no number (Python's bool is an int)
    assert (number(true), number(1.5), number(None), number("nan")) == (None, None, None, None)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("12abc", 12),
        ("", 0),
        (" 5", 5),
        ("-3.5x", Fraction(-7, 2)),
        ("1e3", 1000),
        ("+7", 7),
        (".5", Fraction(1, 2)),
    ],
)
def test_a_prefix_is_read_as_awk_reads_a_number(text: str, value: Fraction) -> None:
    """A SubRip time's parts: the leading number (``$1 + 0``), exactly; 0 if none."""
    assert prefix(text) == value
