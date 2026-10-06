"""Tags and chapters kept (spec 3.13): the tags an output holds not, told; chapters as Vorbis
comments into Ogg and FLAC, where ffmpeg's muxers write none."""

from fractions import Fraction
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.media import flac
from tests.support.media import metadata_seen, tool

SOURCE = (
    ";FFMETADATA1\ntitle=Song\nMOOD=calm\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1700\ntitle=One\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1700\nEND=2500\ntitle=Two\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=2500\nEND=3000\ntitle=Three\n"
)
CHAPTERS = [(Fraction(0), "One"), (Fraction(17, 10), "Two"), (Fraction(5, 2), "Three")]


@pytest.fixture(scope="module")
def sound(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three seconds of FLAC in Matroska: a title, a custom tag, three chapters (1.7 s: Opus' fault)."""
    folder = tmp_path_factory.mktemp("tagged")
    tags = folder / "m.ffmeta"
    _ = tags.write_text(SOURCE)
    path = folder / "src.mka"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=d=3",
        "-i",
        str(tags),
        "-map",
        "0",
        "-map_metadata",
        "1",
        "-map_chapters",
        "1",
        "-c:a",
        "flac",
        str(path),
    )
    return path


def convert(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    status = main(["convert", *argv])
    return status, [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("ffman: ")
    ]


@pytest.mark.parametrize(
    ("ext", "codec", "notes"),
    [
        ("mp4", "aac", ["ffman: the tags MOOD: a .mp4 holds them not: left out"]),  # iTunes atoms
        ("mkv", "flac", []),  # any key: unread, held
    ],
)
def test_a_tag_the_output_holds_not_is_noted(
    capsys: pytest.CaptureFixture[str],
    sound: Path,
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    codec: str,
    notes: list[str],
) -> None:
    out = tmp_path / f"o.{ext}"
    assert convert(capsys, "-i", str(sound), "-o", str(out), "--audio-codec", codec) == (0, notes)
    tags, _, chapters = metadata_seen(ffprobe, str(out))
    assert tags.get("title") == "Song"
    assert [(start, chapter.get("title")) for start, _, chapter in chapters] == CHAPTERS


@pytest.mark.parametrize(("ext", "codec"), [("opus", "opus"), ("ogg", "vorbis"), ("flac", "flac")])
def test_chapters_into_ogg_and_flac_as_comments(
    capsys: pytest.CaptureFixture[str],
    sound: Path,
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    codec: str,
) -> None:
    out = tmp_path / f"o.{ext}"
    assert convert(capsys, "-i", str(sound), "-o", str(out), "--audio-codec", codec) == (
        0,
        [],
    )  # ends implied
    _, _, chapters = metadata_seen(ffprobe, str(out))
    assert [
        (start, chapter.get("title")) for start, _, chapter in chapters
    ] == CHAPTERS  # none late, none lost


def test_flacs_comments_in_order(
    capsys: pytest.CaptureFixture[str], sound: Path, metaflac: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.flac"
    assert convert(capsys, "-i", str(sound), "-o", str(out))[0] == 0
    names = [
        line.split("=", 1)[0]
        for line in tool(metaflac, "--export-tags-to=-", str(out)).splitlines()
    ]
    chapters = [
        "CHAPTER000",
        "CHAPTER000NAME",
        "CHAPTER001",
        "CHAPTER001NAME",
        "CHAPTER002",
        "CHAPTER002NAME",
    ]
    assert names == ["title", "MOOD", *chapters, "encoder"]  # encoder= first: no title moved


def test_an_end_that_says_more_is_noted(
    capsys: pytest.CaptureFixture[str], sound: Path, tmp_path: Path
) -> None:
    gap = tmp_path / "gap.ffmeta"
    _ = gap.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=A\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=2000\nEND=3000\ntitle=B\n"
    )
    status, notes = convert(
        capsys,
        "-i",
        str(sound),
        "-o",
        str(tmp_path / "o.opus"),
        "--audio-codec",
        "opus",
        "--metadata",
        str(gap),
    )
    assert (status, notes) == (
        0,
        [
            "ffman: chapter ends: Vorbis comments hold none (a chapter ends where the next begins): left out"
        ],
    )


def test_no_chapters_no_comments(
    capsys: pytest.CaptureFixture[str], cd_flac: Path, ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.ogg"
    assert convert(capsys, "-i", str(cd_flac), "-o", str(out), "--audio-codec", "vorbis") == (0, [])
    assert metadata_seen(ffprobe, str(out))[2] == []


def test_add_subs_notes_a_tag_too(
    capsys: pytest.CaptureFixture[str], sound: Path, tmp_path: Path
) -> None:
    srt = tmp_path / "s.srt"
    _ = srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nHi\n")
    status, notes = convert(
        capsys, "-i", str(sound), "-o", str(tmp_path / "o.mp4"), "--add-subs", str(srt)
    )
    assert (status, "ffman: the tags MOOD: a .mp4 holds them not: left out" in notes) == (0, True)


def test_copied_ogg_keeps_its_chapters_unremarked(
    capsys: pytest.CaptureFixture[str], sound: Path, ffprobe: str, tmp_path: Path
) -> None:
    ogg = tmp_path / "s.ogg"
    assert convert(capsys, "-i", str(sound), "-o", str(ogg), "--audio-codec", "vorbis")[0] == 0
    copied = tmp_path / "s.oga"  # another extension, nothing asked: copied
    assert convert(capsys, "-i", str(ogg), "-o", str(copied)) == (
        0,
        [],
    )  # its last end the duration's, rounded
    assert [
        (start, chapter.get("title"))
        for start, _, chapter in metadata_seen(ffprobe, str(copied))[2]
    ] == CHAPTERS


def test_a_title_arrives_as_it_is(
    capsys: pytest.CaptureFixture[str], sound: Path, metaflac: str, tmp_path: Path
) -> None:
    titles = [
        "a=b; café",
        "a\\b",
        "line\none",
    ]  # -metadata takes values raw: no form's escape in them
    chapters = "".join(
        f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={n * 1000}\nEND={n * 1000 + 1000}\ntitle={t.replace(chr(92), chr(92) * 2).replace(chr(10), chr(92) + chr(10))}\n"
        for n, t in enumerate(titles)
    )
    given = tmp_path / "m.ffmeta"
    _ = given.write_text(";FFMETADATA1\n" + chapters, encoding="utf-8")
    out = tmp_path / "o.flac"
    assert convert(capsys, "-i", str(sound), "-o", str(out), "--metadata", str(given))[0] == 0
    raw = tool(metaflac, "--export-tags-to=-", str(out))
    assert all(f"NAME={title}\n" in raw for title in titles)


def test_malformed_chapter_comments_read_as_ffmpeg_reads_them(
    capsys: pytest.CaptureFixture[str], cd_flac: Path, metaflac: str, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.flac"
    _ = bad.write_bytes(cd_flac.read_bytes())
    _ = tool(metaflac, "--set-tag=CHAPTER000=notatime", str(bad))
    status, notes = convert(
        capsys, "-i", str(bad), "-o", str(tmp_path / "o.ogg"), "--audio-codec", "vorbis"
    )
    why = f"{bad}:1: a chapter's time is HH:MM:SS.mmm: notatime"
    assert (status, notes) == (
        0,
        [f"ffman: the source's chapter comments: {why}: read as ffmpeg reads them"],
    )


def test_a_title_survives_a_chain_of_conversions(
    capsys: pytest.CaptureFixture[str], sound: Path, tmp_path: Path
) -> None:
    given = tmp_path / "m.ffmeta"
    _ = given.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=3000\ntitle=line\\\none \\\\ two\n",
        encoding="utf-8",
    )
    first, second = tmp_path / "one.flac", tmp_path / "two.flac"
    assert convert(capsys, "-i", str(sound), "-o", str(first), "--metadata", str(given))[0] == 0
    assert convert(capsys, "-i", str(first), "-o", str(second), "--audio-codec", "flac")[0] == 0
    titles = [
        [value for name, value in flac.comments(str(path)) or () if name.endswith("NAME")]
        for path in (first, second)
    ]
    assert titles == [
        ["line\none \\ two"],
        ["line\none \\ two"],
    ]  # a line break and a backslash, each hop
