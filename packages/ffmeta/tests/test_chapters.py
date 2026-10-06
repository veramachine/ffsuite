import re
from collections.abc import Callable
from fractions import Fraction

import ffmeta
import pytest
from ffmeta.chapters import ChapterEdits, ChapterText, edit_chapters, parse_chapters
from ffmeta.model import Chapter, Disc, File, Index, Metadata, Tag, Track
from ffmeta.time import parse as parse_time
from ffmeta_support.metadata import ffmetadata_models
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("62.5", Fraction(125, 2)),
        ("0", Fraction(0)),
        ("1:02.5", Fraction(125, 2)),
        ("1:01:02.5", Fraction(7325, 2)),
        ("4650f", Fraction(62)),
        ("1f", Fraction(1, 75)),
        ("0.000000001", Fraction(1, 10**9)),
        ("99999:59:59.999999999", 99999 * 3600 + 3599 + Fraction(999999999, 10**9)),
    ],
)
def test_a_time_in_each_form_exactly(text: str, seconds: Fraction) -> None:
    assert parse_time(text) == seconds


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1:2",
        "1:60",
        "1:00:60",
        "1:60:00",
        "1:02:03:04",
        "-1",
        "1e3",
        "1.",
        ".5",
        "1:02f",
        "62,5",
        "\u0661",
        "1234567890",
        "1.1234567890",
        "1234567890123f",
    ],
)
def test_a_time_in_no_form_is_refused(text: str) -> None:
    with pytest.raises(
        ffmeta.Error,
        match=r"^a time is SECONDS, M:SS or H:MM:SS \(each with a \.fraction\) or FRAMESf: ",
    ):
        _ = parse_time(text)


def edits(
    new: tuple[str, ...] = (),
    retitles: tuple[str, ...] = (),
    sets: tuple[str, ...] = (),
    drops: tuple[str, ...] = (),
    *,
    clear: bool = False,
) -> ChapterEdits:
    return parse_chapters(ChapterText(new, retitles, sets, drops, clear=clear))


@pytest.mark.parametrize(
    ("made", "message"),
    [
        (lambda: edits(drops=("0",)), "a chapter number is 1, 2, 3...: 0"),
        (lambda: edits(drops=("x",)), "a chapter number is 1, 2, 3...: x"),
        (lambda: edits(retitles=("2",)), "--retitle needs N=TITLE: 2"),
        (lambda: edits(sets=("2=x",)), "--chapter-set needs N:KEY=VALUE: 2=x"),
        (lambda: edits(sets=("2:=x",)), "--chapter-set needs N:KEY=VALUE: 2:=x"),
        (
            lambda: edits(retitles=("2=a",), drops=("2",)),
            "--drop-chapter 2 and --retitle 2 contradict",
        ),
        (
            lambda: edits(sets=("2:artist=a",), drops=("2",)),
            "--drop-chapter 2 and --chapter-set 2 contradict",
        ),
        (lambda: edits(retitles=("2=a",), sets=("2:TITLE=b",)), "chapter 2's TITLE set twice"),
        (
            lambda: edits(retitles=("2=a",), clear=True),
            "--clear-chapters and --retitle 2 contradict",
        ),
        (
            lambda: edits(drops=("3", "2"), clear=True),
            "--clear-chapters and --drop-chapter 2 contradict",
        ),
        (lambda: edits(("2..1",)), "--chapter 2..1: its end before its start"),
        (
            lambda: edits(("1:2=x",)),
            "a time is SECONDS, M:SS or H:MM:SS (each with a .fraction) or FRAMESf: 1:2",
        ),
    ],
)
def test_what_parse_refuses(made: Callable[[], ChapterEdits], message: str) -> None:
    with pytest.raises(ffmeta.Error, match=f"^{re.escape(message)}$"):
        _ = made()


def chapters(*starts: int, fmt_title: str = "title") -> Metadata:
    return Metadata(
        chapters=tuple(
            Chapter(Fraction(s), None, (Tag(fmt_title, f"c{n}"),)) for n, s in enumerate(starts, 1)
        )
    )


def test_ffmetadata_retitle_set_drop_add_in_time_order() -> None:
    meta = chapters(0, 60, 120)
    done, notes = edit_chapters(
        meta, edits(("90=New", "30..40"), ("1=One",), ("3:artist=A",), ("2",)), "ffmetadata", ""
    )
    assert done.chapters == (
        Chapter(Fraction(0), None, (Tag("title", "One"),)),
        Chapter(Fraction(30), Fraction(40), ()),
        Chapter(Fraction(90), None, (Tag("title", "New"),)),
        Chapter(Fraction(120), None, (Tag("title", "c3"), Tag("artist", "A"))),
    )
    assert notes == ()


def test_vorbis_a_chapters_title_is_its_name() -> None:
    meta = chapters(0, 60, fmt_title="NAME")
    done, _ = edit_chapters(meta, edits(("30=Mid",), ("2=Two",)), "vorbis", "")
    assert [c.tags for c in done.chapters] == [
        (Tag("NAME", "c1"),),
        (Tag("NAME", "Mid"),),
        (Tag("NAME", "Two"),),
    ]


def test_a_number_past_the_inputs_chapters() -> None:
    with pytest.raises(ffmeta.Error, match=r"^chapter 3: the input has 2 chapters$"):
        _ = edit_chapters(chapters(0, 60), edits(drops=("3",)), "ffmetadata", "")


def sheet(*tracks: Track, files: int = 1) -> Metadata:
    return Metadata(disc=Disc(tuple(File(f"{n}.flac", "WAVE") for n in range(files)), tracks))


def track(number: int, *indexes: tuple[int, int], title: str | None = None, file: int = 0) -> Track:
    cdtext = (Tag("TITLE", title),) if title else ()
    return Track(number, "AUDIO", tuple(Index(n, f, file) for n, f in indexes), cdtext)


def test_a_cue_a_new_track_numbered_in_time_holding_the_time_before() -> None:
    meta = sheet(track(1, (0, 0), (1, 2250), title="One"), track(2, (1, 9000), title="Two"))
    done, notes = edit_chapters(meta, edits(("60=Mid", "10=First")), "cue", "x")
    assert done.disc is not None
    assert [
        (t.number, t.cdtext, [(i.number, i.frames) for i in t.indexes]) for t in done.disc.tracks
    ] == [
        (1, (Tag("TITLE", "First"),), [(0, 0), (1, 750)]),  # INDEX 00 at 0: the new first's
        (2, (Tag("TITLE", "One"),), [(1, 2250)]),
        (3, (Tag("TITLE", "Mid"),), [(1, 4500)]),
        (4, (Tag("TITLE", "Two"),), [(1, 9000)]),
    ]
    assert notes == ()


def test_a_cue_a_new_track_rounded_and_its_end_noted() -> None:
    done, notes = edit_chapters(Metadata(), edits(("1:00.01..2:00=Odd",)), "cue", "x")  # a new cue
    assert done.disc is not None
    assert done.disc.files == (File("x", "WAVE"),)
    assert done.disc.tracks == (track(1, (0, 0), (1, 4501), title="Odd"),)
    assert notes == (
        "--chapter 1:00.01..2:00=Odd: between frames (1/75 s): at the nearest, frame 4501",
        "--chapter 1:00.01..2:00=Odd's end: a cue's track ends where the next starts: left out",
    )


@pytest.mark.parametrize(
    ("new", "message"),
    [
        ("1:59", "--chapter 1:59: inside track 2 (its INDEX 00 at frame 8850)"),
        ("10", "--chapter 10: inside track 1 (its INDEX 02 at frame 1500)"),
    ],
)
def test_a_cue_a_track_inside_another_is_refused(new: str, message: str) -> None:
    meta = sheet(track(1, (1, 0), (2, 1500)), track(2, (0, 8850), (1, 9000)))
    with pytest.raises(ffmeta.Error, match=rf"^{message.replace('(', '[(]').replace(')', '[)]')}$"):
        _ = edit_chapters(meta, edits((new,)), "cue", "x")


def test_a_cue_over_two_files_takes_no_new_track_but_drops_one() -> None:
    meta = sheet(track(1, (1, 0)), track(2, (1, 0), file=1), files=2)
    with pytest.raises(
        ffmeta.Error,
        match=r"^--chapter 5: a cue over 2 files: which one the track is in cannot be told$",
    ):
        _ = edit_chapters(meta, edits(("5",)), "cue", "x")
    done, _ = edit_chapters(meta, edits(drops=("1",)), "cue", "x")
    assert done.disc == Disc(
        (File("1.flac", "WAVE"),), (track(1, (1, 0)),)
    )  # renumbered, its file alone


def test_a_cue_tracks_fields_set() -> None:
    meta = sheet(track(1, (1, 0), title="One"))
    sets = ("1:performer=P", "1:ISRC=GBAYE7900001", "1:REPLAYGAIN_TRACK_GAIN=-6.00 dB")
    done, _ = edit_chapters(meta, edits(retitles=("1=Uno",), sets=sets), "cue", "x")
    assert done.disc is not None
    assert done.disc.tracks[0] == Track(
        1,
        "AUDIO",
        (Index(1, 0, 0),),
        (Tag("TITLE", "Uno"), Tag("PERFORMER", "P")),
        ("REPLAYGAIN_TRACK_GAIN -6.00 dB",),
        isrc="GBAYE7900001",
    )
    with pytest.raises(
        ffmeta.Error, match=r"^--chapter-set 1:artist: a cue's track holds no artist"
    ):
        _ = edit_chapters(meta, edits(sets=("1:artist=x",)), "cue", "x")


@settings(max_examples=150, deadline=None)
@given(ffmetadata_models(), st.lists(st.integers(0, 10**5), max_size=4), st.data())
def test_chapters_added_keep_time_order_and_a_drop_takes_the_inputs_nth(
    meta: Metadata, starts: list[int], data: st.DataObject
) -> None:
    ordered = sorted(meta.chapters, key=lambda c: c.start)
    meta = Metadata(meta.tags, meta.streams, tuple(ordered))
    drop: set[int] = (
        data.draw(st.sets(st.integers(1, len(ordered)), max_size=2)) if ordered else set()
    )
    done, _ = edit_chapters(
        meta, edits(tuple(f"{s}f" for s in starts), drops=tuple(map(str, drop))), "ffmetadata", ""
    )
    assert len(done.chapters) == len(ordered) - len(drop) + len(starts)
    assert [c.start for c in done.chapters] == sorted(c.start for c in done.chapters)
    kept = [c for n, c in enumerate(ordered, 1) if n not in drop]
    assert [c for c in done.chapters if c in kept] == kept  # the rest, untouched, in order


def test_a_tracks_gain_replaced_where_it_stood_as_given() -> None:
    held = Track(
        1, "AUDIO", (Index(1, 0, 0),), rems=("REPLAYGAIN_TRACK_GAIN -1.00 dB", "COMMENT x")
    )
    done, notes = edit_chapters(
        sheet(held), edits(sets=('1:REPLAYGAIN_TRACK_GAIN=a "b" c',)), "cue", "x"
    )
    assert done.disc is not None
    assert done.disc.tracks[0].rems == (
        'REPLAYGAIN_TRACK_GAIN a "b" c',
        "COMMENT x",
    )  # never quoted
    assert notes == ()


def test_among_unordered_chapters_after_the_last_no_later() -> None:
    meta = Metadata(chapters=tuple(Chapter(Fraction(s), None) for s in (0, 100, 50)))  # Vorbis'
    done, _ = edit_chapters(meta, edits(("60",)), "vorbis", "")
    assert [c.start for c in done.chapters] == [0, 100, 50, 60]  # after 50, the last no later


def test_vorbis_name_is_the_title_so_set_twice() -> None:
    with pytest.raises(ffmeta.Error, match=r"^chapter 1's NAME set twice$"):
        _ = edit_chapters(
            chapters(0, fmt_title="NAME"),
            edits(retitles=("1=A",), sets=("1:NAME=B",)),
            "vorbis",
            "",
        )
    done, _ = edit_chapters(
        chapters(0), edits(retitles=("1=A",), sets=("1:name=B",)), "ffmetadata", ""
    )
    assert done.chapters[0].tags == (Tag("title", "A"), Tag("name", "B"))  # ffmetadata's: two keys


@pytest.mark.parametrize(
    ("made", "message"),
    [
        (lambda: parse_chapters(ChapterText(flags=("2",))), "--flags needs N=FLAGS: 2"),
        (
            lambda: parse_chapters(ChapterText(flags=("2=PRE,COPY",))),
            "FLAGS are DCP, 4CH, PRE, SCMS, each once: PRE,COPY",
        ),
        (
            lambda: parse_chapters(ChapterText(flags=("2=pre,PRE",))),
            "FLAGS are DCP, 4CH, PRE, SCMS, each once: pre,PRE",
        ),
        (lambda: parse_chapters(ChapterText(flags=("2=PRE", "2=DCP"))), "--flags 2 twice"),
        (lambda: parse_chapters(ChapterText(pregaps=("2",))), "--pregap needs N=TIME: 2"),
        (lambda: parse_chapters(ChapterText(pregaps=("2=1:00", "2="))), "--pregap 2 twice"),
        (
            lambda: parse_chapters(ChapterText(flags=("2=PRE",), drops=("2",))),
            "--drop-chapter 2 and --flags 2 contradict",
        ),
        (
            lambda: parse_chapters(ChapterText(pregaps=("1=0",), clear=True)),
            "--clear-chapters and --pregap 1 contradict",
        ),
    ],
)
def test_what_a_cues_track_edits_refuse(made: Callable[[], ChapterEdits], message: str) -> None:
    with pytest.raises(ffmeta.Error, match=f"^{re.escape(message)}$"):
        _ = made()


def test_a_cues_flags_and_pregap_on_its_tracks() -> None:
    meta = sheet(track(1, (1, 0)), track(2, (0, 8000), (1, 9000)), track(3, (1, 15000)))
    given = ChapterText(flags=("2=pre,dcp", "1="), pregaps=("2=", "3=3:10.01"))
    done, notes = edit_chapters(meta, parse_chapters(given), "cue", "x")
    assert done.disc is not None
    assert [(t.flags, [(i.number, i.frames) for i in t.indexes]) for t in done.disc.tracks] == [
        ((), [(1, 0)]),
        (("PRE", "DCP"), [(1, 9000)]),  # its pregap gone
        ((), [(0, 14251), (1, 15000)]),
    ]
    assert notes == ("--pregap 3=3:10.01: between frames (1/75 s): at the nearest, frame 14251",)


@pytest.mark.parametrize(
    ("pregap", "message"),
    [
        ("2=2:30", "--pregap 2=2:30: after its INDEX 01 (frame 9000)"),
        ("2=0:10", "--pregap 2=0:10: inside track 1 (its INDEX 02 at frame 1500)"),
    ],
)
def test_a_pregap_out_of_its_place_is_refused(pregap: str, message: str) -> None:
    meta = sheet(track(1, (1, 0), (2, 1500)), track(2, (1, 9000)))
    with pytest.raises(ffmeta.Error, match=f"^{re.escape(message)}$"):
        _ = edit_chapters(meta, parse_chapters(ChapterText(pregaps=(pregap,))), "cue", "x")


def test_a_cues_track_edits_need_a_cue_input() -> None:
    with pytest.raises(
        ffmeta.Error, match=r"^--flags edits a cue's tracks: the input is Vorbis comments$"
    ):
        _ = edit_chapters(chapters(0), parse_chapters(ChapterText(flags=("1=PRE",))), "vorbis", "")


def test_a_tracks_isrc_is_well_formed() -> None:
    with pytest.raises(
        ffmeta.Error, match=r"^--chapter-set 1:ISRC: a cue's ISRC is CCOOOYYSSSSS \(12\): GB-1$"
    ):
        _ = edit_chapters(sheet(track(1, (1, 0))), edits(sets=("1:ISRC=GB-1",)), "cue", "x")


def test_a_pregap_on_eacs_layout_goes_to_its_index_01s_file() -> None:
    meta = Metadata(
        disc=Disc(
            (File("1.flac", "WAVE"), File("2.flac", "WAVE")),
            (track(1, (1, 0)), Track(2, "AUDIO", (Index(0, 12599, 0), Index(1, 75, 1)))),
        )
    )
    done, _ = edit_chapters(meta, parse_chapters(ChapterText(pregaps=("2=0",))), "cue", "x")
    assert done.disc is not None
    assert done.disc.tracks[1].indexes == (Index(0, 0, 1), Index(1, 75, 1))
    assert len(done.disc.files) == 2  # both still used


def test_a_track_past_a_cues_last_time_is_refused() -> None:
    last = r"past a cue's last time \(999999:59:74\)"
    with pytest.raises(ffmeta.Error, match=rf"^--chapter 4500000000f: {last}$"):
        _ = edit_chapters(Metadata(), edits(("4500000000f",)), "cue", "x")
    done, _ = edit_chapters(Metadata(), edits(("4499999999f",)), "cue", "x")  # the last: held
    assert done.disc is not None
    assert done.disc.tracks[0].start_index.frames == 4499999999
