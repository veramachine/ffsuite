r"""What the highlighted word looks like (``--highlight-colorize``): a colour, or hues in motion.

Gold by default. ASS writes a colour &HAABBGGRR& -- alpha, then blue first: libass reads its hex
digits as one integer and byte-swaps it (ass_parse.c, ``parse_color_tag``). A motion is keyframed
at each sixth of a turn -- red, yellow, green, cyan, blue, magenta -- and libass's ``\t``
interpolates colours linearly in RGB (rendered): between those six, the hue wheel itself, at any
saturation.
"""

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from ffman.values import round_half_up

_HEX: Final = re.compile(r"#?([0-9A-Fa-f]{6})")


@dataclass(frozen=True, slots=True)
class Colour:
    """An opaque colour, 0xRRGGBB."""

    rgb: int

    def code(self) -> str:
        """The colour as a style line writes it: &H00BBGGRR."""
        red, green, blue = self.rgb >> 16, self.rgb >> 8 & 0xFF, self.rgb & 0xFF
        return f"&H00{blue:02X}{green:02X}{red:02X}"

    def ass(self) -> str:
        """The colour as an override tag writes it: &H00BBGGRR&."""
        return f"{self.code()}&"


GOLD: Final = Colour(0xFFD700)  # bash's highlight, and CSS's gold
WHITE: Final = Colour(0xFFFFFF)  # the text, by default
BLACK: Final = Colour(0x000000)  # its outline, by default

# A colour by name: Tailwind CSS's palette (v3.4.17, src/public/colors.js), shade 400 -- the
# darkest at which every hue keeps 7:1 (WCAG AAA) against the black outline; CSS's own names
# fail it (indigo 1.6:1, purple 2.2, blue 2.4, green 4.1). Gold is bash's; white and black the
# extremes (the text and its outline by default); CSS's synonyms alike.
_PALETTE: Final = {
    "gold": GOLD,
    "slate": Colour(0x94A3B8),
    "gray": Colour(0x9CA3AF),
    "zinc": Colour(0xA1A1AA),
    "neutral": Colour(0xA3A3A3),
    "stone": Colour(0xA8A29E),
    "red": Colour(0xF87171),
    "orange": Colour(0xFB923C),
    "amber": Colour(0xFBBF24),
    "yellow": Colour(0xFACC15),
    "lime": Colour(0xA3E635),
    "green": Colour(0x4ADE80),
    "emerald": Colour(0x34D399),
    "teal": Colour(0x2DD4BF),
    "cyan": Colour(0x22D3EE),
    "sky": Colour(0x38BDF8),
    "blue": Colour(0x60A5FA),
    "indigo": Colour(0x818CF8),
    "violet": Colour(0xA78BFA),
    "purple": Colour(0xC084FC),
    "fuchsia": Colour(0xE879F9),
    "pink": Colour(0xF472B6),
    "rose": Colour(0xFB7185),
}
NAMES: Final = {
    **_PALETTE,
    "grey": _PALETTE["gray"],
    "magenta": _PALETTE["fuchsia"],
    "aqua": _PALETTE["cyan"],
    "white": WHITE,
    "black": BLACK,
}


@dataclass(frozen=True, slots=True)
class Motion:
    """Hues cycling: a turn of the wheel each ``period`` ms, at ``saturation``.

    Each letter is ``spread`` of a turn behind the one before it; none, the whole spectrum across
    the word.
    """

    period: int
    spread: Fraction | None
    saturation: Fraction


# At most 3 flashes a second (WCAG 2.3.1): a saturated turn is ~2 general flashes and a red one.
_IRIDESCENT: Final = Motion(3000, Fraction(1, 12), Fraction(3, 10))
MOTIONS: Final = {
    "rainbow": Motion(2000, None, Fraction(1)),
    "lsd": Motion(1000, Fraction(1, 3), Fraction(1)),
    "iridescent": _IRIDESCENT,
    "iridescence": _IRIDESCENT,
}
# the six keyframes, red to magenta: each channel full or none
_WHEEL: Final = ((1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), (1, 0, 1))


type Colorize = Colour | Motion  # the highlighted word: a colour, or hues in motion


@dataclass(frozen=True, slots=True)
class Rectangle:
    """The highlighted word in reverse video: a box the text's colour, the word its outline's."""


RECTANGLE: Final = Rectangle()
type Highlight = Colorize | Rectangle  # what --highlight-colorize may be


def parse_highlight(text: str) -> Highlight | None:
    """``--highlight-colorize``'s value: ``parse``'s, or ``rectangle``, either case; else none."""
    return RECTANGLE if text.lower() == "rectangle" else parse(text)


def parse(text: str) -> Colorize | None:
    """``--highlight-colorize``'s value: ``#RRGGBB``, ``RRGGBB``, a colour's or a motion's name.

    Either case, each; else none.
    """
    found = _HEX.fullmatch(text)
    if found:
        return Colour(int(found[1], 16))
    name = text.lower()
    return NAMES.get(name) or MOTIONS.get(name)


def keyframes(  # noqa: PLR0913 -- the motion, the letter among its letters, and when
    motion: Motion, letter: int, letters: int, fade: int, end: int, start: int = 0
) -> list[tuple[int, Colour]]:
    r"""A letter's colours from ``fade`` (ms into its event) on: there, then each sixth of a turn.

    To the first sixth at or past ``end``, so the colour moves to the end; whole ms, as libass
    reads ``\t``'s times. ``start``: the event's own, ms -- the turn's phase is by it, so a
    letter's hue runs on from one event into the next.
    """
    lag = _lag(motion, letter, letters)
    phase = Fraction(start + fade, motion.period) - lag
    frames = [(fade, _hue(phase, motion.saturation))]
    sixth = math.floor(phase * 6) + 1  # the next one past fade
    while frames[-1][0] < end:
        at = round_half_up((Fraction(sixth, 6) + lag) * motion.period) - start
        # never on the one before: \t(a, a, ...) is nothing, and \t(0, 0, ...) runs the whole
        # event (libass: t2 0 is its duration) -- a boundary within half a ms of 0 rounds there
        at = max(at, frames[-1][0] + 1)
        frames.append((at, _hue(Fraction(sixth, 6), motion.saturation)))
        sixth += 1
    return frames


def colour_at(motion: Motion, letter: int, letters: int, at: int) -> Colour:
    """A letter's colour ``at`` ms (the phase's own time), between the keyframes as libass mixes."""
    return _hue(Fraction(at, motion.period) - _lag(motion, letter, letters), motion.saturation)


def _lag(motion: Motion, letter: int, letters: int) -> Fraction:
    """Turns behind the first letter: ``spread`` each, or the spectrum across them."""
    return letter * (motion.spread if motion.spread is not None else Fraction(1, letters))


def _hue(turns: Fraction, saturation: Fraction) -> Colour:
    """The colour ``turns`` round the wheel (from red), at ``saturation``, full value."""
    at = turns % 1 * 6
    k = math.floor(at)
    near, far = _WHEEL[k], _WHEEL[(k + 1) % 6]
    rgb = 0
    for a, b in zip(near, far, strict=True):
        full = a + (b - a) * (at - k)  # 0..1, linear between the two keyframes
        rgb = rgb << 8 | round_half_up(255 * (1 - saturation * (1 - full)))
    return Colour(rgb)


def luminance(colour: Colour) -> float:
    """WCAG 2.2's relative luminance: sRGB linearised, weighted 0.2126, 0.7152, 0.0722."""
    red, green, blue = (_linear((colour.rgb >> shift & 0xFF) / 255) for shift in (16, 8, 0))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(a: Colour, b: Colour) -> float:
    """WCAG 2.2's contrast ratio, 1 to 21."""
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def outline_for(paint: Colorize) -> Colour:
    """The outline that contrasts most: black or white -- never under sqrt(21), 4.58:1.

    For a motion, the one whose worst over its turn is best (a flip between them would flash):
    its extremes are its six keyframes, each segment moving one channel, one way.
    """
    fills = (
        [paint]
        if isinstance(paint, Colour)
        else [_hue(Fraction(k, 6), paint.saturation) for k in range(6)]
    )
    return max((BLACK, WHITE), key=lambda outline: min(contrast(fill, outline) for fill in fills))


_SRGB_KNEE: Final = 0.04045  # WCAG 2.2's (0.03928 before May 2021)


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= _SRGB_KNEE else ((channel + 0.055) / 1.055) ** 2.4
