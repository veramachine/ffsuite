"""What the effects are sized by: the frame they receive."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Self

from ffman.media.probe import Video


@dataclass(frozen=True, slots=True)
class Stamp:
    """The camcorder's, when it runs: its ASS script, and the fonts folder it is drawn with."""

    script: str
    fonts: str  # jobs.convert.fonts' answer: ffman's own, or FFMAN_FONTS_DIR's


@dataclass(frozen=True, slots=True)
class Frame:
    """What the effects are sized by: the frame they receive, and its SAR.

    ``sar`` is the frame's (bash's FX_SAR): 1 after a resize, which squares the
    pixels -- ``squared`` -- else the stream's own. Chromatic aberration prints it
    as bash did: ``1`` when squared, else ``N/M`` (``1/1`` for square pixels).
    """

    width: int
    height: int
    sar: Fraction
    video: Video
    camcorder: Stamp | None = None  # the camcorder's, when it runs
    squared: bool = False  # a resize squared the pixels (FX_SAR's "1")

    def __post_init__(self) -> None:
        """A squared frame's SAR is 1: the two never disagree."""
        if self.squared and self.sar != 1:
            msg = f"a squared frame has SAR 1, not {self.sar}"
            raise ValueError(msg)

    @classmethod
    def resized(cls, width: int, height: int, video: Video) -> Self:
        """The frame after a resize: its size, its pixels squared."""
        return cls(width, height, Fraction(1), video, squared=True)

    @property
    def shorter(self) -> int:
        """The shorter side (bash's ``m``)."""
        return min(self.width, self.height)
