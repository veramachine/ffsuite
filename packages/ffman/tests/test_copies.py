"""ffman's helpers its libraries copy -- each its own, ffman importing none of theirs: held equal.

A message ffmeta words is one ffman prints (``ffman: error: ...``); a time either rounds is one
the other reads back. The copies are deliberate (a library imports nothing of ffman); a copy
that drifted would change a message or a time unseen, so each is held to ffman's on any input.
"""

from fractions import Fraction

import ffmeta._errors
import ffmeta._values
import pytest
import subverter._values
from hypothesis import example, given
from hypothesis import strategies as st

from ffman import errors, values


@given(st.text())
def test_ffmetas_shown_is_ffmans(text: str) -> None:
    assert ffmeta._errors.shown(text) == errors.shown(text)


@given(st.text(max_size=20), st.integers(min_value=-3, max_value=10**6), st.text(max_size=40))
def test_ffmetas_refuse_at_is_ffmans(source: str, line: int, message: str) -> None:
    if line < 1:  # a caller's mistake, not a refusal: each says so alike
        with pytest.raises(ValueError, match=f"^lines count from 1, not {line}$"):
            ffmeta._errors.refuse_at(source, line, message)
        with pytest.raises(ValueError, match=f"^lines count from 1, not {line}$"):
            errors.refuse_at(source, line, message)
        return
    with pytest.raises(ffmeta.Error) as theirs:
        ffmeta._errors.refuse_at(source, line, message)
    with pytest.raises(errors.FfmanError) as ours:
        errors.refuse_at(source, line, message)
    assert str(theirs.value) == str(ours.value)


# exact halves are where rounding half up is decided, and arbitrary fractions are seldom one
HALVES = st.integers(min_value=-(10**6), max_value=10**6).map(lambda k: Fraction(2 * k + 1, 2))


@given(st.one_of(st.fractions(), HALVES))
@example(Fraction(1, 2))
@example(Fraction(-1, 2))
@example(Fraction(5, 2))
@example(Fraction(-3, 2))
def test_each_round_half_up_is_ffmans(value: Fraction) -> None:
    expected = values.round_half_up(value)
    assert ffmeta._values.round_half_up(value) == expected
    assert subverter._values.round_half_up(value) == expected
