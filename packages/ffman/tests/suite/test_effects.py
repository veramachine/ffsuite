"""The single-pass effects: run.sh's checks, ported (G3). Parameter ids: the bash checks' numbers.

The measured ones (each effect's effect; the CRT's and VHS's figures) wait for
phase 4, with their measuring; the dither's go with it (phase 3's next item).
"""

from pathlib import Path

import pytest

from ffman.cli import main
from ffman.effects.stages import POST, PRE
from tests.support.measures import effect_property, gif_palette
from tests.support.media import ff, raw, tool


@pytest.fixture(scope="module")
def fxs(files: Path, ffmpeg: str) -> Path:
    """run.sh's effects source: 640x360, black with a white band, 10 fps, 2 s, FFV1 and FLAC."""
    band = "color=black:s=640x360:r=10:d=2,drawbox=x=200:y=0:w=240:h=360:c=white:t=fill"
    streams = ["-c:v", "ffv1", "-pix_fmt", "yuv420p", "-c:a", "flac", "-shortest"]
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        band,
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        *streams,
        str(files / "fxs.mkv"),
    )
    return files


def test_every_effect_staged_is_measured_above() -> None:
    """Each effect before or after the subtitles is in EFFECTS, so its size is tested kept:
    the bar is measured on the planned frame (layout.bar_rows), the size these must keep.
    """
    assert set(PRE) | set(POST) <= {spec.split(":")[0] for spec in EFFECTS.values()}


def shape(ffprobe: str, path: str) -> str:
    """Width, height, pixel format and frames counted, as run.sh compared them."""
    entries = "stream=width,height,pix_fmt,nb_read_frames"
    return tool(
        ffprobe,
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        entries,
        "-of",
        "csv=p=0",
        path,
    ).strip()


def rgb(ffmpeg: str, path: str) -> bytes:
    """The first frame, as rgb24 bytes."""
    command = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    return raw(*command)


EFFECTS = {  # run.sh's: each effect, its value
    "blur": "blur",
    "pixelate": "pixelate:8",
    "invert": "invert",
    "ca": "chromatic-aberration:6",
    "halation": "halation",
    "vhs": "vhs",
    "crt": "crt",
    "camcorder": "camcorder",
}


@pytest.fixture(scope="module")
def renders(files: Path, fxs: Path) -> Path:
    """fx0.mkv (the resize alone) and fx_NAME.mkv (with each effect), beside fxs.mkv: made once."""
    source = str(fxs / "fxs.mkv")
    for name, spec in {"": "", **EFFECTS}.items():
        effect = ["--vfx", spec] if spec else []
        out = files / (f"fx_{name}.mkv" if name else "fx0.mkv")
        assert main(["convert", "-i", source, "-w", "640", *effect, "-o", str(out), "-y"]) == 0
    return files


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("blur", id="S223"),
        pytest.param("pixelate", id="S225"),
        pytest.param("invert", id="S227"),
        pytest.param("ca", id="S229"),
        pytest.param("halation", id="S231"),
        pytest.param("vhs", id="S233"),
        pytest.param("crt", id="S235"),
        pytest.param("camcorder", id="camcorder"),
    ],
)
def test_size_pixel_format_and_frames_kept(
    renders: Path, fxs: Path, ffprobe: str, name: str
) -> None:
    assert shape(ffprobe, str(renders / f"fx_{name}.mkv")) == shape(ffprobe, str(fxs / "fxs.mkv"))


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("blur", id="S222"),
        pytest.param("pixelate", id="S224"),
        pytest.param("invert", id="S226"),
        pytest.param("ca", id="S228"),
        pytest.param("halation", id="S230"),
        pytest.param("vhs", id="S232"),
        pytest.param("crt", id="S234"),
    ],
)
def test_each_effect_measured(renders: Path, ffmpeg: str, ffprobe: str, name: str) -> None:
    ok, why = effect_property(
        ffmpeg, ffprobe, name, str(renders / f"fx_{name}.mkv"), str(renders / "fx0.mkv")
    )
    assert ok, why


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "fxs")
def test_effects_alone_need_no_size(capsys: pytest.CaptureFixture[str]) -> None:  # S240
    assert ff(capsys, "-i", "fxs.mkv", "--vfx", "invert", "-o", "inv.mkv", "-y")[0] == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "fxs")
@pytest.mark.parametrize(
    ("argv", "message"),
    [  # surface: the values now go through --vfx, and so do their messages
        pytest.param(["--vfx", "blur:0"], "--vfx blur: must be auto or a sigma above 0", id="S241"),
        pytest.param(
            ["--vfx", "pixelate:1"],
            "--vfx pixelate: must be auto or a block size from 2",
            id="S242",
        ),
        pytest.param(
            ["--vfx", "chromatic-aberration:0"],
            "--vfx chromatic-aberration: must be auto or a shift from 1",
            id="S243",
        ),
        pytest.param(
            ["--add-subs", "s.srt", "--vfx", "vhs"],
            "--add-subs copies the picture and the sound: --vfx",
            id="S246",
        ),
    ],
)
def test_refusals(capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    status, err = ff(capsys, "-i", "fxs.mkv", *argv)
    assert (status, message in err) == (1, True)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_invert_is_exact(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S265
    # on limited-range YUV, negate's 255 - v turned white (235) into 20: grey, not black
    white = [
        "-f",
        "lavfi",
        "-i",
        "color=white:s=320x180:r=10:d=0.5",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "yuv420p",
    ]
    _ = tool(ffmpeg, "-v", "error", "-y", *white, "white.mkv")
    assert ff(capsys, "-i", "white.mkv", "--vfx", "invert", "-o", "whiteinv.mkv", "-y")[0] == 0
    assert max(rgb(ffmpeg, "whiteinv.mkv")) == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_gif_frame_has_256_entries_none_transparent(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S267
    fractal = [
        "-f",
        "lavfi",
        "-i",
        "mandelbrot=s=320x240:r=5",
        "-t",
        "0.4",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",
    ]
    _ = tool(ffmpeg, "-v", "error", "-y", *fractal, "mb.mp4")
    assert ff(capsys, "-i", "mb.mp4", "-w", "320", "-o", "mb.gif", "-y")[0] == 0
    # the table, not the colours a frame shows: those are ffmpeg's arithmetic, the platform's
    # (ubuntu-24.04-arm's frame showed 255); palettegen's reserve_transparent would make one of
    # the 256 transparent
    assert gif_palette(Path("mb.gif")) == (256, False)
