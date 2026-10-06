import re

from hypothesis import given, settings
from subverter.transcript import Transcript

from ffman.subs.ass import Style, script
from tests.support.subtitles import FRAMES, POS, STYLES, transcripts

EVENT = re.compile(
    r"Dialogue: ([01]),(\d+):(\d\d):(\d\d)\.(\d\d),(\d+):(\d\d):(\d\d)\.(\d\d),Default,,0,0,0,,(.*)"
)


def cs(h: str, m: str, s: str, c: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 100 + int(c)


@settings(max_examples=300, deadline=None)
@given(transcripts(), STYLES, FRAMES)
def test_what_holds_of_any_script(t: Transcript, style: Style, frame: tuple[int, int]) -> None:
    text, _ = script(t, *frame, style)
    # the transcript's span, in centiseconds; word mode holds a word up to 400 ms on
    lo, hi = t.chunks[0].start // 10 - 1, (t.chunks[-1].end + 409) // 10 + 1
    xs: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        m = EVENT.fullmatch(line)
        assert m, line
        start, end = cs(*m.group(2, 3, 4, 5)), cs(*m.group(6, 7, 8, 9))
        assert lo <= start < end <= hi, (start, end, lo, hi)
        # a layer of its own only to highlight a word
        assert m[1] == "0" or style.mode == "chunk-word"
        positions: list[tuple[str, str]] = POS.findall(m[10])
        assert positions or style.mode == "plain", m[10]  # placed: every event read, none skipped
        for x, y in positions:
            xs.add(x)
            assert -2000 < float(y) < 3000
    # every line centred: one x, half the canvas
    assert len(xs) <= 1
