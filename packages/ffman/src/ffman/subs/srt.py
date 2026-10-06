"""A transcript as SRT, for a soft subtitle track (the bash ffman's write_srt).

Cues past the media's end are dropped and one running past it is cut there: a
cue past the end would stretch the file. The end is the media's duration in whole
milliseconds, floored -- so no cue outlasts it (bash truncated a float: 1.005 s,
1004 ms).
"""

import math
from fractions import Fraction

from subverter.transcript import Chunk


def srt(chunks: tuple[Chunk, ...], until: Fraction | None) -> str:
    """The chunks as SRT; ``until`` (the media's duration, s): none past it (none known, none)."""
    clip = math.floor(until * 1000) if until is not None else 0
    cues: list[str] = []
    for chunk in chunks:
        if clip > 0 and chunk.start >= clip:
            continue
        end = clip if clip > 0 and chunk.end > clip else chunk.end
        cues.append(f"{len(cues) + 1}\n{_time(chunk.start)} --> {_time(end)}\n{chunk.text}\n\n")
    return "".join(cues)


def _time(ms: int) -> str:
    hours, minutes, seconds = ms // 3600000, ms % 3600000 // 60000, ms % 60000 // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms % 1000:03d}"
