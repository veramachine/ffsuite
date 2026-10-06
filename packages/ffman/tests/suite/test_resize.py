"""run.sh's resize checks, ported (G3): the same inputs, the same expected values.

Each test's parameter id is the bash check it ports. Sources are
made as run.sh made them (conftest.py); frames compared as its ``vmd5`` did.
"""

from fractions import Fraction
from pathlib import Path
from typing import Final

import pytest

from ffman.graph import Labels
from ffman.graph.resize import Picture, bblur_sigma, head
from ffman.graph.sizes import Displayed, Target
from ffman.jobs.convert.options import validate
from ffman.media.probe import Rational, Video
from ffman.options import CONVERT, parse
from ffman.plan.geometry import target_size
from tests.support.media import ff, frames, probe, tool

SOURCE: Final = Displayed(1920, 1080, 1920, 1080, Fraction(1))  # run.sh's planning source


@pytest.mark.parametrize(
    ("width", "height", "aspect", "video", "size"),
    [
        pytest.param(None, None, "9:16", True, (1080, 1920), id="S008"),
        pytest.param(None, None, "16:9", True, (1920, 1080), id="S009"),
        pytest.param(None, None, "1:1", True, (1920, 1920), id="S010"),
        pytest.param(1280, None, None, True, (1280, 720), id="S011"),
        pytest.param(None, 600, None, True, (1066, 600), id="S012"),
        pytest.param(720, None, "9:16", True, (720, 1280), id="S013"),
        pytest.param(1080, 1920, "9:16", True, (1080, 1920), id="S014"),
        pytest.param(1001, None, None, True, (1002, 564), id="S015"),
        pytest.param(1001, None, None, False, (1001, 563), id="S016"),
    ],
)
def test_sizes(
    width: int | None, height: int | None, aspect: str | None, video: bool, size: tuple[int, int]
) -> None:
    target = target_size(SOURCE, video=video, width=width, height=height, aspect=aspect)
    assert target is not None
    assert (target.width, target.height) == size


@pytest.mark.parametrize(
    ("source", "target", "sigma"),
    [
        pytest.param((1920, 1080), (1920, 1080), "31.2", id="S190"),
        pytest.param((868, 600), (1080, 1920), "55.5", id="S191"),
        pytest.param((1080, 1920), (1920, 1080), "55.5", id="S192"),
        pytest.param((1440, 1080), (1920, 1080), "41.6", id="S193"),
        pytest.param((16, 9), (9, 16), "1.0", id="S194"),
    ],
)
def test_auto_sigma(source: tuple[int, int], target: tuple[int, int], sigma: str) -> None:
    shown = Displayed(*source, *source, Fraction(1))
    assert bblur_sigma("auto", shown, Target(*target, None)) == sigma


def test_every_blur_is_gblurs_closest_to_a_gaussian() -> None:  # S195
    o = validate(parse("convert", CONVERT, ["-i", "v.mp4", "-w", "90", "-H", "160", "-b", "7"]))
    video = Video(
        "h264",
        320,
        180,
        None,
        Rational(1, 1),
        None,
        None,
        None,
        None,
        "yuv420p",
        None,
        None,
        None,
        None,
        None,
    )
    picture = Picture(
        Displayed(320, 180, 320, 180, Fraction(1)), Target(90, 160, None), video, moving=True
    )
    assert (
        "gblur=sigma=7:steps=6"
        in head(o.resize_mode, o.bblur, picture, Labels())[0].close("v").render()
    )


# Job-level: ffman convert on files made as run.sh made them.
FIT_160x90: Final = (  # bash's resize_filter for TW=160 TH=90 MODE=fit, a video: the reference
    "scale=160:90:force_original_aspect_ratio=decrease:force_divisible_by=2:"
    "flags=lanczos+accurate_rnd+full_chroma_int,pad=160:90:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("source", "codec", "out", "extra"),
    [
        pytest.param("v.mp4", "h264", "r_h264.mp4", [], id="S018"),
        pytest.param("v265.mp4", "hevc", "r_hevc.mp4", [], id="S019"),
        pytest.param("v9.webm", "vp9", "r_vp9.webm", [], id="S020"),
        pytest.param("v.mp4", "ffv1", "r_ffv1.mkv", ["--video-codec", "ffv1"], id="S021"),
        pytest.param("v.mp4", "av1", "r_av1.mkv", ["--video-codec", "av1"], id="S022"),
    ],
)
def test_codec_kept_frames_bit_exact(
    ffmpeg: str,
    ffprobe: str,
    capsys: pytest.CaptureFixture[str],
    source: str,
    codec: str,
    out: str,
    extra: list[str],
) -> None:
    assert ff(capsys, "-i", source, "-o", out, "-w", "160", *extra, "-y")[0] == 0
    name, pix = probe(ffprobe, out, "stream=codec_name,pix_fmt").split("x")
    reference = frames(ffmpeg, "-i", source, "-map", "0:v:0", "-vf", FIT_160x90, "-pix_fmt", pix)
    written = frames(
        ffmpeg, "-i", out, "-map", "0:v:0", "-fps_mode", "passthrough", "-pix_fmt", pix
    )
    assert (name, written) == (codec, reference)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_audio_copied_bit_exact(ffmpeg: str, capsys: pytest.CaptureFixture[str]) -> None:  # S023
    assert ff(capsys, "-i", "v.mp4", "-o", "r_audio.mp4", "-w", "160", "-y")[0] == 0

    def audio(path: str) -> str:
        copy = ["-map", "0:a", "-c", "copy", "-f", "md5", "-"]
        return tool(ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, *copy)

    assert audio("r_audio.mp4") == audio("v.mp4")


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_fit_and_blur(ffprobe: str, capsys: pytest.CaptureFixture[str]) -> None:  # S024, S025
    assert (
        ff(capsys, "-i", "v.mp4", "-o", "blur.mp4", "-a", "9:16", "-w", "90", "-b", "20", "-y")[0]
        == 0
    )
    assert probe(ffprobe, "blur.mp4", "stream=width,height") == "90x160"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("argv", "message"),
    [
        pytest.param(
            ["-o", "x.mp4", "-w", "1000", "-H", "700", "-a", "16:9"],
            "not the requested --aspect-ratio",
            id="S017",
        ),
        pytest.param(
            ["-o", "x.mp4", "-w", "90", "-r", "cover", "-b", "20"],
            "only applies to --resize-mode fit",
            id="S026",
        ),
        pytest.param(
            ["-o", "x.mp4"], "nothing to do", id="S027"
        ),  # surface: bash said "give --width"
        pytest.param(
            ["-o", "x.mp4", "-w", "90", "--bblur", "soft"],
            "auto or a number from 0 to 1024",
            id="S201",
        ),
    ],
)
def test_refusals(capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    status, err = ff(capsys, "-i", "v.mp4", *argv)
    assert (status, message in err) == (1, True)


@pytest.mark.ffmpeg
def test_in_place(
    here: Path, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S028, S029
    _ = (here / "inplace.mp4").write_bytes((here / "v.mp4").read_bytes())
    assert (
        ff(capsys, "-i", "inplace.mp4", "--in-place", "-w", "160")[0] == 0
    )  # surface: bash's -o inplace.mp4
    assert probe(ffprobe, "inplace.mp4", "stream=width,height") == "160x90"
    assert list(here.rglob(".ffman.*")) == []


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_rotated_and_anamorphic(
    ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-display_rotation",
        "90",
        "-i",
        "v.mp4",
        "-c",
        "copy",
        "rot.mp4",
    )
    assert ff(capsys, "-i", "rot.mp4", "-o", "rot_o.mp4", "-w", "90", "-y")[0] == 0  # S093
    assert probe(ffprobe, "rot_o.mp4", "stream=width,height") == "90x160"  # S094
    lavfi = ["-f", "lavfi", "-i", "testsrc2=s=720x480:r=25:d=0.2", "-vf", "setsar=32/27"]
    _ = tool(
        ffmpeg, "-v", "error", "-y", *lavfi, "-c:v", "libx264", "-pix_fmt", "yuv420p", "anam.mp4"
    )
    assert ff(capsys, "-i", "anam.mp4", "-o", "anam_o.mp4", "-w", "640", "-y")[0] == 0  # S095
    shape = probe(ffprobe, "anam_o.mp4", "stream=width,height,sample_aspect_ratio")
    assert shape == "640x360x1:1"  # S096


@pytest.mark.ffmpeg
def test_a_subtitle_track_is_carried(
    here: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (here / "s.srt").write_text("1\n00:00:00,000 --> 00:00:00,300\nHi\n")
    both = ["-i", "v.mp4", "-i", "s.srt", "-map", "0", "-map", "1", "-c", "copy"]
    _ = tool(ffmpeg, "-v", "error", "-y", *both, "subs.mkv")
    assert ff(capsys, "-i", "subs.mkv", "-o", "subs_o.mkv", "-w", "160", "-y")[0] == 0  # S097
    assert len(probe(ffprobe, "subs_o.mkv", "stream=index", "s").splitlines()) == 1  # S098


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_no_blur_is_allowed_with_cover(capsys: pytest.CaptureFixture[str]) -> None:  # S108
    argv = ["-i", "v.mp4", "-o", "b0.mp4", "-w", "160", "-r", "cover", "-b", "0.00", "-y"]
    assert ff(capsys, *argv)[0] == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(["-b"], id="S196"),
        pytest.param(["--bblur"], id="S197"),
        pytest.param(["--bblur", "auto"], id="S198"),
        pytest.param(["--bblur=auto"], id="S199"),
    ],
)
def test_bblur_auto_is_named(capsys: pytest.CaptureFixture[str], spelling: list[str]) -> None:
    status, err = ff(
        capsys, "-i", "v.mp4", "-o", "ba.mp4", "-a", "9:16", "-w", "90", *spelling, "-y"
    )
    assert (status, "blur auto: sigma 4.6" in err) == (0, True)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_bblur_as_the_last_argument_is_auto(capsys: pytest.CaptureFixture[str]) -> None:  # S200
    status, err = ff(
        capsys, "-i", "v.mp4", "-o", "ba.mp4", "-a", "9:16", "-w", "90", "-y", "--bblur"
    )
    assert (status, err.count("blur auto")) == (0, 1)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_bar_blur_keeps_the_source_format(
    ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S276
    edge = "format=yuv420p,geq=lum='if(lt(X,W/2),60,190)':cb=128:cr=128"
    gray = ["-f", "lavfi", "-i", "color=gray:s=640x360:r=10:d=0.3", "-vf", edge]
    _ = tool(ffmpeg, "-v", "error", "-y", *gray, "-c:v", "ffv1", "-pix_fmt", "yuv420p", "bbl.mkv")
    assert (
        ff(capsys, "-i", "bbl.mkv", "-a", "9:16", "-w", "360", "--bblur", "-o", "bbo.mkv", "-y")[0]
        == 0
    )
    assert probe(ffprobe, "bbo.mkv", "stream=pix_fmt") == "yuv420p"
