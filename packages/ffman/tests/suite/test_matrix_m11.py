"""matrix.sh's M11, effects x outputs: every effect, and all of them, into each output (G3).

Ids: the bash checks' numbers, M683 + effect x 4 + output. Each runs and keeps the
frame size (and, into video, the pixel format); a datamosh on a still image is
refused -- it has no cut to melt.
"""

from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import tool

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
EVERY: Final = [
    "blur",
    "pixelate",
    "invert",
    "chromatic-aberration",
    "halation",
    "vhs",
    "dither",
    "crt",
]
EFFECTS: Final = {  # matrix.sh's effect flags, as --vfx (the harness's mapping: checked by its test)
    "--blur": ["blur"],
    "--blur 3": ["blur:3"],
    "--pixelate": ["pixelate"],
    "--pixelate 4": ["pixelate:4"],
    "--invert": ["invert"],
    "--chromatic-aberration": ["chromatic-aberration"],
    "--chromatic-aberration 3": ["chromatic-aberration:3"],
    "--halation": ["halation"],
    "--vhs": ["vhs"],
    "--dither": ["dither"],
    "--dither 8": ["dither:8"],
    "--crt": ["crt"],
    "--camcorder": ["camcorder"],
    "--camcorder --date 1999:12:31 --time 23:59:59": ["camcorder:date=1999:12:31,time=23:59:59"],
    "--datamosh": ["datamosh"],
    "--datamosh 0.3": ["datamosh:0.3"],
    "--blur --pixelate --invert --chromatic-aberration --halation --vhs --dither --crt": EVERY,
    # the camcorder last: its stamp is drawn over the rest (as the harness adapts it, G1-proven)
    "--blur --pixelate --invert --chromatic-aberration --halation --camcorder --datamosh --vhs --dither --crt": [
        *EVERY[:5], "datamosh", *EVERY[5:], "camcorder",
    ],
}  # fmt: skip
OUTPUTS: Final = (
    ("fxv.mp4", "m11.mp4", False),
    ("fxi.png", "m11.png", False),
    ("fxv.mp4", "m11.mkv", True),
    ("fxv.mp4", "m11.gif", False),
)
CASES: Final = [
    pytest.param(old, source, out, burn, id=f"M{683 + e * 4 + o}")
    for e, old in enumerate(EFFECTS)
    for o, (source, out, burn) in enumerate(OUTPUTS)
]


@pytest.fixture(scope="module")
def sources(files: Path) -> Path:
    """matrix.sh's fxv.mp4 (320x180, 10 fps, 1 s, with sound) and fxi.png."""
    av = ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=1", "-f", "lavfi", "-i", "sine=d=1"]
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        *av,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(files / "fxv.mp4"),
    )
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180",
        "-frames:v",
        "1",
        str(files / "fxi.png"),
    )
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
@pytest.mark.parametrize(("old", "source", "out", "burn"), CASES)
def test_an_effect_into_an_output(
    ffprobe: str, capsys: pytest.CaptureFixture[str], old: str, source: str, out: str, burn: bool
) -> None:
    target = f"m11_{list(EFFECTS).index(old)}_{out}"
    effects = [arg for spec in EFFECTS[old] for arg in ("--vfx", spec)]
    subs = ["--burn-subs", str(TRANSCRIPTS / "regular.srt")] if burn else []
    status = main(["convert", "-i", source, "-o", target, "-y", *subs, *effects])
    said = capsys.readouterr().err
    if "datamosh" in old and source == "fxi.png":  # a still image has no cut to melt
        assert status == 1
        assert "needs a moving source" in said
        return
    assert status == 0, said
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,pix_fmt",
        "-of",
        "csv=p=0",
        target,
    )
    width, height, pix_fmt = shown.strip().split(",")
    assert f"{width}x{height}" == "320x180"
    if target.endswith((".mp4", ".mkv")):
        assert pix_fmt == "yuv420p", "pixel format not kept"
