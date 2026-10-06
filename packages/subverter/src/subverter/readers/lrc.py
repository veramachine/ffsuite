"""LRC: a line's time, its text."""

import re
from typing import Final

from subverter.readers.fields import exact, ms
from subverter.transcript import Cue

__all__ = ["rows"]

_STAMP: Final = re.compile(r"\[([0-9]+):([0-9]+(?:[.][0-9]+)?)\](.*)")  # [mm:ss.xx]text


def rows(lines: list[str]) -> list[Cue]:
    """Starts only: each line ends where the next starts (the last 3 s later)."""
    timed: list[tuple[int, str]] = []
    for line in lines:
        m = _STAMP.fullmatch(line)
        if m is None:
            continue
        minutes, seconds = exact(m[1]), exact(m[2])
        if minutes is None or seconds is None:  # past a double's range: no time, no line
            continue
        start = ms(minutes * 60 + seconds, 1000)
        if start is not None:
            timed.append((start, m[3]))
    timed.sort(key=lambda t: t[0])  # stable, as sort -s
    ends = [t[0] for t in timed[1:]] + ([timed[-1][0] + 3000] if timed else [])
    return [Cue(s, e, t) for (s, t), e in zip(timed, ends, strict=True)]
