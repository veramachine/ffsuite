"""run.sh's blurs: on light, round; and --bblur auto's detail (G3). Ids: the bash checks' numbers.

A blur averages light: gamma-encoded, a fine black/white pattern kept 38% of
it, and a red|green edge dipped below red's own luminance. The PNGs are sRGB.
"""

import pytest

from tests.support.measures import border_detail, light, red_green_dip, roundness
from tests.support.media import ff, tool

GEN = ("ffmpeg", "-v", "error", "-y")


@pytest.fixture
def pattern() -> str:
    """run.sh's chk.png: a one-pixel black/white checkerboard, 640x360 (in the test's directory)."""
    checker = "format=gray,geq=lum='255*mod(X+Y\\,2)'"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=black:s=640x360",
        "-vf",
        checker,
        "-frames:v",
        "1",
        "chk.png",
    )
    return "chk.png"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_blur_keeps_the_light(
    pattern: str, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S286
    assert ff(capsys, "-i", pattern, "--vfx", "blur:8", "-o", "chkb.png", "-y")[0] == 0
    before, after = light(ffmpeg, ffprobe, pattern), light(ffmpeg, ffprobe, "chkb.png", (40, 320))
    assert before * 0.98 < after < before * 1.02, (before, after)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_bar_blur_keeps_the_light(
    pattern: str, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S287
    assert (
        ff(capsys, "-i", pattern, "-a", "9:16", "-w", "360", "--bblur", "-o", "chkbb.png", "-y")[0]
        == 0
    )
    before, border = light(ffmpeg, ffprobe, pattern), light(ffmpeg, ffprobe, "chkbb.png", (5, 90))
    assert before * 0.97 < border < before * 1.03, (before, border)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_no_dark_band_where_red_meets_green(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S288
    green = "drawbox=x=320:y=0:w=320:h=360:c=0x00FF00:t=fill"
    _ = tool(
        *GEN, "-f", "lavfi", "-i", "color=red:s=640x360", "-vf", green, "-frames:v", "1", "rg.png"
    )
    assert ff(capsys, "-i", "rg.png", "--vfx", "blur:12", "-o", "rgb.png", "-y")[0] == 0
    lowest, red = red_green_dip(ffmpeg, "rgb.png")
    assert lowest >= red - 0.005, (lowest, red)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_blur_is_round_on_screen(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S289
    # on non-square pixels, a round blur on screen: sigma / SAR across
    dot = "drawbox=x=158:y=118:w=4:h=4:c=white:t=fill,setsar=2/1"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=black:s=320x240:r=10:d=0.3",
        "-vf",
        dot,
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv444p",
        "ana.mkv",
    )
    assert ff(capsys, "-i", "ana.mkv", "--vfx", "blur:10", "-o", "anab.mkv", "-y")[0] == 0
    assert abs(roundness(ffmpeg, "anab.mkv") - 1) < 0.05


@pytest.fixture
def detailed() -> str:
    """run.sh's det.mp4: random 8 px blocks (detail at the scales a blur removes, as a photo has)."""
    # geq's random() follows its slicing -- 8 threads draw other blocks than 1 -- so it runs in the
    # main graph, on one thread: the same blocks on any machine (a lavfi input's graph takes the cores)
    blocks = "format=gray,geq=lum='random(1)*255',scale=1920:1080:flags=neighbor"
    source = (
        "-f",
        "lavfi",
        "-i",
        "nullsrc=s=240x135:r=25:d=0.4",
        "-filter_threads",
        "1",
        "-vf",
        blocks,
    )
    _ = tool(*GEN, *source, "-c:v", "libx264", "-pix_fmt", "yuv420p", "det.mp4")
    return "det.mp4"


def detail_ratio(ffmpeg: str, capsys: pytest.CaptureFixture[str], source: str, sigma: str) -> float:
    """The border's detail at 360x640 over at 180x320, with ``-b sigma``: 1 is the same blur."""
    for width, out in (("180", "d1.mp4"), ("360", "d2.mp4")):
        assert (
            ff(capsys, "-i", source, "-o", out, "-a", "9:16", "-w", width, "-b", sigma, "-y")[0]
            == 0
        )
    return border_detail(ffmpeg, "d2.mp4") / border_detail(ffmpeg, "d1.mp4")


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_auto_blurs_the_same_at_any_size(
    detailed: str, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S202
    ratio = detail_ratio(ffmpeg, capsys, detailed, "auto")
    assert 0.85 < ratio < 1.15, ratio


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_fixed_sigma_does_not(
    detailed: str, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S203
    ratio = detail_ratio(ffmpeg, capsys, detailed, "6")
    assert ratio > 1.3, ratio
