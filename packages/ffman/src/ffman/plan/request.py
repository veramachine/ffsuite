"""What a convert job asks for, checked: the planners' input (``jobs`` validates it)."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from ffman.effects.spec import Request
from ffman.graph.resize import BBlur, ResizeMode, bblur_on
from ffman.subs.colorize import Colorize, Highlight

OverlayMode = Literal["plain", "chunk-word", "word", "word-highlight"]
HighlightMode = Literal["plain", "pop"]
OVERLAY_MODES: Final[tuple[OverlayMode, ...]] = ("plain", "chunk-word", "word", "word-highlight")
HIGHLIGHT_MODES: Final[tuple[HighlightMode, ...]] = ("plain", "pop")

type Preset = Literal["youtube", "ffmetadata", "vorbiscomment"]  # YouTube's; a .txt output's format


@dataclass(frozen=True, slots=True)
class ConvertOptions:
    """Everything ``convert`` was asked, checked."""

    input: str
    output: str | None
    in_place: bool
    overwrite: bool
    dry_run: bool
    width: int | None
    height: int | None
    aspect: tuple[Fraction, Fraction] | None
    aspect_text: str | None
    resize_mode: ResizeMode
    bblur: BBlur  # a sigma (0: off), or auto
    effects: tuple[Request, ...]
    burn_subs: str | None
    overlay_mode: OverlayMode
    highlight_mode: HighlightMode
    highlight_colorize: Highlight
    font_color: Colorize
    outline_color: Colorize | None  # none: the one that contrasts most with each fill
    font: str
    font_size: Fraction
    margin_bottom: Fraction  # the text box's bottom above the frame's, of its height
    margin_bottom_given: bool
    add_subs: tuple[str, ...]
    languages: tuple[str, ...]
    preset: Preset | None
    video_codec: str | None
    audio_codec: str
    lossless: bool
    normalize: bool
    loop: Literal["once", "loop", "reverse"]

    @property
    def bblur_on(self) -> bool:
        """Whether bar blur is on (``auto`` or a sigma above 0)."""
        return bblur_on(self.bblur)

    metadata: str | None = None  # --metadata FILE (spec 3.10)
