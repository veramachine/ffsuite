"""Hypothesis strategies: transcripts as ingest leaves them, and the styles and frames they meet."""

import re
from fractions import Fraction
from typing import Final

from hypothesis import strategies as st
from subverter.transcript import Chunk, Transcript, Word

from ffman.plan.request import HIGHLIGHT_MODES, OVERLAY_MODES
from ffman.subs.ass import Style

# \pos(x,y): exact since phase 6.4, so an integer or a decimal (libass reads doubles)
_NUMBER: Final = r"-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?"  # as _number writes one (repr: 1e+16)
POS: Final = re.compile(rf"\\pos\(({_NUMBER}),({_NUMBER})\)")

TEXT = st.text(alphabet="ab xyz{}\\日本語 é", min_size=1, max_size=40).map(str.strip).filter(bool)


@st.composite
def transcripts(draw: st.DrawFn) -> Transcript:
    """Ordered, apart chunks; for some, words ordered inside their window (normalize's output)."""
    chunks: list[Chunk] = []
    words: list[Word] = []
    at = draw(st.integers(0, 5000))
    for k in range(draw(st.integers(1, 5))):
        length = draw(st.integers(20, 6000))
        text = draw(TEXT)
        chunks.append(Chunk(at, at + length, text, str(k)))
        if draw(st.booleans()):
            count = draw(st.integers(1, 6))
            starts = sorted(
                draw(st.lists(st.integers(at, at + length - 1), min_size=count, max_size=count))
            )
            for i, start in enumerate(starts):
                end = starts[i + 1] if i + 1 < len(starts) else at + length
                words.append(Word(str(k), start, max(end, start), draw(TEXT)))
        at += length + draw(st.integers(0, 900))
    return Transcript(
        "json", "x", has_words=bool(words), chunks=tuple(chunks), words=tuple(words), notes=()
    )


STYLES = st.builds(
    Style,
    mode=st.sampled_from(OVERLAY_MODES),
    highlight=st.sampled_from(HIGHLIGHT_MODES),
    size=st.one_of(st.none(), st.sampled_from([Fraction(n) for n in ("20", "57", "64", "130.5")])),
    margin=st.sampled_from([Fraction(n) for n in ("0.05573", "0.2", "0")]),
    bar_y=st.one_of(st.none(), st.sampled_from([Fraction(n) for n in ("1040.5", "1000", "900")])),
)
FRAMES = st.sampled_from([(1920, 1080), (1080, 1920), (321, 181), (640, 480)])
