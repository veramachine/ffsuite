"""metaflac, the oracle where the formats meet: FLAC's tag files and its CUESHEET block.

Tags: a comment a line, no escape in metaflac's files -- so single-line values without '\\'
read alike (the vorbiscomment skill). Cue sheets: the block keeps no text, of the flags PRE, a
mode AUDIO or DATA; metaflac's export adds REM FLAC__lead-in and lead-out after the last track,
and writes INDEX in mm:ss:ff at CD-DA alone (the cue skill, measured).
"""

import shutil
from dataclasses import replace
from pathlib import Path

import ffmeta
import pytest
from ffmeta import cue, vorbis
from ffmeta.model import Disc, File, Index, Metadata, Tag, Track
from ffmeta_support.media import CD_SECONDS, tool
from ffmeta_support.metadata import vorbis_models
from hypothesis import given, settings
from hypothesis import strategies as st

SAMPLES = CD_SECONDS * 44_100  # cd_flac's


def fresh(flac: Path) -> Path:
    """A working copy of ``flac`` beside it, made again for each example: one, however many."""
    work = flac.with_name("work.flac")
    _ = shutil.copyfile(flac, work)
    return work


# where Vorbis text meets metaflac's: a value on one line, without '\'
def _meets(meta: Metadata) -> bool:
    values = [t.value for t in meta.tags] + [t.value for c in meta.chapters for t in c.tags]
    return not any(char in value for value in values for char in "\\\n\r")


@settings(max_examples=30, deadline=None)
@given(vorbis_models().filter(_meets))
def test_metaflacs_exported_tags_read_by_ffman(
    metaflac: str, cd_flac: Path, meta: Metadata
) -> None:
    flac = fresh(cd_flac)
    comments = vorbis.write(meta).text.splitlines()  # in this domain, each line a comment as is
    _ = tool(
        metaflac, "--remove-all-tags", *(f"--set-tag={comment}" for comment in comments), str(flac)
    )
    assert vorbis.read(tool(metaflac, "--export-tags-to=-", str(flac)), "export.txt") == meta


@settings(max_examples=30, deadline=None)
@given(vorbis_models().filter(_meets))
def test_ffmans_tags_read_by_metaflac(metaflac: str, cd_flac: Path, meta: Metadata) -> None:
    flac = fresh(cd_flac)
    text = vorbis.write(meta).text
    tags = flac.with_suffix(".txt")
    _ = tags.write_text(text, encoding="utf-8")
    _ = tool(metaflac, "--remove-all-tags", f"--import-tags-from={tags}", str(flac))
    assert tool(metaflac, "--export-tags-to=-", str(flac)) == text  # byte for byte


def test_past_where_they_meet_an_escape_is_metaflacs_text(metaflac: str, cd_flac: Path) -> None:
    flac = fresh(cd_flac)
    tags = flac.with_suffix(".txt")
    _ = tags.write_text(vorbis.write(Metadata((Tag("LYRICS", "one\ntwo"),))).text, encoding="utf-8")
    _ = tool(metaflac, "--remove-all-tags", f"--import-tags-from={tags}", str(flac))
    assert (
        tool(metaflac, "--list", "--block-type=VORBIS_COMMENT", str(flac)).count("LYRICS=one\\ntwo")
        == 1
    )  # not a line break


# a disc the block holds: one file, tracks from 01, the first index at 00:00:00, every index
# inside the stream (480 s at most, of CD_SECONDS); text, REM lines, every flag and a data mode
# too, to see what is kept
@st.composite
def block_discs(draw: st.DrawFn) -> Metadata:
    tracks: list[Track] = []
    frames = -1  # no index yet: the first lands on 0
    for number in range(1, draw(st.integers(1, 6)) + 1):
        indexes: list[Index] = []
        for index_number in (0, 1, 2):
            if index_number == 1 or draw(st.booleans()):  # INDEX 01, 00 and 02 at will
                frames = 0 if frames < 0 else frames + draw(st.integers(1, 2000))  # 480 s at most
                indexes.append(Index(index_number, frames, 0))
        tracks.append(
            Track(
                number,
                draw(st.sampled_from(("AUDIO", "MODE1/2352"))),
                tuple(indexes),
                (Tag("TITLE", "t"),),
                ("REPLAYGAIN_TRACK_GAIN -6.00 dB",),
                tuple(sorted(draw(st.sets(st.sampled_from(("DCP", "4CH", "PRE", "SCMS")))))),
                draw(st.none() | st.from_regex(r"[A-Z0-9]{5}[0-9]{7}", fullmatch=True)),
            )
        )
    catalog = draw(st.none() | st.from_regex(r"[0-9]{13}", fullmatch=True))
    disc = Disc(
        (File("x.wav", "WAVE"),), tuple(tracks), (Tag("TITLE", "Album"),), ("DATE 1991",), catalog
    )
    return Metadata(disc=disc)


def as_the_block_keeps(disc: Disc, flac: Path) -> Disc:
    """The sheet metaflac exports from ``disc`` imported: no text, PRE alone, AUDIO or DATA."""
    tracks = tuple(
        Track(
            track.number,
            "AUDIO" if track.mode == "AUDIO" else "DATA",
            track.indexes,
            flags=("PRE",) if "PRE" in track.flags else (),
            isrc=track.isrc,
        )
        for track in disc.tracks
    )
    lead = ("FLAC__lead-in 88200", f"FLAC__lead-out 170 {SAMPLES}")  # after the last TRACK: its REM
    tracks = (*tracks[:-1], replace(tracks[-1], rems=lead))
    return Disc((File(str(flac), "FLAC"),), tracks, catalog=disc.catalog)


@settings(max_examples=40, deadline=None)
@given(block_discs())
def test_ffmans_cue_sheet_through_flacs_block(metaflac: str, cd_flac: Path, meta: Metadata) -> None:
    assert meta.disc is not None
    flac = fresh(cd_flac)
    sheet = flac.with_suffix(".cue")
    _ = sheet.write_text(cue.write(meta).text, encoding="utf-8")
    _ = tool(metaflac, f"--import-cuesheet-from={sheet}", str(flac))
    exported = cue.read(tool(metaflac, "--export-cuesheet-to=-", str(flac)), "export.cue")
    assert exported.disc == as_the_block_keeps(meta.disc, flac)


EAC = """CATALOG 0724384960650
FILE "album.wav" WAVE
  TRACK 01 AUDIO
    FLAGS DCP PRE
    ISRC GBAYE7900001
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    INDEX 00 02:47:74
    INDEX 01 02:48:27
"""


def test_metaflacs_exported_sheet_read_by_ffman(metaflac: str, cd_flac: Path) -> None:
    flac = fresh(cd_flac)
    sheet = flac.with_suffix(".cue")
    _ = sheet.write_text(EAC, encoding="utf-8")
    _ = tool(metaflac, f"--import-cuesheet-from={sheet}", str(flac))
    exported = tool(metaflac, "--export-cuesheet-to=-", str(flac))
    assert exported == (
        f'CATALOG 0724384960650\nFILE "{flac}" FLAC\n  TRACK 01 AUDIO\n    FLAGS PRE\n    ISRC GBAYE7900001\n'
        + "    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 00 02:47:74\n    INDEX 01 02:48:27\n"
        + f"REM FLAC__lead-in 88200\nREM FLAC__lead-out 170 {SAMPLES}\n"
    )
    assert cue.read(exported, "export.cue").disc == Disc(
        (File(str(flac), "FLAC"),),
        (
            Track(1, "AUDIO", (Index(1, 0, 0),), flags=("PRE",), isrc="GBAYE7900001"),
            Track(
                2,
                "AUDIO",
                (Index(0, 12599, 0), Index(1, 12627, 0)),
                rems=("FLAC__lead-in 88200", f"FLAC__lead-out 170 {SAMPLES}"),
            ),
        ),
        catalog="0724384960650",
    )


def test_metaflacs_sheet_past_cd_da_is_refused(metaflac: str, ffmpeg: str, tmp_path: Path) -> None:
    flac = tmp_path / "hi.flac"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=d=60:r=48000",
        "-ac",
        "2",
        "-c:a",
        "flac",
        str(flac),
    )
    sheet = tmp_path / "a.cue"
    _ = sheet.write_text(EAC, encoding="utf-8")
    _ = tool(metaflac, f"--import-cuesheet-from={sheet}", str(flac))
    exported = tool(metaflac, "--export-cuesheet-to=-", str(flac))
    assert "    INDEX 01 0\n" in exported  # sample numbers, not mm:ss:ff
    with pytest.raises(ffmeta.Error, match=r"^export\.cue:6: a time is mm:ss:ff: 0$"):
        _ = cue.read(exported, "export.cue")
