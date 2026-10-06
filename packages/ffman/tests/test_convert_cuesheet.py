"""A source FLAC's CUESHEET block, carried into a FLAC output (spec 3.13) -- never made."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.errors import FfmanError
from ffman.jobs.convert import cuesheet
from ffman.media.run import Runner
from tests.support.media import status, tool

CUE = 'FILE "x.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 0\n  TRACK 02 AUDIO\n    INDEX 01 81600\n'


@pytest.fixture(scope="module")
def blocked(ffmpeg: str, metaflac: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three seconds of 48 kHz FLAC with a CUESHEET block of two tracks (sample offsets)."""
    folder = tmp_path_factory.mktemp("cue")
    path = folder / "src.flac"
    _ = tool(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=3:r=48000", str(path))
    cue = folder / "two.cue"
    _ = cue.write_text(CUE)
    _ = tool(metaflac, f"--import-cuesheet-from={cue}", str(path))
    return path


def indexes(metaflac: str, path: Path) -> list[str]:
    shown = tool(metaflac, "--export-cuesheet-to=-", str(path))
    return [line.strip() for line in shown.splitlines() if "INDEX" in line]


def test_the_block_carried(
    capsys: pytest.CaptureFixture[str], blocked: Path, metaflac: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.flac"
    assert main(["convert", "-i", str(blocked), "-o", str(out), "--audio-codec", "flac"]) == 0
    _ = capsys.readouterr()
    assert indexes(metaflac, out) == indexes(metaflac, blocked) == ["INDEX 01 0", "INDEX 01 81600"]


def test_metadatas_chapters_replace_it(
    capsys: pytest.CaptureFixture[str], blocked: Path, metaflac: str, tmp_path: Path
) -> None:
    tags = tmp_path / "m.ffmeta"
    _ = tags.write_text(";FFMETADATA1\ntitle=T\n")
    out = tmp_path / "o.flac"
    assert main(["convert", "-i", str(blocked), "-o", str(out), "--metadata", str(tags)]) == 0
    assert (
        "ffman: the source's CUESHEET block: --metadata's chapters replace it: left out\n"
        in capsys.readouterr().err
    )
    assert (
        status(metaflac, "--export-cuesheet-to=-", str(out)) != 0
    )  # metaflac's no block: left out


def test_dry_run_tells_it_only_when_there_is_one(
    capsys: pytest.CaptureFixture[str], blocked: Path, cd_flac: Path
) -> None:
    assert (
        main(["convert", "-i", str(blocked), "-o", "o.flac", "--audio-codec", "flac", "--dry-run"])
        == 0
    )
    assert "metaflac --import-cuesheet-from=" in capsys.readouterr().out
    assert (
        main(["convert", "-i", str(cd_flac), "-o", "o.flac", "--audio-codec", "flac", "--dry-run"])
        == 0
    )
    assert "metaflac" not in capsys.readouterr().out  # no block: nothing to carry


def test_metaflac_failing_is_refused(
    monkeypatch: pytest.MonkeyPatch, blocked: Path, tmp_path: Path
) -> None:
    def failing(_self: Runner, _argv: Sequence[str]) -> int:
        return 1  # as a full disk, a damaged partial

    monkeypatch.setattr(Runner, "run", failing)
    partial = tmp_path / "p.flac"
    _ = partial.write_bytes(blocked.read_bytes())
    with (
        Runner(dry_run=False, cores=1) as runner,
        pytest.raises(FfmanError, match=r"^metaflac failed \(its message is above\)$"),
    ):
        cuesheet.finisher(runner, str(blocked), replaced=False)(str(partial))


def test_a_flacs_own_comments_read_not_ffmpegs_merge(
    capsys: pytest.CaptureFixture[str], blocked: Path, metaflac: str, tmp_path: Path
) -> None:
    both = tmp_path / "both.flac"
    _ = both.write_bytes(blocked.read_bytes())
    chapters = [
        "CHAPTER000=00:00:00.000",
        "CHAPTER000NAME=One",
        "CHAPTER001=00:00:01.700",
        "CHAPTER001NAME=Two",
    ]
    _ = tool(metaflac, *(f"--set-tag={tag}" for tag in chapters), str(both))
    out = tmp_path / "o.flac"
    assert main(["convert", "-i", str(both), "-o", str(out), "--audio-codec", "flac"]) == 0
    assert capsys.readouterr().err == ""  # no end said: no note
    raw = [
        line
        for line in tool(metaflac, "--export-tags-to=-", str(out)).splitlines()
        if line.startswith("CHAPTER")
    ]
    assert raw == chapters  # ffmpeg reads this FLAC merged with its block's tracks: untitled, moved
    assert indexes(metaflac, out) == indexes(metaflac, blocked)


@pytest.fixture(scope="module")
def plain(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A second of FLAC, no CUESHEET block."""
    path = tmp_path_factory.mktemp("plain") / "plain.flac"
    _ = tool(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-c:a", "flac", str(path))
    return path


def spied(monkeypatch: pytest.MonkeyPatch) -> list[Sequence[str]]:
    """Every launch the runner makes from now, recorded (and made)."""
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
    return launched


def test_no_block_no_metaflac_asked(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, plain: Path, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no metaflac: none needed
    launched = spied(monkeypatch)
    with Runner(dry_run=False, cores=1) as runner:
        cuesheet.finisher(runner, str(plain), replaced=False)(str(tmp_path / "p.flac"))
    assert (capsys.readouterr().err, launched) == (
        "",
        [],
    )  # read by ffman: nothing asked, nothing said


def test_a_block_without_metaflac_noted_the_job_done(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    blocked: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    launched = spied(monkeypatch)
    with Runner(dry_run=False, cores=1) as runner:
        cuesheet.finisher(runner, str(blocked), replaced=False)(str(tmp_path / "p.flac"))
    said = capsys.readouterr().err
    assert (said, launched) == (
        "ffman: the source's CUESHEET block: metaflac not found: left out\n",
        [],
    )


def test_metaflac_failing_to_export_is_refused(
    monkeypatch: pytest.MonkeyPatch, blocked: Path, tmp_path: Path
) -> None:
    imported: list[Sequence[str]] = []

    def failing(_self: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            list(argv), 1, "", ""
        )  # a block is there: its loss no silence

    def run(_self: Runner, argv: Sequence[str]) -> int:
        imported.append(argv)
        return 0

    monkeypatch.setattr(Runner, "capture", failing)
    monkeypatch.setattr(Runner, "run", run)
    with (
        Runner(dry_run=False, cores=1) as runner,
        pytest.raises(FfmanError, match=r"^metaflac failed \(its message is above\)$"),
    ):
        cuesheet.finisher(runner, str(blocked), replaced=False)(str(tmp_path / "p.flac"))
    assert imported == []  # refused at the export: no import of nothing tried


def test_metadata_replacing_it_needs_no_metaflac(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    blocked: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no metaflac: the block is replaced, not carried
    launched = spied(monkeypatch)
    with Runner(dry_run=False, cores=1) as runner:
        cuesheet.finisher(runner, str(blocked), replaced=True)(str(tmp_path / "p.flac"))
    replaced = "ffman: the source's CUESHEET block: --metadata's chapters replace it: left out\n"
    assert (capsys.readouterr().err, launched) == (replaced, [])  # not 'metaflac not found'
