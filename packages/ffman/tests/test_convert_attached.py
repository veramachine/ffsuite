"""Attached metadata files (spec 3.14): applied where attachments are not held, carried into Matroska."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.media.run import Runner
from tests.support.media import tool

CUE = 'TITLE "Live set"\nFILE "x" WAVE\n  TRACK 01 AUDIO\n    TITLE "Opening"\n    INDEX 01 00:00:00\n'


@pytest.fixture(scope="module")
def attached(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A second of sound in Matroska: a cue, an ffmetadata file, a readme, a font attached."""
    folder = tmp_path_factory.mktemp("attached")
    files = {
        "set.cue": CUE,
        "more.ffmeta": ";FFMETADATA1\ntitle=Other\n",
        "readme.txt": "just notes\n",
        "f.ttf": "\x00font",
    }
    attach: list[str] = []
    for n, (name, text) in enumerate(files.items()):
        _ = (folder / name).write_text(text)
        attach += [
            "-attach",
            str(folder / name),
            f"-metadata:s:t:{n}",
            "mimetype=application/octet-stream",
        ]
    path = folder / "a.mka"
    _ = tool(
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", *attach, "-c:a", "flac", str(path)
    )
    return path


def convert(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    status = main(["convert", *argv])
    return status, [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("ffman: ")
    ]


def test_into_mp4_the_first_that_applies_the_rest_noted(
    capsys: pytest.CaptureFixture[str], attached: Path, ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.mp4"
    status, notes = convert(capsys, "-i", str(attached), "-o", str(out), "--audio-codec", "aac")
    assert status == 0
    assert (
        notes[:3]
        == [
            "ffman: the attached set.cue: its tags and chapters applied, in place of the media's",
            "ffman: the attached more.ffmeta: set.cue applied already: left out",
            "ffman: the attached readme.txt: set.cue applied already: left out",  # no claim of what it is
        ]
    )
    album = tool(
        ffprobe, "-v", "error", "-show_entries", "format_tags=album", "-of", "csv=p=0", str(out)
    ).strip()
    titles = tool(
        ffprobe, "-v", "error", "-show_entries", "chapter_tags=title", "-of", "csv=p=0", str(out)
    ).split()
    assert (album, titles) == ("Live set", ["Opening"])


def test_one_refused_the_next_tried(
    capsys: pytest.CaptureFixture[str], ffmpeg: str, tmp_path: Path
) -> None:
    readme, cue = tmp_path / "readme.txt", tmp_path / "set.cue"
    _ = readme.write_text("just notes\n")
    _ = cue.write_text(CUE)
    source = tmp_path / "r.mka"
    attach = [
        "-attach",
        str(readme),
        "-metadata:s:t:0",
        "mimetype=text/plain",
        "-attach",
        str(cue),
        "-metadata:s:t:1",
        "mimetype=text/plain",
    ]
    _ = tool(
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", *attach, "-c:a", "flac", str(source)
    )
    status, notes = convert(
        capsys, "-i", str(source), "-o", str(tmp_path / "o.mp4"), "--audio-codec", "aac"
    )
    assert status == 0
    assert notes[0].startswith("ffman: the attached readme.txt: ")
    assert notes[0].endswith(": left out")  # refused, with its reason: not a refusal of the job
    assert (
        notes[1]
        == "ffman: the attached set.cue: its tags and chapters applied, in place of the media's"
    )  # tried next, applied


def test_into_matroska_carried_as_they_are(
    capsys: pytest.CaptureFixture[str], attached: Path, ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.mkv"
    status, notes = convert(capsys, "-i", str(attached), "-o", str(out))
    assert (status, notes) == (0, [])
    kinds = tool(
        ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)
    ).split()
    assert kinds.count("attachment") == 4


def test_metadata_given_wins(
    capsys: pytest.CaptureFixture[str], attached: Path, tmp_path: Path
) -> None:
    given = tmp_path / "m.ffmeta"
    _ = given.write_text(";FFMETADATA1\ntitle=Mine\n")
    status, notes = convert(
        capsys,
        "-i",
        str(attached),
        "-o",
        str(tmp_path / "o.mp4"),
        "--audio-codec",
        "aac",
        "--metadata",
        str(given),
    )
    assert status == 0
    assert not any("the attached" in note for note in notes)


def test_a_dump_that_writes_nothing_is_noted(
    capsys: pytest.CaptureFixture[str],
    attached: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    real = Runner.capture

    def capture(self: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if any(arg.startswith("-dump_attachment") for arg in argv):
            return subprocess.CompletedProcess(
                list(argv), 1, "", ""
            )  # as ffmpeg's exit, but no file
        return real(self, argv)

    monkeypatch.setattr(Runner, "capture", capture)
    status, notes = convert(
        capsys, "-i", str(attached), "-o", str(tmp_path / "o.mp4"), "--audio-codec", "aac"
    )
    assert status == 0
    assert "ffman: the attached set.cue: ffmpeg extracted none: left out" in notes


def test_a_refused_job_claims_nothing_applied(
    capsys: pytest.CaptureFixture[str], ffmpeg: str, tmp_path: Path
) -> None:
    cue = tmp_path / "set.cue"
    _ = cue.write_text(CUE)
    source = tmp_path / "v.mkv"
    attach = ["-attach", str(cue), "-metadata:s:t:0", "mimetype=text/plain"]
    lavfi = ["-f", "lavfi", "-i", "testsrc=d=1:s=32x24", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    _ = tool(ffmpeg, "-v", "error", *lavfi, *attach, str(source))
    status, notes = convert(capsys, "-i", str(source), "-o", str(tmp_path / "o.webm"))
    assert status == 1  # WebM holds no H.264: refused before anything applied
    assert len(notes) == 1  # the refusal alone: no note of a file not applied (F6)
    assert notes[0].startswith("ffman: error: a .webm holds no h264 video")
