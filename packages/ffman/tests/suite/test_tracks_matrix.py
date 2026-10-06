"""matrix.sh's M6: a track added to each media kind, into each output, of each kind (G3).

Ids: the bash checks' numbers (M468 + source x 12 + output x 2 + kind). The oracle is
matrix.sh's: which containers carry text subtitles, in which codec; a stream
the target container itself rejects (H.264 into WebM) may fail, with ffmpeg's
own words for it. In place is --in-place now (a surface change: the default
is a new file).
"""

import re
import shutil
from pathlib import Path
from typing import Final

import pytest

from tests.support.media import ff, tool

pytestmark = pytest.mark.slow  # matrix.sh's M6: the matrix check (ffman-next-matrix)

SOURCES: Final = ("v.mp4", "s.mkv", "s.webm", "s.mov", "s.m4a", "s.mp3", "s.mka")
OUTPUTS: Final = ("inplace", "mkv", "mp4", "webm", "mka", "m4a")
KINDS: Final = ("srt", "ass")
REGULAR: Final = Path(__file__).parents[1] / "fixtures" / "transcripts" / "regular.srt"
# matrix.sh's: what a container says when it rejects a stream it cannot hold
REJECTED: Final = re.compile(
    r"not supported|could not find tag|received no packets|Invalid argument|only VP8|incorrect codec",
    re.IGNORECASE,
)
ASS: Final = (
    "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:00.10,0:00:00.30,Default,,0,0,0,,x\n"
)


def wanted(ext: str, kind: str) -> str | None:
    """The oracle: the new track's codec in a container, or None where none can carry it."""
    if ext in ("mkv", "mka"):
        return "ass" if kind == "ass" else "subrip"
    if ext in ("mp4", "m4v", "mov", "m4a", "m4b"):
        return "mov_text"
    return "webvtt" if ext == "webm" else None


CASES: Final = [
    pytest.param(src, out, kind, id=f"M{468 + s * 12 + o * 2 + k}")
    for s, src in enumerate(SOURCES)
    for o, out in enumerate(OUTPUTS)
    for k, kind in enumerate(KINDS)
]


@pytest.fixture(scope="module")
def media(files: Path) -> Path:
    """matrix.sh's v.mp4 and its six kin; k.ass."""
    gen = ["ffmpeg", "-v", "error", "-y"]
    av = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=0.4",
        "-f",
        "lavfi",
        "-i",
        "sine=d=0.4:r=48000",
        "-ac",
        "2",
    ]
    _ = tool(
        *gen,
        *av,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        str(files / "v.mp4"),
    )
    v = str(files / "v.mp4")
    for name, how in (
        ("s.mkv", ["-c", "copy"]),
        ("s.webm", ["-c:v", "libvpx-vp9", "-b:v", "200k", "-c:a", "libopus"]),
        ("s.mov", ["-c", "copy"]),
        ("s.m4a", ["-vn", "-c:a", "copy"]),
        ("s.mp3", ["-vn", "-c:a", "libmp3lame"]),
        ("s.mka", ["-vn", "-c:a", "copy"]),
    ):
        _ = tool(*gen, "-i", v, *how, str(files / name))
    _ = (files / "k.ass").write_text(ASS)
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(("src", "out", "kind"), CASES)
def test_a_track_into_each_container(
    media: Path, ffprobe: str, capfd: pytest.CaptureFixture[str], src: str, out: str, kind: str
) -> None:
    ext = src.rsplit(".", 1)[1]
    given = f"in.{ext}"
    _ = shutil.copyfile(media / src, given)
    subs = str(REGULAR if kind == "srt" else media / "k.ass")
    target, oext = (given, ext) if out == "inplace" else (f"o.{out}", out)
    where = ["--in-place"] if out == "inplace" else ["-o", target, "-y"]
    want = wanted(oext, kind)
    status, said = ff(
        capfd, "-i", given, "--add-subs", subs, *where
    )  # capfd: ffmpeg's own words too
    if want is None:
        assert status == 1
        assert "cannot carry a subtitle track" in said
        return
    if status != 0:  # only a stream the container itself rejects may fail
        assert REJECTED.search(said), said[-300:]
        return
    got = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "csv=p=0",
        target,
    )
    assert got.split()[-1] == want
