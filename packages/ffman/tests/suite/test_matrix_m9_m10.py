"""matrix.sh's M9 and M10: where burned text lands, measured on the frame (G3).

M9 (M603 + source x 8 + mode x 2 + margin): centred in a black bar under the
picture when there is one and no --margin-bottom, else its bottom at the margin
(5.573% by default). M10 (M643 + source x 10 + resize x 2 + mode): self-
consistent under every resize -- the text never at the frame's edge; a bar of
N of H px reported puts its centre at 1 - N/2H (or, a block too tall, lifts it
to the margin); no bar puts its bottom at the margin. The reference is the same
resize without subtitles. The measure is check.py's text_band, at 2.2 s.
"""

import re
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.measures import text_band
from tests.support.media import tool

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
GEN: Final = ("ffmpeg", "-v", "error", "-y")
H264: Final = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
BLACK: Final = ("-f", "lavfi", "-i", "color=black:s=640x360:r=25:d=4")


def picture_on_black(files: Path, size: str, at: str, name: str) -> None:
    """matrix.sh's pic: a test picture of ``size`` at ``at`` on black 640x360, 4 s."""
    over = (
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={size}:r=25:d=4",
        "-filter_complex",
        f"[0][1]overlay={at}:shortest=1",
    )
    _ = tool(*GEN, *BLACK, *over, *H264, str(files / name))


@pytest.fixture(scope="module")
def placed(files: Path) -> Path:
    """M9's and M10's sources."""
    picture_on_black(
        files, "640x200", "0:0", "bottombar.mp4"
    )  # a 160 px bar below the picture: centre 0.778
    picture_on_black(
        files, "640x250", "0:55", "letterbox.mp4"
    )  # 55 px above and below: centre about 0.922
    picture_on_black(files, "480x360", "80:0", "pillarbox.mp4")
    _ = tool(*GEN, *BLACK, *H264, str(files / "allblack.mp4"))
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=0x203040:s=640x360:r=25:d=4",
        *H264,
        str(files / "open.mp4"),
    )
    picture_on_black(files, "640x200", "0:0", "bbar.mp4")
    _ = tool(
        *GEN,
        "-f",
        "lavfi",
        "-i",
        "color=0x203040:s=640x360:r=25:d=4",
        *H264,
        str(files / "open10.mp4"),
    )
    _ = tool(
        *GEN,
        "-display_rotation",
        "180",
        "-i",
        str(files / "bbar.mp4"),
        "-c",
        "copy",
        str(files / "bbar180.mp4"),
    )  # the bar at the top
    sar = (
        "-f",
        "lavfi",
        "-i",
        "color=black:s=720x480:r=25:d=4",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=720x267:r=25:d=4",
    )
    _ = tool(
        *GEN,
        *sar,
        "-filter_complex",
        "[0][1]overlay=0:0:shortest=1,setsar=32/27",
        *H264,
        str(files / "bbarsar.mp4"),
    )
    return files


MODES: Final = (
    ("plain", "regular.srt"),
    ("chunk-word", "sentences.ojf.json"),
    ("word", "words.srt"),
    ("word-highlight", "words.srt"),
)
M9: Final = [
    pytest.param(source, mode, subs, margin, id=f"M{603 + s * 8 + m * 2 + g}")
    for s, source in enumerate(("bottombar", "letterbox", "pillarbox", "allblack", "open"))
    for m, (mode, subs) in enumerate(MODES)
    for g, margin in enumerate(("", "20%"))
]


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "placed")
@pytest.mark.parametrize(("source", "mode", "subs", "margin"), M9)
def test_placement(
    ffmpeg: str,
    ffprobe: str,
    capsys: pytest.CaptureFixture[str],
    source: str,
    mode: str,
    subs: str,
    margin: str,
) -> None:
    out = f"m9_{source}_{mode}_{margin.strip('%') or 'none'}.mkv"
    margins = ["--margin-bottom", margin] if margin else []
    argv = [
        "convert",
        "-i",
        f"{source}.mp4",
        "--burn-subs",
        str(TRANSCRIPTS / subs),
        "--overlay-mode",
        mode,
        *margins,
        "--video-codec",
        "ffv1",
        "-o",
        out,
        "-y",
    ]
    status = main(argv)
    said = capsys.readouterr().err
    assert status == 0, said
    bar = not margin and source in ("bottombar", "letterbox")
    assert ("black bar" in said) == bar
    what, lo, hi = (
        ("centre", 0.755, 0.80) if bar and source == "bottombar"
        else ("centre", 0.90, 0.94) if bar
        else ("bottom", 0.76, 0.80) if margin
        else ("bottom", 0.92, 0.95)
    )  # fmt: skip
    found = text_band(ffmpeg, ffprobe, out, f"{source}.mp4", 2.2, what)
    assert found is not None, "no subtitle pixels"
    if bar and source == "letterbox" and not lo <= found <= hi:
        # a block taller than the 55 px bar grows upward from where one centred line ends
        bottom = text_band(ffmpeg, ffprobe, out, f"{source}.mp4", 2.2, "bottom")
        assert bottom is not None
        assert 0.93 <= bottom <= 0.98, (
            f"neither centred ({found:.3f}) nor grown from the bar ({bottom:.3f})"
        )
        return
    assert lo <= found <= hi, f"text {what} at {found:.3f} (want {lo}-{hi})"


RESIZES: Final = {
    "none": [],
    "fit": ["-a", "9:16", "-w", "360"],
    "fitauto": ["-a", "9:16", "-w", "360", "--bblur"],
    "cover": ["-a", "1:1", "-w", "360", "-r", "cover"],
    "stretch": ["-a", "1:1", "-w", "360", "-r", "stretch"],
}
M10: Final = [
    pytest.param(source, resize, mode, subs, id=f"M{643 + s * 10 + r * 2 + m}")
    for s, source in enumerate(("bbar", "open10", "bbar180", "bbarsar"))
    for r, resize in enumerate(RESIZES)
    for m, (mode, subs) in enumerate(MODES[:2])
]
_BAR: Final = re.compile(r"black bar under the picture \(([0-9]+) of ([0-9]+) px\)")


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "placed")
@pytest.mark.parametrize(("source", "resize", "mode", "subs"), M10)
def test_placement_and_resize(
    ffmpeg: str,
    ffprobe: str,
    capsys: pytest.CaptureFixture[str],
    source: str,
    resize: str,
    mode: str,
    subs: str,
) -> None:
    sized = RESIZES[resize]
    ref = f"{source}.mp4"
    if sized:  # the same resize without subtitles
        ref = f"m10ref_{source}_{resize}.mp4"
        assert main(["convert", "-i", f"{source}.mp4", *sized, "-o", ref, "-y"]) == 0
        _ = capsys.readouterr()
    out = f"m10_{source}_{resize}_{mode}.mkv"
    argv = [
        "convert",
        "-i",
        f"{source}.mp4",
        "--burn-subs",
        str(TRANSCRIPTS / subs),
        "--overlay-mode",
        mode,
        *sized,
        "--video-codec",
        "ffv1",
        "-o",
        out,
        "-y",
    ]
    status = main(argv)
    said = capsys.readouterr().err
    assert status == 0, said
    bottom = text_band(ffmpeg, ffprobe, out, ref, 2.2, "bottom")
    assert bottom is not None, "no subtitle pixels"
    assert bottom <= 0.995, f"text at the frame's edge ({bottom:.3f})"
    at_margin = 0.92 <= bottom <= 0.95
    reported = _BAR.search(said)
    if reported is None:
        assert at_margin, f"no bar, and the bottom at {bottom:.3f}, not the margin"
        return
    c = 1 - int(reported[1]) / (2 * int(reported[2]))
    centre = text_band(ffmpeg, ffprobe, out, ref, 2.2, "centre")
    assert centre is not None
    assert c - 0.03 <= centre <= c + 0.03 or at_margin, (
        f"neither centred on {c:.4f} ({centre:.3f}) nor lifted to the margin"
    )
