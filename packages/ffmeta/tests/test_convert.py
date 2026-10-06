from fractions import Fraction

import ffmeta
import pytest
from ffmeta import cue, ffmetadata, vorbis
from ffmeta.convert import convert
from ffmeta.fields import RENAMED, Format
from ffmeta.model import Chapter, Index, Metadata, Tag, Track, folded
from ffmeta_support.metadata import (
    cue_models,
    ffmetadata_models,
    vorbis_models,
    whole_cue_models,
)
from hypothesis import given, settings

FORMATS: tuple[Format, ...] = ("ffmetadata", "vorbis", "cue")
# an EAC-style sheet: every field a row maps, and what none does
EAC = """REM GENRE "Alternative Rock"
REM DATE 1991
REM DISCID 860B640B
REM COMMENT "ExactAudioCopy v1.6"
CATALOG 0724384960650
PERFORMER "My Band"
TITLE "The Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Opening"
    PERFORMER "My Band"
    ISRC GBAYE7900001
    REM REPLAYGAIN_TRACK_GAIN -6.00 dB
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "The Road"
    SONGWRITER "Someone"
    INDEX 00 04:15:00
    INDEX 01 04:17:52
"""
EAC_LOST = (
    "the disc's REM DISCID: none maps it: left out",
    "the disc's REM COMMENT: none maps it: left out",
)
# what ffmpeg exports: its generic keys, its encoder, chapters in milliseconds
EXPORTED = """;FFMETADATA1
title=Song
album_artist=Band
artist=Band
track=1/12
comment=Ripped
encoder=Lavf61.7.100
[CHAPTER]
TIMEBASE=1/1000
START=0
END=90500
title=Intro
[CHAPTER]
TIMEBASE=1/1000
START=90500
END=180000
title=Verse
"""
# the vorbiscomment skill's example
COMMENTS = r"""TITLE=The Long Way
ARTIST=Ana Souza
ARTIST=Rui Lima
DATE=2026-10-03
TRACKNUMBER=1
TRACKTOTAL=12
DESCRIPTION=Unabridged\nread by the authors
CHAPTER000=00:00:00.000
CHAPTER000NAME=Departure
CHAPTER001=00:12:30.000
CHAPTER001NAME=The Road
CHAPTER002=00:41:05.500
CHAPTER002NAME=Arrival
"""


# (A) the cases: each converted, then written by the target's writer


def test_an_eac_sheet_into_ffmetadata() -> None:
    converted = convert(cue.read(EAC, "a.cue"), "cue", "ffmetadata")
    assert ffmetadata.write(converted.meta, Fraction(600)).text == (
        ";FFMETADATA1\nalbum_artist=My Band\nalbum=The Album\ngenre=Alternative Rock\ndate=1991\n"
        + "BARCODE=0724384960650\n"
        + "[CHAPTER]\nTIMEBASE=1/75\nSTART=0\nEND=19327\ntitle=Opening\nperformer=My Band\n"
        + "REPLAYGAIN_TRACK_GAIN=-6.00 dB\nISRC=GBAYE7900001\n"
        + "[CHAPTER]\nTIMEBASE=1/75\nSTART=19327\nEND=45000\ntitle=The Road\n"
    )  # frames exact: TIMEBASE=1/75 (the mappings, E)
    assert converted.notes == (
        *EAC_LOST,
        "track 02's SONGWRITER: none maps it: left out",
        "INDEX 00 (a pregap: the chapter before's, as mpv and Kodi place it), track 02: "
        + "chapters hold none: left out",
    )


def test_an_eac_sheet_into_vorbis() -> None:
    converted = convert(cue.read(EAC, "a.cue"), "cue", "vorbis")
    written = vorbis.write(converted.meta)
    assert written.text == (
        "ALBUMARTIST=My Band\nALBUM=The Album\nGENRE=Alternative Rock\nDATE=1991\n"
        + "BARCODE=0724384960650\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=Opening\n"
        + "CHAPTER001=00:04:17.693\nCHAPTER001NAME=The Road\n"
    )
    title_alone = "Vorbis' chapters hold a title alone: left out"
    assert converted.notes == (
        *EAC_LOST,
        f"track 01's PERFORMER: {title_alone}",
        f"track 01's REM REPLAYGAIN_TRACK_GAIN: {title_alone}",
        f"track 01's ISRC: {title_alone}",
        "track 02's SONGWRITER: none maps it: left out",
        "INDEX 00 (a pregap: the chapter before's, as mpv and Kodi place it), track 02: "
        + "chapters hold none: left out",
    )
    assert written.notes == ("chapter 2 starts between milliseconds: at the nearest, 257693 ms",)


def test_an_eac_sheet_through_ffmetadata_and_back_keeps_what_maps() -> None:
    there = convert(cue.read(EAC, "a.cue"), "cue", "ffmetadata")
    back = convert(there.meta, "ffmetadata", "cue", media="album.flac")
    assert back.notes == ()
    assert cue.write(back.meta).text == (
        'REM GENRE "Alternative Rock"\nREM DATE 1991\nCATALOG 0724384960650\n'
        + 'PERFORMER "My Band"\nTITLE "The Album"\nFILE "album.flac" WAVE\n'
        + '  TRACK 01 AUDIO\n    ISRC GBAYE7900001\n    TITLE "Opening"\n    PERFORMER "My Band"\n'
        + "    REM REPLAYGAIN_TRACK_GAIN -6.00 dB\n    INDEX 01 00:00:00\n"
        + '  TRACK 02 AUDIO\n    TITLE "The Road"\n    INDEX 01 04:17:52\n'
    )


def test_ffmpegs_export_into_vorbis_and_cue() -> None:
    meta = ffmetadata.read(EXPORTED, "a.ffmeta")
    to_vorbis = convert(meta, "ffmetadata", "vorbis")
    written = vorbis.write(to_vorbis.meta)
    assert written.text == (
        "title=Song\nALBUMARTIST=Band\nartist=Band\nTRACKNUMBER=1/12\nDESCRIPTION=Ripped\n"
        + "encoder=Lavf61.7.100\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=Intro\n"
        + "CHAPTER001=00:01:30.500\nCHAPTER001NAME=Verse\n"
    )
    assert (to_vorbis.notes, written.notes) == (
        (),
        (
            "chapter ends: Vorbis comments hold none (a chapter ends where the next begins): left out",
        ),
    )
    to_cue = convert(meta, "ffmetadata", "cue", media="song.flac")
    assert cue.write(to_cue.meta).text == (
        'PERFORMER "Band"\nFILE "song.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Intro"\n'
        + '    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Verse"\n    INDEX 01 01:30:38\n'
    )
    assert to_cue.notes == (
        *(
            f"the tag '{name}': no cue field: left out"
            for name in ("title", "artist", "track", "comment", "encoder")
        ),
        "chapter 2's end: a cue's last track ends with its media: left out",
        "chapter 2 starts between frames (1/75 s): at the nearest, frame 6788",
    )


def test_the_vorbis_skills_example_into_ffmetadata_and_cue() -> None:
    meta = vorbis.read(COMMENTS, "a.txt")
    to_ffmetadata = convert(meta, "vorbis", "ffmetadata")
    assert ffmetadata.write(to_ffmetadata.meta, Fraction(3000)).text == (
        ";FFMETADATA1\nTITLE=The Long Way\nARTIST=Ana Souza\\;Rui Lima\nDATE=2026-10-03\ntrack=1\n"
        + "TRACKTOTAL=12\ncomment=Unabridged\\\nread by the authors\n"
        + "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=750000\ntitle=Departure\n"
        + "[CHAPTER]\nTIMEBASE=1/1000\nSTART=750000\nEND=2465500\ntitle=The Road\n"
        + "[CHAPTER]\nTIMEBASE=1/1000\nSTART=2465500\nEND=3000000\ntitle=Arrival\n"
    )
    assert to_ffmetadata.notes == ("a tag 'ARTIST': 2 values joined with ';', one a key",)
    to_cue = convert(meta, "vorbis", "cue", media="book.opus")
    assert cue.write(to_cue.meta).text == (
        'REM DATE 2026-10-03\nFILE "book.opus" WAVE\n  TRACK 01 AUDIO\n    TITLE "Departure"\n'
        + '    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "The Road"\n    INDEX 01 12:30:00\n'
        + '  TRACK 03 AUDIO\n    TITLE "Arrival"\n    INDEX 01 41:05:38\n'
    )
    assert (
        to_cue.notes[-1] == "chapter 3 starts between frames (1/75 s): at the nearest, frame 184913"
    )


# (B) the rows


def test_the_same_format_is_no_conversion() -> None:
    meta = Metadata((Tag("a", "1"),))
    assert all(convert(meta, f, f, media="m") == convert(meta, f, f) for f in FORMATS)
    assert convert(meta, "vorbis", "vorbis").meta is meta


def test_ffmpegs_four_names_both_ways_any_case() -> None:
    generic = Metadata(
        tuple(Tag(g.upper() if n % 2 else g, str(n)) for n, (g, _) in enumerate(RENAMED))
    )
    there = convert(generic, "ffmetadata", "vorbis").meta
    assert [t.name for t in there.tags] == [v for _, v in RENAMED]
    back = convert(
        Metadata(tuple(Tag(v.lower(), "x") for _, v in RENAMED)), "vorbis", "ffmetadata"
    ).meta
    assert [t.name for t in back.tags] == [g for g, _ in RENAMED]


def test_comment_and_description_meet_and_are_joined() -> None:
    converted = convert(
        Metadata((Tag("COMMENT", "a"), Tag("DESCRIPTION", "b"))), "vorbis", "ffmetadata"
    )
    assert converted.meta.tags == (Tag("COMMENT", "a;b"),)
    assert converted.notes == ("a tag 'COMMENT': 2 values joined with ';', one a key",)


def test_a_chapters_title_and_name() -> None:
    chapter = Chapter(Fraction(1), Fraction(2), (Tag("Title", "t"), Tag("artist", "a")))
    there = convert(Metadata(chapters=(chapter,)), "ffmetadata", "vorbis").meta
    assert there.chapters[0].tags == (
        Tag("NAME", "t"),
        Tag("artist", "a"),
    )  # the writer notes 'artist'
    assert convert(there, "vorbis", "ffmetadata").meta.chapters == (
        Chapter(Fraction(1), Fraction(2), (Tag("title", "t"), Tag("artist", "a"))),
    )


def test_an_ffmetadata_chapters_name_is_no_vorbis_title() -> None:
    chapter = Chapter(Fraction(0), None, (Tag("Name", "a key"), Tag("title", "t")))
    converted = convert(Metadata(chapters=(chapter,)), "ffmetadata", "vorbis")
    assert converted.meta.chapters[0].tags == (Tag("NAME", "t"),)
    assert converted.notes == ("chapter 1's tag 'Name': Vorbis' NAME is a title: left out",)


def test_a_multi_file_sheet_is_placed_by_its_files_durations() -> None:
    sheet = cue.read(
        'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 00 02:47:74\n'
        + 'FILE "2.wav" WAVE\n    INDEX 01 00:00:00\n  TRACK 03 AUDIO\n    INDEX 01 01:00:00\n',
        "a.cue",
    )
    converted = convert(sheet, "cue", "ffmetadata", durations=(Fraction(170),))
    assert [(c.start, c.end) for c in converted.meta.chapters] == [
        (Fraction(0), Fraction(170)),
        (Fraction(170), Fraction(230)),
        (Fraction(230), None),
    ]
    assert converted.notes[-1] == "the 2 FILEs' bounds: chapters are of one stream: left out"
    with pytest.raises(
        ffmeta.Error,
        match=r"^a cue sheet over 2 files: its tracks are placed by the durations of the first 1, 0 given$",
    ):
        _ = convert(sheet, "cue", "vorbis")


@pytest.mark.parametrize(
    ("lines", "note"),
    [
        ("    FLAGS DCP\n", "FLAGS, track 01: chapters hold none: left out"),
        ("    PREGAP 00:02:00\n", "PREGAP, track 01: chapters hold none: left out"),
        ("    POSTGAP 00:02:00\n", "POSTGAP, track 01: chapters hold none: left out"),
    ],
)
def test_what_only_a_cues_layout_holds_is_noted(lines: str, note: str) -> None:
    before, after = (lines, "") if "POSTGAP" not in lines else ("", lines)
    sheet = cue.read(
        f'FILE "a" WAVE\n  TRACK 01 MODE1/2352\n{before}    INDEX 01 00:00:00\n    INDEX 02 00:01:00\n{after}',
        "a.cue",
    )
    notes = convert(sheet, "cue", "ffmetadata").notes
    assert note in notes
    assert "INDEX 02 and after, track 01: chapters hold none: left out" in notes
    assert "a data mode, track 01: chapters hold none: left out" in notes


def test_track_one_index_00_at_0_is_kept_others_noted() -> None:
    kept = cue.read(
        'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:30:00\n', "a.cue"
    )
    assert convert(kept, "cue", "ffmetadata").notes == ()
    zero = cue.read(
        'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:00:00\n', "a.cue"
    )
    assert convert(zero, "cue", "ffmetadata").notes == (
        "INDEX 00 (a pregap: the chapter before's, as mpv and Kodi place it), track 01: chapters hold none: left out",
    )


def test_numbers_not_from_1_and_cdtextfile_and_libcues_cdtext() -> None:
    sheet = cue.read(
        'CDTEXTFILE "d.cdt"\nFILE "a" WAVE\n  TRACK 05 AUDIO\n    COMPOSER "c"\n    INDEX 01 00:00:00\n',
        "a.cue",
    )
    assert convert(sheet, "cue", "vorbis").notes == (
        "the disc's CDTEXTFILE: none maps it: left out",
        "track 05's COMPOSER: none maps it: left out",
        "the track numbers: chapters count from 1, these from 05: left out",
    )


def test_into_a_cue_the_rems_quoting_and_the_catalog() -> None:
    tags = (
        Tag("GENRE", "Alternative Rock"),
        Tag("DATE", "1991"),
        Tag("DISCNUMBER", "1"),
        Tag("REPLAYGAIN_ALBUM_GAIN", "-7.03 dB"),
        Tag("BARCODE", "123"),
        Tag("genre", "again"),
    )
    converted = convert(Metadata(tags), "vorbis", "cue", media="m.flac")
    assert converted.meta.disc is not None
    assert converted.meta.disc.rems == (
        'GENRE "Alternative Rock"',
        "DATE 1991",
        "DISCNUMBER 1",
        "REPLAYGAIN_ALBUM_GAIN -7.03 dB",
    )
    assert converted.meta.disc.catalog == "123"  # the cue writer notes a CATALOG not 13 digits
    assert converted.notes == (
        "the tag 'genre': again: a cue holds one REM GENRE: left out",
        "no chapters: a cue sheet lays out tracks, so one, at 0",
    )
    quoted = convert(Metadata((Tag("genre", 'say "hi" now'),)), "ffmetadata", "cue", media="m")
    assert quoted.notes[0] == "the tag 'genre': a quote and a space: no REM quotes it: left out"


def test_into_a_cue_chapters_ordered_gapped_rounded_and_past_99() -> None:
    chapters = (
        Chapter(Fraction(30), Fraction(40)),
        Chapter(Fraction(10), Fraction(20)),
        Chapter(Fraction(1, 1000), None),
    )
    converted = convert(Metadata(chapters=chapters), "ffmetadata", "cue", media="m")
    assert converted.meta.disc is not None
    assert [[(i.number, i.frames) for i in t.indexes] for t in converted.meta.disc.tracks] == [
        [(1, 0)],
        [(1, 750)],
        [(1, 2250)],
    ]
    assert converted.notes == (
        "the chapters: not in time order, so reordered: a cue's tracks run in time",
        "chapter 3's end: a cue's last track ends with its media: left out",
        "chapter 2's end: a gap: a track ends where the next starts: left out",
        "chapter 1 starts between frames (1/75 s): at the nearest, frame 0",
    )
    many = convert(
        Metadata(chapters=tuple(Chapter(Fraction(n), None) for n in range(101))),
        "vorbis",
        "cue",
        media="m",
    )
    assert many.notes == ("chapters 100 to 101: a cue sheet holds 99 tracks: left out",)
    first_late = convert(
        Metadata(chapters=(Chapter(Fraction(30), None),)), "vorbis", "cue", media="m"
    )
    assert first_late.meta.disc is not None
    assert first_late.meta.disc.tracks[0].indexes == (Index(0, 0, 0), Index(1, 2250, 0))


def test_a_chapters_tags_into_a_track_and_streams_noted() -> None:
    chapter = Chapter(
        Fraction(0),
        None,
        (
            Tag("title", "t"),
            Tag("performer", "p"),
            Tag("ISRC", "GBAYE7900001"),
            Tag("TITLE", "u"),
            Tag("x", "y"),
        ),
    )
    converted = convert(
        Metadata(streams=((Tag("s", "1"),),), chapters=(chapter,)), "ffmetadata", "cue", media="m"
    )
    assert converted.meta.disc is not None
    assert converted.meta.disc.tracks[0] == Track(
        1,
        "AUDIO",
        (Index(1, 0, 0),),
        (Tag("TITLE", "t"), Tag("PERFORMER", "p")),
        isrc="GBAYE7900001",
    )
    assert converted.notes == (
        "streams' tags: a cue sheet holds the disc's and its tracks': left out",
        "chapter 1's tag 'TITLE': again: a track holds one TITLE: left out",
        "chapter 1's tag 'x': no cue field: left out",
    )


def test_what_is_a_bug() -> None:
    with pytest.raises(ValueError, match=r"^a cue sheet names its media: media is empty$"):
        _ = convert(Metadata(), "vorbis", "cue")
    with pytest.raises(ValueError, match=r"^a cue sheet's model holds a disc$"):
        _ = convert(Metadata(), "cue", "vorbis")


# (C) exact where lossless; (D) each loss noted -- by meaning: names without case, ffmpeg's
# four and a chapter's title as one, an end at the next start, track 1's INDEX 00 at 0, files
# counted (the media is the target's)

_GENERIC = {folded(vorbis_name): generic for generic, vorbis_name in RENAMED}
_TITLE = {"ffmetadata": "title", "vorbis": "name"}  # a chapter's title, in each format's words


def _meaning(meta: Metadata, fmt: Format) -> object:
    def name(raw: str) -> str:
        return _GENERIC.get(folded(raw), folded(raw))

    def chapter_name(raw: str) -> str:
        return "<title>" if folded(raw) == _TITLE.get(fmt) else name(raw)

    tags = tuple((name(t.name), t.value) for t in meta.tags)
    nexts = [c.start for c in meta.chapters[1:]] + [None]
    chapters = tuple(
        (
            c.start,
            None if c.end == after else c.end,
            tuple((chapter_name(t.name), t.value) for t in c.tags),
        )
        for c, after in zip(meta.chapters, nexts, strict=False)
    )
    disc = meta.disc
    if disc is None:
        return tags, meta.streams, chapters, None
    tracks: list[object] = []
    for t in disc.tracks:
        indexes = t.indexes
        if (
            t is disc.tracks[0]
            and len(indexes) > 1
            and indexes[0].frames == indexes[0].file == indexes[1].file == 0 < indexes[1].frames
        ):
            indexes = indexes[1:]
        tracks.append(
            (t.number, t.mode, indexes, t.cdtext, t.rems, t.flags, t.isrc, t.pregap, t.postgap)
        )
    return (
        tags,
        meta.streams,
        chapters,
        (len(disc.files), tuple(tracks), disc.cdtext, disc.rems, disc.catalog, disc.cdtextfile),
    )


def _durations(meta: Metadata) -> tuple[Fraction, ...]:
    """Each file but the last as long as its last index, and a frame."""
    disc = meta.disc
    if disc is None:
        return ()
    files = range(len(disc.files) - 1)
    return tuple(
        Fraction(max(i.frames for t in disc.tracks for i in t.indexes if i.file == f) + 1, 75)
        for f in files
    )


def _there_and_back(
    meta: Metadata, source: Format, target: Format
) -> tuple[Metadata, tuple[str, ...]]:
    media = meta.disc.files[0].name if meta.disc is not None else "media.flac"
    there = convert(meta, source, target, media=media, durations=_durations(meta))
    back = convert(there.meta, target, source, media=media)
    return back.meta, there.notes + back.notes


@settings(max_examples=200, deadline=None)
@given(whole_cue_models())
def test_a_whole_disc_through_ffmetadata_is_exact(meta: Metadata) -> None:
    assert _there_and_back(meta, "cue", "ffmetadata") == (meta, ())


@settings(max_examples=200, deadline=None)
@given(whole_cue_models(track_fields=False))
def test_a_whole_disc_through_vorbis_is_exact(meta: Metadata) -> None:
    assert _there_and_back(meta, "cue", "vorbis") == (meta, ())


_TAKEN = {folded(v) for _, v in RENAMED} | {folded(g) for g, _ in RENAMED}


@settings(max_examples=200, deadline=None)
@given(ffmetadata_models().filter(lambda m: not any(folded(t.name) in _TAKEN for t in m.tags)))
def test_ffmetadata_through_vorbis_means_the_same(meta: Metadata) -> None:
    back, notes = _there_and_back(meta, "ffmetadata", "vorbis")
    assert notes == ()
    assert _meaning(back, "ffmetadata") == _meaning(meta, "ffmetadata")  # TITLE back: title


@settings(max_examples=200, deadline=None)
@given(vorbis_models().filter(lambda m: len({folded(t.name) for t in m.tags}) == len(m.tags)))
def test_vorbis_once_each_through_ffmetadata_means_the_same(meta: Metadata) -> None:
    back, notes = _there_and_back(meta, "vorbis", "ffmetadata")
    assert notes == ()
    assert _meaning(back, "vorbis") == _meaning(
        meta, "vorbis"
    )  # a chapter's NAME back as written: NAME


@settings(max_examples=200, deadline=None)
@given(whole_cue_models())
def test_ffmetadata_a_cue_holds_through_a_cue_is_exact(disc: Metadata) -> None:
    meta = convert(disc, "cue", "ffmetadata").meta  # tags and chapters a cue holds whole
    assert _there_and_back(meta, "ffmetadata", "cue") == (meta, ())


@settings(max_examples=200, deadline=None)
@given(whole_cue_models(track_fields=False))
def test_vorbis_a_cue_holds_through_a_cue_is_exact(disc: Metadata) -> None:
    meta = convert(disc, "cue", "vorbis").meta
    assert _there_and_back(meta, "vorbis", "cue") == (meta, ())


@pytest.mark.parametrize(("source", "target"), [(s, t) for s in FORMATS for t in FORMATS if s != t])
def test_each_loss_is_noted(source: Format, target: Format) -> None:
    strategy = {"ffmetadata": ffmetadata_models(), "vorbis": vorbis_models(), "cue": cue_models()}[
        source
    ]

    @settings(max_examples=300, deadline=None)
    @given(strategy)
    def noted(meta: Metadata) -> None:
        back, notes = _there_and_back(meta, source, target)
        assert notes or _meaning(back, source) == _meaning(meta, source)

    noted()


def test_chapters_past_a_cues_last_time_are_left_out_noted() -> None:
    starts = (0, 60 * 10**6, 70 * 10**6)  # the last two past 999999:59:74 (about 60 million s)
    far = Metadata(chapters=tuple(Chapter(Fraction(start), None) for start in starts))
    done = convert(far, "ffmetadata", "cue", media="m.flac")
    assert done.meta.disc is not None
    assert len(done.meta.disc.tracks) == 1
    assert "chapters 2 to 3: past a cue's last time (999999:59:74): left out" in done.notes
