import re
from fractions import Fraction
from pathlib import Path

import ffmeta
import pytest
from ffmeta import vorbis
from ffmeta.model import Chapter, Disc, Metadata, Tag, Tags, Written, folded
from ffmeta_support.examples import VORBIS as EXAMPLE
from ffmeta_support.flac import with_comments
from ffmeta_support.media import metadata_seen
from ffmeta_support.metadata import vorbis_models
from hypothesis import given, settings


def read(text: str) -> Metadata:
    return vorbis.read(text, "tags.txt")


def refused(text: str, line: int, message: str) -> None:
    with pytest.raises(ffmeta.Error, match=rf"^{re.escape(f'tags.txt:{line}: {message}')}$"):
        _ = read(text)


def pairs(tags: Tags) -> list[tuple[str, str]]:
    return [(tag.name, tag.value) for tag in tags]


# (A) ffman's form, read


def test_the_skills_example_reads_as_the_skill_says() -> None:
    meta = read(EXAMPLE)
    assert pairs(meta.tags) == [
        ("TITLE", "The Long Way"),
        ("ARTIST", "Ana Souza"),
        ("ARTIST", "Rui Lima"),
        ("DATE", "2026-10-03"),
        ("TRACKNUMBER", "1"),
        ("TRACKTOTAL", "12"),
        ("DESCRIPTION", "Unabridged\nread by the authors"),
    ]
    assert meta.chapters == (
        Chapter(Fraction(0), None, (Tag("NAME", "Departure"),)),
        Chapter(Fraction(750), None, (Tag("NAME", "The Road"),)),
        Chapter(Fraction(4931, 2), None, (Tag("NAME", "Arrival"),)),
    )
    assert vorbis.write(meta) == Written(EXAMPLE)  # written back, byte for byte


def test_nothing_is_no_comment() -> None:
    assert read("") == Metadata()
    assert vorbis.write(Metadata()) == Written("")


def test_what_the_form_allows() -> None:
    text = "A Name=x\n#not a comment=y\nEmpty=\nk=a=b\nv=\\\\ \\n \\r\nCHAPTER000ARTIST=plain\nChapters=3\n"
    assert pairs(read(text).tags) == [
        ("A Name", "x"),
        ("#not a comment", "y"),
        ("Empty", ""),
        ("k", "a=b"),
        ("v", "\\ \n \r"),
        ("CHAPTER000ARTIST", "plain"),  # ffmpeg's own writer's, a tag to its reader
        ("Chapters", "3"),
    ]


def test_chapters_by_their_numbers_their_comments_without_case() -> None:
    text = "chapter002=00:00:02.000\nCHAPTER000=00:00:00.000\nchapter000name=a\nCHAPTER002Url=u\n"
    assert read(text).chapters == (
        Chapter(Fraction(0), None, (Tag("name", "a"),)),
        Chapter(Fraction(2), None, (Tag("Url", "u"),)),
    )


# (B) refused, the line named


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("a=1\nb=2", 2, "no line break ends the last line: every line ends with LF"),
        ("a=1\r\n", 1, "a carriage return: lines end with LF alone, a CR is \\r"),
        ("a=1\nb=x\0y\n", 2, "a NUL"),
        ("a=1\n\n", 2, "no '=': not a comment: "),
        ("a=1\njust words\n", 2, "no '=': not a comment: just words"),
        ("=v\n", 1, "an empty name"),
        ("a~b=v\n", 1, "a name of ASCII 0x20-0x7D but '=' and '~': a~b"),
        ("tí=v\n", 1, "a name of ASCII 0x20-0x7D but '=' and '~': tí"),
        ("a\tb=v\n", 1, "a name of ASCII 0x20-0x7D but '=' and '~': a\\tb"),
        ("\ufeffTITLE=v\n", 1, "a name of ASCII 0x20-0x7D but '=' and '~': \\ufeffTITLE"),
        (
            "A=1\rB=2\r",
            1,
            "a carriage return: lines end with LF alone, a CR is \\r",
        ),  # not the break
        ("a=x\\ty\n", 1, "an escape but \\\\, \\n, \\r: \\t"),
        ("a=x\\\n", 1, "a '\\' ending the line: it escapes nothing"),
    ],
)
def test_a_line_not_in_ffmans_form(text: str, line: int, message: str) -> None:
    refused(text, line, message)


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        ("CHAPTER000=1:00:00.000\n", 1, "a chapter's time is HH:MM:SS.mmm: 1:00:00.000"),
        ("CHAPTER000=00:00:01.5\n", 1, "a chapter's time is HH:MM:SS.mmm: 00:00:01.5"),
        ("CHAPTER000=00:60:00.000\n", 1, "a chapter's time is HH:MM:SS.mmm: 00:60:00.000"),
        ("CHAPTER000=00:00:00\n", 1, "a chapter's time is HH:MM:SS.mmm: 00:00:00"),
        ("CHAPTER000=00:00:00.000\nchapter000=00:00:01.000\n", 2, "chapter000 again (line 1)"),
        (
            "CHAPTER001NAME=a\nCHAPTER001=00:00:00.000\n",
            1,
            "CHAPTER001NAME before its time: a chapter's comments follow CHAPTER001",
        ),
        (
            "CHAPTER001URL=u\n",
            1,
            "CHAPTER001URL before its time: a chapter's comments follow CHAPTER001",
        ),
        (
            "CHAPTER001=00:00:00.000\nCHAPTER001NAME=a\nCHAPTER001name=b\n",
            3,
            "CHAPTER001name again: a chapter has one NAME and one URL",
        ),
    ],
)
def test_a_chapters_comments_in_the_extensions_form_and_order(
    text: str, line: int, message: str
) -> None:
    refused(text, line, message)


@pytest.mark.parametrize(
    "name",
    [
        "CHAPTER01",
        "CHAPTER 01",
        "CHAPTER+01",
        "CHAPTER1000NAME",
        "CHAPTER01NAME",
        "chapter001xname",
    ],
)
def test_a_name_ffmpeg_may_read_as_a_chapters_is_refused(name: str) -> None:
    message = f"not the Chapter Extension's form (CHAPTERxxx, three digits), yet ffmpeg reads it as a chapter's: {name}"
    refused(f"{name}=00:00:01.000\n", 1, message)


@pytest.mark.parametrize(
    "name",
    [
        "CHAPTER",
        "CHAPTER1",
        "CHAPTERS",
        "CHAPTER1000",
        "CHAPTER000ARTIST",
        "CHAPTERxyz",
        "CHAPTER001URLS",
    ],
)
def test_a_name_ffmpeg_reads_as_a_tag_is_one(name: str) -> None:
    assert pairs(read(f"{name}=v\n").tags) == [(name, "v")]


# (C) the writer


def test_the_writer_escapes_backslash_lf_cr() -> None:
    assert vorbis.write(Metadata((Tag("K", "a\\b\nc\rd=e"),))) == Written("K=a\\\\b\\nc\\rd=e\n")


def test_tags_the_form_cannot_hold_are_left_out_and_noted() -> None:
    meta = Metadata(
        (
            Tag("", "x"),
            Tag("a~b", "x"),
            Tag("tí", "x"),
            Tag("k", "a\0b"),
            Tag("CHAPTER001", "x"),
            Tag("chapter01", "x"),
            Tag("ok", "1"),
        )
    )
    written = vorbis.write(meta)
    assert written.text == "ok=1\n"
    not_a_name = "not a Vorbis name (ASCII 0x20-0x7D but '=' and '~')"
    assert written.notes == (
        f"a tag '': {not_a_name}: left out",
        f"a tag 'a~b': {not_a_name}: left out",
        f"a tag 'tí': {not_a_name}: left out",
        "a tag 'k': a NUL: the form holds none: left out",
        "a tag 'CHAPTER001': a chapter's comment by its name, not a tag: left out",
        "a tag 'chapter01': a chapter's comment by its name, not a tag: left out",
    )


def test_what_a_chapter_cannot_hold_is_noted() -> None:
    chapters = (
        Chapter(
            Fraction(1, 3), Fraction(5), (Tag("title", "t"), Tag("NAME", "a"), Tag("name", "b"))
        ),
        Chapter(Fraction(100 * 3600), None),
        Chapter(Fraction(2), None, (Tag("URL", "x\0"),)),
    )
    written = vorbis.write(Metadata(chapters=chapters))
    assert written.text == "CHAPTER000=00:00:00.333\nCHAPTER000NAME=a\nCHAPTER001=00:00:02.000\n"
    assert written.notes == (
        "chapter ends: Vorbis comments hold none (a chapter ends where the next begins): left out",
        "chapter 1 starts between milliseconds: at the nearest, 333 ms",
        "chapter 1's tag 'title': the extension holds a chapter's NAME and URL alone: left out",
        "chapter 1's tag 'name': again: a chapter has one NAME and one URL: left out",
        "chapter 2: it starts past 99:59:59.999: left out",
        "chapter 3's tag 'URL': a NUL: the form holds none: left out",
    )


def test_an_end_at_the_next_start_is_no_loss() -> None:
    chapters = (Chapter(Fraction(0), Fraction(5)), Chapter(Fraction(5), None))
    assert vorbis.write(Metadata(chapters=chapters)).notes == ()
    last = (Chapter(Fraction(0), Fraction(5)), Chapter(Fraction(5), Fraction(9)))
    assert vorbis.write(Metadata(chapters=last)).notes[0].startswith("chapter ends: ")


def test_past_a_thousand_chapters_left_out_and_noted() -> None:
    written = vorbis.write(
        Metadata(chapters=tuple(Chapter(Fraction(n), None) for n in range(1001)))
    )
    assert written.text.splitlines()[-1] == "CHAPTER999=00:16:39.000"
    assert written.notes == ("chapter 1001: past 1000 chapters: left out",)


def test_streams_and_a_disc_are_noted() -> None:
    written = vorbis.write(Metadata(streams=((Tag("a", "1"),),), disc=Disc((), ())))
    assert written == Written(
        "",
        (
            "streams' tags: Vorbis comments are one list, a stream's own: left out",
            "a cue sheet's disc: Vorbis comments hold none (a conversion makes its tracks chapters): left out",
        ),
    )


# (D) round trip


@settings(max_examples=400, deadline=None)
@given(vorbis_models())
def test_what_the_writer_writes_the_reader_reads_back_exactly(meta: Metadata) -> None:
    written = vorbis.write(meta)
    assert written.notes == ()
    assert read(written.text) == meta
    assert vorbis.write(read(written.text)).text == written.text


# (E) ffmpeg reads what ffman writes as ffman reads it (repeats joined with ';', as ffmpeg does)


def ffprobed(ffprobe: str, path: Path) -> tuple[dict[str, str], list[tuple[Fraction, str | None]]]:
    """ffprobe's reading: the file's tags, each chapter's start and title."""
    tags, _, chapters = metadata_seen(ffprobe, str(path))
    return tags, [(start, held.get("title")) for start, _, held in chapters]


def as_ffmpeg_reads(meta: Metadata) -> tuple[dict[str, str], list[tuple[Fraction, str | None]]]:
    tags: dict[str, str] = {}
    spelled: dict[str, str] = {}  # a folded name: its first spelling, which ffmpeg keeps
    comments = [*meta.tags]
    for number, chapter in enumerate(meta.chapters):
        comments += [
            Tag(f"CHAPTER{number:03d}{tag.name}", tag.value)
            for tag in chapter.tags
            if folded(tag.name) == "url"
        ]
    for tag in comments:
        if not tag.value:
            continue
        key = spelled.setdefault(folded(tag.name), tag.name)
        tags[key] = f"{tags[key]};{tag.value}" if key in tags else tag.value
    # an empty value is no comment to ffmpeg (oggparsevorbis.c: "if (!tl || !vl)"): no title
    titles = [
        next((t.value for t in c.tags if folded(t.name) == "name" and t.value), None)
        for c in meta.chapters
    ]
    return tags, [(c.start, title) for c, title in zip(meta.chapters, titles, strict=True)]


def comments_of(text: str) -> list[bytes]:
    """The comments ffman's text stands for, as a file holds them: its three escapes undone."""
    undone = {"\\": "\\", "n": "\n", "r": "\r"}
    return [
        re.sub(r"\\(.)", lambda m: undone[m[1]], line).encode() for line in text.split("\n")[:-1]
    ]


@settings(max_examples=40, deadline=None)
@given(vorbis_models())  # none of ffmpeg's four renamed names: see VORBIS_NAME
def test_ffmpeg_reads_what_ffman_writes_as_ffman_does(
    ffprobe: str, cd_flac: Path, meta: Metadata
) -> None:
    flac = cd_flac.with_name("vorbis.flac")  # one working file, written again each example
    _ = flac.write_bytes(with_comments(cd_flac.read_bytes(), comments_of(vorbis.write(meta).text)))
    assert ffprobed(ffprobe, flac) == as_ffmpeg_reads(meta)


# (F) why the chapter refusals: ffmpeg reads these comments otherwise than the extension


@pytest.mark.parametrize(
    ("comments", "tags", "chapters"),
    [
        # two digits: a chapter to ffmpeg (sscanf's %03d), not the extension's
        ([b"CHAPTER01=00:00:01.000"], {}, [(Fraction(1), None)]),
        # a title before its time: a plain tag, the chapter untitled
        (
            [b"CHAPTER000NAME=t", b"CHAPTER000=00:00:01.000"],
            {"CHAPTER000NAME": "t"},
            [(Fraction(1), None)],
        ),
        # four digits and NAME: sscanf reads three -- chapter 100's title
        (
            [b"CHAPTER100=00:00:02.000", b"CHAPTER1000NAME=t"],
            {},
            [(Fraction(2), "t")],
        ),
    ],
)
def test_ffmpeg_reads_the_refused_comments_otherwise(
    ffprobe: str,
    cd_flac: Path,
    tmp_path: Path,
    comments: list[bytes],
    tags: dict[str, str],
    chapters: list[tuple[Fraction, str | None]],
) -> None:
    flac = tmp_path / "b.flac"
    _ = flac.write_bytes(with_comments(cd_flac.read_bytes(), comments))
    assert ffprobed(ffprobe, flac) == (tags, chapters)


def test_comments_are_raw_the_writers_text_escaped() -> None:
    meta = Metadata(chapters=(Chapter(Fraction(0), None, (Tag("NAME", "a\\b\nc"),)),))
    pairs, notes = vorbis.comments(meta)
    assert (pairs, notes) == ((("CHAPTER000", "00:00:00.000"), ("CHAPTER000NAME", "a\\b\nc")), ())
    assert vorbis.write(meta).text == "CHAPTER000=00:00:00.000\nCHAPTER000NAME=a\\\\b\\nc\n"
