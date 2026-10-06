from collections.abc import Callable
from fractions import Fraction

import pytest
from ffmeta.model import (
    FRAMES,
    MILLISECONDS,
    Chapter,
    Disc,
    File,
    Index,
    Metadata,
    Track,
    Written,
    exact,
    folded,
    left_out,
    nearest,
)
from hypothesis import given, settings
from hypothesis import strategies as st


def test_a_name_folds_its_ascii_case_only() -> None:
    assert folded("ARTIST") == folded("artist") == "artist"
    assert folded("Album_Artist") == "album_artist"
    # ffmpeg folds A-Z only (av_tolower), Vorbis names are ASCII: these are two names
    assert folded("TÍTULO") == "tÍtulo" != folded("título")
    assert folded("artist") != folded("artists")


def test_a_chapter_starts_at_zero_or_after_and_ends_at_its_start_or_after() -> None:
    assert Chapter(Fraction(0), None).end is None
    assert Chapter(Fraction(3, 2), Fraction(3, 2)).end == Fraction(
        3, 2
    )  # no length: ffmpeg makes them
    with pytest.raises(ValueError, match=r"^a chapter's start is negative: -1/75$"):
        _ = Chapter(Fraction(-1, 75), None)
    with pytest.raises(ValueError, match=r"^a chapter ends before it starts: 1 < 2$"):
        _ = Chapter(Fraction(2), Fraction(1))


@pytest.mark.parametrize(
    ("number", "frames", "file", "message"),
    [
        (-1, 0, 0, r"^an index number outside 0-99: -1$"),
        (100, 0, 0, r"^an index number outside 0-99: 100$"),
        (1, -1, 0, r"^an index's frames is negative: -1$"),
        (1, 0, -1, r"^an index's file is negative: -1$"),
    ],
)
def test_an_index_out_of_range_is_a_bug(number: int, frames: int, file: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = Index(number, frames, file)


def test_an_index_at_its_bounds() -> None:
    assert Index(0, 0, 0).number == 0
    assert Index(99, 4_500_000, 3).frames == 4_500_000


ONE = (Index(1, 0, 0),)


@pytest.mark.parametrize(
    ("track", "message"),
    [
        (lambda: Track(0, "AUDIO", ONE), r"^a track number outside 1-99: 0$"),
        (lambda: Track(100, "AUDIO", ONE), r"^a track number outside 1-99: 100$"),
        (
            lambda: Track(1, "AUDIO", (Index(1, 0, 0), Index(0, 0, 0))),
            r"^a track's index numbers do not count up by one: \[1, 0\]$",
        ),
        (
            lambda: Track(1, "AUDIO", (Index(1, 0, 0), Index(1, 5, 0))),
            r"^a track's index numbers do not count up by one: \[1, 1\]$",
        ),
        (
            lambda: Track(1, "AUDIO", (Index(1, 0, 0), Index(3, 5, 0))),
            r"^a track's index numbers do not count up by one: \[1, 3\]$",
        ),
        (
            lambda: Track(1, "AUDIO", ()),
            r"^track 1 has no INDEX 01 first or after its INDEX 00: \[\]$",
        ),
        (
            lambda: Track(1, "AUDIO", (Index(0, 0, 0),)),
            r"^track 1 has no INDEX 01 first or after its INDEX 00: \[0\]$",
        ),
        (
            lambda: Track(2, "AUDIO", (Index(2, 0, 0), Index(3, 0, 0))),
            r"^track 2 has no INDEX 01 first or after its INDEX 00: \[2, 3\]$",
        ),
        (
            lambda: Track(1, "AUDIO", (Index(1, 0, 0), Index(2, 0, 1))),
            r"^track 1's indexes from 01 on are in more than one file$",
        ),
        (lambda: Track(1, "AUDIO", ONE, pregap=-1), r"^a pregap is negative: -1$"),
        (lambda: Track(1, "AUDIO", ONE, postgap=-150), r"^a postgap is negative: -150$"),
    ],
)
def test_a_track_out_of_shape_is_a_bug(track: Callable[[], Track], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = track()


def test_a_track_finds_its_indexes() -> None:
    track = Track(2, "AUDIO", (Index(0, 17870, 0), Index(1, 18000, 0), Index(2, 18500, 0)))
    assert track.index(1) == Index(1, 18000, 0)
    assert track.index(0) == Index(0, 17870, 0)
    assert track.index(3) is None
    assert Track(99, "MODE1/2352", ONE, pregap=0, postgap=0).number == 99


def test_a_disc_holds_eacs_track_over_two_files_and_a_hidden_track() -> None:
    # Hydrogenaudio's non-compliant layout: track 2's INDEX 00 in the first file, 01 in the next
    disc = Disc(
        (File("1.wav", "WAVE"), File("2.wav", "WAVE")),
        (
            Track(1, "AUDIO", (Index(0, 0, 0), Index(1, 2250, 0))),  # a hidden track before 01
            Track(2, "AUDIO", (Index(0, 12599, 0), Index(1, 0, 1))),
        ),
    )
    assert [index.file for index in disc.tracks[1].indexes] == [0, 1]
    assert disc.cdtext == disc.rems == ()
    assert disc.catalog is disc.cdtextfile is None
    assert Disc((), ()).tracks == ()  # no track: a writer's to note


def _disc(files: int, *tracks: tuple[int, tuple[tuple[int, int, int], ...]]) -> Disc:
    return Disc(
        tuple(File(f"{n}.wav", "WAVE") for n in range(files)),
        tuple(
            Track(number, "AUDIO", tuple(Index(*index) for index in indexes))
            for number, indexes in tracks
        ),
    )


@pytest.mark.parametrize(
    ("disc", "message"),
    [
        (
            lambda: _disc(1, (2, ((1, 0, 0),)), (1, ((1, 5, 0),))),
            r"^the disc's track numbers do not count up by one: \[2, 1\]$",
        ),
        (
            lambda: _disc(1, (1, ((1, 0, 0),)), (1, ((1, 5, 0),))),
            r"^the disc's track numbers do not count up by one: \[1, 1\]$",
        ),
        (
            lambda: _disc(1, (1, ((1, 0, 0),)), (3, ((1, 5, 0),))),
            r"^the disc's track numbers do not count up by one: \[1, 3\]$",
        ),
        (
            lambda: _disc(2, (1, ((1, 0, 1),))),
            r"^the disc's first index is in file 1, not its first$",
        ),
        (
            lambda: _disc(3, (1, ((1, 0, 0),)), (2, ((1, 0, 2),))),
            r"^track 2's index 1: file 2 after 0$",
        ),
        (
            lambda: _disc(2, (1, ((1, 0, 0),)), (2, ((1, 0, 1),)), (3, ((1, 0, 0),))),
            r"^track 3's index 1: file 0 after 1$",
        ),
        (
            lambda: _disc(1, (1, ((1, 750, 0),)), (2, ((1, 700, 0),))),
            r"^track 2's index 1 goes back in its file: 700 < 750 \(track 1's index 1\)$",
        ),
        (
            lambda: _disc(
                1,
                (
                    1,
                    ((0, 100, 0), (1, 50, 0)),
                ),
            ),
            r"^track 1's index 1 goes back in its file: 50 < 100 \(track 1's index 0\)$",
        ),
        (lambda: _disc(2, (1, ((1, 0, 0),))), r"^the disc's files: 2; its indexes use 1$"),
        (lambda: _disc(0, (1, ((1, 0, 0),))), r"^the disc's files: 0; its indexes use 1$"),
        (lambda: _disc(1), r"^the disc's files: 1; its indexes use 0$"),
    ],
)
def test_a_disc_out_of_shape_is_a_bug(disc: Callable[[], Disc], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = disc()


def test_the_others_hold_no_disc_and_a_writer_may_note_nothing() -> None:
    assert Metadata() == Metadata((), (), (), None)
    assert Written("x").notes == ()


def test_exact_is_seconds() -> None:
    assert exact(19327, FRAMES) == Fraction(19327, 75)
    assert exact(1500, MILLISECONDS) == Fraction(3, 2)


def test_nearest_rounds_a_half_up() -> None:
    assert nearest(Fraction(1, 150), FRAMES) == 1  # half a frame
    assert nearest(Fraction(1, 151), FRAMES) == 0
    assert nearest(Fraction(1, 2000), MILLISECONDS) == 1
    assert nearest(Fraction(257693, 1000), FRAMES) == 19327  # ffman-mappings.md, H
    assert nearest(Fraction(750500, 1000), FRAMES) == 56288  # 56287.5 frames: up


@settings(max_examples=500, deadline=None)
@given(st.integers(min_value=0, max_value=10**12), st.sampled_from([FRAMES, MILLISECONDS, 44100]))
def test_nearest_undoes_exact(count: int, per_second: int) -> None:
    assert nearest(exact(count, per_second), per_second) == count


@settings(max_examples=500, deadline=None)
@given(
    st.fractions(min_value=0, max_value=10**7, max_denominator=10**9),
    st.sampled_from([FRAMES, MILLISECONDS]),
)
def test_nearest_is_half_a_unit_off_at_most(seconds: Fraction, per_second: int) -> None:
    assert abs(exact(nearest(seconds, per_second), per_second) - seconds) <= Fraction(
        1, 2 * per_second
    )


def test_a_cues_frames_cross_milliseconds_and_back_every_one_to_an_hour() -> None:
    # ffman-mappings.md, D: a frame to the nearest millisecond (never a tie), and back
    for frames in range(FRAMES * 3600 + 1):
        ms = nearest(exact(frames, FRAMES), MILLISECONDS)
        assert nearest(exact(ms, MILLISECONDS), FRAMES) == frames


def test_a_writers_note_for_what_it_leaves_out() -> None:
    assert (
        left_out("chapter 2", "it starts past 99:59:59.999")
        == "chapter 2: it starts past 99:59:59.999: left out"
    )
