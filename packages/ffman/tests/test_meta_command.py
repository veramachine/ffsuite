"""``ffman meta`` (spec 8), in process: each format written and edited, its refusals."""

import io
import sys
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.errors import shown

SHEET = 'REM GENRE Ska\nTITLE "Old"\nFILE "album.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n'


def meta(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    status = main(["meta", *argv])
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def test_a_new_vorbis_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out = tmp_path / "n.txt"
    edits = (
        "--set",
        "title=Song",
        "--set",
        "album_artist=Band",
        "--add",
        "artist=A",
        "--add",
        "artist=B",
    )
    assert meta(capsys, "-o", str(out), "-p", "vorbiscomment", *edits) == (0, f"{out}\n", "")
    assert out.read_text() == "TITLE=Song\nALBUMARTIST=Band\nARTIST=A\nARTIST=B\n"


def test_an_edit_in_place_keeps_what_it_does_not_touch(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "a.ffmeta"
    _ = path.write_text(
        ";FFMETADATA1\ntitle=Old\nartist=A\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n"
    )
    assert (
        meta(capsys, "-i", str(path), "--in-place", "--set", "TITLE=New", "--unset", "artist")[0]
        == 0
    )
    assert (
        path.read_text()
        == ";FFMETADATA1\ntitle=New\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n"
    )


def test_a_cue_edited_its_disc_fields(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path, out = tmp_path / "a.cue", tmp_path / "b.cue"
    _ = path.write_text(SHEET)
    assert (
        meta(
            capsys, "-i", str(path), "-o", str(out), "--set", "genre=Alt Rock", "--set", "album=LP"
        )[0]
        == 0
    )
    assert out.read_text() == SHEET.replace("GENRE Ska", 'GENRE "Alt Rock"').replace(
        '"Old"', '"LP"'
    )


def test_what_is_removed_is_never_noted_lost(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "v.txt"
    _ = path.write_text("TITLE=T\nARTIST=A\nARTIST=B\n")
    status, _, err = meta(
        capsys, "-i", str(path), "-o", str(tmp_path / "o.ffmeta"), "--unset", "artist"
    )
    assert (status, err) == (
        0,
        "",
    )  # converted to ffmetadata, the two ARTISTs would be joined: gone first


def test_dry_run_writes_nothing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out = tmp_path / "n.ffmeta"
    assert meta(capsys, "-o", str(out), "--set", "title=T", "--dry-run") == (0, "", "")
    assert not out.exists()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ((), "meta: --output is required without --input"),
        (("--in-place",), "meta: --output is required without --input"),
        (("-o", "x.txt", "--in-place"), "--in-place and --output exclude each other"),
        (
            ("-o", "x.txt", "-p", "youtube"),
            "unknown preset: youtube (ffmetadata, vorbiscomment, cue)",
        ),
        (("-o", "{tmp}/x.mp4"), "meta writes a metadata file (.ffmeta, .txt, .cue): {tmp}/x.mp4"),
        (
            ("-o", "{tmp}/x.cue", "-p", "vorbiscomment"),
            "--preset vorbiscomment: a .cue output is a cue sheet",
        ),
        (
            ("-o", "{tmp}/x.cue", "--set", "album=A"),
            "nothing to write: no tag or chapter of the edits is one {tmp}/x.cue holds",
        ),
        (("-o", "{tmp}/x.txt", "--set", "a=1", "--unset", "A"), "--set a and --unset A contradict"),
    ],
)
def test_what_meta_refuses(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, argv: tuple[str, ...], message: str
) -> None:
    resolved = [arg.format(tmp=tmp_path) for arg in argv]
    status, _, err = meta(capsys, *resolved)
    assert (status, err.splitlines()[-1]) == (1, f"ffman: error: {message.format(tmp=tmp_path)}")


def test_its_help(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = meta(capsys, "--help")
    assert status == 0
    assert out.startswith("Usage: ffman meta [-i INPUT] (-o OUTPUT | -o - | --in-place)")
    assert "- for stdout" in out
    assert "Tags:\n" in out
    assert "--set KEY=VALUE" in out


def test_a_cue_from_a_metadata_file_names_its_stem_noted(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "x.ffmeta"
    _ = path.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n")
    for command in ("meta", "convert"):
        out = tmp_path / f"{command}.cue"
        status = main([command, "-i", str(path), "-o", str(out)])
        err = capsys.readouterr().err
        assert status == 0
        assert out.read_text().startswith('FILE "x" WAVE\n')
        assert (
            "ffman: the cue's FILE: x, the media a metadata file does not name -- check it\n" in err
        )


def test_chapters_into_vorbis_in_time_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "c.txt"
    status, _, err = meta(
        capsys,
        "-o",
        str(out),
        "-p",
        "vorbiscomment",
        "--chapter",
        "1:30.5=Verse",
        "--chapter",
        "0=Intro",
    )
    assert (status, err) == (0, "")
    assert (
        out.read_text()
        == "CHAPTER000=00:00:00.000\nCHAPTER000NAME=Intro\nCHAPTER001=00:01:30.500\nCHAPTER001NAME=Verse\n"
    )


def test_a_cues_tracks_edited(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "a.cue"
    _ = path.write_text(SHEET + '  TRACK 02 AUDIO\n    TITLE "Two"\n    INDEX 01 02:00:00\n')
    argv = (
        "-i",
        str(path),
        "--in-place",
        "--chapter",
        "1:00=Mid",
        "--retitle",
        "2=Second",
        "--drop-chapter",
        "1",
    )
    assert meta(capsys, *argv)[0] == 0
    assert path.read_text() == (
        'REM GENRE Ska\nTITLE "Old"\nFILE "album.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Mid"\n'
        + '    INDEX 00 00:00:00\n    INDEX 01 01:00:00\n  TRACK 02 AUDIO\n    TITLE "Second"\n'
        + "    INDEX 01 02:00:00\n"
    )


def test_a_cues_own_edits(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "a.cue"
    _ = path.write_text(
        'FILE "album.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 01 02:00:00\n'
    )
    argv = (
        "--flags",
        "2=pre,dcp",
        "--pregap",
        "2=1:58",
        "--file",
        "My Album.flac",
        "--set",
        "barcode=0724384960650",
    )
    assert meta(
        capsys, "-i", str(path), "--in-place", "--chapter-set", "1:isrc=GBAYE7900001", *argv
    ) == (0, f"{path}\n", "")
    assert path.read_text() == (
        'CATALOG 0724384960650\nFILE "My Album.flac" WAVE\n  TRACK 01 AUDIO\n    ISRC GBAYE7900001\n'
        + "    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    FLAGS PRE DCP\n    INDEX 00 01:58:00\n    INDEX 01 02:00:00\n"
    )


def test_file_names_the_media_no_guess(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "x.ffmeta"
    _ = path.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n")
    out = tmp_path / "x.cue"
    status, _, err = meta(capsys, "-i", str(path), "-o", str(out), "--file", "album.flac")
    assert status == 0
    assert out.read_text().startswith('FILE "album.flac" WAVE\n')
    assert "the cue's FILE" not in err


@pytest.mark.parametrize("name", [" album.flac", '"album.flac', "a\nb", "a\x00b"])
def test_a_file_name_no_cue_holds_is_refused(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str
) -> None:
    status, _, err = meta(capsys, "-o", str(tmp_path / "x.cue"), "--chapter", "0", "--file", name)
    rule = "a cue's FILE name has no line break or NUL, no space at either end, no quote first"
    assert (status, err) == (1, f"ffman: error: --file: {rule}: {shown(name)}\n")  # not a traceback


@pytest.mark.parametrize(
    ("argv", "out", "err"),
    [
        (("-i", "{sheet}", "-o", "-"), SHEET, ""),  # the input's format
        (
            ("-i", "{sheet}", "-o", "-", "-p", "vorbiscomment"),
            "ALBUM=Old\nGENRE=Ska\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=One\n",  # a disc's TITLE: the album
            "",
        ),
        (("-o", "-", "--set", "title=T"), ";FFMETADATA1\ntitle=T\n", ""),  # no input: ffmetadata
        (
            ("-o", "-", "-p", "cue", "--chapter", "0=One"),
            'FILE "media" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n',
            "ffman: the cue's FILE: media, the media the edits do not name -- check it\n",
        ),
        (("-o", "-", "-p", "vorbiscomment"), "", ""),  # empty: a pipe takes it
        (("-i", "{sheet}", "-o", "-", "--dry-run"), "", ""),
    ],
)
def test_the_result_to_stdout(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, argv: tuple[str, ...], out: str, err: str
) -> None:
    sheet = tmp_path / "a.cue"
    _ = sheet.write_text(SHEET)
    assert meta(capsys, *(arg.format(sheet=sheet) for arg in argv)) == (0, out, err)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.cue"]  # no file, no partial


def test_a_media_files_tags_to_stdout(capsys: pytest.CaptureFixture[str], cd_flac: Path) -> None:
    status, out, _ = meta(capsys, "-i", str(cd_flac), "-o", "-")
    assert status == 0
    assert out.startswith(";FFMETADATA1\n")


def test_preset_cue_is_stdouts(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    status, _, err = meta(capsys, "-o", str(tmp_path / "x.txt"), "-p", "cue")
    assert (status, err) == (
        1,
        "ffman: error: --preset cue: a .txt output is ffmetadata or Vorbis comments\n",
    )


def test_stdout_is_utf8_whatever_the_locale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sheet = tmp_path / "a.ffmeta"
    _ = sheet.write_text(";FFMETADATA1\ntitle=日本の歌\n", encoding="utf-8")
    raw = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(raw, encoding="latin-1")
    )  # a non-UTF-8 locale's
    assert main(["meta", "-i", str(sheet), "-o", "-"]) == 0
    assert raw.getvalue() == ";FFMETADATA1\ntitle=日本の歌\n".encode()  # not an encoding error
