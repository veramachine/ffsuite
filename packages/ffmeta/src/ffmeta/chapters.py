"""Edits of a metadata file's chapters (spec 8) -- in a cue sheet, its tracks.

Those that name the input's chapter N (``--drop-chapter``, ``--retitle``, ``--chapter-set``,
``--clear-chapters``) apply in the input's words, before converting, so N is the input's;
``--chapter`` adds, in time order, in the output's words. Declarative, as the tags' edits.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Final

from ffmeta._errors import refuse, shown
from ffmeta.cue import FLAGS, LAST_FRAME, LAST_TIME, are_flags, is_isrc
from ffmeta.fields import TRACK, Format, key, rem_field, rem_text, spelled
from ffmeta.files import NAMES
from ffmeta.model import (
    FRAMES,
    Chapter,
    Disc,
    File,
    Index,
    Metadata,
    Tag,
    Track,
    exact,
    left_out,
    nearest,
    put,
    set_where,
)
from ffmeta.time import parse as parse_time

__all__ = ["ChapterEdits", "ChapterText", "NewChapter", "edit_chapters", "parse_chapters"]

_NUMBER: Final = re.compile(r"[1-9][0-9]{0,3}", re.ASCII)
_TRACK: Final = {key(field.ffmetadata): field for field in TRACK.fields}  # a track's, by key
_TRACK_HOLDS: Final = ", ".join(field.ffmetadata for field in TRACK.fields)


@dataclass(frozen=True, slots=True)
class NewChapter:
    """A chapter ``--chapter`` adds: its start, its end if given, its title if given."""

    start: Fraction
    end: Fraction | None
    title: str | None
    text: str  # as given: the notes name it so


@dataclass(frozen=True, slots=True)
class ChapterText:
    """The chapter edits as given on the command line, each option's values in order."""

    new: Sequence[str] = ()
    retitles: Sequence[str] = ()
    sets: Sequence[str] = ()
    drops: Sequence[str] = ()
    flags: Sequence[str] = ()
    pregaps: Sequence[str] = ()
    clear: bool = False


@dataclass(frozen=True, slots=True)
class ChapterEdits:
    """No chapter (``clear``), these of the input's gone, these tags on the input's, more."""

    clear: bool = False
    drop: frozenset[int] = frozenset()
    set: tuple[tuple[int, Tag], ...] = ()  # the input's chapter N, a tag of its
    new: tuple[NewChapter, ...] = ()
    flags: tuple[tuple[int, tuple[str, ...]], ...] = ()  # a cue's track N: its flags
    pregaps: tuple[
        tuple[int, Fraction | None, str], ...
    ] = ()  # its INDEX 00 (None: none), as given


def parse_chapters(given: ChapterText) -> ChapterEdits:
    """The chapter edits given; refused: a malformed one, or two that contradict."""
    edits = _tag_edits(given.retitles, given.sets)
    flagged = tuple(_flags(text) for text in given.flags)
    gapped = tuple(_pregap(text) for text in given.pregaps)
    dropped = frozenset(_number(text) for text in given.drops)
    _contradictions(
        [
            *((flag, number) for flag, number, _ in edits),
            *(("--flags", number) for number, _ in flagged),
            *(("--pregap", number) for number, _, _ in gapped),
        ],
        dropped,
        clear=given.clear,
    )
    _once("--flags", [number for number, _ in flagged])
    _once("--pregap", [number for number, _, _ in gapped])
    seen: set[tuple[int, str]] = set()
    for _, number, tag in edits:
        if (number, key(tag.name)) in seen:
            refuse(f"chapter {number}'s {tag.name} set twice")
        seen.add((number, key(tag.name)))
    added = tuple(_new(text) for text in given.new)
    tagged = tuple((number, tag) for _, number, tag in edits)
    return ChapterEdits(given.clear, dropped, tagged, added, flagged, gapped)


def _tag_edits(retitles: Sequence[str], sets: Sequence[str]) -> list[tuple[str, int, Tag]]:
    """``--retitle N=T`` (N's title) and ``--chapter-set N:K=V``: each its flag, N, tag."""
    edits: list[tuple[str, int, Tag]] = []
    for text in retitles:
        number, equals, title = text.partition("=")
        if not equals:
            refuse(f"--retitle needs N=TITLE: {shown(text)}")
        edits.append(("--retitle", _number(number), Tag("title", title)))
    for text in sets:
        number, colon, pair = text.partition(":")
        name, equals, value = pair.partition("=")
        if not colon or not equals or not name:
            refuse(f"--chapter-set needs N:KEY=VALUE: {shown(text)}")
        edits.append(("--chapter-set", _number(number), Tag(name, value)))
    return edits


def _contradictions(
    numbered: list[tuple[str, int]], dropped: frozenset[int], *, clear: bool
) -> None:
    """No edit of the input's chapter N with N dropped, or with every chapter cleared."""
    for flag, number in numbered:
        if clear:
            refuse(f"--clear-chapters and {flag} {number} contradict")
        if number in dropped:
            refuse(f"--drop-chapter {number} and {flag} {number} contradict")
    if clear and dropped:
        refuse(f"--clear-chapters and --drop-chapter {min(dropped)} contradict")


def _once(flag: str, numbers: list[int]) -> None:
    """Each N ``flag`` names, once."""
    twice = next((number for number in numbers if numbers.count(number) > 1), None)
    if twice is not None:
        refuse(f"{flag} {twice} twice")


def _flags(text: str) -> tuple[int, tuple[str, ...]]:
    """``N=FLAGS``: comma-separated, any case; empty: none."""
    number, equals, value = text.partition("=")
    if not equals:
        refuse(f"--flags needs N=FLAGS: {shown(text)}")
    names = tuple(name.strip().upper() for name in value.split(",")) if value else ()
    if not are_flags(names):
        refuse(f"FLAGS are {', '.join(FLAGS)}, each once: {shown(value)}")
    return _number(number), names


def _pregap(text: str) -> tuple[int, Fraction | None, str]:
    """``N=TIME``: track N's INDEX 00; empty: none."""
    number, equals, value = text.partition("=")
    if not equals:
        refuse(f"--pregap needs N=TIME: {shown(text)}")
    return _number(number), parse_time(value) if value else None, text


def _number(text: str) -> int:
    if _NUMBER.fullmatch(text) is None:
        refuse(f"a chapter number is 1, 2, 3...: {shown(text)}")
    return int(text)


def _new(text: str) -> NewChapter:
    """``TIME[..END][=TITLE]``."""
    times, equals, title = text.partition("=")
    start_text, dots, end_text = times.partition("..")
    start = parse_time(start_text)
    end = parse_time(end_text) if dots else None
    if end is not None and end < start:
        refuse(f"--chapter {shown(text)}: its end before its start")
    return NewChapter(start, end, title if equals else None, text)


def edit_chapters(
    meta: Metadata, edits: ChapterEdits, fmt: Format, media: str
) -> tuple[Metadata, tuple[str, ...]]:
    """``meta``'s chapters (a cue's tracks) edited, in ``fmt``'s words; a note for each loss.

    ``media`` names a new cue's FILE, should a track be its first.
    """
    if fmt == "cue":
        return _tracks(meta, edits, media)
    for flag, given in (("--flags", edits.flags), ("--pregap", edits.pregaps)):
        if given:
            refuse(f"{flag} edits a cue's tracks: the input is {NAMES[fmt]}")
    _within(edits, len(meta.chapters))
    seen: set[tuple[int, str]] = set()  # in this format's words: Vorbis' NAME is the title
    for number, tag in edits.set:
        if (number, _chapter_key(tag.name, fmt)) in seen:
            refuse(f"chapter {number}'s {tag.name} set twice")
        seen.add((number, _chapter_key(tag.name, fmt)))
    chapters = [] if edits.clear else list(meta.chapters)
    for number, tag in edits.set:
        chapter = chapters[number - 1]
        chapters[number - 1] = replace(chapter, tags=_tagged(chapter.tags, tag, fmt))
    chapters = [chapter for i, chapter in enumerate(chapters, 1) if i not in edits.drop]
    for new in edits.new:  # after the chapters starting no later
        title = (Tag(_chapter_spelled("title", fmt), new.title),) if new.title is not None else ()
        at = _after([chapter.start for chapter in chapters], new.start)
        chapters.insert(at, Chapter(new.start, new.end, title))
    return replace(meta, chapters=tuple(chapters)), ()


def _after[T: (Fraction, int)](starts: list[T], value: T) -> int:
    """The place after the last of ``starts`` no later than ``value``, in any order.

    In time order where they are (a cue's tracks); defined where not (Vorbis numbers chapters).
    """
    return max((i + 1 for i, start in enumerate(starts) if start <= value), default=0)


def _pregapped(
    tracks: list[Track], number: int, time: Fraction | None, text: str, notes: list[str]
) -> Track:
    """Track N's INDEX 00 at ``time`` (None: none), in its INDEX 01's file.

    Refused after its INDEX 01, or inside the track before.
    """
    track = tracks[number - 1]
    one, rest = track.start_index, tuple(index for index in track.indexes if index.number)
    if time is None:
        return replace(track, indexes=rest)
    frames = nearest(time, FRAMES)
    if exact(frames, FRAMES) != time:
        notes.append(f"--pregap {text}: between frames (1/75 s): at the nearest, frame {frames}")
    if frames > one.frames:
        refuse(f"--pregap {shown(text)}: after its INDEX 01 (frame {one.frames})")
    before = tracks[number - 2] if number > 1 else None
    later = (
        i for i in (before.indexes if before else ()) if i.file == one.file and i.frames > frames
    )
    if before is not None and (clash := next(later, None)):
        where = f"its INDEX {clash.number:02d} at frame {clash.frames}"
        refuse(f"--pregap {shown(text)}: inside track {before.number} ({where})")
    return replace(track, indexes=(Index(0, frames, one.file), *rest))


def _within(edits: ChapterEdits, count: int) -> None:
    """Each N an edit names is one of the input's ``count`` chapters."""
    named = {
        *edits.drop,
        *(n for n, _ in edits.set),
        *(n for n, _ in edits.flags),
        *(n for n, _, _ in edits.pregaps),
    }
    for number in sorted(named):
        if number > count:
            refuse(f"chapter {number}: the input has {count} chapters")


def _chapter_key(name: str, fmt: Format) -> str:
    """A chapter's tag key, as compared: Vorbis' NAME is its title."""
    generic = key(name)
    return "title" if fmt == "vorbis" and generic == "name" else generic


def _chapter_spelled(name: str, fmt: Format) -> str:
    if _chapter_key(name, fmt) == "title":
        return "NAME" if fmt == "vorbis" else "title"
    return spelled(name, fmt)


def _tagged(tags: tuple[Tag, ...], tag: Tag, fmt: Format) -> tuple[Tag, ...]:
    """``tag`` set on a chapter: where its key stood (its spelling kept), else last."""
    wanted = _chapter_key(tag.name, fmt)

    def same(held: Tag) -> bool:
        return _chapter_key(held.name, fmt) == wanted

    return tuple(set_where(list(tags), tag, same, _chapter_spelled(tag.name, fmt)))


def _tracks(meta: Metadata, edits: ChapterEdits, media: str) -> tuple[Metadata, tuple[str, ...]]:
    """A cue's tracks edited: their fields, drops, new tracks at the nearest frame."""
    disc = meta.disc or Disc((), ())
    _within(edits, len(disc.tracks))
    notes: list[str] = []
    tracks = [] if edits.clear else list(disc.tracks)
    for number, tag in edits.set:
        tracks[number - 1] = _track_set(tracks[number - 1], tag, number, notes)
    for number, names in edits.flags:
        tracks[number - 1] = replace(tracks[number - 1], flags=names)
    for number, time, text in edits.pregaps:
        tracks[number - 1] = _pregapped(tracks, number, time, text, notes)
    tracks = [track for i, track in enumerate(tracks, 1) if i not in edits.drop]
    files = list(disc.files) or [File(media, "WAVE")]
    for new in edits.new:
        tracks = _inserted(tracks, new, notes)
    first = disc.tracks[0].number if disc.tracks else 1
    return replace(meta, disc=_renumbered(disc, tracks, files, first)), tuple(notes)


def _track_set(track: Track, tag: Tag, number: int, notes: list[str]) -> Track:
    """``tag`` on a cue's track: its CD-Text, a REM line, or its ISRC."""
    field = _TRACK.get(key(tag.name))
    if field is None:
        holds = f"a cue's track holds no {tag.name} (it holds: {_TRACK_HOLDS})"
        refuse(f"--chapter-set {number}:{tag.name}: {holds}")
    if field.cue == "ISRC":
        if not is_isrc(tag.value):
            form = f"a cue's ISRC is CCOOOYYSSSSS (12): {shown(tag.value)}"
            refuse(f"--chapter-set {number}:{tag.name}: {form}")
        return replace(track, isrc=tag.value)
    if field.cue.startswith("REM "):
        # rem_text is None only for a quoted field (a disc's GENRE): none of a track's is
        text = rem_text(field, tag, notes)

        def same(rem: str) -> bool:
            return rem_field(rem)[0] == field.cue

        rems = put(list(track.rems), text, same) if text is not None else list(track.rems)
        return replace(track, rems=tuple(rems))
    cdtext = put(list(track.cdtext), Tag(field.cue, tag.value), lambda old: old.name == field.cue)
    return replace(track, cdtext=tuple(cdtext))


def _inserted(tracks: list[Track], new: NewChapter, notes: list[str]) -> list[Track]:
    """A track for ``new`` among ``tracks``, by time; refused inside one, or over two files."""
    what = f"--chapter {shown(new.text)}"
    files = {index.file for track in tracks for index in track.indexes}
    if len(files) > 1:
        refuse(f"{what}: a cue over {len(files)} files: which one the track is in cannot be told")
    file = min(files, default=0)
    frames = nearest(new.start, FRAMES)
    if frames > LAST_FRAME:
        refuse(f"{what}: past a cue's last time ({LAST_TIME})")
    if exact(frames, FRAMES) != new.start:
        notes.append(
            f"--chapter {new.text}: between frames (1/75 s): at the nearest, frame {frames}"
        )
    if new.end is not None:
        why = "a cue's track ends where the next starts"
        notes.append(left_out(f"--chapter {new.text}'s end", why))
    at = _after([track.start_index.frames for track in tracks], frames)
    if at == 0 and tracks and (zero := tracks[0].index(0)) is not None and zero.frames == 0:
        old = tracks[0]  # the time before the first track: now the new first's, at 0 or after
        tracks = [replace(old, indexes=old.indexes[1:]), *tracks[1:]]
    earlier = tracks[at - 1] if at else None  # its indexes: none past the new one
    later = tracks[at] if at < len(tracks) else None  # its indexes: none before it
    for track, clash in (
        (
            earlier,
            next((i for i in earlier.indexes if i.frames > frames), None) if earlier else None,
        ),
        (later, next((i for i in later.indexes if i.frames < frames), None) if later else None),
    ):
        if track is not None and clash is not None:
            where = f"its INDEX {clash.number:02d} at frame {clash.frames}"
            refuse(f"{what}: inside track {track.number} ({where})")
    one = Index(1, frames, file)
    indexes = (Index(0, 0, file), one) if at == 0 and frames else (one,)  # track 1's time before
    cdtext = (Tag("TITLE", new.title),) if new.title is not None else ()
    return [*tracks[:at], Track(1, "AUDIO", indexes, cdtext), *tracks[at:]]


def _renumbered(disc: Disc, tracks: list[Track], files: list[File], first: int) -> Disc:
    """``tracks`` numbered from ``first``, one more each; the files they use alone, in turn."""
    used = sorted({index.file for track in tracks for index in track.indexes})
    moved = {old: new for new, old in enumerate(used)}

    def renumbered(i: int, track: Track) -> Track:
        indexes = tuple(replace(index, file=moved[index.file]) for index in track.indexes)
        return replace(track, number=first + i, indexes=indexes)

    numbered = tuple(renumbered(i, track) for i, track in enumerate(tracks))
    return replace(disc, files=tuple(files[old] for old in used), tracks=numbered)
