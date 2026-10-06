"""Conversions between the three formats' words, through the model (``docs/ffman-mappings.md``).

A reader gives a model in its format's words -- names as written; a conversion renames and
reshapes it into another's, a row of the mappings an entry of the tables here, each loss noted.
The target's writer then writes it, noting what its own form cannot hold (a Vorbis chapter's
end, a quote in a cue string): those are its notes, not repeated here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Final

from ffmeta._errors import refuse
from ffmeta.cue import LAST_FRAME, LAST_TIME
from ffmeta.fields import (
    BARCODE,
    DISC,
    DISC_BY_CUE,
    RENAMED,
    TRACK,
    TRACK_BY_CUE,
    Field,
    Format,
    Table,
    joined,
    rem_field,
    rem_text,
)
from ffmeta.model import (
    FRAMES,
    TRACKS,
    Chapter,
    Disc,
    File,
    Index,
    Metadata,
    Tag,
    Tags,
    Track,
    exact,
    folded,
    left_out,
    nearest,
)

__all__ = ["Converted", "convert"]


@dataclass(frozen=True, slots=True)
class Converted:
    """A model in the target's words, and a note for each thing that did not cross."""

    meta: Metadata
    notes: tuple[str, ...] = ()


_CUE_TRACKS: Final = len(TRACKS)  # 99


def convert(
    meta: Metadata,
    source: Format,
    target: Format,
    *,
    media: str = "",
    durations: Sequence[Fraction] = (),
) -> Converted:
    """``meta``, read as ``source``, in ``target``'s words.

    ``media`` names a cue's FILE (the target cue's media); ``durations`` are a source cue's
    files' lengths in seconds, which place the tracks of every file after the first.
    """
    if source == target:
        return Converted(meta)
    if target == "cue":
        if not media:
            msg = "a cue sheet names its media: media is empty"
            raise ValueError(msg)
        return _to_cue(meta, source, media)
    if source == "cue":
        return _from_cue(meta, target, durations)
    return _between_tags(meta, target)


def _between_tags(meta: Metadata, target: Format) -> Converted:
    """Between ffmetadata and Vorbis (table 1): ffmpeg's four names, a chapter's title.

    A name repeated is joined with ';' for ffmetadata, as ffmpeg does -- noted.
    """
    if target == "vorbis":
        renamed = {folded(generic): vorbis for generic, vorbis in RENAMED}
        title = {"title": "NAME"}
    else:
        renamed = {folded(vorbis): generic for generic, vorbis in RENAMED}
        title = {"name": "title"}
    notes: list[str] = []
    tags = tuple(Tag(renamed.get(folded(tag.name), tag.name), tag.value) for tag in meta.tags)
    if target == "ffmetadata":
        tags = joined(tags, "a tag", notes)
    chapters: list[Chapter] = []
    for number, chapter in enumerate(meta.chapters, 1):
        held: list[Tag] = []
        for tag in chapter.tags:
            if target == "vorbis" and folded(tag.name) == "name":  # a key of ffmetadata's own
                notes.append(
                    left_out(f"chapter {number}'s tag '{tag.name}'", "Vorbis' NAME is a title")
                )
            else:
                held.append(Tag(title.get(folded(tag.name), tag.name), tag.value))
        chapters.append(Chapter(chapter.start, chapter.end, tuple(held)))
    return Converted(Metadata(tags, meta.streams, tuple(chapters), meta.disc), tuple(notes))


def _from_cue(meta: Metadata, target: Format, durations: Sequence[Fraction]) -> Converted:
    """A cue's disc as tags and chapters (table 2): a track a chapter from its INDEX 01."""
    disc = meta.disc
    if disc is None:
        msg = "a cue sheet's model holds a disc"
        raise ValueError(msg)
    notes: list[str] = []
    offsets = _offsets(disc, durations)
    tags = _fields(_lines(disc.cdtext, disc.rems), DISC_BY_CUE, target, "the disc's", notes)
    if disc.catalog is not None:
        tags.append(Tag(BARCODE, disc.catalog))
    if disc.cdtextfile is not None:
        notes.append(left_out("the disc's CDTEXTFILE", "none maps it"))
    chapters: list[Chapter] = []
    for track in disc.tracks:
        what = f"track {track.number:02d}'s"
        lines = _lines(track.cdtext, track.rems)
        if track.isrc is not None:
            lines.append(("ISRC", track.isrc))
        held = _fields(lines, TRACK_BY_CUE, target, what, notes)
        one = track.start_index
        chapters.append(Chapter(offsets[one.file] + exact(one.frames, FRAMES), None, tuple(held)))
    ended = [Chapter(c.start, n.start, c.tags) for c, n in pairwise(chapters)] + chapters[-1:]
    notes += _cue_only(disc)
    if len(disc.files) > 1:
        notes.append(left_out(f"the {len(disc.files)} FILEs' bounds", "chapters are of one stream"))
    return Converted(Metadata(tuple(tags), chapters=tuple(ended)), tuple(notes))


def _offsets(disc: Disc, durations: Sequence[Fraction]) -> list[Fraction]:
    """Where each file starts in one stream: the durations of the files before it."""
    if len(durations) < len(disc.files) - 1:
        refuse(
            f"a cue sheet over {len(disc.files)} files: its tracks are placed by the durations"
            + f" of the first {len(disc.files) - 1}, {len(durations)} given"
        )
    offsets = [Fraction(0)]
    for duration in durations[: len(disc.files) - 1]:
        offsets.append(offsets[-1] + duration)
    return offsets


def _fields(
    lines: list[tuple[str, str]],
    by_cue: dict[str, Field],
    target: Format,
    what: str,
    notes: list[str],
) -> list[Tag]:
    """A cue's lines -- each its command and value -- as the target's tags; the rest noted."""
    tags: list[Tag] = []
    for command, value in lines:
        field = by_cue.get(command)
        name = None if field is None else field.name(target)
        if name is None:
            why = "none maps it" if field is None else "Vorbis' chapters hold a title alone"
            notes.append(left_out(f"{what} {command}", why))
        else:
            tags.append(Tag(name, value))
    return tags


def _lines(cdtext: Tags, rems: tuple[str, ...]) -> list[tuple[str, str]]:
    """CD-Text and REM lines as (command, value): a REM's command is ``REM`` and its word."""
    return [(tag.name, tag.value) for tag in cdtext] + [rem_field(rem) for rem in rems]


def _pregap_noted(disc: Disc, track: Track) -> bool:
    """Whether chapters lose this INDEX 00: all but track 1's at 0 before its INDEX 01.

    That one a cue written from chapters holds again: the time before the first chapter.
    """
    zero, one = track.index(0), track.start_index
    if zero is None:
        return False
    first_at_zero = track is disc.tracks[0] and zero.frames == zero.file == one.file == 0
    return not (first_at_zero and one.frames > 0)


def _cue_only(disc: Disc) -> list[str]:
    """What a cue's layout holds that chapters cannot: noted once a kind, its tracks named."""
    kinds = {
        "INDEX 00 (a pregap: the chapter before's, as mpv and Kodi place it)": [
            t for t in disc.tracks if _pregap_noted(disc, t)
        ],
        "INDEX 02 and after": [t for t in disc.tracks if t.index(2) is not None],
        "PREGAP": [t for t in disc.tracks if t.pregap is not None],
        "POSTGAP": [t for t in disc.tracks if t.postgap is not None],
        "FLAGS": [t for t in disc.tracks if t.flags],
        "a data mode": [t for t in disc.tracks if t.mode != "AUDIO"],
    }
    notes = [
        left_out(
            f"{kind}, track {', '.join(f'{t.number:02d}' for t in tracks)}", "chapters hold none"
        )
        for kind, tracks in kinds.items()
        if tracks
    ]
    first = disc.tracks[0].number if disc.tracks else 1
    if first != 1:
        notes.append(
            left_out("the track numbers", f"chapters count from 1, these from {first:02d}")
        )
    return notes


def _to_cue(meta: Metadata, source: Format, media: str) -> Converted:
    """Tags and chapters as a cue's disc (table 3): a chapter a track at its nearest frame."""
    notes: list[str] = []
    disc_lines = _cue_lines(meta.tags, DISC, source, "the tag", notes)
    if meta.streams:
        notes.append(left_out("streams' tags", "a cue sheet holds the disc's and its tracks'"))
    chapters = sorted(meta.chapters, key=lambda chapter: chapter.start)  # stable: ties keep order
    if chapters != list(meta.chapters):
        notes.append("the chapters: not in time order, so reordered: a cue's tracks run in time")
    if len(chapters) > _CUE_TRACKS:
        why = f"a cue sheet holds {_CUE_TRACKS} tracks"
        notes.append(left_out(f"chapters {_CUE_TRACKS + 1} to {len(chapters)}", why))
        chapters = chapters[:_CUE_TRACKS]
    far = next(
        (i for i, chapter in enumerate(chapters) if nearest(chapter.start, FRAMES) > LAST_FRAME),
        None,
    )
    if far is not None:  # in time order: every one after it as far
        why = f"past a cue's last time ({LAST_TIME})"
        notes.append(left_out(f"chapters {far + 1} to {len(chapters)}", why))
        chapters = chapters[:far]
    if chapters and chapters[-1].end is not None:
        notes.append(
            left_out(f"chapter {len(chapters)}'s end", "a cue's last track ends with its media")
        )
    for number, (chapter, after) in enumerate(pairwise(chapters), 1):
        if chapter.end is not None and chapter.end != after.start:
            gap = "a gap" if chapter.end < after.start else "an overlap"
            notes.append(
                left_out(f"chapter {number}'s end", f"{gap}: a track ends where the next starts")
            )
    tracks = [_track(number, chapter, source, notes) for number, chapter in enumerate(chapters, 1)]
    if not tracks:
        notes.append("no chapters: a cue sheet lays out tracks, so one, at 0")
        tracks = [Track(1, "AUDIO", (Index(1, 0, 0),))]
    disc = Disc(
        (File(media, "WAVE"),),
        tuple(tracks),
        disc_lines.cdtext,
        disc_lines.rems,
        disc_lines.values.get("CATALOG"),
    )
    return Converted(Metadata(disc=disc), tuple(notes))


@dataclass(frozen=True, slots=True)
class _CueLines:
    """Tags as a cue's lines: CD-Text, REM texts, and the rest by command (CATALOG, ISRC)."""

    cdtext: tuple[Tag, ...]
    rems: tuple[str, ...]
    values: dict[str, str]


def _cue_lines(tags: Tags, table: Table, source: Format, what: str, notes: list[str]) -> _CueLines:
    """``tags`` by ``table``: each its line once; every other tag, or a field again, noted."""
    fields = table.fields
    by_name = {folded(name): field for field in fields if (name := field.name(source)) is not None}
    cdtext: list[Tag] = []
    rems: list[str] = []
    values: dict[str, str] = {}
    used: set[str] = set()
    for tag in tags:
        field = by_name.get(folded(tag.name))
        if field is None or field.cue in used:
            why = (
                "no cue field" if field is None else f"again: {table.holder} holds one {field.cue}"
            )
            notes.append(left_out(f"{what} '{tag.name}'", why))
            continue
        used.add(field.cue)
        if field.cue.startswith("REM "):
            if (rem := rem_text(field, tag, notes)) is not None:
                rems.append(rem)
        elif field.cue in {"TITLE", "PERFORMER"}:
            cdtext.append(Tag(field.cue, tag.value))
        else:  # its own command: the cue writer checks its form (13 digits, CCOOOYYSSSSS)
            values[field.cue] = tag.value
    return _CueLines(tuple(cdtext), tuple(rems), values)


def _track(number: int, chapter: Chapter, source: Format, notes: list[str]) -> Track:
    """A chapter as a track: INDEX 01 at its nearest frame (track 1 after 0: INDEX 00 at 0)."""
    frames = nearest(chapter.start, FRAMES)
    if exact(frames, FRAMES) != chapter.start:
        notes.append(
            f"chapter {number} starts between frames (1/75 s): at the nearest, frame {frames}"
        )
    indexes = (Index(1, frames, 0),)
    if number == 1 and frames:
        indexes = (Index(0, 0, 0), *indexes)  # the time before it, track 1's (the cue skill)
    lines = _cue_lines(chapter.tags, TRACK, source, f"chapter {number}'s tag", notes)
    return Track(number, "AUDIO", indexes, lines.cdtext, lines.rems, isrc=lines.values.get("ISRC"))
