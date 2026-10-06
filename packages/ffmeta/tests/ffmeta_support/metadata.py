"""Hypothesis strategies: metadata as each format can hold it."""

from fractions import Fraction
from typing import Final

from ffmeta.model import Chapter, Disc, File, Index, Metadata, Tag, Tags, Track, folded
from hypothesis import strategies as st

# every character ffmetadata escapes, a line's ends, case pairs, and text past ASCII
ALPHABET: Final = "aAbB =;#\\\n\r[]é日Íí"
# the time bases the formats bring: seconds, cue frames, milliseconds, both, samples, a prime
DENOMINATORS: Final = (1, 75, 1000, 3000, 44100, 7)

TEXT = st.text(alphabet=ALPHABET, max_size=12)


@st.composite
def tag_lists(draw: st.DrawFn, *, value: st.SearchStrategy[str] = TEXT) -> Tags:
    """Tags whose names differ but for case (ffmetadata keeps one value a key)."""
    names = draw(st.lists(TEXT, max_size=5, unique_by=folded))
    return tuple(Tag(name, draw(value)) for name in names)


@st.composite
def times(draw: st.DrawFn) -> Fraction:
    """A time in seconds, exact: a whole number of one format's units."""
    return Fraction(draw(st.integers(0, 10**7)), draw(st.sampled_from(DENOMINATORS)))


@st.composite
def ffmetadata_models(draw: st.DrawFn) -> Metadata:
    """What ffmetadata holds and ffmpeg reads back: no value ending in '\\', ends given."""
    value = TEXT.filter(lambda v: not v.endswith("\\"))
    chapters: list[Chapter] = []
    for _ in range(draw(st.integers(0, 4))):
        start = draw(times())
        end = start + draw(times())
        chapters.append(Chapter(start, end, draw(tag_lists(value=value))))
    streams = draw(st.lists(tag_lists(value=value), max_size=3))
    return Metadata(draw(tag_lists(value=value)), tuple(streams), tuple(chapters))


# a Vorbis name: ASCII 0x20-0x7D but '=' -- a few of each kind, case pairs, a space; and names
# that begin as a chapter's yet are tags, to ffmpeg's ogm_chapter and to ffman (shorter than 9;
# no digit for sscanf; longer than 10 and no NAME ending them). The alphabet spells neither
# "chapter" nor the four names ffmpeg renames (ALBUMARTIST, TRACKNUMBER, DISCNUMBER, DESCRIPTION).
PLAIN_CHAPTERISH: Final = (
    "CHAPTER", "Chapters", "CHAPTER1", "CHAPTERxyz", "CHAPTER1000", "chapter000artist", "CHAPTER001URLS",
)  # fmt: skip
VORBIS_NAME = st.text(alphabet="AaBbZz09 #;[]_-", min_size=1, max_size=8) | st.sampled_from(
    PLAIN_CHAPTERISH
)


@st.composite
def vorbis_models(draw: st.DrawFn) -> Metadata:
    """What ffman's Vorbis form holds: names repeated, any value but NUL, chapters at whole ms
    under 100 hours with a NAME and a URL at most, no end."""
    tags = draw(st.lists(st.builds(Tag, VORBIS_NAME, TEXT), max_size=6))
    chapters: list[Chapter] = []
    for _ in range(draw(st.integers(0, 4))):
        ms = draw(st.integers(0, 100 * 3_600_000 - 1))
        held = [
            Tag(draw(st.sampled_from(spellings)), draw(TEXT))
            for spellings in (("NAME", "name", "Name"), ("URL", "url"))
            if draw(st.booleans())
        ]
        chapters.append(Chapter(Fraction(ms, 1000), None, tuple(held)))
    return Metadata(tuple(tags), chapters=tuple(chapters))


# a cue string: what a quote holds -- no quote, no line break, no '\' ending it (libcue's escape);
# a REM's text: no space or tab at either end either (the reader takes a line's rest, trimmed)
CUE_TEXT = st.text(alphabet="aB 9#;\\é日\t", max_size=10).filter(
    lambda text: not text.endswith("\\")
)
REM_TEXT = CUE_TEXT.map(lambda text: text.strip(" \t"))
CUE_FILE = st.text(alphabet="aB9_-. é", min_size=1, max_size=8).map(str.strip).filter(bool)


@st.composite
def cue_models(draw: st.DrawFn) -> Metadata:
    """What ffman's cue writer writes back: tracks one more each, indexes 00-02, times never back
    in a file, a new file at a track's start (EAC's, between INDEX 00 and 01, it leaves out)."""
    files = [File(draw(CUE_FILE), draw(st.sampled_from(("WAVE", "MP3", "BINARY"))))]
    tracks: list[Track] = []
    frames = 0
    first = draw(st.integers(1, 99))  # to 99: the format's last track
    for number in range(first, first + draw(st.integers(1, min(4, 100 - first)))):
        indexes: list[Index] = []
        for index_number in (0, 1, 2):
            if (index_number == 0 and not draw(st.booleans())) or (
                index_number == 2 and draw(st.booleans())
            ):
                continue
            if not indexes and tracks and draw(st.integers(0, 3)) == 0:  # a new file, at a track
                files.append(File(draw(CUE_FILE), "WAVE"))
                frames = 0
            frames += draw(st.integers(0, 10**6))
            indexes.append(Index(index_number, frames, len(files) - 1))
        cdtext = [
            Tag(name, draw(CUE_TEXT))
            for name in ("TITLE", "PERFORMER", "SONGWRITER")
            if draw(st.booleans())
        ]
        tracks.append(
            Track(
                number,
                draw(st.sampled_from(("AUDIO", "MODE1/2352"))),
                tuple(indexes),
                tuple(cdtext),
                tuple(draw(st.lists(REM_TEXT, max_size=2))),
                tuple(draw(st.sets(st.sampled_from(("DCP", "4CH", "PRE", "SCMS"))))),
                draw(st.none() | st.from_regex(r"[A-Z0-9]{5}[0-9]{7}", fullmatch=True)),
                draw(st.none() | st.integers(0, 10**5)),
                draw(st.none() | st.integers(0, 10**5)),
            )
        )
    disc = Disc(
        tuple(files),
        tuple(tracks),
        tuple(
            Tag(name, draw(CUE_TEXT))
            for name in ("TITLE", "PERFORMER", "SONGWRITER")
            if draw(st.booleans())
        ),
        tuple(draw(st.lists(REM_TEXT, max_size=3))),
        draw(st.none() | st.from_regex(r"[0-9]{13}", fullmatch=True)),
        draw(st.none() | CUE_TEXT.filter(bool)),
    )
    return Metadata(disc=disc)


# a REM field's value for a disc chapters hold whole: words with single spaces, no quote
_REM_VALUE = st.from_regex(r"[A-Za-z0-9.-]+( [A-Za-z0-9.-]+)?", fullmatch=True)


@st.composite
def whole_cue_models(draw: st.DrawFn, *, track_fields: bool = True) -> Metadata:
    """A disc chapters hold whole: one file, tracks from 01, AUDIO, INDEX 01 rising (track 1's
    INDEX 00 at 0 when its 01 is after), the mapped fields alone, each REM in its written form
    (GENRE quoted when spaced). ``track_fields``: a track's PERFORMER, ISRC and gains too --
    ffmetadata's chapters hold them, Vorbis' a title alone."""
    tracks: list[Track] = []
    frames = 0
    for number in range(1, draw(st.integers(1, 5)) + 1):
        frames += draw(st.integers(0, 10**6))
        indexes = (Index(1, frames, 0),)
        if number == 1 and frames:
            indexes = (Index(0, 0, 0), *indexes)
        names = ("TITLE", "PERFORMER") if track_fields else ("TITLE",)
        cdtext = tuple(Tag(name, draw(CUE_TEXT)) for name in names if draw(st.booleans()))
        rems: tuple[str, ...] = ()
        isrc = None
        if track_fields:
            gains = ("REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_TRACK_PEAK")
            rems = tuple(f"{gain} {draw(_REM_VALUE)}" for gain in gains if draw(st.booleans()))
            isrc = draw(st.none() | st.from_regex(r"[A-Z0-9]{5}[0-9]{7}", fullmatch=True))
        tracks.append(Track(number, "AUDIO", indexes, cdtext, rems, isrc=isrc))
    genre = draw(_REM_VALUE)
    disc_rems = [f'GENRE "{genre}"' if " " in genre else f"GENRE {genre}"]
    disc_rems += [
        f"{word} {draw(_REM_VALUE)}" for word in ("DATE", "DISCNUMBER", "REPLAYGAIN_ALBUM_GAIN")
    ]
    disc = Disc(
        (File("media.flac", "WAVE"),),
        tuple(tracks),
        tuple(Tag(name, draw(CUE_TEXT)) for name in ("TITLE", "PERFORMER") if draw(st.booleans())),
        tuple(rem for rem in disc_rems if draw(st.booleans())),
        draw(st.none() | st.from_regex(r"[0-9]{13}", fullmatch=True)),
    )
    return Metadata(disc=disc)
