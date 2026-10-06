"""Edits of a metadata file's tags (spec 8): what the result holds, in the output's words.

Declarative: ``--clear``, then ``--unset``, ``--set``, ``--add`` -- their order on the command
line is none of theirs, so what would hang on it (a key set twice, set and unset) is refused.
A key is ffmpeg's generic one (``avformat.h``) or Vorbis' own, any case, written in the
output's spelling (``fields.py``); another key as given -- a cue sheet holds none.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Final

from ffmeta._errors import refuse, shown
from ffmeta.chapters import ChapterEdits, edit_chapters
from ffmeta.cue import is_catalog
from ffmeta.fields import DISC, Field, Format, joined, key, rem_field, rem_text, spelled
from ffmeta.files import NAMES
from ffmeta.model import Disc, Metadata, Tag, Tags, folded, put, set_where

__all__ = ["Edits", "apply", "in_output", "in_source", "parse"]

_CUE: Final = {folded(field.ffmetadata): field for field in DISC.fields}  # a disc's, by key
_CUE_HOLDS: Final = ", ".join(field.ffmetadata for field in DISC.fields)


@dataclass(frozen=True, slots=True)
class Edits:
    """What the result holds: no tag (``clear``), no value for these keys, these values, more."""

    clear: bool = False
    unset: tuple[str, ...] = ()
    set: tuple[Tag, ...] = ()
    add: tuple[Tag, ...] = ()
    chapters: ChapterEdits = field(default_factory=ChapterEdits)
    file: str | None = None  # a cue's one FILE: the media it names


def parse(sets: list[str], adds: list[str], unsets: list[str], *, clear: bool) -> Edits:
    """The edits given; refused: no ``KEY=VALUE``, a key set twice, set or added and unset."""
    set_tags = tuple(_pair("--set", text) for text in sets)
    add_tags = tuple(_pair("--add", text) for text in adds)
    if any(not name for name in unsets):
        refuse("--unset needs a KEY")
    seen: set[str] = set()
    for tag in set_tags:
        if key(tag.name) in seen:
            refuse(f"--set {tag.name} twice: --add gives another value")
        seen.add(key(tag.name))
    unset = {key(name): name for name in unsets}
    for flag, tags in (("--set", set_tags), ("--add", add_tags)):
        for tag in tags:
            if key(tag.name) in unset:
                refuse(f"{flag} {tag.name} and --unset {unset[key(tag.name)]} contradict")
    return Edits(clear, tuple(unsets), set_tags, add_tags)


def _pair(flag: str, text: str) -> Tag:
    name, equals, value = text.partition("=")
    if not equals or not name:
        refuse(f"{flag} needs KEY=VALUE: {shown(text)}")
    return Tag(name, value)


def apply(
    meta: Metadata, edits: Edits, fmt: Format, media: str = ""
) -> tuple[Metadata, tuple[str, ...]]:
    """``meta``, in ``fmt``'s words, edited -- its tags, then its chapters; a note for each loss.

    ``media`` names a new cue's FILE, should a track be its first.
    """
    tagged, tag_notes = _disc(meta, edits) if fmt == "cue" else _tags(meta, edits, fmt)
    edited, chapter_notes = edit_chapters(tagged, edits.chapters, fmt, media)
    return edited, (*tag_notes, *chapter_notes)


def _tags(meta: Metadata, edits: Edits, fmt: Format) -> tuple[Metadata, tuple[str, ...]]:
    """The tags of ffmetadata or Vorbis comments, edited."""
    if edits.file is not None:
        refuse(f"--file names a cue's media: the output is {NAMES[fmt]}")
    notes: list[str] = []
    gone = {key(name) for name in edits.unset}
    kept: Tags = () if edits.clear else meta.tags
    tags = [tag for tag in kept if key(tag.name) not in gone]
    for tag in edits.set:  # where the key stood, its spelling kept; else last
        tags = set_where(tags, tag, _keyed(tag.name), spelled(tag.name, fmt))
    for tag in edits.add:  # after the key's last value, its spelling kept; else last
        last = max((i for i, held in enumerate(tags) if _keyed(tag.name)(held)), default=None)
        name = spelled(tag.name, fmt) if last is None else tags[last].name
        tags.insert(len(tags) if last is None else last + 1, Tag(name, tag.value))
    held = tuple(tags) if fmt == "vorbis" else joined(tuple(tags), "a tag", notes)  # one a key
    return replace(meta, tags=held), tuple(notes)


def _keyed(name: str) -> Callable[[Tag], bool]:
    """Whether a tag is ``name``'s, as ffman compares keys."""
    wanted = key(name)
    return lambda held: key(held.name) == wanted


def in_source(edits: Edits) -> Edits:
    """The edits in the input's words, applied before converting.

    What takes away (``--clear``, ``--unset``, ``--clear-chapters``, ``--drop-chapter``), so
    nothing gone is ever noted lost; and what names the input's chapter N (``--retitle``,
    ``--chapter-set``), so N is the input's.
    """
    chapters = replace(edits.chapters, new=())
    return Edits(clear=edits.clear, unset=edits.unset, chapters=chapters)


def in_output(edits: Edits) -> Edits:
    """The edits in the output's words, after converting: ``--set``, ``--add``, ``--chapter``."""
    return Edits(
        set=edits.set, add=edits.add, chapters=ChapterEdits(new=edits.chapters.new), file=edits.file
    )


def _field(flag: str, name: str) -> Field:
    field = _CUE.get(key(name))
    if field is None:
        refuse(f"{flag} {name}: a cue sheet holds no {name} (it holds: {_CUE_HOLDS})")
    return field


def _disc(meta: Metadata, edits: Edits) -> tuple[Metadata, tuple[str, ...]]:
    """A cue's disc edited: its CD-Text, REM lines and CATALOG, one value each."""
    unset = [_CUE[key(name)] for name in edits.unset if key(name) in _CUE]  # else: none to remove
    sets = [(_field("--set", tag.name), tag) for tag in edits.set]
    for tag in edits.add:
        refuse(f"--add {tag.name}: a cue sheet holds one {_field('--add', tag.name).ffmetadata}")
    disc = meta.disc or Disc((), ())
    cdtext = [] if edits.clear else list(disc.cdtext)
    rems = [] if edits.clear else list(disc.rems)
    catalog = None if edits.clear else disc.catalog
    notes: list[str] = []
    for entry in unset:
        cdtext = [tag for tag in cdtext if tag.name != entry.cue]
        rems = [rem for rem in rems if rem_field(rem)[0] != entry.cue]
        catalog = None if entry.cue == "CATALOG" else catalog
    for entry, tag in sets:
        if entry.cue == "CATALOG":
            if not is_catalog(tag.value):
                refuse(f"--set {tag.name}: a cue's CATALOG is 13 digits: {shown(tag.value)}")
            catalog = tag.value
        elif entry.cue.startswith("REM "):
            if (text := rem_text(entry, tag, notes)) is not None:
                rems = put(rems, text, lambda rem, cue=entry.cue: rem_field(rem)[0] == cue)
        else:
            cdtext = put(
                cdtext, Tag(entry.cue, tag.value), lambda held, cue=entry.cue: held.name == cue
            )
    files = disc.files
    if edits.file is not None and len(files) > 1:
        refuse(f"--file: a cue over {len(files)} files names {len(files)}")
    if edits.file is not None and files:
        files = (replace(files[0], name=edits.file),)  # with none, a track's makes one: the media's
    edited = replace(disc, files=files, cdtext=tuple(cdtext), rems=tuple(rems), catalog=catalog)
    return replace(meta, disc=edited), tuple(notes)
