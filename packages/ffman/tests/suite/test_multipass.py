"""Dither, the camcorder and datamosh: run.sh's checks, ported (G3). Ids: the bash checks' numbers.

Its measures were numpy's; they are mean absolute differences, computed here in
Python on the same frames.
"""

import re
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest

from ffman.effects.camcorder import clock, script, width
from tests.support.media import ff, raw, tool

NEVER = datetime(2000, 1, 1)  # noqa: DTZ001 -- each clock here is given, or from the file


def one_frame(ffmpeg: str, path: str, *args: str, fmt: str = "rgb24") -> bytes:
    """One frame, raw (the first, unless ``args`` select another)."""
    command = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        *args,
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        fmt,
        "-",
    ]
    return raw(*command)


def colours(ffmpeg: str, path: str) -> int:
    """run.sh's colours: the distinct RGB values of the first frame."""
    frame = one_frame(ffmpeg, path)
    return len({frame[i : i + 3] for i in range(0, len(frame), 3)})


def mean_difference(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


@pytest.fixture(scope="module")
def sources(files: Path, ffmpeg: str) -> Path:
    """run.sh's: g.png, fxs.mkv (the effects'), c4.mp4 and cct.mp4 (the camcorder's), cuts.mkv (the mosh's)."""
    gen = [ffmpeg, "-v", "error", "-y"]
    _ = tool(
        *gen, "-f", "lavfi", "-i", "testsrc2=s=640x360", "-frames:v", "1", str(files / "g.png")
    )
    band = "color=black:s=640x360:r=10:d=2,drawbox=x=200:y=0:w=240:h=360:c=white:t=fill"
    fxs = ["-c:v", "ffv1", "-pix_fmt", "yuv420p", "-c:a", "flac", "-shortest"]
    _ = tool(
        *gen,
        "-f",
        "lavfi",
        "-i",
        band,
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        *fxs,
        str(files / "fxs.mkv"),
    )
    four = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=640x360:r=10:d=4",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ]
    _ = tool(*gen, *four, str(files / "c4.mp4"))
    stamped = ["-c", "copy", "-metadata", "creation_time=2003-07-14T09:05:00Z"]
    _ = tool(*gen, "-i", str(files / "c4.mp4"), *stamped, str(files / "cct.mp4"))
    three = [
        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=20:d=1.5",
        "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=20,trim=duration=1.5",
        "-f", "lavfi", "-i", "rgbtestsrc=s=320x180:r=20:d=1.5,scroll=h=0.01",
        "-f", "lavfi", "-i", "sine=d=4.5",
    ]  # fmt: skip
    joined = [
        "-filter_complex",
        "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "3",
    ]
    _ = tool(*gen, *three, *joined, "-c:v", "ffv1", "-c:a", "flac", str(files / "cuts.mkv"))
    return files


# -- dither
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
def test_dither(ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert ff(capsys, "-i", "g.png", "--vfx", "dither:8", "-o", "d8.png", "-y")[0] == 0
    assert colours(ffmpeg, "d8.png") <= 8  # S236
    assert colours(ffmpeg, "d8.png") == 8  # S266: palettegen keeps no slot for transparency
    assert ff(capsys, "-i", "fxs.mkv", "--vfx", "dither:8", "-o", "d8.gif", "-y")[0] == 0
    assert colours(ffmpeg, "d8.gif") <= 8  # S237
    assert ff(capsys, "-i", "fxs.mkv", "--vfx", "dither", "-o", "dauto.mkv", "-y")[0] == 0
    kinds = tool(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,pix_fmt",
        "-of",
        "csv=p=0",
        "dauto.mkv",
    )
    assert kinds.split() == ["video,yuv420p", "audio"]  # S238


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
def test_every_effect_at_once(capsys: pytest.CaptureFixture[str]) -> None:  # S239
    every = [
        "blur",
        "pixelate",
        "invert",
        "chromatic-aberration",
        "halation",
        "vhs",
        "dither",
        "crt",
    ]
    argv = [a for name in every for a in ("--vfx", name)]
    assert ff(capsys, "-i", "fxs.mkv", *argv, "-o", "all.mkv", "-y")[0] == 0


# -- the camcorder
def stamps(
    creation_time: str | None, date: str | None, hour: str | None, count: int = 4
) -> list[str]:
    """run.sh's clock(): the date-and-time events' text, in order (c4.mp4: 4 s, 640x360)."""
    text = script(clock(creation_time, date, hour, NEVER), Fraction("4.000000"), width(640, 360))
    return [re.sub(r".*\}", "", line) for line in text.splitlines() if "an3" in line][:count]


def test_the_clock_runs_and_midnight_turns_the_date() -> None:  # S248
    assert stamps(None, "1999-12-31", "23:59:58") == [
        r"11:59:58 PM\NDEC. 31 1999",
        r"11:59:59 PM\NDEC. 31 1999",
        r"12:00:00 AM\NJAN. 01 2000",
        r"12:00:01 AM\NJAN. 01 2000",
    ]
    assert stamps(None, "1999:12:31", "23:59:58") == stamps(None, "1999-12-31", "23:59:58")  # S249


def test_the_clock_from_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "UTC")  # as run.sh ran them
    time.tzset()
    try:
        assert stamps("2003-07-14T09:05:00Z", None, None, 1) == [
            r"09:05:00 AM\NJUL. 14 2003"
        ]  # S250
        assert stamps("2003-07-14T09:05:00Z", None, "21:30:00", 1) == [
            r"09:30:00 PM\NJUL. 14 2003"
        ]  # S251
    finally:
        monkeypatch.undo()
        time.tzset()


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
def test_the_camcorder_renders(
    ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ff(capsys, "-i", "c4.mp4", "--vfx", "camcorder", "-o", "cam.mkv", "-y")[0] == 0
    count = ["-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames"]
    assert tool(ffprobe, "-v", "error", *count, "-of", "csv=p=0", "cam.mkv").strip() == "40"  # S256

    def corner(
        path: str,
    ) -> bytes:  # the bottom right, where the clock is: rows 300-349, columns 440-629
        frame = one_frame(ffmpeg, path, fmt="gray")
        return b"".join(frame[r * 640 + 440 : r * 640 + 630] for r in range(300, 350))

    assert mean_difference(corner("cam.mkv"), corner("c4.mp4")) > 10  # S257


# -- datamosh
def frame_n(ffmpeg: str, path: str, n: int) -> bytes:
    return one_frame(ffmpeg, path, "-vf", f"select=eq(n\\,{n})", fmt="gray")


def near(ffmpeg: str, moshed: str, n: int, like: int, unlike: int, factor: float = 4) -> bool:
    """run.sh's near: frame ``n`` is ``factor`` times nearer the source's ``like`` than its ``unlike``."""
    a = frame_n(ffmpeg, moshed, n)
    b, c = frame_n(ffmpeg, "cuts.mkv", like), frame_n(ffmpeg, "cuts.mkv", unlike)
    return mean_difference(a, b) * factor < mean_difference(a, c)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
def test_datamosh(ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert ff(capsys, "-i", "cuts.mkv", "--vfx", "datamosh", "-o", "mosh.mkv", "-y")[0] == 0
    kept = [
        "-count_frames",
        "-show_entries",
        "stream=nb_read_frames:format=duration",
        "-of",
        "csv=p=0",
    ]
    assert tool(ffprobe, "-v", "error", *kept, "mosh.mkv") == tool(
        ffprobe, "-v", "error", *kept, "cuts.mkv"
    )  # S258
    assert near(
        ffmpeg, "mosh.mkv", 31, 29, 31
    )  # S259: after the cut, the old scene's pixels move on
    assert near(ffmpeg, "mosh.mkv", 41, 29, 41, 2)  # S260: still melting 0.55 s later
    assert ff(capsys, "-i", "cuts.mkv", "--vfx", "datamosh:0.5", "-o", "heal.mkv", "-y")[0] == 0
    assert near(ffmpeg, "heal.mkv", 31, 29, 31)  # S261: melted after the cut
    assert near(ffmpeg, "heal.mkv", 41, 41, 29)  # S262: healed 0.55 s later


# -- refusals
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        pytest.param(
            ["-i", "fxs.mkv", "--vfx", "dither:1"],
            "--vfx dither: must be auto or a palette size",
            id="S244",
        ),
        pytest.param(
            ["-i", "fxs.mkv", "--vfx", "dither:300"],
            "--vfx dither: must be auto or a palette size",
            id="S245",
        ),
        pytest.param(
            ["-i", "c4.mp4", "--date", "1999-12-31"],
            "--date and --time are now parameters",
            id="S252",
        ),
        pytest.param(
            ["-i", "c4.mp4", "--vfx", "camcorder:date=2023-02-29"],
            "date must be a real date",
            id="S253",
        ),
        pytest.param(
            ["-i", "c4.mp4", "--vfx", "camcorder:date=1999-12:31"],
            "date must be a real date",
            id="S254",
        ),
        pytest.param(
            ["-i", "c4.mp4", "--vfx", "camcorder:time=24:00:00"], "time must be HH:MM:SS", id="S255"
        ),
        pytest.param(["-i", "g.png", "--vfx", "datamosh"], "needs a moving source", id="S263"),
        pytest.param(
            ["-i", "cuts.mkv", "--vfx", "datamosh:0"], "seconds each mosh lasts", id="S264"
        ),
    ],
)
def test_refusals(capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    status, err = ff(capsys, *argv)
    assert (status, message in err) == (1, True)
