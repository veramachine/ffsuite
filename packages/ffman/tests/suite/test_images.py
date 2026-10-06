"""Images, the lossless optimisers and GIF: run.sh's checks, ported (G3).

The same inputs and assertions; every reference a literal of bash's own
commands, independent of the code under test. Parameter ids: the bash checks' numbers.
"""

from pathlib import Path
from typing import Final

import pytest

from tests.support.media import ff, probe, tool

FLAGS: Final = "flags=lanczos+accurate_rnd+full_chroma_int"


def fit(width: int, height: int, *, video: bool) -> str:
    """bash's resize_filter, MODE=fit, no blur: the reference's filter."""
    even = ":force_divisible_by=2" if video else ""
    scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease{even}:{FLAGS}"
    return f"{scale},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"


def fsums(ffmpeg: str, path: str, *args: str) -> list[str]:
    """run.sh's fsums (and the images' framemd5): each frame's md5, in order."""
    out = tool(
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, *args, "-f", "framemd5", "-"
    )
    return [
        line.rsplit(",", 1)[-1].strip() for line in out.splitlines() if not line.startswith("#")
    ]


def loopext(path: str) -> str:
    """run.sh's loopext: the NETSCAPE2.0 loop count, or none."""
    data = Path(path).read_bytes()
    i = data.find(b"NETSCAPE2.0")
    return "none" if i < 0 else str(int.from_bytes(data[i + 13 : i + 15], "little"))


@pytest.fixture(scope="module")
def pictures(files: Path, ffmpeg: str) -> Path:
    """run.sh's: img.png (320x180), g.png (640x360), g10.mp4 (320x180, 10 fps, 1 s)."""
    gen = [ffmpeg, "-v", "error", "-y"]
    _ = tool(
        *gen,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:d=1",
        "-frames:v",
        "1",
        str(files / "img.png"),
    )
    _ = tool(
        *gen, "-f", "lavfi", "-i", "testsrc2=s=640x360", "-frames:v", "1", str(files / "g.png")
    )
    ten = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=10:d=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ]
    _ = tool(*gen, *ten, str(files / "g10.mp4"))
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "pictures")
@pytest.mark.parametrize(
    ("ext", "codec", "want"),
    [
        pytest.param("png", "png", "exact", id="S031"),
        pytest.param("webp", "webp", "exact", id="S032"),
        pytest.param("tiff", "tiff", "exact", id="S033"),
        pytest.param("jpg", "mjpeg", "yuvj444p", id="S034"),
        pytest.param("avif", "av1", "yuv444p10le", id="S035"),
    ],
)
def test_images(
    ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str], ext: str, codec: str, want: str
) -> None:
    assert ff(capsys, "-i", "img.png", "-o", f"o.{ext}", "-w", "160", "-y")[0] == 0
    got = probe(ffprobe, f"o.{ext}", "stream=codec_name,pix_fmt", "v:0")
    if want == "exact":
        reference = fsums(ffmpeg, "img.png", "-vf", fit(160, 90, video=False), "-pix_fmt", "rgb24")
        assert (got.split("x")[0], fsums(ffmpeg, f"o.{ext}", "-pix_fmt", "rgb24")) == (
            codec,
            reference,
        )
    else:
        assert got == f"{codec}x{want}"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "pictures")
def test_jpegoptim_keeps_the_pixels_and_never_grows(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ff(capsys, "-i", "g.png", "-w", "320", "-o", "j.jpg", "-y")[0] == 0
    graph = f"[0:v:0]{fit(320, 180, video=False)}[v]"
    jpeg = ["-c:v", "mjpeg", "-q:v", "1", "-pix_fmt", "yuvj444p"]  # bash's image_encoder jpg
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        "g.png",
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-frames:v",
        "1",
        "-update",
        "1",
        *jpeg,
        "jraw.jpg",
    )
    assert fsums(ffmpeg, "j.jpg", "-map", "0:v") == fsums(ffmpeg, "jraw.jpg", "-map", "0:v")  # S210
    assert Path("j.jpg").stat().st_size <= Path("jraw.jpg").stat().st_size  # S211


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "pictures")
def test_gifs(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert ff(capsys, "-i", "g10.mp4", "-w", "160", "-o", "once.gif", "-y")[0] == 0
    palette = "split[ga][gb];[ga]palettegen=stats_mode=single:reserve_transparent=0[gp];[gb][gp]paletteuse=new=1"
    graph = f"[0:v:0]{fit(160, 90, video=True)},{palette}[v]"
    once = ["-c:v", "gif", "-loop", "-1", "-an"]  # bash's gif_encoder, LOOP=once
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        "g10.mp4",
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        *once,
        "graw.gif",
    )
    assert fsums(ffmpeg, "once.gif", "-map", "0:v") == fsums(
        ffmpeg, "graw.gif", "-map", "0:v"
    )  # S212
    assert loopext("once.gif") == "none"  # S213
    assert ff(capsys, "-i", "g10.mp4", "-w", "160", "--loop", "-o", "loop.gif", "-y")[0] == 0
    assert loopext("loop.gif") == "0"  # S214
    assert ff(capsys, "-i", "g10.mp4", "-w", "160", "--loop-reverse", "-o", "rev.gif", "-y")[0] == 0
    fr = fsums(ffmpeg, "rev.gif", "-map", "0:v")
    assert (len(fr), loopext("rev.gif")) == (18, "0")  # S215
    assert all(fr[k] == fr[18 - k] for k in range(10, 18))  # S216


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "pictures")
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        pytest.param(
            ["-i", "g10.mp4", "-w", "160", "--loop", "-o", "x.mp4"], "need a .gif output", id="S217"
        ),
        pytest.param(
            ["-i", "g.png", "-w", "160", "--loop", "-o", "x.gif"], "need a moving source", id="S218"
        ),
    ],
)
def test_loop_refusals(capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    status, err = ff(capsys, *argv)
    assert (status, message in err) == (1, True)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "pictures")
def test_an_image_makes_a_one_frame_gif(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S219
    assert ff(capsys, "-i", "g.png", "-w", "160", "-o", "one.gif", "-y")[0] == 0
    assert len(fsums(ffmpeg, "one.gif", "-map", "0:v")) == 1
