import re
from fractions import Fraction
from pathlib import Path

import ffmeta
import pytest
from ffmeta import ffmetadata
from ffmeta.model import Chapter, Disc, Metadata, Tag, Tags, Written
from ffmeta_support.examples import FFMETADATA as EXAMPLE
from ffmeta_support.media import Seen, metadata_seen
from ffmeta_support.metadata import ffmetadata_models
from hypothesis import given, settings


def read(text: str) -> Metadata:
    return ffmetadata.read(text, "x.ffmeta")


def refused(text: str, line: int, message: str) -> None:
    with pytest.raises(ffmeta.Error, match=rf"^{re.escape(f'x.ffmeta:{line}: {message}')}$"):
        _ = read(text)


def pairs(tags: Tags) -> list[tuple[str, str]]:
    return [(tag.name, tag.value) for tag in tags]


# (A) what ffmpeg reads, ffman reads alike


def test_the_skills_example_reads_as_the_skill_says() -> None:
    meta = read(EXAMPLE)
    assert pairs(meta.tags) == [
        ("title", "bike\\shed"),
        ("artist", "FFmpeg troll team"),
        ("x_custom", "a=b"),
        ("artist-sort", "troll team, FFmpeg"),
    ]
    assert [pairs(stream) for stream in meta.streams] == [[("language", "eng")]]
    assert meta.chapters == (
        Chapter(Fraction(0), Fraction(60), (Tag("title", "chapter #1"),)),
        Chapter(Fraction(60), Fraction(120), (Tag("title", "two\nlines"),)),
    )


def test_crlf_reads_as_lf() -> None:
    text = ";FFMETADATA1\ntitle=a\n[CHAPTER]\nTIMEBASE=1/75\nSTART=1\nEND=2\ntitle=c\n"
    assert read(text.replace("\n", "\r\n")) == read(text)


def test_a_chapter_without_timebase_counts_nanoseconds() -> None:
    meta = read(";FFMETADATA1\n[CHAPTER]\nSTART=5\nEND=1000000000\n")
    assert meta.chapters == (Chapter(Fraction(5, 10**9), Fraction(1)),)


def test_comments_and_empty_lines_anywhere_even_among_a_chapters_times() -> None:
    text = ";FFMETADATA1\n\n# a comment\na=1\n[CHAPTER]\n;c\n\nTIMEBASE=1/1000\n#c\nSTART=0\n\nEND=5\n;c\nb=2\n"
    meta = read(text)
    assert pairs(meta.tags) == [("a", "1")]
    assert meta.chapters == (Chapter(Fraction(0), Fraction(1, 200), (Tag("b", "2"),)),)


def test_what_the_format_allows() -> None:
    # ffmpeg checks no version; keeps an empty key and an empty value; whitespace is the tag's
    meta = read(";FFMETADATA9\n=v\nk=\n k = v \n[x]=1\n\\;not a comment=x")
    assert pairs(meta.tags) == [
        ("", "v"),
        ("k", ""),
        (" k ", " v "),
        ("[x]", "1"),
        (";not a comment", "x"),
    ]


def test_an_escaped_cr_is_the_values_and_crlf_still_ends_the_line() -> None:
    assert pairs(read(";FFMETADATA1\nk=a\\\r\nnext=1\n").tags) == [("k", "a\r"), ("next", "1")]


def test_an_escaped_backslash_ending_the_file_is_the_values() -> None:
    # no line break after it: ffmpeg reads it so too (measured)
    assert pairs(read(";FFMETADATA1\nk=x\\\\").tags) == [("k", "x\\")]


def test_a_timebase_after_a_chapters_times_is_one_of_its_tags() -> None:
    meta = read(";FFMETADATA1\n[CHAPTER]\nSTART=0\nEND=1\nTIMEBASE=1/1000\n")
    assert pairs(meta.chapters[0].tags) == [("TIMEBASE", "1/1000")]


def test_the_same_key_in_two_sections_is_two_tags() -> None:
    meta = read(";FFMETADATA1\ntitle=a\n[STREAM]\nTITLE=b\n[STREAM]\ntitle=c\n")
    assert [pairs(s) for s in meta.streams] == [[("TITLE", "b")], [("title", "c")]]


# (B) what ffmpeg reads otherwise than written: refused, the line named


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("", "an empty file"),
        ("title=a\n", "title=a"),
        ("\ufeff;FFMETADATA1\n", "\\ufeff;FFMETADATA1"),  # a BOM, shown: ffmpeg reads none
        ("\n;FFMETADATA1\n", ""),
    ],
)
def test_no_header(text: str, found: str) -> None:
    refused(text, 1, f"not ffmetadata: the first line must begin ;FFMETADATA: {found}")


@pytest.mark.parametrize(
    ("text", "line", "message"),
    [
        (
            ";FFMETADATA1\na=1\n; a comment \\\nb=2\n",
            3,
            "a comment ending in '\\': ffmpeg reads the next line into it",
        ),
        (
            ";FFMETADATA1\\\na=1\n",
            1,
            "a comment ending in '\\': ffmpeg reads the next line into it",
        ),
        (";FFMETADATA1\na=1\nb=x\0y\n", 3, "a NUL: ffmpeg ends the line there"),
        (";FFMETADATA1\na=1\rb=2\n", 2, "a carriage return alone: end lines with LF or CR LF"),
        (
            ";FFMETADATA1\nk=x\\\\\nnext=1\n",
            2,
            "a line ending in '\\': ffmpeg reads the next line into it",
        ),
        (";FFMETADATA1\na=1\nk=x\\", 3, "a '\\' ending the file: it escapes nothing"),
        (
            ";FFMETADATA1\n[chapter]\nSTART=0\n",
            2,
            "not a section ([STREAM] or [CHAPTER], in capitals): [chapter]",
        ),
        (";FFMETADATA1\njust words\n", 2, "no '=': not a tag (ffmpeg drops the line): just words"),
        (
            ";FFMETADATA1\nTitle=a\nb=1\ntitle=b\n",
            4,
            "the key 'title' again (line 2): ffmpeg keeps only the last",
        ),
        (
            ";FFMETADATA1\n[STREAM]\na=1\nA=2\n",
            4,
            "the key 'A' again (line 3): ffmpeg keeps only the last",
        ),
    ],
)
def test_a_line_ffmpeg_misreads(text: str, line: int, message: str) -> None:
    refused(text, line, message)


def test_a_comment_with_equals_ending_the_file_is_refused_else_a_comment() -> None:
    # ffmpeg skips a comment unless it ends the file: then it reads it as a tag (measured)
    refused(
        ";FFMETADATA1\nk=v\n;x=y", 3, "a comment with '=' ending the file: ffmpeg reads it as a tag"
    )
    refused(
        ";FFMETADATA1\n[CHAPTER]\nSTART=0\nEND=5\n#t=x",
        5,
        "a comment with '=' ending the file: ffmpeg reads it as a tag",
    )
    assert (
        read(";FFMETADATA1\nk=v\n;x=y\n")
        == read(";FFMETADATA1\nk=v\n;no equals")
        == read(";FFMETADATA1\nk=v")
    )
    assert (
        read(";FFMETADATA1") == Metadata()
    )  # its header alone, no line break: ffmpeg reads nothing


def test_a_file_not_ffmetadata_is_refused_as_that_whatever_it_holds() -> None:
    refused(
        "\x89PNG\r\n\x1a\n\0\0\0\rIHDR",
        1,
        "not ffmetadata: the first line must begin ;FFMETADATA: \\x89PNG\\r",
    )


def test_a_joined_line_is_named_by_its_first() -> None:
    # line 2 runs on to line 3 (an escaped line break); line 4 is the culprit
    refused(
        ";FFMETADATA1\na=one\\\ntwo\nnothing\n",
        4,
        "no '=': not a tag (ffmpeg drops the line): nothing",
    )
    refused(
        ";FFMETADATA1\na=one\\\ntwo\\\\\nb=1\n",
        2,
        "a line ending in '\\': ffmpeg reads the next line into it",
    )


@pytest.mark.parametrize(
    ("times", "line", "message"),
    [
        ("TIMEBASE=1\nSTART=5\nEND=9\n", 3, "not TIMEBASE=N/D, two whole numbers: TIMEBASE=1"),
        (
            "TIMEBASE=0/1000\nSTART=5\nEND=9\n",
            3,
            "TIMEBASE's terms run 1 to 2147483647: TIMEBASE=0/1000",
        ),
        (
            "TIMEBASE=1/2147483648\nSTART=5\nEND=9\n",
            3,
            "TIMEBASE's terms run 1 to 2147483647: TIMEBASE=1/2147483648",
        ),
        ("title=x\nSTART=5\nEND=9\n", 3, "[CHAPTER] (line 2) needs START= here"),
        ("TIMEBASE=1/1000\nEND=9\n", 4, "[CHAPTER] (line 2) needs START= here"),
        ("TIMEBASE=1/1000\nSTART=5\n", 2, "[CHAPTER] (line 2) needs END= here"),
        ("", 2, "[CHAPTER] (line 2) needs START= here"),
        ("START=12abc\nEND=50\n", 3, "not START= and a whole number: START=12abc"),
        ("START=+5\nEND=50\n", 3, "not START= and a whole number: START=+5"),
        ("START= 5\nEND=50\n", 3, "not START= and a whole number: START= 5"),
        ("START=-5\nEND=50\n", 3, "not START= and a whole number: START=-5"),
        ("START=5\nEND=9x\n", 4, "not END= and a whole number: END=9x"),
        (f"START=0\nEND={2**63}\n", 4, f"END past {2**63 - 1}: {2**63}"),
        ("START=2\nEND=1\n", 4, "a chapter ending before it starts: END=1 < START=2"),
    ],
)
def test_a_chapters_times_are_strict(times: str, line: int, message: str) -> None:
    refused(f";FFMETADATA1\n[CHAPTER]\n{times}", line, message)


def test_a_number_of_thousands_of_digits_is_refused_not_a_crash() -> None:
    # int() stops at 4300 digits (sys.int_info): the reader refuses before it
    nines = "9" * 5000
    refused(
        f";FFMETADATA1\n[CHAPTER]\nSTART={nines}\nEND=1\n",
        3,
        f"a number past {2**63 - 1}: START={'9' * 51}...",
    )
    refused(
        f";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/{nines}\n",
        3,
        f"a number past {2**63 - 1}: TIMEBASE=1/{'9' * 46}...",
    )
    refused(
        ";FFMETADATA1\n[CHAPTER]\nSTART=" + "1" * 20 + "\nEND=1\n",
        3,
        f"a number past {2**63 - 1}: START={'1' * 20}",
    )
    # leading zeros are no digits of its size
    assert read(";FFMETADATA1\n[CHAPTER]\nSTART=" + "0" * 21 + "5000\nEND=6000\n").chapters[
        0
    ].start == Fraction(1, 200000)


def test_a_line_in_a_message_is_one_line_of_60_characters_at_most() -> None:
    refused(
        ";FFMETADATA1\n" + "x" * 100 + "\n",
        2,
        "no '=': not a tag (ffmpeg drops the line): " + "x" * 57 + "...",
    )
    refused(";FFMETADATA1\na\\\nb\n", 2, "no '=': not a tag (ffmpeg drops the line): a\\\\nb")


# (C) the writer


def test_the_writer_escapes_what_ffmpeg_reads_specially_the_cr_too() -> None:
    written = ffmetadata.write(Metadata((Tag("k=;#", "a\\b\nc\rd"),)))
    assert written.text == ";FFMETADATA1\nk\\=\\;\\#=a\\\\b\\\nc\\\rd\n"
    assert written.notes == ()


def test_nothing_is_a_header() -> None:
    assert ffmetadata.write(Metadata()) == Written(";FFMETADATA1\n")


def test_what_ffmpeg_cannot_read_back_is_left_out_and_noted() -> None:
    meta = Metadata(
        (Tag("a", "x\0y"), Tag("b", "ends\\"), Tag("c", "1"), Tag("C", "2")),
        ((Tag("s", "\\"),),),
        (Chapter(Fraction(0), Fraction(1), (Tag("t", "a"), Tag("T", "b"))),),
    )
    written = ffmetadata.write(meta)
    assert (
        written.text
        == ";FFMETADATA1\nc=1\n[STREAM]\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\nt=a\n"
    )
    assert written.notes == (
        "a global tag 'a': a NUL: ffmpeg ends the line there: left out",
        "a global tag 'b': it ends in '\\': ffmpeg reads the next line into it: left out",
        "a global tag 'C': its key again: ffmpeg keeps only the last: left out",
        "stream 0's tag 's': it ends in '\\': ffmpeg reads the next line into it: left out",
        "chapter 1's tag 'T': its key again: ffmpeg keeps only the last: left out",
    )


@pytest.mark.parametrize(
    ("start", "end", "lines"),
    [
        (
            Fraction(3, 2),
            Fraction(2),
            ["TIMEBASE=1/1000", "START=1500", "END=2000"],
        ),  # ms: they divide
        (Fraction(19327, 75), Fraction(40724, 75), ["TIMEBASE=1/75", "START=19327", "END=40724"]),
        (Fraction(1, 1000), Fraction(1, 75), ["TIMEBASE=1/3000", "START=3", "END=40"]),
        (Fraction(1, 44100), Fraction(1), ["TIMEBASE=1/44100", "START=1", "END=44100"]),
        (Fraction(2), Fraction(3), ["TIMEBASE=1/1000", "START=2000", "END=3000"]),  # seconds: in ms
    ],
)
def test_chapter_times_are_exact_in_ms_or_the_least_time_base(
    start: Fraction, end: Fraction, lines: list[str]
) -> None:
    text = ffmetadata.write(Metadata(chapters=(Chapter(start, end),))).text
    assert text.splitlines() == [";FFMETADATA1", "[CHAPTER]", *lines]


def test_a_time_base_past_ffmpegs_int_is_rounded_to_nanoseconds_and_noted() -> None:
    big = 2**31 + 11  # a prime: no smaller time base holds 1/big
    written = ffmetadata.write(Metadata(chapters=(Chapter(Fraction(1, big), Fraction(1)),)))
    assert written.text.splitlines()[2:] == ["TIMEBASE=1/1000000000", "START=0", "END=1000000000"]
    assert written.notes == (
        f"chapter 1's times need a time base of 1/{big}: rounded to nanoseconds",
    )


def test_a_chapter_past_ffmpegs_int64_is_left_out_and_noted() -> None:
    written = ffmetadata.write(Metadata(chapters=(Chapter(Fraction(0), Fraction(2**63, 1000)),)))
    assert written.text == ";FFMETADATA1\n"
    assert written.notes == (
        f"chapter 1: it ends past what ffmpeg reads ({2**63 - 1} of 1/1000 s): left out",
    )


def test_a_chapter_without_an_end_ends_at_the_next_or_at_the_duration() -> None:
    chapters = (
        Chapter(Fraction(10), None),
        Chapter(Fraction(0), None),
        Chapter(Fraction(5), Fraction(6)),
    )
    written = ffmetadata.write(Metadata(chapters=chapters), duration=Fraction(30))
    assert [c.end for c in read(written.text).chapters] == [Fraction(30), Fraction(5), Fraction(6)]
    assert written.notes == ()


@pytest.mark.parametrize("duration", [None, Fraction(5)])
def test_a_last_chapter_without_an_end_or_a_duration_past_it_ends_where_it_starts(
    duration: Fraction | None,
) -> None:
    written = ffmetadata.write(Metadata(chapters=(Chapter(Fraction(10), None),)), duration=duration)
    assert read(written.text).chapters == (Chapter(Fraction(10), Fraction(10)),)
    assert written.notes == (
        "chapter 1 has no end, nor a chapter after it, nor a duration: it ends where it starts",
    )


def test_a_cue_sheets_disc_is_noted() -> None:
    written = ffmetadata.write(Metadata(disc=Disc((), ())))
    assert written.notes == (
        "a cue sheet's disc: ffmetadata holds none (a conversion makes its tracks chapters): left out",
    )


# (D) round trip


@settings(max_examples=400, deadline=None)
@given(ffmetadata_models())
def test_what_the_writer_writes_the_reader_reads_back_exactly(meta: Metadata) -> None:
    written = ffmetadata.write(meta)
    assert written.notes == ()
    assert read(written.text) == meta
    assert ffmetadata.write(read(written.text)).text == written.text  # and writes it alike


# (E) ffmpeg itself, the oracle: what ffman writes, ffmpeg reads as ffman's model


def as_ffprobe_sees(meta: Metadata) -> Seen:
    return (
        dict(pairs(meta.tags)),
        [dict(pairs(stream)) for stream in meta.streams],
        [
            (c.start, c.start if c.end is None else c.end, dict(pairs(c.tags)))
            for c in meta.chapters
        ],
    )


@settings(max_examples=40, deadline=None)
@given(ffmetadata_models())
def test_ffmpeg_reads_what_ffman_writes_as_ffman_does(
    ffprobe: str, tmp_path_factory: pytest.TempPathFactory, meta: Metadata
) -> None:
    path = tmp_path_factory.mktemp("ffmeta") / "x.ffmeta"
    _ = path.write_text(ffmetadata.write(meta).text, encoding="utf-8", newline="")
    assert metadata_seen(ffprobe, str(path)) == as_ffprobe_sees(meta)


def test_ffmpeg_reads_a_comment_ending_the_file_as_a_tag(ffprobe: str, tmp_path: Path) -> None:
    # why the reader refuses it
    path = tmp_path / "x.ffmeta"
    _ = path.write_text(";FFMETADATA1\nk=v\n;x=y", encoding="utf-8", newline="")
    assert metadata_seen(ffprobe, str(path))[0] == {"k": "v", ";x": "y"}


def test_ffmpeg_reads_a_line_after_an_escaped_backslash_into_it(
    ffprobe: str, tmp_path: Path
) -> None:
    # why the reader refuses it: ffmpeg joins "next=1" to k's value
    path = tmp_path / "x.ffmeta"
    _ = path.write_text(";FFMETADATA1\nk=x\\\\\nnext=1\n", encoding="utf-8", newline="")
    assert metadata_seen(ffprobe, str(path))[0] == {"k": "x\\\nnext=1"}
