from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ffman.errors import FfmanError
from ffman.graph.sizes import Displayed, Target
from ffman.media.probe import Rational, Video
from ffman.plan.geometry import displayed, round_even, target_size
from ffman.values import round_half_up


def src(w: int, h: int) -> Displayed:
    return Displayed(w, h, w, h, Fraction(1))


def video_stream(
    w: int | None, h: int | None, sar: str | None = None, rotation: str | None = None
) -> Video:
    return Video(
        None,
        w,
        h,
        rotation,
        Rational.parse(sar, ":"),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


# bash's own answers (its plan_dimensions, run on each case): the literals below --
# one corrected, where bash rounded a tie the wrong way.
@pytest.mark.parametrize(
    ("source", "video", "width", "height", "aspect", "expected"),
    [
        ((1920, 1080), True, None, None, None, None),
        ((1920, 1080), True, 640, None, None, Target(640, 360, None)),
        ((1920, 1080), True, None, 360, None, Target(640, 360, None)),
        (
            (1920, 1080),
            True,
            641,
            None,
            None,
            Target(642, 360, "rounded to 642x360: video dimensions must be even"),
        ),
        (
            (1920, 1080),
            False,
            641,
            None,
            None,
            Target(641, 361, None),
        ),  # an image: no even rounding
        ((1920, 1080), True, 640, 480, None, Target(640, 480, None)),
        ((1920, 1080), True, None, None, "9:16", Target(1080, 1920, None)),  # the longest side kept
        ((1920, 1080), True, None, None, "2.39:1", Target(1920, 804, None)),
        ((1080, 1920), True, None, None, "1:1", Target(1920, 1920, None)),
        (
            (1920, 1080),
            False,
            8,
            None,
            "16:9",
            Target(8, 5, None),
        ),  # 4.5, half up (bash: 4, from 1.77778)
        ((1920, 1080), True, 1280, 720, "16:9", Target(1280, 720, None)),
        ((1920, 1080), True, None, 720, "4:3", Target(960, 720, None)),  # a height and a ratio
        ((1920, 1080), False, None, 5, "2.39:1", Target(12, 5, None)),
        (
            (1920, 1080),
            True,
            1,
            None,
            None,
            Target(2, 2, "rounded to 2x2: video dimensions must be even"),
        ),
        ((1920, 1080), False, 1, None, None, Target(1, 1, None)),
    ],
)
def test_target_size_as_bash(
    source: tuple[int, int],
    video: bool,
    width: int | None,
    height: int | None,
    aspect: str | None,
    expected: Target | None,
) -> None:
    assert (
        target_size(src(*source), video=video, width=width, height=height, aspect=aspect)
        == expected
    )


@pytest.mark.parametrize(
    ("source", "width", "height", "aspect", "message"),
    [
        (
            (1920, 1080),
            1280,
            700,
            "16:9",
            "--width 1280 and --height 700 are 64:35, which is not the requested --aspect-ratio 16:9",
        ),
        ((4001, 3), 1, None, None, "computed size 1x0 is not usable"),
        # the ratio exact at any size (bash cut "%.6g" to six characters: 123456:1, 1.2345:1)
        (
            (1920, 1080),
            12345678,
            1,
            "16:9",
            "--width 12345678 and --height 1 are 12345678:1, which is not the requested --aspect-ratio 16:9",
        ),
        (
            (1920, 1080),
            2469135,
            2,
            "16:9",
            "--width 2469135 and --height 2 are 2469135:2, which is not the requested --aspect-ratio 16:9",
        ),
    ],
)
def test_target_size_refusals(
    source: tuple[int, int], width: int | None, height: int | None, aspect: str | None, message: str
) -> None:
    with pytest.raises(FfmanError) as error:
        _ = target_size(src(*source), video=False, width=width, height=height, aspect=aspect)
    assert str(error.value) == message


def test_the_suites_rotated_case() -> None:
    # run.sh: "rotated: 90x160, not 90x50" -- a 320x180 clip turned 90 degrees, -w 90
    d = displayed(video_stream(320, 180, rotation="90"), "r.mp4")
    assert (d.width, d.height, d.frame_width, d.frame_height) == (180, 320, 180, 320)
    assert target_size(d, video=True, width=90, height=None, aspect=None) == Target(90, 160, None)


@pytest.mark.parametrize(
    ("rotation", "turned"),
    [
        ("90", True),
        ("-90", True),
        ("270", True),
        ("-270", True),
        ("90.9", True),
        ("180", False),
        ("0", False),
        ("450", False),
        (None, False),
    ],
)
def test_rotation_as_bash(rotation: str | None, turned: bool) -> None:
    d = displayed(video_stream(640, 360, rotation=rotation), "f")
    assert (d.width, d.height) == ((360, 640) if turned else (640, 360))


def test_sar_widens_the_display_and_is_kept() -> None:
    d = displayed(video_stream(720, 480, sar="32:27"), "f")
    assert (d.width, d.height, d.frame_width, d.sar) == (
        853,
        480,
        720,
        Fraction(32, 27),
    )  # 720 * 32/27 = 853.3
    for sar in ("1:1", "0:1", "N/A", None):
        assert displayed(video_stream(720, 480, sar=sar), "f").sar == 1


@pytest.mark.parametrize(("w", "h"), [(None, 480), (640, None), (0, 480), (640, 0)])
def test_no_picture(w: int | None, h: int | None) -> None:
    with pytest.raises(FfmanError, match=r"^no picture stream in: x\.mp4$"):
        _ = displayed(video_stream(w, h), "x.mp4")
    with pytest.raises(FfmanError, match=r"^no picture stream in: y\.mp3$"):
        _ = displayed(None, "y.mp3")


# Proven corrections (docs/ffman-python.md, G4): each comment gives bash's answer.
@pytest.mark.parametrize(
    ("source", "video", "width", "height", "aspect", "expected"),
    [
        # rounded twice: 1938.996 -> "1939" (%.6g) -> even 1940; the nearest even is 1938
        (
            (7291, 3454),
            True,
            4093,
            None,
            None,
            Target(4094, 1938, "rounded to 4094x1938: video dimensions must be even"),
        ),
        # exactly 1 px from 1:3 (the rule's limit); bash's 0.333333 made it 1.000001: refused
        ((1920, 1080), False, 2, 3, "1:3", Target(2, 3, None)),
        ((2676, 1843), False, 5481, 2348, "21:9", Target(5481, 2348, None)),
        # a tie (7, between 6 and 8): up; bash's 2.33333 made it 6.99999, down to 6
        (
            (1920, 1080),
            True,
            None,
            3,
            "21:9",
            Target(8, 4, "rounded to 8x4: video dimensions must be even"),
        ),
    ],
)
def test_corrections_of_bash(
    source: tuple[int, int],
    video: bool,
    width: int | None,
    height: int | None,
    aspect: str | None,
    expected: Target,
) -> None:
    assert (
        target_size(src(*source), video=video, width=width, height=height, aspect=aspect)
        == expected
    )


# Properties: what must hold for every input -- exactly.
@given(st.fractions(min_value=0, max_value=10**6))
def test_round_even_is_the_nearest_even_halves_up(x: Fraction) -> None:
    n = round_even(x)
    assert n % 2 == 0
    assert n >= 2
    if x >= 1:
        assert abs(x - n) < 1 or n - x == 1


@given(st.integers(1, 8000), st.integers(1, 8000), st.integers(1, 8000), st.booleans())
def test_a_width_alone_keeps_the_shape(sw: int, sh: int, w: int, video: bool) -> None:
    true = Fraction(w * sh, sw)
    try:
        t = target_size(src(sw, sh), video=video, width=w, height=None, aspect=None)
    except FfmanError:  # only an image whose height rounds to 0
        assert not video
        assert true < Fraction(1, 2)
        return
    assert t is not None
    expected = (round_even(Fraction(w)), round_even(true)) if video else (w, round_half_up(true))
    assert (t.width, t.height) == expected


@given(
    st.integers(1, 8000),
    st.integers(1, 8000),
    st.sampled_from(["16:9", "9:16", "4:3", "1:1", "2.39:1", "1:3"]),
)
def test_no_side_given_keeps_the_longest_side(sw: int, sh: int, aspect: str) -> None:
    a, b = (Fraction(x) for x in aspect.split(":"))
    ratio = max(a, b) / min(a, b)
    try:
        t = target_size(src(sw, sh), video=False, width=None, height=None, aspect=aspect)
    except FfmanError:  # only when the shorter side rounds to 0
        assert max(sw, sh) / ratio < Fraction(1, 2)
        return
    assert t is not None
    assert max(t.width, t.height) == max(sw, sh)


@given(st.integers(1, 8000), st.integers(1, 8000))
def test_a_quarter_turn_swaps_the_sides(w: int, h: int) -> None:
    d = displayed(video_stream(w, h, rotation="90"), "f")
    assert (d.width, d.height) == (h, w)
