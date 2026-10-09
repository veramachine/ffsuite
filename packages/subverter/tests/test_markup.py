"""markup: a text's tags off, and WebVTT's character references decoded as HTML decodes them."""

import html
from typing import Final

import pytest
import subverter
from hypothesis import given
from hypothesis import strategies as st


def test_untagged_puts_what_it_is_given_where_each_tag_was() -> None:
    assert subverter.untagged("a<b>c</b>") == "ac"
    assert subverter.untagged("a<b>c</b>", into="|") == "a|c|"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("A &amp; B &lt;b&gt; &#x263A; &#9786; &copy;", "A & B <b> \u263a \u263a \u00a9"),
        ("&amp &notit; &AMP;", "& \u00acit; &"),  # HTML's legacy names, as its data state
        ("&bogus; &#; &# & x", "&bogus; &#; &# & x"),  # no reference: as written
        ("&#0; &#55296; &#1114112; &#x80;", "\ufffd \ufffd \ufffd \u20ac"),  # HTML's numerics
        ("&#" + "9" * 5000 + ";x", "\ufffdx"),  # past int's 4300 digits: no crash
        ("&#" + "0" * 5000 + "65;", "A"),  # its zeros no digits
        ("&#1000000; &#1114111;", "\U000f4240 "),  # 7 digits: read (U+10FFFF a noncharacter)
        ("&#65;;", "A;"),  # its own ; consumed, the next kept
    ],
)
def test_a_webvtt_runs_references_decoded_as_html_does(text: str, shown: str) -> None:
    assert subverter.decoded(text) == shown


# what references are made of
_PARTS: Final = ("&", "#", ";", "x", "X", "0", "9", "65", "amp", "AMP", "lt", "not", "it", " ")
_NUMBERS: Final = ("1114111", "1114112", "\ufffd")  # each side of U+10FFFF, and its stand-in


@given(st.lists(st.sampled_from(_PARTS + _NUMBERS), max_size=12).map("".join))
def test_decoded_is_html_unescape_wherever_that_reads_the_text(text: str) -> None:
    assert subverter.decoded(text) == html.unescape(text)
