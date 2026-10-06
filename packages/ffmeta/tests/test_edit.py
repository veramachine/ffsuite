from fractions import Fraction

import ffmeta
import pytest
from ffmeta.edit import Edits, apply, in_output, in_source, parse
from ffmeta.fields import key, spelled
from ffmeta.model import Chapter, Disc, File, Index, Metadata, Tag, Track
from ffmeta_support.metadata import vorbis_models
from hypothesis import given, settings
from hypothesis import strategies as st


def test_a_key_compares_without_case_vorbis_four_as_generic() -> None:
    assert [key(n) for n in ("Title", "ALBUMARTIST", "tracknumber", "DESCRIPTION", "My Key")] == [
        "title",
        "album_artist",
        "track",
        "comment",
        "my key",
    ]


def test_a_generic_key_in_each_formats_spelling_another_as_given() -> None:
    assert [spelled("Album_Artist", f) for f in ("ffmetadata", "vorbis")] == [
        "album_artist",
        "ALBUMARTIST",
    ]
    assert [spelled("title", f) for f in ("ffmetadata", "vorbis")] == ["title", "TITLE"]
    assert spelled("My Key", "vorbis") == "My Key"


@pytest.mark.parametrize(
    ("sets", "adds", "unsets", "message"),
    [
        (["title"], [], [], "--set needs KEY=VALUE: title"),
        (["=x"], [], [], "--set needs KEY=VALUE: =x"),
        ([], ["artist"], [], "--add needs KEY=VALUE: artist"),
        ([], [], [""], "--unset needs a KEY"),
        (["title=a", "TITLE=b"], [], [], "--set TITLE twice: --add gives another value"),
        (
            ["ALBUMARTIST=a"],
            [],
            ["album_artist"],
            "--set ALBUMARTIST and --unset album_artist contradict",
        ),
        ([], ["artist=a"], ["Artist"], "--add artist and --unset Artist contradict"),
    ],
)
def test_what_parse_refuses(
    sets: list[str], adds: list[str], unsets: list[str], message: str
) -> None:
    with pytest.raises(ffmeta.Error, match=rf"^{message}$"):
        _ = parse(sets, adds, unsets, clear=False)


def test_a_set_and_an_add_of_one_key_mean_two_values() -> None:
    edits = parse(["artist=A"], ["artist=B", "x=a=b"], [], clear=True)
    want = (Tag("artist", "B"), Tag("x", "a=b"))
    assert edits == Edits(clear=True, unset=(), set=(Tag("artist", "A"),), add=want)
    assert in_source(edits) == Edits(clear=True)
    assert in_output(edits) == Edits(set=edits.set, add=edits.add)


def tags(*pairs: str) -> Metadata:
    return Metadata(tuple(Tag(*pair.split("=", 1)) for pair in pairs))


def test_set_where_the_key_stood_its_spelling_kept_the_rest_gone() -> None:
    meta = tags("Title=Old", "ARTIST=A", "title=Older")
    edited, notes = apply(meta, parse(["TITLE=New", "album=LP"], [], [], clear=False), "vorbis")
    assert edited.tags == (Tag("Title", "New"), Tag("ARTIST", "A"), Tag("ALBUM", "LP"))
    assert notes == ()


def test_add_after_the_keys_last_value() -> None:
    meta = tags("ARTIST=A", "TITLE=T")
    edited, _ = apply(meta, parse([], ["artist=B", "genre=Ska"], [], clear=False), "vorbis")
    assert edited.tags == (
        Tag("ARTIST", "A"),
        Tag("ARTIST", "B"),
        Tag("TITLE", "T"),
        Tag("GENRE", "Ska"),
    )


def test_ffmetadata_holds_one_value_a_key_joined_and_noted() -> None:
    edited, notes = apply(tags("artist=A"), parse([], ["artist=B"], [], clear=False), "ffmetadata")
    assert edited.tags == (Tag("artist", "A;B"),)
    assert notes == ("a tag 'artist': 2 values joined with ';', one a key",)


def test_clear_and_unset_leave_chapters_and_streams() -> None:
    meta = Metadata(
        (Tag("a", "1"), Tag("b", "2")), ((Tag("s", "1"),),), (Chapter(Fraction(0), None),)
    )
    assert apply(meta, parse([], [], ["A"], clear=False), "ffmetadata")[0] == Metadata(
        (Tag("b", "2"),), meta.streams, meta.chapters
    )
    assert apply(meta, parse(["c=3"], [], [], clear=True), "ffmetadata")[0].tags == (Tag("c", "3"),)


def disc(*rems: str, cdtext: tuple[Tag, ...] = (), catalog: str | None = None) -> Metadata:
    track = Track(1, "AUDIO", (Index(1, 0, 0),))
    return Metadata(disc=Disc((File("a.flac", "WAVE"),), (track,), cdtext, rems, catalog))


def test_a_cue_disc_its_fields_one_each() -> None:
    meta = disc("GENRE Ska", "DISCID 1", cdtext=(Tag("TITLE", "Old"),))
    edits = parse(
        ["genre=Alt Rock", "album=LP", "album_artist=Band", "date=1991", "BARCODE=0123456789012"],
        [],
        [],
        clear=False,
    )
    edited, notes = apply(meta, edits, "cue")
    assert edited.disc is not None
    assert edited.disc.rems == (
        'GENRE "Alt Rock"',
        "DISCID 1",
        "DATE 1991",
    )  # where it stood; quoted, spaced
    assert edited.disc.cdtext == (Tag("TITLE", "LP"), Tag("PERFORMER", "Band"))
    assert (edited.disc.catalog, notes) == ("0123456789012", ())
    unset = apply(edited, parse([], [], ["genre", "album", "barcode"], clear=False), "cue")[0].disc
    assert unset is not None
    assert (unset.rems, unset.cdtext, unset.catalog) == (
        ("DISCID 1", "DATE 1991"),
        (Tag("PERFORMER", "Band"),),
        None,
    )
    cleared = apply(edited, parse([], [], [], clear=True), "cue")[0].disc
    assert cleared is not None
    assert (cleared.rems, cleared.cdtext, cleared.catalog, cleared.tracks) == (
        (),
        (),
        None,
        edited.disc.tracks,
    )


@pytest.mark.parametrize(
    ("sets", "adds", "unsets", "message"),
    [
        (
            ["artist=X"],
            [],
            [],
            "--set artist: a cue sheet holds no artist (it holds: album, album_artist, genre, date, disc, REPLAYGAIN_ALBUM_GAIN, REPLAYGAIN_ALBUM_PEAK, BARCODE)",
        ),
        ([], ["genre=x"], [], "--add genre: a cue sheet holds one genre"),
    ],
)
def test_what_a_cue_refuses(
    sets: list[str], adds: list[str], unsets: list[str], message: str
) -> None:
    with pytest.raises(ffmeta.Error, match=rf"^{message.replace('(', '[(]').replace(')', '[)]')}"):
        _ = apply(disc(), parse(sets, adds, unsets, clear=False), "cue")


def test_a_rem_value_no_quote_holds_is_noted() -> None:
    edited, notes = apply(disc(), parse(['genre=say "hi" now'], [], [], clear=False), "cue")
    assert edited.disc is not None
    assert (edited.disc.rems, notes) == (
        (),
        ("the tag 'genre': a quote and a space: no REM quotes it: left out",),
    )


@settings(max_examples=200, deadline=None)
@given(
    vorbis_models(),
    st.sampled_from(("TITLE", "artist", "ALBUMARTIST", "New Key")),
    st.text(alphabet="ab ;é", max_size=4),
)
def test_a_set_key_holds_its_one_value_the_others_untouched(
    meta: Metadata, name: str, value: str
) -> None:
    edited, _ = apply(meta, parse([f"{name}={value}"], [], [], clear=False), "vorbis")
    mine = [t for t in edited.tags if key(t.name) == key(name)]
    others = [t for t in edited.tags if key(t.name) != key(name)]
    assert [t.value for t in mine] == [value]
    assert others == [t for t in meta.tags if key(t.name) != key(name)]
    assert (edited.chapters, edited.streams) == (meta.chapters, meta.streams)


def test_unsetting_what_a_cue_cannot_hold_is_nothing_to_remove() -> None:
    meta = disc("GENRE Ska")
    assert apply(meta, parse([], [], ["title", "artist"], clear=False), "cue") == (meta, ())


def test_a_cues_catalog_is_well_formed() -> None:
    with pytest.raises(ffmeta.Error, match=r"^--set barcode: a cue's CATALOG is 13 digits: 123$"):
        _ = apply(disc(), parse(["barcode=123"], [], [], clear=False), "cue")


def test_file_names_a_cues_one_media() -> None:
    renamed, _ = apply(disc(), Edits(file="My Album.flac"), "cue")
    assert renamed.disc is not None
    assert renamed.disc.files == (File("My Album.flac", "WAVE"),)
    with pytest.raises(
        ffmeta.Error, match=r"^--file names a cue's media: the output is ffmetadata$"
    ):
        _ = apply(Metadata(), Edits(file="x"), "ffmetadata")
    two = Metadata(
        disc=Disc(
            (File("1", "WAVE"), File("2", "WAVE")),
            (Track(1, "AUDIO", (Index(1, 0, 0),)), Track(2, "AUDIO", (Index(1, 0, 1),))),
        )
    )
    with pytest.raises(ffmeta.Error, match=r"^--file: a cue over 2 files names 2$"):
        _ = apply(two, Edits(file="x"), "cue")
