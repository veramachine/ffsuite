"""Subtitle streams kept (spec 3.12): each copied, converted, or left out -- noted."""

from pathlib import Path

import pytest

from ffman.cli import main
from ffman.jobs.convert import output, subtitles
from ffman.media.probe import Media, Subtitle
from ffman.media.run import Runner
from tests.support.media import tool


@pytest.fixture(scope="module")
def two(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """H.264, AAC, an SRT track in English and an ASS track titled Signs, in Matroska."""
    folder = tmp_path_factory.mktemp("subs")
    srt = folder / "s.srt"
    _ = srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nHi\n")
    lavfi = ["-f", "lavfi", "-i", "testsrc=d=1:s=64x48", "-f", "lavfi", "-i", "sine=d=1"]
    maps = ["-map", "0", "-map", "1", "-map", "2", "-map", "3", "-c:v", "libx264", "-c:a", "aac"]
    tags = [
        "-c:s:0",
        "srt",
        "-c:s:1",
        "ass",
        "-metadata:s:s:0",
        "language=eng",
        "-metadata:s:s:1",
        "title=Signs",
    ]
    path = folder / "two.mkv"
    _ = tool(ffmpeg, "-v", "error", *lavfi, "-i", str(srt), "-i", str(srt), *maps, *tags, str(path))
    return path


def codecs(ffprobe: str, path: Path) -> list[str]:
    return tool(
        ffprobe, "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)
    ).split()


@pytest.mark.parametrize(
    ("ext", "job", "streams", "notes"),
    [
        (
            "mp4",
            (),
            ["h264", "aac", "mov_text", "mov_text"],
            ["subrip converted to mov_text", "ass converted to mov_text"],
        ),
        ("mkv", ("-w", "32"), ["h264", "aac", "subrip", "ass"], []),  # held as they are: ASS as ASS
        (
            "webm",
            ("--video-codec", "vp9", "--audio-codec", "opus"),
            ["vp9", "opus", "webvtt", "webvtt"],
            ["subrip converted to webvtt", "ass converted to webvtt"],
        ),
        (
            "avi",
            ("--video-codec", "ffv1"),
            ["ffv1", "aac"],
            [
                "subrip -- a .avi holds it neither as it is nor as text: left out",
                "ass -- a .avi holds it neither as it is nor as text: left out",
            ],
        ),
    ],
)
def test_each_track_as_the_output_holds_it(
    capsys: pytest.CaptureFixture[str],
    two: Path,
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    job: tuple[str, ...],
    streams: list[str],
    notes: list[str],
) -> None:
    out = tmp_path / f"o.{ext}"
    assert main(["convert", "-i", str(two), "-o", str(out), *job]) == 0
    told = [
        line
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("ffman: subtitle track")
    ]
    names = ["subtitle track 1 (eng)", "subtitle track 2 (Signs)"]
    assert told == [f"ffman: {name}: {note}" for name, note in zip(names, notes, strict=False)]
    assert codecs(ffprobe, out) == streams


def test_a_track_left_out_is_named_as_a_reader_knows_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def holds(_runner: Runner, _args: list[str], _ext: str) -> str | None:
        return "held nowhere"  # nothing held: each track noted

    monkeypatch.setattr(output, "holds", holds)
    tracks = (Subtitle("subrip", "eng", "Commentary"), Subtitle(None, None, None))
    media = Media(None, None, tracks, (), None, None)
    with Runner(dry_run=True, cores=1) as runner:
        done = subtitles.kept(runner, media, "in.mkv", "avi")
    why = "a .avi holds it neither as it is nor as text: left out"
    assert done == output.Kept(
        (),
        (
            f"subtitle track 1 (eng, Commentary): subrip -- {why}",
            f"subtitle track 2: unknown -- {why}",
        ),
    )


def test_one_answer_a_codec_and_the_kept_numbered_in_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, str]] = []

    def holds(_runner: Runner, args: list[str], _ext: str) -> str | None:
        index, codec = args[args.index("-map") + 1], args[args.index("-c:s") + 1]
        asked.append((index, codec))
        return (
            None if codec == "mov_text" and index != "0:s:1" else "not held"
        )  # the DVD track: nowhere

    monkeypatch.setattr(output, "holds", holds)
    tracks = (
        Subtitle("subrip", None, None),
        Subtitle("dvd_subtitle", None, None),
        Subtitle("subrip", None, None),
        Subtitle(None, None, None),
    )
    with Runner(dry_run=True, cores=1) as runner:
        done = subtitles.kept(runner, Media(None, None, tracks, (), None, None), "in.mkv", "mp4")
    trials = [index for index, _ in asked]
    assert (
        trials.count("0:s:0"),
        trials.count("0:s:1"),
        trials.count("0:s:2"),
        trials.count("0:s:3"),
    ) == (2, 5, 0, 2)
    maps = [
        "-map",
        "0:s:0",
        "-c:s:0",
        "mov_text",
        "-map",
        "0:s:2",
        "-c:s:1",
        "mov_text",
        "-map",
        "0:s:3",
        "-c:s:2",
        "mov_text",
    ]
    assert done.args == tuple(maps)  # numbered in turn: the one left out leaves no gap
