"""matrix.sh's M3, resize outcomes: kind x mode x size, against matrix.sh's oracle (G3).

Ids: the bash checks' numbers, M138 + kind x 35 + mode x 7 + spec. The oracle restates
the planner's rules independently (matrix.sh's oracle_dims); the corner (2,2)
of a red source stays red, but for plain fit into another shape, whose bars
are black where 3 px or more (blurred bars are red again).
"""

from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import raw, tool

pytestmark = pytest.mark.slow
KINDS: Final = (("video", "red.mp4", "mp4"), ("image", "red.png", "png"))
MODES: Final = {
    "fit": ["-r", "fit"],
    "fitblur": ["-r", "fit", "-b", "8"],
    "fitauto": ["-r", "fit", "-b"],  # a bare -b, an option after it (-y): auto
    "cover": ["-r", "cover"],
    "stretch": ["-r", "stretch"],
}
SPECS: Final = (
    "w=240",
    "h=120",
    "w=240,h=240",
    "a=9:16",
    "a=9:16,w=90",
    "a=1:1,h=100",
    "a=4:3,w=240,h=180",
)
FLAGS: Final = {"w": "-w", "h": "-H", "a": "-a"}


def oracle_dims(video: bool, spec: str) -> tuple[int, int]:
    """matrix.sh's oracle: the planner's rules restated (source 320x180, 16:9)."""
    sw, sh = 320, 180
    kv = dict(p.split("=") for p in spec.split(","))
    w = float(kv["w"]) if "w" in kv else None
    h = float(kv["h"]) if "h" in kv else None
    if "a" in kv:
        x, y = kv["a"].split(":")
        r = float(x) / float(y)
        if w and h:
            pass
        elif w:
            h = w / r
        elif h:
            w = h * r
        else:
            long = max(sw, sh)
            w, h = (long, long / r) if r >= 1 else (long * r, long)
    elif w and not h:
        h = w * sh / sw
    elif h and not w:
        w = h * sw / sh
    assert w is not None and h is not None  # noqa: PT018 -- every spec sizes both
    if video:
        return max(2, int(w / 2 + 0.5) * 2), max(2, int(h / 2 + 0.5) * 2)
    return int(w + 0.5), int(h + 0.5)


CASES: Final = [
    pytest.param(kind, source, ext, mode, spec, id=f"M{138 + k * 35 + m * 7 + s}")
    for k, (kind, source, ext) in enumerate(KINDS)
    for m, mode in enumerate(MODES)
    for s, spec in enumerate(SPECS)
]


@pytest.fixture(scope="module")
def reds(files: Path) -> Path:
    """matrix.sh's red.mp4 (lossless, 4:4:4) and red.png, 320x180."""
    gen = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    _ = tool(
        *gen,
        "-i",
        "color=c=red:s=320x180:r=25:d=0.2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",
        "-qp",
        "0",
        str(files / "red.mp4"),
    )
    _ = tool(*gen, "-i", "color=c=red:s=320x180:d=1", "-frames:v", "1", str(files / "red.png"))
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "reds")
@pytest.mark.parametrize(("kind", "source", "ext", "mode", "spec"), CASES)
def test_a_resize_outcome(
    ffmpeg: str, ffprobe: str, kind: str, source: str, ext: str, mode: str, spec: str
) -> None:
    size = [arg for part in spec.split(",") for arg in (FLAGS[part[0]], part[2:])]
    out = f"m3_{kind}_{mode}_{spec.replace(',', '_').replace(':', '-').replace('=', '')}.{ext}"
    assert main(["convert", "-i", source, "-o", out, *size, *MODES[mode], "-y"]) == 0
    want = oracle_dims(kind == "video", spec)
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        out,
    )
    assert shown.strip() == f"{want[0]}x{want[1]}"
    r, g, b = raw(
        ffmpeg,
        "-v",
        "error",
        "-i",
        out,
        "-frames:v",
        "1",
        "-vf",
        "format=rgb24,crop=1:1:2:2",
        "-f",
        "rawvideo",
        "-",
    )
    scale = min(want[0] / 320, want[1] / 180)
    bar = int(max((want[0] - 320 * scale) / 2, (want[1] - 180 * scale) / 2))
    if mode == "fit" and bar >= 3:
        assert r < 30, f"fit bars not black (corner {r},{g},{b})"
    else:
        assert r > 200 and g < 40, f"corner not red ({r},{g},{b})"  # noqa: PT018
