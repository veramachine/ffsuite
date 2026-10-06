"""The tools ffman needs (spec 1): looked up before any work, refused by name when missing."""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.errors import FfmanError
from ffman.media.run import Runner, missing
from tests.support.media import tool

FFMPEG_SAID = "ffman: error: ffmpeg not found: install ffmpeg (https://ffmpeg.org)\n"
METADATA = ";FFMETADATA1\ntitle=T\n"


def holding(tmp_path: Path, **tools: str) -> Path:
    """A PATH directory holding ``tools`` (name: target), and nothing else."""
    folder = tmp_path / "bin"
    folder.mkdir()
    for name, target in tools.items():
        (folder / name).symlink_to(target)
    return folder


def test_convert_refused_before_any_work(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ffprobe: str,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PATH", str(holding(tmp_path, ffprobe=ffprobe)))  # ffprobe, no ffmpeg
    launched: list[Sequence[str]] = []
    real_run, real_capture = Runner.run, Runner.capture

    def run(self: Runner, argv: Sequence[str]) -> int:
        launched.append(argv)
        return real_run(self, argv)

    def capture(self: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        launched.append(argv)
        return real_capture(self, argv)

    monkeypatch.setattr(Runner, "run", run)
    monkeypatch.setattr(Runner, "capture", capture)
    source = tmp_path / "v.mp4"
    _ = source.write_bytes(b"not looked at")
    assert main(["convert", "-i", str(source), "-o", str(tmp_path / "o.mkv")]) == 1
    said = capsys.readouterr().err
    assert (said, launched) == (FFMPEG_SAID, [])  # no tool launched, not even the probe


def test_a_tool_missing_at_launch_is_named(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(holding(tmp_path)))
    source = tmp_path / "v.mp4"
    _ = source.write_bytes(b"media, so ffprobe is asked")
    assert main(["meta", "-i", str(source), "-o", str(tmp_path / "v.ffmeta")]) == 1
    assert (
        capsys.readouterr().err
        == "ffman: error: ffprobe not found: install ffmpeg (https://ffmpeg.org)\n"
    )


@pytest.mark.parametrize("command", ["meta", "convert"])
def test_metadata_files_need_no_tool(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    monkeypatch.setenv("PATH", str(holding(tmp_path)))
    given, out = tmp_path / "a.ffmeta", tmp_path / "a.cue"
    _ = given.write_text(METADATA)
    assert main([command, "-i", str(given), "-o", str(out)]) == 0
    assert (
        "nproc" not in capsys.readouterr().err
    )  # no ffmpeg run: the count never asked, never noted
    assert out.is_file()


def test_missing_words_a_tool_with_its_provider_or_alone() -> None:
    assert missing("ffprobe") == "ffprobe not found: install ffmpeg (https://ffmpeg.org)"
    assert missing("metaflac") == "metaflac not found"


def test_a_launch_failing_for_another_file_is_the_environments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def popen(*_args: object, **_kwargs: object) -> subprocess.Popen[str]:
        raise FileNotFoundError(2, "No such file or directory", "elsewhere")

    monkeypatch.setattr(subprocess, "Popen", popen)
    with Runner(dry_run=False, cores=1) as runner, pytest.raises(FileNotFoundError):
        _ = runner.capture(["sh", "-c", "true"])  # sh is found: not a tool missing


def test_a_tool_missing_at_launch_is_refused_by_the_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(holding(tmp_path)))
    with (
        Runner(dry_run=False, cores=1) as runner,
        pytest.raises(FfmanError, match=r"^metaflac not found$"),
    ):
        _ = runner.capture(["metaflac", "--version"])


@pytest.mark.parametrize(
    ("ext", "optimiser"), [("png", "oxipng"), ("jpg", "jpegoptim"), ("gif", "gifsicle")]
)
def test_an_optimiser_missing_is_noted_the_output_kept(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    optimiser: str,
) -> None:
    picture = tmp_path / "p.png"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=red:s=32x32",
        "-frames:v",
        "1",
        str(picture),
    )
    nproc = shutil.which("nproc")
    assert nproc is not None
    folder = holding(
        tmp_path, ffmpeg=ffmpeg, ffprobe=ffprobe, nproc=nproc
    )  # no optimiser: the one studied
    monkeypatch.setenv("PATH", str(folder))
    out = tmp_path / f"o.{ext}"
    assert main(["convert", "-i", str(picture), "-w", "16", "-o", str(out)]) == 0
    said = capsys.readouterr().err
    assert (said, out.is_file()) == (
        f"ffman: {optimiser} not found: the .{ext} written unoptimised\n",
        True,
    )
