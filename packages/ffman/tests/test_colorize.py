"""subs.colorize: the highlighted word's colour, parsed and written as ASS writes it."""

import itertools
from fractions import Fraction

import pytest

from ffman.subs.colorize import (
    BLACK,
    GOLD,
    MOTIONS,
    NAMES,
    RECTANGLE,
    WHITE,
    Colour,
    contrast,
    keyframes,
    outline_for,
    parse,
    parse_highlight,
)
from ffman.values import round_half_up


@pytest.mark.parametrize(
    ("text", "rgb"),
    [("#00FF00", 0x00FF00), ("00ff00", 0x00FF00), ("#FfD700", 0xFFD700), ("#000000", 0)],
)
def test_a_hex_colour(text: str, rgb: int) -> None:
    assert parse(text) == Colour(rgb)


@pytest.mark.parametrize(
    "text",
    ["", "#", "#FFF", "#FFD7000", "##FFD700", "#GGGGGG", " #FFD700", "glitter"],
)
def test_not_a_colour(text: str) -> None:
    assert parse(text) is None


def test_ass_writes_blue_first() -> None:
    """&H00BBGGRR& -- gold as ffman always wrote it."""
    assert Colour(0xFF0000).ass() == "&H000000FF&"
    assert Colour(0x0000FF).ass() == "&H00FF0000&"
    assert GOLD.ass() == "&H0000D7FF&"


@pytest.mark.parametrize(
    ("text", "name"),
    [("rainbow", "rainbow"), ("RAINBOW", "rainbow"), ("Lsd", "lsd"), ("iridescence", "iridescent")],
)
def test_a_motion_by_name(text: str, name: str) -> None:
    assert parse(text) is MOTIONS[name]


def test_not_a_motion() -> None:
    assert parse("glitter") is None
    assert parse("rainbows") is None


def test_the_keyframes_are_the_wheel() -> None:
    """From the fade, then each sixth of a turn: red, yellow, green... exactly, whole ms, to the end."""
    frames = keyframes(MOTIONS["lsd"], 0, 1, 80, 1000)
    times = [t for t, _ in frames]
    assert times[0] == 80
    assert times == sorted(set(times))
    assert times[-1] >= 1000 > times[-2]
    wheel = [0xFF0000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF]
    assert [c.rgb for _, c in frames[1:]] == [wheel[k % 6] for k in range(1, len(frames))]
    assert [t for t, _ in frames[1:]] == [
        round_half_up(Fraction(1000 * k, 6)) for k in range(1, len(frames))
    ]


def test_a_rainbow_spans_the_word() -> None:
    """Letter k of n, k/n of a turn behind: the spectrum across the word."""
    first = [keyframes(MOTIONS["rainbow"], k, 6, 0, 1)[0][1].rgb for k in range(6)]
    assert first == [0xFF0000, 0xFF00FF, 0x0000FF, 0x00FFFF, 0x00FF00, 0xFFFF00]


def test_iridescence_is_pastel() -> None:
    """Saturation 3/10: no channel under 255 x 7/10, rounded half up."""
    frames = keyframes(MOTIONS["iridescent"], 0, 1, 0, 6000)
    assert min(min(c.rgb >> 16, c.rgb >> 8 & 0xFF, c.rgb & 0xFF) for _, c in frames) == 179


def _track(frames: list[tuple[int, Colour]], fade: int) -> list[tuple[float, float, float]]:
    """A letter's colour each ms as libass draws it: white, faded to the first, then linear."""
    points = ([(0, Colour(0xFFFFFF))] if fade >= 1 else []) + frames
    out: list[tuple[float, float, float]] = []
    for (a, ca), (b, cb) in itertools.pairwise(points):
        for t in range(a, b):
            f = (t - a) / (b - a)

            def at(shift: int, f: float = f, ca: Colour = ca, cb: Colour = cb) -> float:
                return ((ca.rgb >> shift & 255) * (1 - f) + (cb.rgb >> shift & 255) * f) / 255

            out.append((at(16), at(8), at(0)))
    return out


def _linear(c: float) -> float:
    return (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    )  # WCAG 2.2's relative luminance


def _flashes(track: list[tuple[float, float, float]]) -> tuple[int, int]:
    """The most general and red flashes in any 1 s (WCAG 2.2, 2.3.1), counted high.

    General: a transition between successive turning points of relative luminance, of 0.1 or more,
    the darker under 0.8; a flash, a pair: ceil(transitions / 2). Red: each stretch of saturated
    red (R / (R + G + B) >= 0.8, linear) is a flash, its chromaticity change taken as over 0.2.
    """
    lin = [tuple(_linear(c) for c in rgb) for rgb in track]
    lum = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in lin]
    turns = (
        [0]
        + [t for t in range(1, len(lum) - 1) if (lum[t] - lum[t - 1]) * (lum[t + 1] - lum[t]) < 0]
        + [len(lum) - 1]
    )
    counted = [
        b
        for a, b in itertools.pairwise(turns)
        if abs(lum[b] - lum[a]) >= 0.1 and min(lum[a], lum[b]) < 0.8
    ]
    red = [r / (r + g + b) >= 0.8 if r + g + b > 0 else False for r, g, b in lin]
    starts = [t for t in range(len(red)) if red[t] and (t == 0 or not red[t - 1])]
    general = max(
        (-(-sum(1 for t in counted if w <= t < w + 1000) // 2) for w in range(0, len(lum), 10)),
        default=0,
    )
    reds = max(
        (sum(1 for t in starts if w <= t < w + 1000) for w in range(0, len(lum), 10)), default=0
    )
    return general, reds


@pytest.mark.parametrize("name", ["rainbow", "lsd", "iridescent"])
def test_no_more_than_three_flashes_a_second(name: str) -> None:
    """Every letter of words of 1 to 8 letters, 0.3 to 4 s, faded in or at once: <= 3 a second."""
    worst = (0, 0)
    for letters in range(1, 9):
        for letter in range(letters):
            for end in (300, 1000, 2500, 4000):
                for fade in (0, 80):
                    found = _flashes(
                        _track(keyframes(MOTIONS[name], letter, letters, fade, end), fade)[:end]
                    )
                    worst = (max(worst[0], found[0]), max(worst[1], found[1]))
    assert worst[0] <= 3
    assert worst[1] <= 3


@pytest.mark.parametrize("letters", [667, 701, 1001])
def test_the_keyframes_never_meet(letters: int) -> None:
    """A boundary within half a ms of the last rounds onto it: moved a ms on, never \\t(0,0) --
    libass runs that to the event's end (its first form gave one letter [0, 0, 334])."""
    for letter in range(letters):
        times = [t for t, _ in keyframes(MOTIONS["rainbow"], letter, letters, 0, 2500)]
        assert all(a < b for a, b in itertools.pairwise(times))


@pytest.mark.parametrize("text", ["gold", "Gold", "GOLD"])
def test_gold_by_name_is_the_default(text: str) -> None:
    assert parse(text) == GOLD


@pytest.mark.parametrize(
    ("text", "rgb"),
    [("Teal", 0x2DD4BF), ("amber", 0xFBBF24), ("VIOLET", 0xA78BFA), ("green", 0x4ADE80)],
)
def test_a_colour_by_name(text: str, rgb: int) -> None:
    """Tailwind's shade 400, in either case."""
    assert parse(text) == Colour(rgb)


def test_css_synonyms() -> None:
    assert (NAMES["grey"], NAMES["magenta"], NAMES["aqua"]) == (
        NAMES["gray"],
        NAMES["fuchsia"],
        NAMES["cyan"],
    )


def test_every_hue_keeps_7_to_1_against_a_black_outline() -> None:
    """WCAG AAA against the default outline: the rule the palette's shade was chosen by (white
    and black are the extremes, each outlined by the other)."""

    def luminance(c: Colour) -> float:
        r, g, b = (_linear((c.rgb >> s & 255) / 255) for s in (16, 8, 0))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    hues = [c for name, c in NAMES.items() if name not in ("white", "black")]
    assert min((luminance(c) + 0.05) / 0.05 for c in hues) >= 7


@pytest.mark.parametrize(
    ("fill", "outline"), [(WHITE, BLACK), (BLACK, WHITE), (GOLD, BLACK), (Colour(0x1E3A8A), WHITE)]
)
def test_the_outline_that_contrasts_most(fill: Colour, outline: Colour) -> None:
    assert outline_for(fill) == outline


def test_the_outline_never_under_sqrt_21() -> None:
    """(L + .05)/.05 x 1.05/(L + .05) = 21: the better of black and white is 4.58:1 at least."""
    worst = min(
        max(contrast(Colour(c), BLACK), contrast(Colour(c), WHITE))
        for c in range(0, 0x1000000, 4099)
    )
    assert worst >= 21**0.5 - 1e-9


@pytest.mark.parametrize("name", ["rainbow", "lsd", "iridescent"])
def test_a_motion_s_outline_is_one(name: str) -> None:
    """The best worst over its turn -- black, for all three (rainbow's blue: 2.44 against 1.07)."""
    assert outline_for(MOTIONS[name]) == BLACK


def test_contrast_is_wcag_s() -> None:
    assert abs(contrast(WHITE, BLACK) - 21) < 1e-9
    assert abs(contrast(GOLD, BLACK) - 14.97) < 0.005
    assert contrast(BLACK, GOLD) == contrast(GOLD, BLACK)


def test_white_and_black_by_name() -> None:
    assert (parse("White"), parse("BLACK")) == (WHITE, BLACK)


@pytest.mark.parametrize("text", ["rectangle", "Rectangle", "RECTANGLE"])
def test_the_rectangle_is_a_highlight(text: str) -> None:
    assert parse_highlight(text) is RECTANGLE
    assert parse(text) is None  # no text colour: the font's and the outline's are parse's


def test_a_highlight_is_parse_s_too() -> None:
    assert (parse_highlight("teal"), parse_highlight("lsd")) == (NAMES["teal"], MOTIONS["lsd"])
