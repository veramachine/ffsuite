"""``convert`` with metadata files (spec 3.9): each direction, the output's rules, refusals."""

from pathlib import Path

import pytest

from tests.support.media import ff, tool

SHEET = 'FILE "album.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Two"\n    SONGWRITER "S"\n    INDEX 01 01:00:00\n'
FFMETA = ";FFMETADATA1\ntitle=Album\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=60000\ntitle=One\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=60000\nEND=90000\ntitle=Two\n"
COMMENTS = "TITLE=Album\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=One\nCHAPTER001=00:01:00.000\nCHAPTER001NAME=Two\n"
SONGWRITER_NOTE = "ffman: track 02's SONGWRITER: none maps it: left out\n"


def write(path: Path, text: str) -> str:
    _ = path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_cue_into_vorbis_comments(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out = tmp_path / "a.txt"
    status, err = ff(
        capsys, "-i", write(tmp_path / "a.cue", SHEET), "-o", str(out), "--preset", "vorbiscomment"
    )
    assert (status, err) == (0, SONGWRITER_NOTE)
    assert out.read_text(encoding="utf-8") == COMMENTS.replace("TITLE=Album\n", "")


def test_a_txt_is_told_by_its_first_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for name, text in (("ff.txt", FFMETA), ("vc.txt", COMMENTS)):
        out = tmp_path / f"{name}.cue"
        status, err = ff(capsys, "-i", write(tmp_path / name, text), "-o", str(out))
        assert status == 0, err
        assert 'TITLE "Album"' not in out.read_text()  # a work's title: no cue field
        assert '    TITLE "Two"\n    INDEX 01 01:00:00\n' in out.read_text()


def test_a_txt_out_is_ffmetadata_unless_its_preset_says(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = write(tmp_path / "a.ffmeta", FFMETA)
    assert ff(capsys, "-i", source, "-o", str(tmp_path / "b.txt"))[0] == 0
    assert (tmp_path / "b.txt").read_text() == FFMETA
    assert ff(capsys, "-i", source, "-o", str(tmp_path / "c.txt"), "-p", "vorbiscomment")[0] == 0
    assert (
        (tmp_path / "c.txt").read_text()
        == "title=Album\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=One\nCHAPTER001=00:01:00.000\nCHAPTER001NAME=Two\n"
    )


def test_the_default_output_rewrites_it_and_in_place_replaces_it(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = write(tmp_path / "a.cue", SHEET.replace("    TITLE", "\ttitle"))
    assert ff(capsys, "-i", source) == (0, "")  # a cue holds all a cue holds: no note
    assert (tmp_path / "a.ffman.cue").read_text().count('    TITLE "') == 2  # ffman's form
    assert (
        ff(capsys, "-i", source)[1]
        == f"ffman: error: output exists: {tmp_path}/a.ffman.cue (use --overwrite to replace it)\n"
    )
    assert ff(capsys, "-i", source, "--in-place")[0] == 0
    assert Path(source).read_text() == (tmp_path / "a.ffman.cue").read_text()


def test_dry_run_reads_and_notes_and_writes_nothing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "b.ffmeta"
    assert ff(capsys, "-i", write(tmp_path / "a.cue", SHEET), "-o", str(out), "--dry-run")[0] == 0
    assert not out.exists()
    assert not list(tmp_path.glob(".ffman.*"))  # no partial either


@pytest.mark.parametrize(
    ("name", "raw", "message"),
    [
        ("a.cue", b'FILE "a" WAVE\n  TITLE \xff\n', "not UTF-8: {path} (byte 22)"),
        (
            "a.cue",
            b'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:61:00\n',
            "{path}:3: a time's seconds run to 59, its frames to 74: 00:61:00",
        ),
        (
            "a.cue",
            b'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "b" WAVE\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n',
            "a cue sheet over 2 files: its tracks are placed by the durations of the first 1, 0 given",
        ),
        ("a.txt", b"", "nothing to write: no tag or chapter of {path} is one {out} holds"),
    ],
)
def test_a_file_that_cannot_be_read_or_written(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str, raw: bytes, message: str
) -> None:
    path, out = tmp_path / name, tmp_path / "out.txt"
    _ = path.write_bytes(raw)
    status, err = ff(capsys, "-i", str(path), "-o", str(out), "-p", "vorbiscomment")
    assert (status, err.splitlines()[-1]) == (
        1,
        f"ffman: error: {message.format(path=path, out=out)}",
    )


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["-o", "x.mp4"], "a metadata file makes a metadata file: {tmp}/x.mp4"),
        (["-o", "x.txt", "-w", "100"], "a metadata file is a job of its own: -w cannot be added"),
        (
            ["-o", "x.txt", "--vfx", "invert"],
            "a metadata file is a job of its own: --vfx cannot be added",
        ),
        (
            ["-o", "x.txt", "--video-codec", "h264"],
            "a metadata file is a job of its own: --video-codec cannot be added",
        ),
        (
            ["-o", "x.txt", "--add-subs", "s.srt"],
            "a metadata file is a job of its own: --add-subs cannot be added",
        ),
        (
            ["-o", "x.txt", "-p", "yt"],
            "a metadata file is a job of its own: --preset youtube cannot be added",
        ),
        (
            ["-o", "x.cue", "-p", "vorbiscomment"],
            "--preset vorbiscomment: a .cue output is a cue sheet",
        ),
        (
            ["-o", "x.ffmeta", "-p", "ffmetadata"],
            "--preset ffmetadata: a .ffmeta output is ffmetadata",
        ),
        (["-o", "x.txt", "-p", "ffmetadata", "--normalize"], "--normalize needs --preset youtube"),
    ],
)
def test_what_a_metadata_job_refuses(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, args: list[str], message: str
) -> None:
    source = write(tmp_path / "a.cue", SHEET)
    resolved = [str(tmp_path / a) if a.startswith("x.") else a for a in args]
    assert ff(capsys, "-i", source, *resolved) == (
        1,
        f"ffman: error: {message.format(tmp=tmp_path)}\n",
    )


def test_a_txt_preset_with_a_media_output(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert ff(capsys, "-i", str(tmp_path / "v.mp4"), "-w", "100", "-p", "vorbiscomment") == (
        1,
        "ffman: error: --preset vorbiscomment is for a .txt output\n",
    )


@pytest.fixture
def tagged(ffmpeg: str, tmp_path: Path) -> Path:
    """A Matroska with tags, chapters and ffmpeg's own ENCODER, as a source has its encoder."""
    meta = write(
        tmp_path / "in.ffmeta", FFMETA.replace("title=Album\n", "title=Album\nartist=A;B\n")
    )
    media = tmp_path / "m.mkv"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        "-i",
        meta,
        "-map",
        "0",
        "-map_metadata",
        "1",
        "-map_chapters",
        "1",
        "-c:a",
        "flac",
        str(media),
    )
    return media


def test_a_media_files_tags_and_chapters_out(
    capsys: pytest.CaptureFixture[str], ffprobe: str, tagged: Path
) -> None:
    encoder = tool(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format_tags=encoder",
        "-of",
        "csv=p=0",
        str(tagged),
    ).strip()
    out = tagged.with_suffix(".ffmeta")
    assert ff(capsys, "-i", str(tagged), "-o", str(out)) == (0, "")
    assert (
        out.read_text()
        == (
            ";FFMETADATA1\ntitle=Album\nARTIST=A\\;B\n"
            + f"ENCODER={encoder}\n"  # the source's own: ffmpeg's export drops it (mux.c), ffprobe gives it back
            + "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=60000\ntitle=One\n"  # ffman's writer: 1/1000
            + "[CHAPTER]\nTIMEBASE=1/1000\nSTART=60000\nEND=90000\ntitle=Two\n"
        )
    )
    cue = tagged.with_suffix(".cue")
    status, err = ff(capsys, "-i", str(tagged), "-o", str(cue))
    assert status == 0, err
    assert cue.read_text().startswith('FILE "m.mkv" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n')


def test_the_tags_ffmpegs_export_drops_come_back(
    capsys: pytest.CaptureFixture[str], ffmpeg: str, tmp_path: Path
) -> None:
    media = tmp_path / "t.mp4"
    tagged = ("-metadata", "creation_time=2001-02-03T04:05:06Z", "-metadata", "title=T")
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=64x36:d=0.2",
        "-c:v",
        "libx264",
        *tagged,
        str(media),
    )
    out = tmp_path / "t.txt"
    assert ff(capsys, "-i", str(media), "-o", str(out), "-p", "vorbiscomment") == (0, "")
    comments = out.read_text().splitlines()
    assert "creation_time=2001-02-03T04:05:06.000000Z" in comments  # ffmpeg_mux_init.c deletes it
    assert any(line.startswith("encoder=Lavf") for line in comments)  # mux.c deletes it


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("nothing.mp4", None, "no such file: {path}"),
        ("bad.mp4", "not media\n", "ffprobe cannot read: {path}"),
    ],
)
def test_a_media_input_is_refused_as_every_flow_refuses_it(
    capsys: pytest.CaptureFixture[str],
    ffmpeg: str,
    tmp_path: Path,
    name: str,
    content: str | None,
    message: str,
) -> None:
    del ffmpeg  # the pinned ffprobe beside it
    path = tmp_path / name
    if content is not None:
        _ = path.write_text(content)
    assert ff(capsys, "-i", str(path), "-o", str(tmp_path / "o.cue")) == (
        1,
        f"ffman: error: {message.format(path=path)}\n",
    )
