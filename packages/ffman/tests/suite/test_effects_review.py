"""run.sh's "effects review": each effect measured as it arises (G3). Ids: the bash checks' numbers.

The measures are run.sh's numpy (tests/support/measures.py), its thresholds kept.
"""

from pathlib import Path

import pytest

from ffman.cli import main
from tests.support.measures import (
    colour_edge,
    crt_line,
    edge_width,
    halation_tint,
    head_switching,
    lateral_shift,
    vhs_noise,
    vhs_response,
)
from tests.support.media import ff, tool

GEN = ("ffmpeg", "-v", "error", "-y")


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_halation_glows_the_films_colour(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S268
    # a bright cyan light (red low): per channel it glowed blue-green; through the film's red
    # layer, from luminance, red-orange
    light = "drawbox=x=280:y=140:w=80:h=80:c=0x40FFFF:t=fill"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=black:s=640x360",
        "-vf",
        light,
        "-frames:v",
        "1",
        "yel.png",
    )
    assert ff(capsys, "-i", "yel.png", "--vfx", "halation", "-o", "yelh.png", "-y")[0] == 0
    r, g, b = halation_tint(ffmpeg, "yelh.png", "yel.png")
    assert r > 1
    assert r > g > b, (r, g, b)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_lateral_ca_grows_to_the_edges(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S269
    # exact in full colour: none at the centre, 8 px at the edges, so 8 * 280/320 = 7.0 at 280 px out
    lines = "drawbox=x=38:y=0:w=4:h=360:c=white:t=fill,drawbox=x=318:y=0:w=4:h=360:c=white:t=fill"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=black:s=640x360",
        "-vf",
        lines,
        "-frames:v",
        "1",
        "lines.png",
    )
    assert (
        ff(capsys, "-i", "lines.png", "--vfx", "chromatic-aberration:8", "-o", "linesca.png", "-y")[
            0
        ]
        == 0
    )
    centre, out = lateral_shift(ffmpeg, "linesca.png")
    assert (f"{centre:.1f}", f"{out:.1f}") == ("0.0", "7.0")


@pytest.fixture(scope="module")
def crt_lines(files: Path, ffmpeg: str) -> dict[int, tuple[int, float, float]]:
    """run.sh's crtline at grey 90 and 200: a flat field through --crt, at 1080 rows."""
    found: dict[int, tuple[int, float, float]] = {}
    for grey in (90, 200):
        source, out = files / f"cg{grey}.png", files / f"cgo{grey}.png"
        colour = f"color=0x{grey:02x}{grey:02x}{grey:02x}:s=640x1080"
        _ = tool(*GEN, "-f", "lavfi", "-i", colour, "-frames:v", "1", str(source))
        assert main(["convert", "-i", str(source), "--vfx", "crt", "-o", str(out), "-y"]) == 0
        found[grey] = crt_line(ffmpeg, str(out), str(source))
    return found


@pytest.mark.ffmpeg
def test_crt_has_240_scanlines(crt_lines: dict[int, tuple[int, float, float]]) -> None:  # S270
    assert crt_lines[90][0] == 240


@pytest.mark.ffmpeg
def test_crt_keeps_a_flat_fields_light(
    crt_lines: dict[int, tuple[int, float, float]],
) -> None:  # S271
    dim, bright = crt_lines[90][1], crt_lines[200][1]  # in linear light
    assert 0.98 < dim < 1.02, dim
    assert 0.97 < bright < 1.02, bright


@pytest.mark.ffmpeg
def test_crt_brighter_lines_are_wider(
    crt_lines: dict[int, tuple[int, float, float]],
) -> None:  # S272
    assert crt_lines[200][2] < crt_lines[90][2] - 0.1  # shallower gaps


def sine_through_vhs(
    ffmpeg: str, capsys: pytest.CaptureFixture[str], cycles: int, plane: int
) -> float:
    """run.sh's vhsresp: a sine of ``cycles`` across 1080 lines on one plane, its amplitude kept."""
    wave = f"128+100*sin(2*PI*X*{cycles}/1080)"
    planes = f"lum=128:cb='{wave}':cr=128" if plane else f"lum='{wave}':cb=128:cr=128"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=gray:s=1920x1080:r=10:d=1",
        "-vf",
        f"format=yuv444p,geq={planes}",
        "-c:v",
        "ffv1",
        "gr.mkv",
    )
    assert ff(capsys, "-i", "gr.mkv", "--vfx", "vhs", "-o", "grv.mkv", "-y")[0] == 0
    return vhs_response(ffmpeg, "grv.mkv", "gr.mkv", plane)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_vhs_luma_bandwidth(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S273
    kept = sine_through_vhs(ffmpeg, capsys, 120, 0)  # 240 TVL: about -3 dB (0.708)
    assert 0.66 < kept < 0.78, kept


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_vhs_chroma_bandwidth(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S274
    kept = sine_through_vhs(ffmpeg, capsys, 15, 1)  # 30 TVL: about -3 dB
    assert 0.66 < kept < 0.76, kept


# -- bar blur at 4:4:4; VHS as the format
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_bar_blurs_colour_as_far_as_detail(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S275
    # gblur's one sigma is in plane pixels: on 4:2:0 the colour spread twice as far
    def edge(name: str, planes: str) -> int:
        split = f"format=yuv420p,geq={planes}"
        _ = tool(
            *GEN,
            "-f",
            "lavfi",
            "-i",
            "color=gray:s=640x360:r=10:d=0.3",
            "-vf",
            split,
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "yuv420p",
            name,
        )
        assert (
            ff(capsys, "-i", name, "-a", "9:16", "-w", "360", "--bblur", "-o", "bbo.mkv", "-y")[0]
            == 0
        )
        return edge_width(ffmpeg, "bbo.mkv")

    luma = edge("bbl.mkv", "lum='if(lt(X,W/2),60,190)':cb=128:cr=128")
    colour = edge("bbc.mkv", "lum=128:cb='if(lt(X,W/2),60,196)':cr=128")
    assert luma * 0.9 <= colour <= luma * 1.1, (luma, colour)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("width", "height"), [pytest.param(640, 360, id="S277"), pytest.param(1920, 1080, id="S278")]
)
def test_vhs_noise_is_the_same_at_any_size(
    ffmpeg: str, capsys: pytest.CaptureFixture[str], width: int, height: int
) -> None:
    # 43 dB luma (1.55 RMS), about 40 dB chroma (2.24): within 1.5 dB
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        f"color=0x808080:s={width}x{height}:r=10:d=0.4",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv444p",
        "vg.mkv",
    )
    assert ff(capsys, "-i", "vg.mkv", "--vfx", "vhs", "-o", "vgo.mkv", "-y")[0] == 0
    luma, chroma = vhs_noise(ffmpeg, "vgo.mkv", width, height)
    assert 1.31 < luma < 1.84, luma
    assert 1.89 < chroma < 2.66, chroma


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_vhs_colour_droops(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S279
    # the 1H comb smears colour down half a line pair (h/480): 2 px at 1080
    edge = "format=yuv444p,geq=lum=128:cb='if(lt(Y,H/2),60,196)':cr=128"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=gray:s=1920x1080:r=10:d=0.4",
        "-vf",
        edge,
        "-c:v",
        "ffv1",
        "vd.mkv",
    )
    assert ff(capsys, "-i", "vd.mkv", "--vfx", "vhs", "-o", "vdo.mkv", "-y")[0] == 0
    moved = colour_edge(ffmpeg, "vdo.mkv") - colour_edge(ffmpeg, "vd.mkv")
    assert 1.5 < moved < 2.5, moved


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_vhs_head_switching(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S280
    # 6.5 H before vertical sync: the bottom 7 of 480 lines (16 of 1080) jump w/50
    bar = "format=yuv444p,drawbox=x=900:y=0:w=120:h=ih:c=white:t=fill"
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=black:s=1920x1080:r=10:d=0.4",
        "-vf",
        bar,
        "-c:v",
        "ffv1",
        "vb.mkv",
    )
    assert ff(capsys, "-i", "vb.mkv", "--vfx", "vhs", "-o", "vbo.mkv", "-y")[0] == 0
    assert head_switching(ffmpeg, "vbo.mkv") == (16, 24)
