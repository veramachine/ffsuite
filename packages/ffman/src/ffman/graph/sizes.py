"""A picture's sizes: as ffmpeg's filters receive it, and as a resize targets it.

Data the planners make (``plan.geometry``) and the filtergraphs read
(``graph.resize``): below both.
"""

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class Displayed:
    """The picture as ffmpeg's filters receive it.

    ``width``/``height``: displayed -- turned by the display matrix, non-square
    pixels at their display width (what sizes are planned from). ``frame_*``:
    the stored pixels, turned (what effects are sized by). ``sar``: 1, or the
    stream's own when it is positive and another (ffprobe reduces it:
    av_guess_sample_aspect_ratio, libavformat/avformat.c, n8.1.2).
    """

    width: int
    height: int
    frame_width: int
    frame_height: int
    sar: Fraction


@dataclass(frozen=True, slots=True)
class Target:
    """A resize's size, and the note bash printed when rounding changed a size given."""

    width: int
    height: int
    note: str | None
