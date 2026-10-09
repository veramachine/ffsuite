import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from fractions import Fraction
from importlib import resources
from pathlib import Path
from typing import Final, cast

import pytest

from ffman.cli import main
from ffman.graph.resize import Picture
from ffman.graph.sizes import Displayed, Target
from ffman.jobs.convert.burn import detection_chain, font_metrics
from ffman.jobs.convert.options import validate
from ffman.jobs.convert.output import encoders
from ffman.media.probe import Video
from ffman.media.run import Runner, note
from ffman.options import CONVERT, parse
from ffman.subs.ass import FONT_FILES, Style
from ffman.subs.layout import CROPDETECT
from tests.support.fonts import font
from tests.support.media import tool

pytestmark = pytest.mark.ffmpeg


def make(ffmpeg: str, *args: str) -> None:
    _ = subprocess.run([ffmpeg, "-v", "error", *args], check=True)  # noqa: S603 -- ffmpeg, checked by the fixture


def streams(ffprobe: str, path: Path) -> list[dict[str, object]]:
    command = [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)]
    out = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603 -- the pinned ffprobe
    return cast("list[dict[str, object]]", json.loads(out.stdout)["streams"])


@pytest.fixture
def clip(tmp_path: Path, ffmpeg: str) -> Path:
    """A second of 640x360 video, stereo audio and a subtitle track, in Matroska."""
    srt = tmp_path / "s.srt"
    _ = srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    path = tmp_path / "clip.mkv"
    lavfi = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=640x360:r=25:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=48000",
    ]
    streams_ = [
        "-map",
        "0",
        "-map",
        "1",
        "-map",
        "2",
        "-ac",
        "2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-c:s",
        "srt",
    ]
    make(ffmpeg, *lavfi, "-i", str(srt), *streams_, "-shortest", str(path))
    return path


def test_a_resize_writes_the_output_and_says_where(
    clip: Path, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["convert", "-i", str(clip), "-w", "321"]) == 0
    out, err = capsys.readouterr()
    written = clip.with_name("clip.ffman.mkv")
    assert out.endswith(f"{written}\n")
    assert "ffman: rounded to 322x180: video dimensions must be even" in err  # 321*360/640 = 180.56
    found = streams(ffprobe, written)
    kinds = {(s["codec_type"], s.get("codec_name")) for s in found}
    assert kinds == {
        ("video", "h264"),
        ("audio", "aac"),
        ("subtitle", "subrip"),
    }  # audio copied, track carried
    assert next(s for s in found if s["codec_type"] == "video")["width"] == 322
    assert not list(clip.parent.glob(".ffman.*"))  # no partial left


def test_the_notes_of_a_resize(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = str(clip.with_name("o.mp4"))
    assert (
        main(["convert", "-i", str(clip), "-w", "320", "-H", "320", "-b", "auto", "-o", out]) == 0
    )
    err = capsys.readouterr().err
    assert "ffman: --bblur auto: sigma 9.2 for 640x360 into 320x320 (set it with --bblur N)" in err
    assert (
        "ffman: subtitle track 1: subrip converted to mov_text\n" in err
    )  # kept, as MP4's text (3.12)


def test_a_dry_run_writes_nothing(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "-i", str(clip), "-w", "320", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "-filter_complex '[0:v:0]scale=320:180:" in out
    assert f"{clip.parent}/.ffman.XXXXXX.mkv" in out
    assert not clip.with_name("clip.ffman.mkv").exists()


def count(ffprobe: str, path: Path) -> str:
    """codec,frames of the first video stream, the frames decoded and counted."""
    entries = [
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,nb_read_frames",
    ]
    command = [ffprobe, "-v", "error", *entries, "-of", "csv=p=0", str(path)]
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603 -- the pinned ffprobe


@pytest.mark.parametrize("loop", [[], ["--loop"], ["--loop-reverse"]])
def test_a_gif(
    clip: Path, ffprobe: str, loop: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    out = clip.with_name("a.gif")
    assert main(["convert", "-i", str(clip), "-w", "160", "-o", str(out), *loop]) == 0
    assert capsys.readouterr().out.endswith(f"{out}\n")
    n = int(count(ffprobe, clip).split(",")[1])
    # n frames; reversed, forward then back without repeating either end: 2n - 2
    assert count(ffprobe, out) == f"gif,{2 * n - 2 if loop == ['--loop-reverse'] else n}"


@pytest.mark.parametrize(("ext", "codec"), [("png", "png"), ("jpg", "mjpeg"), ("webp", "webp")])
def test_an_image(tmp_path: Path, ffmpeg: str, ffprobe: str, ext: str, codec: str) -> None:
    png = tmp_path / "a.png"
    make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", str(png))
    out = tmp_path / f"b.{ext}"
    assert main(["convert", "-i", str(png), "-w", "33", "-o", str(out)]) == 0
    video = next(s for s in streams(ffprobe, out) if s["codec_type"] == "video")
    assert (video["codec_name"], video["width"], video["height"]) == (
        codec,
        33,
        33,
    )  # an image keeps odd sizes


def test_an_image_format_ffman_cannot_write(
    tmp_path: Path, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:
    png = tmp_path / "a.png"
    make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", str(png))
    assert main(["convert", "-i", str(png), "-w", "32", "-o", str(tmp_path / "b.bmp")]) == 1
    assert (
        capsys.readouterr().err
        == "ffman: error: unsupported image output '.bmp' (png, jpg, webp, avif, tiff)\n"
    )


def test_a_failing_optimiser_ends_the_job(
    tmp_path: Path, ffmpeg: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    oxipng = fake / "oxipng"
    _ = oxipng.write_text("#!/bin/sh\nexit 3\n")
    oxipng.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    png = tmp_path / "a.png"
    make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", str(png))
    assert main(["convert", "-i", str(png), "-w", "32", "-o", str(tmp_path / "b.png")]) == 1
    assert capsys.readouterr().err == "ffman: error: oxipng failed (its message is above)\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.png", "bin"]  # no output, no partial


def test_a_dry_run_prints_the_optimiser_too(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "convert",
                "-i",
                str(clip),
                "-w",
                "160",
                "-o",
                str(clip.with_name("a.gif")),
                "--dry-run",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out.splitlines()
    assert printed[-1] == f"gifsicle -b -O3 -- {clip.parent}/.ffman.XXXXXX.gif"


@pytest.mark.parametrize(
    ("argv", "ext"),
    [
        (["--vfx", "pixelate:8"], "mkv"),  # no size: the frame as it is
        (["-w", "320", "--vfx", "crt"], "mkv"),
        (["-w", "160", "--vfx", "vhs", "--vfx", "invert"], "gif"),
    ],
)
def test_effects_render(clip: Path, ffprobe: str, argv: list[str], ext: str) -> None:
    out = clip.with_name(f"fx.{ext}")
    assert main(["convert", "-i", str(clip), *argv, "-o", str(out), "-y"]) == 0
    video = next(s for s in streams(ffprobe, out) if s["codec_type"] == "video")
    assert video["codec_name"] == {"mkv": "h264", "gif": "gif"}[ext]


def test_encoders_honour_ffman_no_fdk(monkeypatch: pytest.MonkeyPatch) -> None:
    with Runner(dry_run=True, cores=1) as runner:
        found = encoders(runner)
        monkeypatch.setenv("FFMAN_NO_FDK", "1")
        assert encoders(runner) == found - {"libfdk_aac"}
    assert "libx264" in found


def test_note(capsys: pytest.CaptureFixture[str]) -> None:
    note("hello")
    assert capsys.readouterr().err == "ffman: hello\n"


@pytest.mark.parametrize("spec", ["datamosh:0.5", "camcorder:date=2020-02-29,time=23:59:30"])
def test_mosh_and_camcorder_render(tmp_path: Path, ffmpeg: str, ffprobe: str, spec: str) -> None:
    # a cut at 1 s (black to bars), so the mosh has something to melt
    cut = tmp_path / "cut.mkv"
    two = [
        "-f",
        "lavfi",
        "-i",
        "color=black:s=320x180:r=10:d=1",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=10:d=1",
    ]
    make(
        ffmpeg,
        *two,
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        str(cut),
    )
    out = tmp_path / "out.mkv"
    assert main(["convert", "-i", str(cut), "--vfx", spec, "--vfx", "vhs", "-o", str(out)]) == 0
    assert (
        next(s for s in streams(ffprobe, out) if s["codec_type"] == "video")["codec_name"] == "h264"
    )


def test_a_dither_to_eight_colours(tmp_path: Path, ffmpeg: str) -> None:
    png = tmp_path / "a.png"
    make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", str(png))
    out = tmp_path / "d8.png"
    assert main(["convert", "-i", str(png), "--vfx", "dither:8", "-o", str(out)]) == 0
    raw = [ffmpeg, "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    pixels = subprocess.run(raw, capture_output=True, check=True).stdout  # noqa: S603 -- the pinned ffmpeg
    assert len({pixels[i : i + 3] for i in range(0, len(pixels), 3)}) <= 8


def test_a_mosh_without_a_cut_says_so(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = clip.with_name("still.mkv")
    assert main(["convert", "-i", str(clip), "--vfx", "datamosh", "-o", str(out), "--dry-run"]) == 0
    assert "ffman: --datamosh: no scene cut found, so nothing melts" in capsys.readouterr().err


def probe_video() -> Video:
    return Video(
        "h264",
        640,
        360,
        None,
        None,
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


@pytest.mark.parametrize("extra", [["-b", "20"], ["--vfx", "invert"], []])
def test_the_bar_is_found_on_the_picture_as_ffmpeg_reads_it(ffmpeg: str, extra: list[str]) -> None:
    # bash's det: the head without its input label, -vf's; a blurred-bars head is several chains
    o = validate(
        parse("convert", CONVERT, ["-i", "a.mp4", "-a", "9:16", "--burn-subs", "s.srt", *extra])
    )
    picture = Picture(
        Displayed(640, 360, 640, 360, Fraction(1)),
        Target(360, 640, None),
        probe_video(),
        moving=True,
    )
    chain = detection_chain(o, picture)
    assert chain.endswith(",")
    assert "[0:v:0]" not in chain
    assert "negate" not in chain  # the resize alone: an effect recolours the bar, not moves it
    assert "gblur" not in chain  # a blurred bar filled black: detection sees it
    source = ["-f", "lavfi", "-i", "testsrc2=s=640x360:r=5:d=1"]
    ran = subprocess.run(  # noqa: S603 -- the pinned ffmpeg
        [ffmpeg, "-v", "error", *source, "-vf", f"{chain}{CROPDETECT}", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr


SRT = str(Path(__file__).parent / "fixtures" / "transcripts" / "regular.srt")


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        (["-w", "181"], "ffman: rounded to 182x102: video dimensions must be even"),
        (
            ["-a", "9:16", "-b"],
            "ffman: --bblur auto: sigma 18.5 for 640x360 into 360x640 (set it with --bblur N)",
        ),
        (["--font-size", "1000"], "wrap past the top of the frame at --font-size 1000"),
    ],
)
def test_a_burn_says_what_it_did(
    clip: Path, capsys: pytest.CaptureFixture[str], extra: list[str], said: str
) -> None:
    out = clip.with_name("b.mkv")
    assert (
        main(["convert", "-i", str(clip), "--burn-subs", SRT, *extra, "-o", str(out), "--dry-run"])
        == 0
    )
    assert said in capsys.readouterr().err


def test_a_burn_of_ones_own_ass(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    own = clip.with_name("own.ass")
    _ = own.write_text("[Script Info]\nScriptType: v4.00+\n")
    out = clip.with_name("b.mkv")
    assert (
        main(["convert", "-i", str(clip), "--burn-subs", str(own), "-o", str(out), "--dry-run"])
        == 0
    )
    printed = capsys.readouterr()
    assert "subs.ass" in printed.out + printed.err  # copied, burned as it is
    assert "black bar" not in printed.err  # its own placement: no detection


def test_a_burn_refuses(
    clip: Path,
    tmp_path: Path,
    ffmpeg: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    png = tmp_path / "a.png"
    make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=64x64", "-frames:v", "1", str(png))
    assert main(["convert", "-i", str(png), "--burn-subs", SRT]) == 1
    assert f"overlay needs a video, not an image: {png}" in capsys.readouterr().err
    monkeypatch.setenv("FFMAN_FONTS_DIR", "/fonts/with space")
    assert (
        main(
            [
                "convert",
                "-i",
                str(clip),
                "--burn-subs",
                SRT,
                "-o",
                str(tmp_path / "b.mkv"),
                "--dry-run",
            ]
        )
        == 1
    )
    said = "FFMAN_FONTS_DIR has characters ffmpeg's filter syntax would split on: /fonts/with space"
    assert said in capsys.readouterr().err


GAPS = str(Path(__file__).parent / "fixtures" / "transcripts" / "wx-gaps.json")


@pytest.mark.parametrize(
    ("track", "out_ext", "copied"),
    [
        ("own.ass", "mkv", ["-c:s:1", "ass"]),  # styled, where Matroska can keep it
        ("own.ass", "mp4", ["-c:s", "mov_text"]),  # across families: every subtitle converted
        (SRT, "mp4", ["-c:s", "mov_text"]),
    ],
)
def test_a_track_is_added(
    clip: Path, capsys: pytest.CaptureFixture[str], track: str, out_ext: str, copied: list[str]
) -> None:
    if track == "own.ass":
        own = clip.with_name("own.ass")
        _ = own.write_text("[Script Info]\nScriptType: v4.00+\n")
        track = str(own)
    out = clip.with_name(f"t.{out_ext}")
    assert main(["convert", "-i", str(clip), "--add-subs", track, "-o", str(out), "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert " ".join(copied) in printed
    assert "-map 1:s:0" in printed


def test_a_tracks_notes_are_passed_on(clip: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = clip.with_name("t.mkv")
    assert main(["convert", "-i", str(clip), "--add-subs", GAPS, "-o", str(out), "--dry-run"]) == 0
    assert "ffman: 4 words had no usable time of their own" in capsys.readouterr().err


@pytest.fixture
def compliant(tmp_path: Path, ffmpeg: str) -> Path:
    """A second of 25 fps video, AAC LC 48 kHz stereo: what YouTube asks for."""
    path = tmp_path / "yt.mp4"
    av = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=48000",
    ]
    make(
        ffmpeg,
        *av,
        "-ac",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        str(path),
    )
    return path


def test_youtube_copies_compliant_audio(
    compliant: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = compliant.with_name("up.mp4")
    assert main(["convert", "-i", str(compliant), "-p", "yt", "-o", str(out), "--dry-run"]) == 0
    said = capsys.readouterr()
    assert "ffman: H.264 High 320x180 @ 25.000000 fps, GOP 12, 1000 kbps two-pass" in said.err
    first, second = [line for line in said.out.splitlines() if " -pass " in line]
    assert " -pass 1 " in first
    assert "-an -f null /dev/null" in first
    assert "-map 0:a:0" in second
    assert "-c:a copy" in second


def test_youtube_normalises_other_audio(
    compliant: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = compliant.with_name("up.mp4")
    argv = ["convert", "-i", str(compliant), "-p", "yt", "--normalize", "-o", str(out), "--dry-run"]
    monkeypatch.delenv("FFMAN_NORMALIZE_HOME", raising=False)  # ffman's own presets
    assert main(argv) == 0
    own = resources.files("ffman") / "normalize"  # quoted if its path needs it (a space)
    assert (
        shlex.join(["env", f"XDG_CONFIG_HOME={own}", "ffmpeg-normalize"]) in capsys.readouterr().out
    )
    home = tmp_path / "home"
    monkeypatch.setenv("FFMAN_NORMALIZE_HOME", str(home))
    assert main(argv) == 1
    assert (
        "missing ffmpeg-normalize preset youtube-aac" in capsys.readouterr().err
    )  # the ffmpeg here has FDK or not
    presets = home / "ffmpeg-normalize" / "presets"
    presets.mkdir(parents=True)
    for preset in ("youtube-aac", "youtube-aac-native"):
        _ = (presets / f"{preset}.json").write_text("{}")
    assert main(argv) == 0
    said = capsys.readouterr()
    assert "ffman: normalising audio (aac 48000 Hz 2 ch) with preset youtube-aac" in said.err
    assert shlex.join(["env", f"XDG_CONFIG_HOME={home}", "ffmpeg-normalize"]) in said.out
    assert "-map 1:a:0" in said.out


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_a_failed_normalisation_is_refused(
    compliant: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub = tmp_path / "bin"
    stub.mkdir()
    _ = (stub / "ffmpeg-normalize").write_text("#!/bin/sh\nexit 3\n")
    (stub / "ffmpeg-normalize").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}:{os.environ['PATH']}")
    out = compliant.with_name("up.mp4")
    assert main(["convert", "-i", str(compliant), "-p", "yt", "--normalize", "-o", str(out)]) == 1
    assert "ffman: error: ffmpeg-normalize failed" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_normalisation_without_ffmpeg_normalize_is_refused_as_today(
    compliant: Path,
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],  # env is a child: its line is the descriptor's
) -> None:
    env = shutil.which("env")
    assert env is not None
    folder = tmp_path / "bin"
    folder.mkdir()
    for name, target in (
        ("ffmpeg", ffmpeg),
        ("ffprobe", ffprobe),
        ("env", env),
    ):  # no ffmpeg-normalize
        (folder / name).symlink_to(target)
    monkeypatch.setenv("PATH", str(folder))
    out = tmp_path / "up.mp4"
    assert main(["convert", "-i", str(compliant), "-p", "yt", "--normalize", "-o", str(out)]) == 1
    said = capfd.readouterr().err
    assert said.endswith("ffman: error: ffmpeg-normalize failed\n")
    # its cause, not a failure of its own: env's line names it (GNU's and BusyBox's words differ)
    assert any(
        "ffmpeg-normalize" in line and "No such file or directory" in line
        for line in said.splitlines()
    )
    assert not out.exists()  # left as it is used today: re-assessed at NixOS 26.11


def test_youtube_without_sound_and_its_container(
    tmp_path: Path, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:
    silent = tmp_path / "silent.mp4"
    make(
        ffmpeg,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(silent),
    )
    assert (
        main(
            ["convert", "-i", str(silent), "-p", "yt", "-o", str(tmp_path / "up.mp4"), "--dry-run"]
        )
        == 0
    )
    assert "ffman: no audio stream: the upload will be silent" in capsys.readouterr().err
    assert main(["convert", "-i", str(silent), "-p", "yt", "-o", str(tmp_path / "up.mkv")]) == 1
    assert "YouTube's container is MP4: --output must end in .mp4" in capsys.readouterr().err


def test_a_youtube_upload_is_made(compliant: Path, ffprobe: str) -> None:
    out = compliant.with_name("up.mp4")
    assert main(["convert", "-i", str(compliant), "-p", "yt", "-o", str(out)]) == 0
    kinds = [(s["codec_type"], s["codec_name"]) for s in streams(ffprobe, out)]
    assert kinds == [("video", "h264"), ("audio", "aac")]


def test_a_normalisation_refused_says_nothing_first(
    compliant: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # bash checked the presets before its note: a refusal alone
    monkeypatch.setenv("FFMAN_NORMALIZE_HOME", str(tmp_path))  # none in it
    out = compliant.with_name("up.mp4")
    assert (
        main(
            [
                "convert",
                "-i",
                str(compliant),
                "-p",
                "yt",
                "--normalize",
                "-o",
                str(out),
                "--dry-run",
            ]
        )
        == 1
    )
    said = capsys.readouterr().err.splitlines()
    preset = r"youtube-aac(-native)?"  # the ffmpeg here has FDK or not
    assert len(said) == 1, said
    assert re.fullmatch(
        rf"ffman: error: missing ffmpeg-normalize preset {preset} in {re.escape(str(tmp_path))}",
        said[0],
    )


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every process ffman starts past its setup, probes included, and its work directory, in order.

    Each still runs; the work directory is recorded as it is made -- ffman removes it on exit.
    """
    seen: list[str] = []
    run, capture, mkdtemp = Runner.run, Runner.capture, tempfile.mkdtemp

    def run_(self: Runner, argv: Sequence[str]) -> int:
        seen.append(" ".join(argv[:3]))
        return run(self, argv)

    def capture_(self: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        seen.append(" ".join(argv[:3]))
        return capture(self, argv)

    def mkdtemp_(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,  # noqa: A002 -- tempfile's own name: ffman passes it by keyword
    ) -> str:
        seen.append(f"a work directory ({prefix}*)")
        return mkdtemp(suffix, prefix, dir)

    monkeypatch.setattr(Runner, "run", run_)
    monkeypatch.setattr(Runner, "capture", capture_)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp_)
    return seen


@pytest.fixture
def existing(clip: Path) -> Path:
    """An output that exists: a copy of the clip."""
    path = clip.parent / "exists.mkv"
    _ = shutil.copy(clip, path)
    return path


DECIDING: Final = ("ffprobe ", "ffmpeg -hide_banner -encoders")  # what a decision may ask


@pytest.mark.parametrize(
    ("case", "message"),
    [  # what ran first, before: 9 ffmpeg (F6); the bar's detection; the same; the mosh
        # render; the transcript written
        ("burn-image", "overlay output must be a video"),
        ("burn-exists", "output exists"),
        ("burn-fonts", "FFMAN_FONTS_DIR has characters ffmpeg's filter syntax would split on"),
        ("mosh-no-lossless", "no lossless encoder for video codec 'mpeg4'"),
        ("attach-exists", "output exists"),
    ],
)
def test_a_refusal_comes_before_any_work(
    case: str,
    message: str,
    clip: Path,
    existing: Path,
    ffmpeg: str,
    started: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refusals come from the options and the probe: nothing runs, nothing is written, first."""
    srt = clip.parent / "s.srt"
    avi = clip.parent / "m4v.avi"
    if case == "mosh-no-lossless":  # a codec with no lossless encoder
        make(ffmpeg, "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=1", "-c:v", "mpeg4", str(avi))
    burn = ["-i", str(clip), "--burn-subs", str(srt)]
    argv = {
        "burn-image": [*burn, "--vfx", "datamosh", "-o", str(clip.parent / "x.png")],
        "burn-exists": [*burn, "-o", str(existing)],
        "burn-fonts": [*burn, "-o", str(clip.parent / "x.mkv")],
        "mosh-no-lossless": [
            "-i",
            str(avi),
            "-w",
            "160",
            "--vfx",
            "datamosh",
            "-o",
            str(clip.parent / "x.mkv"),
        ],
        "attach-exists": ["-i", str(clip), "--add-subs", str(srt), "-o", str(existing)],
    }[case]
    if case == "burn-fonts":
        monkeypatch.setenv("FFMAN_FONTS_DIR", "/fonts:here")
    assert main(["convert", *argv]) == 1
    assert message in capsys.readouterr().err
    assert [s for s in started if not s.startswith(DECIDING)] == []


@pytest.mark.parametrize(
    ("case", "message"),
    [  # bash: "a . file cannot carry a subtitle track"; then the transcript's, twice
        ("attach-no-extension", "output needs an extension (it selects the container)"),
        ("burn-exists-bad-transcript", "output exists"),
        ("burn-image-bad-transcript", "overlay output must be a video"),
    ],
)
def test_the_options_refusal_comes_before_the_transcripts(
    case: str, message: str, clip: Path, existing: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The options' and the probe's refusals first, the transcript's after (bash: its order's)."""
    empty = clip.parent / "empty.srt"
    _ = empty.write_text("")
    argv = {
        "attach-no-extension": [
            "--add-subs",
            str(clip.parent / "s.srt"),
            "-o",
            str(clip.parent / "x"),
        ],
        "burn-exists-bad-transcript": ["--burn-subs", str(empty), "-o", str(existing)],
        "burn-image-bad-transcript": ["--burn-subs", str(empty), "-o", str(clip.parent / "x.png")],
    }[case]
    assert main(["convert", "-i", str(clip), *argv]) == 1
    assert message in capsys.readouterr().err


def test_the_font_measured_is_the_one_shipped(tmp_path: Path) -> None:
    """The fonts folder's Plex for the style's weight; None -- the lines estimated -- else."""
    _ = (tmp_path / FONT_FILES[False]).write_bytes(font({"a": 500}))
    _ = (tmp_path / FONT_FILES[True]).write_bytes(b"not a font")
    measured = font_metrics(str(tmp_path), Style())  # plain: the regular
    assert measured is not None
    assert measured.advances == {ord("a"): 500}
    assert font_metrics(str(tmp_path), Style("chunk-word")) is None  # the bold: unreadable
    assert font_metrics("", Style()) is None  # no fonts handed to libass
    assert font_metrics(str(tmp_path / "elsewhere"), Style()) is None  # no file there
    # another font: libass finds it, ffman cannot measure it; Plex in any case, as libass matches
    assert font_metrics(str(tmp_path), Style(font="DejaVu Sans")) is None
    assert font_metrics(str(tmp_path), Style(font="ibm plex sans")) is not None


@pytest.fixture
def youtube_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """FFMAN_NORMALIZE_HOME with YouTube's two presets: enough for a --dry-run."""
    home = tmp_path / "home"
    presets = home / "ffmpeg-normalize" / "presets"
    presets.mkdir(parents=True)
    for preset in ("youtube-aac", "youtube-aac-native"):
        _ = (presets / f"{preset}.json").write_text("{}")
    monkeypatch.setenv("FFMAN_NORMALIZE_HOME", str(home))
    return home


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_youtube_notes_a_tag_mp4_holds_not(
    compliant: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tags = tmp_path / "m.ffmeta"
    _ = tags.write_text(";FFMETADATA1\ntitle=T\nMOOD=calm\n")
    argv = [
        "convert",
        "-i",
        str(compliant),
        "-p",
        "yt",
        "-o",
        str(tmp_path / "up.mp4"),
        "--metadata",
        str(tags),
        "--dry-run",
    ]
    assert main(argv) == 0
    assert "ffman: the tags MOOD: a .mp4 holds them not: left out\n" in capsys.readouterr().err


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_youtube_carries_subtitles(
    compliant: Path,
    ffmpeg: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    srt = tmp_path / "s.srt"
    _ = srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nHi\n")
    subbed = tmp_path / "subbed.mkv"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(compliant),
        "-i",
        str(srt),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        str(subbed),
    )
    assert (
        main(
            ["convert", "-i", str(subbed), "-p", "yt", "-o", str(tmp_path / "up.mp4"), "--dry-run"]
        )
        == 0
    )
    said = capsys.readouterr()
    assert "-map 0:s:0 -c:s:0 mov_text" in said.out  # the final pass, as every flow (3.12)
    assert "ffman: subtitle track 1: subrip converted to mov_text\n" in said.err


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_youtube_notes_attachments_mp4_holds_not(
    compliant: Path,
    ffmpeg: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    font = tmp_path / "f.ttf"
    _ = font.write_bytes(b"\x00\x01an attachment's bytes")
    attached = tmp_path / "attached.mkv"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(compliant),
        "-attach",
        str(font),
        "-metadata:s:t:0",
        "mimetype=font/ttf",
        "-map",
        "0",
        "-c",
        "copy",
        str(attached),
    )
    assert (
        main(
            [
                "convert",
                "-i",
                str(attached),
                "-p",
                "yt",
                "-o",
                str(tmp_path / "up.mp4"),
                "--dry-run",
            ]
        )
        == 0
    )
    assert (
        "ffman: attachments are not carried into .mp4 (another container family)\n"
        in capsys.readouterr().err
    )


@pytest.mark.usefixtures("youtube_home")  # FFMAN_NORMALIZE_HOME set
def test_youtube_keeps_a_cover(
    compliant: Path, ffmpeg: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    png = tmp_path / "c.png"
    _ = tool(
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=red:s=16x16", "-frames:v", "1", str(png)
    )
    covered = tmp_path / "covered.mp4"
    maps = ["-map", "0", "-map", "1", "-c", "copy", "-disposition:v:1", "attached_pic"]
    _ = tool(ffmpeg, "-v", "error", "-i", str(compliant), "-i", str(png), *maps, str(covered))
    assert (
        main(
            ["convert", "-i", str(covered), "-p", "yt", "-o", str(tmp_path / "up.mp4"), "--dry-run"]
        )
        == 0
    )
    said = capsys.readouterr()
    assert (
        "-map 0:v:1 -c:v:1 copy -disposition:v:1 attached_pic" in said.out
    )  # the picture's options v:0 alone
    assert "the cover" not in said.err
