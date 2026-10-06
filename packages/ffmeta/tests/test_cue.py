import re
from collections.abc import Callable
from fractions import Fraction

import ffmeta
import pytest
from ffmeta import cue
from ffmeta.model import Chapter, Disc, File, Index, Metadata, Tag, Track, Written
from ffmeta_support.examples import CUE as EXAMPLE
from ffmeta_support.metadata import cue_models
from hypothesis import given, settings

# every command, as EAC and CDRWIN place them
EVERY = """REM GENRE Ska
REM COMMENT "ExactAudioCopy v1.6"
CATALOG 0123456789012
CDTEXTFILE "disc.cdt"
PERFORMER "The Specials"
TITLE "Singles"
SONGWRITER "Dammers"
FILE "a.flac" WAVE
  TRACK 01 AUDIO
    FLAGS DCP PRE
    ISRC GBAYE7900001
    TITLE "Gangsters"
    REM REPLAYGAIN_TRACK_GAIN -6.00 dB
    PREGAP 00:02:00
    INDEX 01 00:00:00
    INDEX 02 00:30:00
    POSTGAP 00:01:00
  TRACK 02 MODE1/2352
    INDEX 00 02:47:74
    INDEX 01 02:48:27
"""


def read(text: str) -> Metadata:
    return cue.read(text, "a.cue")


def disc(text: str) -> Disc:
    found = read(text).disc
    assert found is not None
    return found


def refused(text: str, line: int, message: str) -> None:
    with pytest.raises(ffmeta.Error, match=rf"^{re.escape(f'a.cue:{line}: {message}')}$"):
        _ = read(text)


def one(*lines: str) -> str:
    """A one-track sheet with ``lines`` in its track, before its INDEX 01."""
    return (
        'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n'
        + "".join(f"    {line}\n" for line in lines)
        + "    INDEX 01 00:00:00\n"
    )


# (A) read


def test_the_skills_example_reads_as_the_skill_says_and_writes_back() -> None:
    found = disc(EXAMPLE)
    assert found.rems == ('GENRE "Alternative Rock"', "DATE 1991")
    assert found.cdtext == (Tag("PERFORMER", "My Band"), Tag("TITLE", "The Album"))
    assert found.files == (File("album.flac", "WAVE"),)
    assert [[(i.number, i.frames) for i in t.indexes] for t in found.tracks] == [
        [(1, 0)],
        [(0, 19125), (1, 19327)],
        [(1, 40724)],
    ]
    assert cue.write(Metadata(disc=found)) == Written(EXAMPLE)  # byte for byte


def test_every_command() -> None:
    found = disc(EVERY)
    assert (found.catalog, found.cdtextfile) == ("0123456789012", "disc.cdt")
    assert found.rems == ("GENRE Ska", 'COMMENT "ExactAudioCopy v1.6"')
    assert found.cdtext == (
        Tag("PERFORMER", "The Specials"),
        Tag("TITLE", "Singles"),
        Tag("SONGWRITER", "Dammers"),
    )
    assert found.tracks == (
        Track(
            1,
            "AUDIO",
            (Index(1, 0, 0), Index(2, 2250, 0)),
            (Tag("TITLE", "Gangsters"),),
            ("REPLAYGAIN_TRACK_GAIN -6.00 dB",),
            ("DCP", "PRE"),
            "GBAYE7900001",
            150,
            75,
        ),
        Track(2, "MODE1/2352", (Index(0, 12599, 0), Index(1, 12627, 0))),
    )
    assert cue.write(Metadata(disc=found)) == Written(EVERY)


def test_case_crlf_a_bom_tabs_and_blank_lines_read_alike() -> None:
    plain = read(EVERY)
    lower = re.sub(r"^(\s*)([A-Z]+)", lambda m: m[1] + m[2].lower(), EVERY, flags=re.MULTILINE)
    assert read(lower) == plain
    assert read("\ufeff" + EVERY.replace("\n", "\r\n")) == plain
    assert read(EVERY.replace("    ", "\t\t").replace("  ", "\t") + "\n\n  \t\n") == plain


def test_a_last_line_without_its_break_reads_the_same() -> None:
    assert read(EXAMPLE.removesuffix("\n")) == read(EXAMPLE)


def test_strings_quoted_or_to_the_end_of_their_line() -> None:
    found = disc(
        'FILE my\tfile.wav\tWAVE\n  TRACK 01 AUDIO\n    TITLE Theme Of "Rome"\n    PERFORMER ""\n    SONGWRITER "  spaced  "\n    INDEX 01 00:00:00\n'
    )
    assert found.files == (File("my\tfile.wav", "WAVE"),)
    assert found.tracks[0].cdtext == (
        Tag("TITLE", 'Theme Of "Rome"'),
        Tag("PERFORMER", ""),
        Tag("SONGWRITER", "  spaced  "),
    )


def test_eacs_layouts_a_hidden_track_and_libcues_cdtext() -> None:
    noncompliant = 'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 00 02:47:74\nFILE "2.wav" WAVE\n    INDEX 01 00:00:00\n'
    assert disc(noncompliant).tracks[1].indexes == (Index(0, 12599, 0), Index(1, 0, 1))
    prepended = 'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "2.wav" WAVE\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:00:28\n'
    assert disc(prepended).tracks[1].indexes == (Index(0, 0, 1), Index(1, 28, 1))
    hidden = 'FILE "a.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 03:22:70\n'
    assert disc(hidden).tracks[0].indexes == (Index(0, 0, 0), Index(1, 15220, 0))
    assert disc(one('COMPOSER "c"', "MESSAGE m")).tracks[0].cdtext == (
        Tag("COMPOSER", "c"),
        Tag("MESSAGE", "m"),
    )


def test_where_rem_and_the_discs_lines_go() -> None:
    found = disc(
        'FILE "a.wav" WAVE\nREM DATE 1991\nTITLE "Album"\nCATALOG 0123456789012\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n    REM after its index\nREM\n'
    )
    assert (found.rems, found.cdtext, found.catalog) == (
        ("DATE 1991",),
        (Tag("TITLE", "Album"),),
        "0123456789012",
    )
    assert found.tracks[0].rems == ("after its index", "")


# (B) refused, the line named


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("", 1, "no TRACK: a cue sheet lays out tracks"),
        ("REM nothing\n", 1, "no TRACK: a cue sheet lays out tracks"),
        (
            'FILE "a" WAVE\r  TRACK 01 AUDIO\n',
            1,
            "a carriage return alone: lines end with LF or CR LF",
        ),
        (one("TITLE a\0b"), 3, "a NUL"),
        (one("BOGUS 1"), 3, "not a cue command: BOGUS"),
        (one('\u00a0TITLE "x"'), 3, 'not a cue line:     \\xa0TITLE "x"'),
        (one("\f"), 3, "not a cue line:     \\x0c"),
        (
            'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n    TITLE "x"\n',
            4,
            "TITLE after an INDEX: a track's comes before",
        ),
        (one('TITLE "x"', 'title "y"'), 4, "TITLE again: once the disc's, once each track's"),
        (one("TITLE"), 3, "TITLE without its value"),
        (one('TITLE "x'), 3, "TITLE's quote not closed: \"x"),
        (one('TITLE "x" y'), 3, 'TITLE: text after its quoted value: "x" y'),
        (one("CATALOG 0123456789012"), 3, "CATALOG after a TRACK: it is the disc's"),
        ("CATALOG 0123456789012\nCATALOG 0123456789012\n", 2, "CATALOG again"),
        ("CATALOG 123\n", 1, "CATALOG is 13 digits: 123"),
        ('CDTEXTFILE "a"\nCDTEXTFILE "b"\n', 2, "CDTEXTFILE again"),
        ("FILE a.wav\n", 1, "FILE is a name and a type: a.wav"),
        ('FILE "a.wav WAVE\n', 1, "FILE's quote not closed: \"a.wav WAVE"),
        ('FILE "a.wav" WAVE MP3\n', 1, 'FILE is a name and a type: "a.wav" WAVE MP3'),
        ('FILE "a" WAVE\nFILE "b" WAVE\n', 1, "a FILE no INDEX follows"),
        (one() + 'FILE "b" WAVE\n', 4, "a FILE no INDEX follows"),
        ("TRACK 01 AUDIO\n", 1, "TRACK before any FILE"),
        ('FILE "a" WAVE\n  TRACK 01\n', 2, "TRACK is a number 01-99 and a mode: 01"),
        ('FILE "a" WAVE\n  TRACK 100 AUDIO\n', 2, "TRACK is a number 01-99 and a mode: 100 AUDIO"),
        ('FILE "a" WAVE\n  TRACK 00 AUDIO\n', 2, "TRACK is a number 01-99 and a mode: 00 AUDIO"),
        (one() + "  TRACK 03 AUDIO\n", 4, "TRACK 03 after TRACK 01: one more each"),
        ('FILE "a" WAVE\n  TRACK 01 AUDIO\n  TRACK 02 AUDIO\n', 2, "TRACK 01 without INDEX 01"),
        (
            'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n',
            2,
            "TRACK 01 without INDEX 01",
        ),
        ("FLAGS DCP\n", 1, "FLAGS outside a TRACK's lines before its INDEX"),
        (one() + "    ISRC GBAYE7900001\n", 4, "ISRC outside a TRACK's lines before its INDEX"),
        (one("FLAGS DCP", "FLAGS PRE"), 4, "FLAGS again"),
        (one("FLAGS DCP COPY"), 3, "FLAGS are DCP, 4CH, PRE, SCMS, each once: DCP COPY"),
        (one("FLAGS PRE pre"), 3, "FLAGS are DCP, 4CH, PRE, SCMS, each once: PRE pre"),
        (one("FLAGS"), 3, "FLAGS are DCP, 4CH, PRE, SCMS, each once: "),
        (one("ISRC GBAYE7900001", "ISRC GBAYE7900002"), 4, "ISRC again"),
        (one("ISRC GB-AYE-79-00001"), 3, "ISRC is 12 characters, CCOOOYYSSSSS: GB-AYE-79-00001"),
        (one("PREGAP 00:02:00", "PREGAP 00:02:00"), 4, "PREGAP again"),
        ("INDEX 01 00:00:00\n", 1, "INDEX before any TRACK"),
        (one("INDEX 01"), 3, "INDEX is a number 00-99 and a time: 01"),
        (one("INDEX 02 00:00:00"), 3, "INDEX 02 here: 00 or 01"),
        (one() + "    INDEX 03 00:01:00\n", 4, "INDEX 03 here: 02"),
        (one() + "    POSTGAP 00:01:00\n    INDEX 02 00:02:00\n", 5, "INDEX after POSTGAP"),
        (
            'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:10:00\n  TRACK 02 AUDIO\n    INDEX 01 00:05:00\n',
            5,
            "INDEX 01 goes back in its FILE: 00:05:00",
        ),
        (one("INDEX 00 00:60:00"), 3, "a time's seconds run to 59, its frames to 74: 00:60:00"),
        (one("INDEX 00 00:00:75"), 3, "a time's seconds run to 59, its frames to 74: 00:00:75"),
        (one("INDEX 00 1:2:3"), 3, "a time is mm:ss:ff: 1:2:3"),
        (one("INDEX 00 1234567:00:00"), 3, "a time is mm:ss:ff: 1234567:00:00"),
        (
            one() + 'FILE "b" WAVE\n    INDEX 02 00:00:00\n',
            5,
            "INDEX 02 in a FILE after its INDEX 01's: libcue reads it in that one",
        ),
        (one("POSTGAP 00:01:00"), 3, "POSTGAP before its TRACK's INDEX"),
        (one() + "    POSTGAP 00:01:00\n    POSTGAP 00:01:00\n", 5, "POSTGAP again"),
    ],
)
def test_what_cannot_be_placed(text: str, line: int, message: str) -> None:
    refused(text, line, message)


# (C) the writer


def test_what_a_cue_sheet_does_not_hold_is_noted() -> None:
    meta = Metadata((Tag("a", "1"),), ((Tag("b", "2"),),), (Chapter(Fraction(0), None),))
    assert cue.write(meta) == Written(
        "",
        (
            "the global tags: a cue sheet holds its disc alone (a conversion makes its lines): left out",
            "streams' tags: a cue sheet holds its disc alone (a conversion makes its lines): left out",
            "chapters: a cue sheet holds its disc alone (a conversion makes its lines): left out",
            "no disc with tracks: no cue sheet",
        ),
    )
    assert cue.write(Metadata(disc=Disc((), ()))) == Written(
        "", ("no disc with tracks: no cue sheet",)
    )


def _written(
    *,
    cdtext: tuple[Tag, ...] = (),
    rems: tuple[str, ...] = (),
    flags: tuple[str, ...] = (),
    isrc: str | None = None,
) -> Written:
    """A one-track disc with these values, written."""
    track = Track(1, "AUDIO", (Index(1, 0, 0),), cdtext, rems, flags, isrc)
    return cue.write(Metadata(disc=Disc((File("a.flac", "WAVE"),), (track,))))


def test_values_no_reader_takes_are_noted_and_left_out() -> None:
    written = _written(
        cdtext=(
            Tag("TITLE", 'say "hi"'),
            Tag("PERFORMER", "a\nb"),
            Tag("SONGWRITER", "ends\\"),
            Tag("COMPOSER", "c"),
            Tag("LYRICS", "l"),
            Tag("title", "again"),
        ),
        rems=("fine", "two\nlines"),
        flags=("DCP", "COPY"),
        isrc="nope",
    )
    assert (
        written.text
        == 'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "again"\n    REM fine\n    INDEX 01 00:00:00\n'
    )
    quote = "a quote, a line break or a NUL, which no cue string holds"
    assert written.notes == (
        "track 01's FLAGS 'DCP COPY': flags are DCP, 4CH, PRE, SCMS: left out",
        "track 01's ISRC 'nope': not CCOOOYYSSSSS: left out",
        f"track 01's TITLE: {quote}: left out",
        f"track 01's PERFORMER: {quote}: left out",
        "track 01's SONGWRITER: it ends in '\\': libcue reads the rest of the sheet into it: left out",
        "track 01's COMPOSER: libcue's alone: mpv refuses a sheet with it: left out",
        "track 01's LYRICS: no cue command: left out",
        "track 01's REM 'two\\nlines': a line break or a NUL: left out",
    )


def test_a_rems_spaces_at_either_end_are_trimmed_and_noted() -> None:
    written = _written(rems=(" padded\t", "plain"))
    assert "    REM padded\n    REM plain\n" in written.text
    assert written.notes == (
        "track 01's REM ' padded\\t': spaces at either end, which readers drop: trimmed",
    )
    assert disc(written.text).tracks[0].rems == ("padded", "plain")


def test_a_value_over_80_characters_is_kept_and_noted() -> None:
    written = _written(cdtext=(Tag("TITLE", "x" * 81),))
    assert '    TITLE "' + "x" * 81 + '"\n' in written.text
    assert written.notes == ("track 01's TITLE: over 80 characters, CD-Text's most: kept",)


def test_the_discs_own_lines_and_a_repeat() -> None:
    meta = Metadata(
        disc=Disc(
            (File("a.flac", "WAVE"),),
            (Track(1, "AUDIO", (Index(1, 0, 0),)),),
            (Tag("TITLE", "a"), Tag("TITLE", "b")),
            ("x\ny",),
            "12345",
            'c"t',
        )
    )
    written = cue.write(meta)
    assert (
        written.text == 'TITLE "a"\nFILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
    )
    assert written.notes == (
        "the disc's REM 'x\\ny': a line break or a NUL: left out",
        "the CATALOG '12345': not 13 digits: left out",
        "the CDTEXTFILE: a quote, a line break or a NUL, which no cue string holds: left out",
        "the disc's TITLE: again: once each: left out",
    )


def test_eacs_index_00_in_the_file_before_is_left_out() -> None:
    found = disc(
        'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 00 02:47:74\nFILE "2.wav" WAVE\n    INDEX 01 00:00:00\n'
    )
    written = cue.write(Metadata(disc=found))
    assert (
        written.text
        == 'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "2.wav" WAVE\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n'
    )
    assert written.notes == (
        "track 02's INDEX 00: in the file before its INDEX 01's: Kodi and foobar2000 refuse that, libcue misplaces the tracks after: left out",
    )


_UNQUOTED = "the FILE '{}': unquoted, for a quote or a final '\\' in it: {}"


@pytest.mark.parametrize(
    ("name", "line", "notes"),
    [
        ("plain name.flac", 'FILE "plain name.flac" WAVE', ()),
        (
            'say"hi.flac',
            'FILE say"hi.flac WAVE',
            (_UNQUOTED.format('say"hi.flac', "mpv reads no name"),),
        ),
        ("ends\\", "FILE ends\\ WAVE", (_UNQUOTED.format("ends\\", "mpv reads no name"),)),
        (
            'a "b" c',
            'FILE a "b" c WAVE',
            (_UNQUOTED.format('a "b" c', "mpv and libcue read no name"),),
        ),
        (
            "a b\\",
            "FILE a b\\ WAVE",
            (_UNQUOTED.format("a b\\", "mpv and libcue read no name"),),
        ),
    ],
)
def test_a_file_name_no_quote_holds_safely(name: str, line: str, notes: tuple[str, ...]) -> None:
    written = cue.write(
        Metadata(
            disc=Disc(
                (File(name, "wave"),), (Track(1, "audio", (Index(1, 0, 0),), flags=("pre",)),)
            )
        )
    )
    assert (
        written.text == f"{line}\n  TRACK 01 AUDIO\n    FLAGS PRE\n    INDEX 01 00:00:00\n"
    )  # keywords upper
    assert written.notes == notes
    assert disc(written.text).files == (File(name, "WAVE"),)  # read back as written


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: Disc((File("a\nb", "WAVE"),), (Track(1, "AUDIO", (Index(1, 0, 0),)),)),
            r"^a FILE name no cue sheet holds: 'a\\nb'$",
        ),
        (
            lambda: Disc((File(" a", "WAVE"),), (Track(1, "AUDIO", (Index(1, 0, 0),)),)),
            r"^a FILE name no cue sheet holds: ' a'$",
        ),
        (
            lambda: Disc((File('"a', "WAVE"),), (Track(1, "AUDIO", (Index(1, 0, 0),)),)),
            r"^a FILE name no cue sheet holds: '\"a'$",
        ),
        (
            lambda: Disc(
                (File("a", "WAVE"),), (Track(1, "AUDIO", (Index(1, 75 * 60 * 1_000_000, 0),)),)
            ),
            r"^a cue time past 999999 minutes: 4500000000 frames$",
        ),
    ],
)
def test_what_no_reader_produces_is_a_bug(build: Callable[[], Disc], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = cue.write(Metadata(disc=build()))


# (D) round trip


@settings(max_examples=300, deadline=None)
@given(cue_models())
def test_what_the_writer_writes_the_reader_reads_back_exactly(meta: Metadata) -> None:
    written = cue.write(meta)
    assert written.notes == ()
    assert read(written.text) == meta
    assert cue.write(read(written.text)).text == written.text
