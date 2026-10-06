"""--metadata FILE (spec 3.10): a metadata file's tags and chapters applied to a media output."""

from fractions import Fraction
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.jobs.convert.options import validate
from ffman.options import CONVERT, parse
from ffman.plan.flows import Flow, select_flow
from ffman.plan.streams import kept_metadata
from tests.support.media import metadata_seen, tool

ORIGINAL = (
    ";FFMETADATA1\ntitle=Original\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=OldA\n"
)


@pytest.fixture(scope="module")
def film(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two seconds of picture and sound: its own title and chapter, its sound in French."""
    folder = tmp_path_factory.mktemp("film")
    tags = folder / "orig.ffmeta"
    _ = tags.write_text(ORIGINAL)
    path = folder / "film.mkv"
    lavfi = ["-f", "lavfi", "-i", "testsrc=d=2:s=64x48", "-f", "lavfi", "-i", "sine=d=2"]
    maps = ["-map", "0", "-map", "1", "-map_metadata", "2", "-map_chapters", "2"]
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        *lavfi,
        "-i",
        str(tags),
        *maps,
        "-metadata:s:a:0",
        "language=fra",
        "-c:v",
        "ffv1",
        "-c:a",
        "flac",
        str(path),
    )
    return path


def convert(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    status = main(["convert", *argv])
    return status, capsys.readouterr().err


def write(folder: Path, name: str, text: str) -> str:
    path = folder / name
    _ = path.write_text(text)
    return str(path)


def test_the_mapping_one_never_two() -> None:
    assert kept_metadata(["-i", "a"], None) == ([], ["-map_metadata", "0", "-map_chapters", "0"])
    extra, kept = kept_metadata(["-i", "a", "-i", "b"], Path("m.ffmeta"))
    assert (extra, kept) == (
        ["-f", "ffmetadata", "-i", "m.ffmeta"],
        ["-map_metadata", "2", "-map_chapters", "2"],
    )


@pytest.mark.parametrize(("extra", "flow"), [((), Flow.REMUX), (("-w", "32"), Flow.PICTURE)])
def test_metadata_alone_is_a_job_of_its_own(extra: tuple[str, ...], flow: Flow) -> None:
    o = validate(parse("convert", CONVERT, ["-i", "a.mkv", "--metadata", "m.ffmeta", *extra]))
    assert select_flow(o) is flow


def test_vorbis_comments_applied_alone(
    capsys: pytest.CaptureFixture[str], film: Path, ffprobe: str, tmp_path: Path
) -> None:
    text = "TITLE=Applied\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=One\nCHAPTER001=00:00:01.500\nCHAPTER001NAME=Two\n"
    out = tmp_path / "out.mkv"
    assert (
        convert(
            capsys, "-i", str(film), "-o", str(out), "--metadata", write(tmp_path, "m.txt", text)
        )[0]
        == 0
    )
    tags, streams, chapters = metadata_seen(ffprobe, str(out))
    assert tags.get("title") == "Applied"  # the file's, in place of the media's
    assert [(start, chapter.get("title")) for start, _, chapter in chapters] == [
        (0, "One"),
        (Fraction(3, 2), "Two"),
    ]
    assert streams[1].get("language") == "fra"  # each stream's own tags kept


def test_a_cues_last_track_ends_with_the_media(
    capsys: pytest.CaptureFixture[str], film: Path, ffprobe: str, tmp_path: Path
) -> None:
    cue = 'FILE "film.mkv" WAVE\n  TRACK 01 AUDIO\n    TITLE "A"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "B"\n    INDEX 01 00:01:00\n'
    out = tmp_path / "out.mkv"
    assert (
        convert(
            capsys, "-i", str(film), "-o", str(out), "--metadata", write(tmp_path, "m.cue", cue)
        )[0]
        == 0
    )
    _, _, chapters = metadata_seen(ffprobe, str(out))
    assert [(start, chapter.get("title")) for start, _, chapter in chapters] == [(0, "A"), (1, "B")]
    assert chapters[-1][1] >= Fraction(2)  # the media's end: the cue holds none


def test_applied_with_a_resize(
    capsys: pytest.CaptureFixture[str], film: Path, ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "out.mkv"
    given = write(tmp_path, "m.ffmeta", ";FFMETADATA1\ntitle=Resized\n")
    assert convert(capsys, "-i", str(film), "-o", str(out), "-w", "32", "--metadata", given)[0] == 0
    tags, streams, chapters = metadata_seen(ffprobe, str(out))
    assert (tags.get("title"), chapters, streams[1].get("language")) == (
        "Resized",
        [],
        "fra",
    )  # the file's: no chapter


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ("-o", "{tmp}/e.gif", "-w", "32", "--metadata", "{tmp}/m.ffmeta"),
            "--metadata: a .gif holds no tags or chapters",
        ),
        (
            ("-o", "{tmp}/e.mkv", "--metadata", "{film}"),
            "--metadata takes a metadata file (.ffmeta, .txt, .cue): {film}",
        ),
        (
            ("-o", "{tmp}/e.mkv", "--metadata", "{tmp}/two.cue"),
            "--metadata: a cue over 2 files describes 2 media",
        ),
    ],
)
def test_what_metadata_refuses(
    capsys: pytest.CaptureFixture[str],
    film: Path,
    tmp_path: Path,
    argv: tuple[str, ...],
    message: str,
) -> None:
    _ = write(tmp_path, "m.ffmeta", ";FFMETADATA1\n")
    _ = write(
        tmp_path,
        "two.cue",
        'FILE "1" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "2" WAVE\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n',
    )
    given = [arg.format(tmp=tmp_path, film=film) for arg in argv]
    assert convert(capsys, "-i", str(film), *given) == (
        1,
        f"ffman: error: {message.format(film=film)}\n",
    )
    assert not any(p.suffix == ".gif" or p.name == "e.mkv" for p in tmp_path.iterdir())


def test_a_metadata_job_takes_no_metadata(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    given = write(tmp_path, "m.ffmeta", ";FFMETADATA1\n")
    status, err = convert(capsys, "-i", given, "-o", str(tmp_path / "o.txt"), "--metadata", given)
    assert (status, err) == (
        1,
        "ffman: error: a metadata file is a job of its own: --metadata cannot be added\n",
    )


def test_a_files_stream_sections_are_noted_not_applied(
    capsys: pytest.CaptureFixture[str], film: Path, ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "out.mkv"
    given = write(tmp_path, "m.ffmeta", ";FFMETADATA1\ntitle=T\n[STREAM]\nlanguage=eng\n")
    status, err = convert(capsys, "-i", str(film), "-o", str(out), "--metadata", given)
    assert (status, err.splitlines()[0]) == (
        0,
        "ffman: the file's stream sections: not applied -- each stream keeps its own tags",
    )
    assert metadata_seen(ffprobe, str(out))[1][1].get("language") == "fra"


@pytest.mark.parametrize("job", [(), ("--add-subs", "{tmp}/s.srt"), ("-w", "32")])
def test_the_flows_refusals_come_before_the_files(
    capsys: pytest.CaptureFixture[str], film: Path, tmp_path: Path, job: tuple[str, ...]
) -> None:
    _ = write(tmp_path, "s.srt", "1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    malformed = write(
        tmp_path, "m.ffmeta", ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\n"
    )  # no END=
    exists = tmp_path / "exists.mkv"
    exists.touch()
    argv = [
        "-i",
        str(film),
        "-o",
        str(exists),
        *(arg.format(tmp=tmp_path) for arg in job),
        "--metadata",
        malformed,
    ]
    status, err = convert(capsys, *argv)
    assert (status, err) == (
        1,
        f"ffman: error: output exists: {exists} (use --overwrite to replace it)\n",
    )
