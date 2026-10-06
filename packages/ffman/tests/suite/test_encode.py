"""Encoders, containers, carried tracks and the audio policy: run.sh's and matrix.sh's M4, ported.

The same inputs and the same assertions as the suites (G3); each parameter id is
the bash check it ports.
"""

import itertools
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import ff, frames, probe, tool
from tests.support.processes import marked

CONTAINERS: Final = ("mp4", "mkv", "webm", "mov")
VIDEO_CODECS: Final = ("h264", "hevc", "vp9", "av1", "ffv1")
AUDIO_CODECS: Final = ("copy", "none", "flac", "aac", "opus", "mp3", "vorbis", "alac", "pcm")
AUDIO_WANTED: Final = {"copy": "aac", "none": "", "pcm": "pcm_s24le"}  # what the stream is then

# matrix.sh M4's loops, in its order: M208..M263
M4: Final = [
    *(
        (f"video {vc} -> .{ext}", vc, "none", ext)
        for vc, ext in itertools.product(VIDEO_CODECS, CONTAINERS)
    ),
    *(
        (f"audio {ac} -> .{ext}", "vp9" if ext == "webm" else "h264", ac, ext)
        for ac, ext in itertools.product(AUDIO_CODECS, CONTAINERS)
    ),
]
M4_IDS: Final = [f"M{208 + i}" for i in range(len(M4))]


@pytest.mark.slow  # matrix.sh's M4: the matrix check (ffman-next-matrix)
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("title", "video", "audio", "ext"),
    [pytest.param(*c, id=i) for c, i in zip(M4, M4_IDS, strict=True)],
)
def test_codecs_and_containers(
    ffprobe: str, capsys: pytest.CaptureFixture[str], title: str, video: str, audio: str, ext: str
) -> None:
    out = f"m4.{ext}"
    Path(out).unlink(missing_ok=True)
    status, err = ff(
        capsys,
        "-i",
        "v.mp4",
        "-o",
        out,
        "-w",
        "64",
        "--video-codec",
        video,
        "--audio-codec",
        audio,
        "-y",
    )
    if status != 0:  # the suite's rule: a refusal is fine when it is clean
        assert (status, err.startswith("ffman: error: "), list(Path().glob(".ffman.*"))) == (
            1,
            True,
            [],
        ), title
        return
    if title.startswith("video"):
        assert probe(ffprobe, out, "stream=codec_name") == video, title
    else:
        assert probe(ffprobe, out, "stream=codec_name", "a:0") == AUDIO_WANTED.get(audio, audio), (
            title
        )


@pytest.mark.ffmpeg
def test_across_families_a_notice_not_a_failure(
    here: Path, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S099
    _ = (here / "s.srt").write_text("1\n00:00:00,000 --> 00:00:00,300\nHi\n")
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        "v.mp4",
        "-i",
        "s.srt",
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "subs.mkv",
    )
    status, err = ff(capsys, "-i", "subs.mkv", "-o", "subs_x.mp4", "-w", "160", "-y")
    assert (status, "ffman: subtitle track 1: subrip converted to mov_text\n" in err) == (
        0,
        True,
    )  # a note


@pytest.mark.ffmpeg
def test_a_name_that_looks_like_a_protocol(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # S102
    _ = (here / "part1:intro.mp4").write_bytes((here / "v.mp4").read_bytes())
    assert ff(capsys, "-i", "part1:intro.mp4", "-o", "colon_o.mp4", "-w", "160", "-y")[0] == 0


@pytest.mark.ffmpeg
def test_sigterm_leaves_nothing(here: Path, ffmpeg: str, tmp_path: Path) -> None:  # S104
    lavfi = ["-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=8"]
    _ = tool(
        ffmpeg, "-v", "error", "-y", *lavfi, "-c:v", "libx264", "-pix_fmt", "yuv420p", "zqslow.mp4"
    )
    env = {
        **os.environ,
        "TMPDIR": str(tmp_path),
    }  # its work dir, if any, lands where it can be seen
    command = [
        sys.executable,
        "-m",
        "ffman",
        "convert",
        "-i",
        "zqslow.mp4",
        "-o",
        "zqterm.mp4",
        "-w",
        "630",
    ]
    job = subprocess.Popen(  # noqa: S603 -- ffman itself
        [*command, "--video-codec", "av1", "-y"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    job.send_signal(signal.SIGTERM)
    status = job.wait(timeout=30)
    time.sleep(0.5)
    reading = marked("zqslow")
    assert (status, reading, list(here.rglob(".ffman.*")), list(tmp_path.glob("ffman.*"))) == (
        143,
        [],
        [],
        [],
    )


THREAD_OPTIONS: Final = re.compile(
    r"-filter_(?:complex_)?threads [0-9]+|-threads [0-9]+ -i|-slices [0-9]+|-threads [0-9]+ \S+\.(?:mkv|mp4)$"
)


def threads_for(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cores: int,
    *argv: str,
) -> str:
    """run.sh's threads_for: the thread options the command gave ffmpeg, the core count faked (nproc)."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    nproc = fake / "nproc"
    _ = nproc.write_text(f"#!/bin/sh\necho {cores}\n")
    nproc.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    assert main(["convert", *argv, "-y", "--dry-run"]) == 0  # the command printed, not run
    line = next(line for line in capsys.readouterr().out.splitlines() if "-filter_complex" in line)
    found = [
        re.sub(r" \S+\.(mkv|mp4)$", " out", m)
        for m in (m[0] for m in THREAD_OPTIONS.finditer(line.rstrip()))
    ]
    return "".join(f"{m} " for m in found)


@pytest.fixture(scope="module")
def t720(files: Path, ffmpeg: str) -> Path:
    """run.sh's thread sources: 1280x720, in FFV1 and in H.264."""
    lavfi = ["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=10:d=0.5"]
    _ = tool(ffmpeg, "-v", "error", "-y", *lavfi, "-c:v", "ffv1", str(files / "t720.mkv"))
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        *lavfi,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(files / "t720.mp4"),
    )
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "t720")
@pytest.mark.parametrize(
    ("cores", "source", "out", "expected"),
    [
        pytest.param(1, "t720.mkv", "th.mkv", "", id="S281"),
        pytest.param(8, "t720.mkv", "th.mkv", "-slices 8 ", id="S282"),
        pytest.param(
            32,
            "t720.mkv",
            "th.mkv",
            "-filter_threads 33 -filter_complex_threads 33 -threads 33 -i -slices 32 -threads 33 out ",
            id="S283",
        ),
        pytest.param(
            32,
            "t720.mp4",
            "th.mp4",
            "-filter_threads 33 -filter_complex_threads 33 -threads 33 -i ",
            id="S284",
        ),
    ],
)
def test_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cores: int,
    source: str,
    out: str,
    expected: str,
) -> None:
    assert (
        threads_for(tmp_path, monkeypatch, capsys, cores, "-i", source, "-w", "640", "-o", out)
        == expected
    )


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "t720")
def test_vp9_at_good_is_still_lossless(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S285
    assert (
        ff(capsys, "-i", "t720.mkv", "-w", "640", "-o", "v9.webm", "--video-codec", "vp9", "-y")[0]
        == 0
    )
    assert ff(capsys, "-i", "t720.mkv", "-w", "640", "-o", "v9ref.mkv", "-y")[0] == 0
    vmd5 = ["-map", "0:v:0", "-fps_mode", "passthrough", "-pix_fmt", "yuv420p"]
    assert frames(ffmpeg, "-i", "v9.webm", *vmd5) == frames(ffmpeg, "-i", "v9ref.mkv", *vmd5)
