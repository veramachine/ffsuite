"""The resize: into the target size by fit, cover or stretch (the bash ffman's resize_filter).

Non-square pixels are squared first: scale's force_original_aspect_ratio
ignores the SAR. ``fit`` pads with black, or -- with --bblur -- puts the
picture, covered and blurred, behind itself: blurred in linear light (a blur
averages light), in 16-bit RGB, from before the scale (scaling averages too).
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from ffman.graph import Filter, Labels, Open
from ffman.graph.light import DECODE, ENCODE, curves
from ffman.graph.sizes import Displayed, Target
from ffman.media.probe import Video
from ffman.values import decimal

SCALER: Final = "lanczos+accurate_rnd+full_chroma_int"  # bash's SWS: every rescale's flags
# the auto sigma: a 34.6th of the shorter side of the picture scaled to cover the
# frame -- the blur-fill recipe's boxblur min(h,w)/20, as a Gaussian (decisions.md)
AUTO_BLUR_DIVISOR: Final = 34.6
# gblur steps: 6 approximates a Gaussian closely (its default 1 is 14% off; decisions.md)
BLUR_STEPS: Final = "6"


ResizeMode = Literal["fit", "cover", "stretch"]
RESIZE_MODES: Final[tuple[ResizeMode, ...]] = ("fit", "cover", "stretch")
BBLUR_MAX: Final = 1024  # sigma, the spec's range (and gblur's)
type BBlur = Fraction | Literal["auto"]  # --bblur: a sigma (0 is off), or auto


_BLACK: Final = Filter("drawbox", (("color", "black"), ("t", "fill")))  # a frame, filled


def blurred_fit(mode: ResizeMode, bblur: BBlur) -> bool:
    """Whether the resize fits the picture over a blurred copy of it: its bars blurred."""
    return mode == "fit" and bblur_on(bblur)


def bblur_on(bblur: BBlur) -> bool:
    """Whether bar blur is on: ``auto``, or a sigma above 0 (``0`` is off)."""
    return bblur == "auto" or bblur > 0


def bblur_sigma(bblur: BBlur, source: Displayed, target: Target) -> str:
    """The bar blur's sigma: its value, or auto's -- awk's doubles, printed %.1f (bash's text)."""
    if bblur != "auto":
        return decimal(bblur)
    zoom = target.width / source.width
    zoom = max(zoom, target.height / source.height)
    sigma = min(source.width, source.height) * zoom / AUTO_BLUR_DIVISOR
    return f"{min(max(sigma, 1), BBLUR_MAX):.1f}"


@dataclass(frozen=True, slots=True)
class Picture:
    """What the resize knows of the picture.

    As displayed, its target, its stream, and whether it moves (a video's sizes
    stay even).
    """

    source: Displayed
    target: Target
    video: Video
    moving: bool

    @property
    def even(self) -> tuple[tuple[str, str], ...]:
        """A video's scale keeps its sizes even."""
        return (("force_divisible_by", "2"),) if self.moving else ()


_SQUARE: Final = Filter("setsar", ("1",))  # the pixels square after every resize


def _scaled(target: Target, *how: tuple[str, str]) -> Filter:
    return Filter("scale", (str(target.width), str(target.height), *how, ("flags", SCALER)))


def head(  # noqa: PLR0913 -- the resize, the picture, its labels, where from; to measure it
    mode: ResizeMode,
    bblur: BBlur,
    picture: Picture,
    labels: Labels,
    start: Open | None = None,
    *,
    measure: bool = False,
) -> tuple[Open, str | None]:
    """The resize from ``start`` (the picture stream), left open for what follows; its note.

    ``measure``: blurred bars filled black instead, all else the same -- the picture's place
    then measurable, where the render puts it by construction (the padded fit agrees on every
    case measured, but is another graph: only the render's own is sure, for any format).
    """
    source, target = picture.source, picture.target
    size = (str(target.width), str(target.height))
    graph = Open(("0:v:0",)) if start is None else start  # Open(()): unlabelled, for -vf
    if source.sar != 1:
        graph = graph.then(Filter("scale", ("iw*sar", "ih", ("flags", SCALER))), _SQUARE)
    match mode:
        case "stretch":
            return graph.then(_scaled(target), _SQUARE), None
        case "cover":
            cover = _scaled(target, ("force_original_aspect_ratio", "increase"))
            return graph.then(cover, Filter("crop", size), _SQUARE), None
        case "fit" if not blurred_fit(mode, bblur):
            fit = _scaled(target, ("force_original_aspect_ratio", "decrease"), *picture.even)
            pad = Filter("pad", (*size, "(ow-iw)/2", "(oh-ih)/2", ("color", "black")))
            return graph.then(fit, pad, _SQUARE), None
        case _:  # fit, the borders the picture blurred
            return _blurred_bars(bblur, picture, graph, labels, measure=measure)


def _blurred_bars(
    bblur: BBlur, picture: Picture, graph: Open, labels: Labels, *, measure: bool
) -> tuple[Open, str | None]:
    source, target, video = picture.source, picture.target, picture.video
    sigma = bblur_sigma(bblur, source, target)
    note = None
    if bblur == "auto":
        into = f"{source.width}x{source.height} into {target.width}x{target.height}"
        note = f"--bblur auto: sigma {sigma} for {into} (set it with --bblur N)"
    # the source's format after the blur and after the overlay: overlay's format=auto
    # chose one with an alpha plane otherwise; a paletted one scale never outputs
    restore = (Filter("format", (video.pix_fmt,)),) if video.pix_fmt not in (None, "pal8") else ()
    back, front, blurred, fitted = (labels.new(n) for n in ("bg", "fg", "bgb", "fgs"))
    chains = graph.then(Filter("split", ("2",))).end((back, front))
    behind = Open((back,)).then(
        Filter("format", ("gbrp16le",)),
        curves(DECODE, video),
        _scaled(target, ("force_original_aspect_ratio", "increase")),
        Filter("crop", (str(target.width), str(target.height))),
        _BLACK if measure else Filter("gblur", (("sigma", sigma), ("steps", BLUR_STEPS))),
        curves(ENCODE, video),
        *restore,
    )
    fitted_scale = _scaled(target, ("force_original_aspect_ratio", "decrease"), *picture.even)
    ahead = Open((front,)).then(fitted_scale)
    overlay = Filter("overlay", ("(W-w)/2", "(H-h)/2", ("format", "auto")))
    joined = (*chains, *behind.end((blurred,)), *ahead.end((fitted,)))
    return Open((blurred, fitted), (overlay, *restore, _SQUARE), joined), note
