"""Where the subtitles go: their size, and a black bar under the picture to sit in.

The bash ffman's font_size and bottom_bar. A bar is found by cropdetect on
samples of the picture as the subtitles will see it (after the resize and
the effects before them); it is used when it can hold the text -- its height
at least 1.25 times the font size, on the 1080-line canvas -- and the text is
then centred in it. Its share, threshold and centre are exact, and the sample
times exact seconds.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from ffman.media.paths import file_url
from ffman.values import decimal

CANVAS: Final = 1080  # the ASS canvas' height (PlayResY): sizes are in its lines
SAMPLES: Final = 7  # at 1/8 .. 7/8 of the duration
FRAMES: Final = 5  # a sample's frames; 50 from the start when the duration is unknown
CROPDETECT: Final = "cropdetect=round=2:reset=0:skip=0"
_PRINT: Final = "metadata=mode=print:file=-"  # every frame's metadata, to stdout
_Y1: Final = "lavfi.cropdetect.y1"  # the first row with picture
_Y2: Final = "lavfi.cropdetect.y2"  # the last
_ROW: Final = re.compile(r"[0-9]+")  # a row as av_dict_set_int writes one


def font_size(given: Fraction | None, *, plain: bool) -> Fraction:
    """As given, else mpv's 57 for plain text, 64 for the highlighting modes (bash's font_size)."""
    return given if given is not None else Fraction(57 if plain else 64)


def bar_times(duration: Fraction | None) -> tuple[list[str | None], int]:
    """Where to look, and how many frames each: 7 samples of 5, else 50 frames from the start."""
    if duration is None:
        return [None], 50
    return [decimal(duration * t / 8) for t in range(1, SAMPLES + 1)], FRAMES  # exact seconds


def bar_args(path: str, at: str | None, frames: int, chain: str) -> list[str]:
    """One sample's cropdetect (bash's ffargs; ``chain`` is "" or "FILTERS,"), its rows printed.

    ``metadata=print`` writes each frame's cropdetect values to stdout (``file=-``: pipe:1,
    f_metadata.c) -- the very y1 and y2 cropdetect logs (vf_cropdetect.c), as data.
    """
    seek = ["-ss", at] if at is not None else []
    picture = ["-i", file_url(path), "-map", "0:v:0", "-frames:v", str(frames)]
    detect = f"{chain}{CROPDETECT},{_PRINT}"
    return ["-v", "error", "-noaccurate_seek", *seek, *picture, "-vf", detect, "-f", "null", "-"]


def bar_rows(printed: str) -> int | None:
    """The lowest row with picture across the samples' frames; None if none had any.

    ``printed`` is metadata=print's: a ``frame:`` line, then a frame's ``key=value``
    lines. A frame with nothing but black so far has a y2 less than its y1 (reset=0).
    """
    frames: list[dict[str, str]] = []
    for line in printed.splitlines():
        if line.startswith("frame:"):
            frames.append({})
        elif frames:
            key, _, value = line.partition("=")
            frames[-1][key] = value
    rows = [row for frame in frames if (row := _last_row(frame)) is not None]
    return max(rows, default=None)


def _last_row(frame: dict[str, str]) -> int | None:
    """A frame's last row with picture; None if it has none yet (y2 less than y1), or no rows."""
    y1, y2 = frame.get(_Y1, ""), frame.get(_Y2, "")
    if not (_ROW.fullmatch(y1) and _ROW.fullmatch(y2)) or int(y2) < int(y1):
        return None
    return int(y2)


BarKind = Literal["black", "blurred"]  # what fills a bar: the picture's black, a fit's blur


@dataclass(frozen=True, slots=True)
class Bar:
    """A bar that holds the text: its centre on the canvas (bash's BARY), and its note."""

    y: Fraction
    note: str


def bar_centre(height: int, lowest: int, size: Fraction, kind: BarKind = "black") -> Bar | None:
    """The bar's centre, when it is tall enough for the text; else None. ``kind``: what fills it."""
    rows = height - 1 - lowest
    share = Fraction(rows, height)  # the bar's part of the picture, exactly
    if share < size * Fraction(5, 4) / CANVAS:  # lower than a line of text
        return None
    where = f"a {kind} bar under the picture ({rows} of {height} px)"
    note = f"{where}: subtitles centred in it (--margin-bottom overrides)"
    return Bar(CANVAS - share * CANVAS / 2, note)
