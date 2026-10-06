r"""Vorbis comments as text, ffman's form of them: read and written.

The form is the vorbiscomment skill's, decided from ``vorbiscomment -e`` and ``metaflac``: a
comment a line, ``NAME=value``, every line ended by LF; a name of ASCII 0x20-0x7D but ``=``
and ``~`` (the Vorbis I specification's range, less what libFLAC and vorbiscomment refuse); a
value in UTF-8 whose backslash, line feed and carriage return are written ``\\``, ``\n``,
``\r``. Anything else is refused, naming the line.

Chapters are the Chapter Extension's comments (Xiph): ``CHAPTERxxx=HH:MM:SS.mmm``, its
``CHAPTERxxxNAME`` and ``CHAPTERxxxURL``, ``xxx`` three digits, names without ASCII case.
A name ffmpeg may read as a chapter's though it is not the extension's -- ``CHAPTER01``,
``CHAPTER1000NAME`` (chapter 100's, to its ``sscanf``) -- is refused, as are a chapter's
comments before its time (ffmpeg drops a title so placed) or repeated (it keeps the last).
Every other name is a tag, ``CHAPTER000ARTIST`` too, as ffmpeg reads it.
"""

import re
from collections.abc import Iterable
from typing import Final

from ffmeta._errors import refuse_at, shown
from ffmeta.model import (
    MILLISECONDS,
    Chapter,
    Metadata,
    Tag,
    Tags,
    Written,
    exact,
    folded,
    left_out,
    nearest,
)

__all__ = ["CHAPTERS", "comments", "read", "text", "write"]

CHAPTERS: Final = 1000  # CHAPTER000-CHAPTER999
_NAME: Final = re.compile(r"[\x20-\x3c\x3e-\x7d]+")  # 0x20-0x7D but '=' (0x3D); '~' is 0x7E
_ESCAPE: Final = re.compile(r"\\(.?)", re.DOTALL)
_UNESCAPED: Final = {"\\": "\\", "n": "\n", "r": "\r"}
_ESCAPES: Final = str.maketrans({"\\": "\\\\", "\n": "\\n", "\r": "\\r"})
# the extension's comments, names folded: a chapter's time, its title, its URL
_EXTENSION: Final = re.compile(r"chapter([0-9]{3})(name|url)?")
_TIME: Final = re.compile(r"([0-9]{2}):([0-5][0-9]):([0-5][0-9])\.([0-9]{3})")
_HOURS: Final = 100  # two digits: ffmpeg reads two (%02d)
# ffmpeg's ogm_chapter: "CHAPTER", then what sscanf("%03d") reads -- spaces, a sign, digits;
# shorter than 9, not a chapter's; 10 at most, a time; longer, a title if "NAME" ends it
_FFMPEG_NUMBER: Final = re.compile(r" *[+-]?[0-9]")
_FFMPEG_SHORTEST: Final = len("CHAPTER00")  # keylen < 9: not a chapter's
_FFMPEG_TIME: Final = len("CHAPTER000")  # keylen <= 10: a time
_PREFIX: Final = len("CHAPTER000")  # the extension's: a suffix after it


def read(text: str, source: str) -> Metadata:
    """``text``, Vorbis comments in ffman's form: its tags, and chapters from the extension's.

    ``source`` names it in messages; each refusal names its line.
    """
    tags: list[Tag] = []
    chapters: dict[int, tuple[int, int, list[Tag]]] = {}  # number: its line, its ms, its tags
    *lines, last = text.split("\n")  # last: after the final LF, empty unless one is missing
    for number, line in enumerate(lines, 1):
        name, value = _comment(line, number, source)
        extension = _EXTENSION.fullmatch(folded(name))
        if extension is None:
            if _ffmpeg_takes_for_a_chapter(name):
                refuse_at(
                    source,
                    number,
                    "not the Chapter Extension's form (CHAPTERxxx, three digits), "
                    + f"yet ffmpeg reads it as a chapter's: {shown(name)}",
                )
            tags.append(Tag(name, value))
            continue
        index, suffix = int(extension[1]), extension[2]
        if suffix is None:
            if index in chapters:
                refuse_at(source, number, f"{name} again (line {chapters[index][0]})")
            chapters[index] = (number, _milliseconds(value, number, source), [])
            continue
        if index not in chapters:
            refuse_at(
                source,
                number,
                f"{name} before its time: a chapter's comments follow CHAPTER{index:03d}",
            )
        held = chapters[index][2]
        if any(folded(tag.name) == suffix for tag in held):
            refuse_at(source, number, f"{name} again: a chapter has one NAME and one URL")
        held.append(Tag(name[_PREFIX:], value))
    if last:  # its characters first: a CR or a NUL says more than the break missing
        _unbroken(last, len(lines) + 1, source)
        refuse_at(
            source, len(lines) + 1, "no line break ends the last line: every line ends with LF"
        )
    ordered = sorted(chapters.items())
    return Metadata(
        tuple(tags),
        chapters=tuple(
            Chapter(exact(ms, MILLISECONDS), None, tuple(held)) for _, (_, ms, held) in ordered
        ),
    )


def _comment(line: str, number: int, source: str) -> tuple[str, str]:
    """A line's name and value, unescaped: refused unless it is ffman's form."""
    _unbroken(line, number, source)
    name, equals, value = line.partition("=")
    if not equals:
        refuse_at(source, number, f"no '=': not a comment: {shown(line)}")
    if _NAME.fullmatch(name) is None:
        why = (
            "an empty name"
            if not name
            else f"a name of ASCII 0x20-0x7D but '=' and '~': {shown(name)}"
        )
        refuse_at(source, number, why)
    for escape in _ESCAPE.finditer(value):
        if not escape[1]:
            refuse_at(source, number, "a '\\' ending the line: it escapes nothing")
        if escape[1] not in _UNESCAPED:
            refuse_at(source, number, f"an escape but \\\\, \\n, \\r: {shown(escape[0])}")
    return name, _ESCAPE.sub(lambda escape: _UNESCAPED[escape[1]], value)


def _unbroken(line: str, number: int, source: str) -> None:
    """A line holds no NUL and no CR: ffman's form writes a CR in a value as an escape."""
    for char, why in (
        ("\0", "a NUL"),
        ("\r", "a carriage return: lines end with LF alone, a CR is \\r"),
    ):
        if char in line:
            refuse_at(source, number, why)


def _ffmpeg_takes_for_a_chapter(name: str) -> bool:
    """Whether ffmpeg's ``ogm_chapter`` reads ``name`` as a chapter's time or title."""
    key = folded(name)
    if len(name) < _FFMPEG_SHORTEST or not key.startswith("chapter"):
        return False
    if _FFMPEG_NUMBER.match(name, len("CHAPTER")) is None:
        return False
    return len(name) <= _FFMPEG_TIME or key.endswith("name")


def _a_chapters(name: str) -> bool:
    """Whether ``name`` is a chapter's comment: the extension's, or ffmpeg's reading of one."""
    return _EXTENSION.fullmatch(folded(name)) is not None or _ffmpeg_takes_for_a_chapter(name)


def _milliseconds(value: str, number: int, source: str) -> int:
    """A chapter's time, ``HH:MM:SS.mmm``, in milliseconds."""
    time = _TIME.fullmatch(value)
    if time is None:
        refuse_at(source, number, f"a chapter's time is HH:MM:SS.mmm: {shown(value)}")
    hours, minutes, seconds, ms = (int(part) for part in time.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * MILLISECONDS + ms


def write(meta: Metadata) -> Written:
    """``meta`` in ffman's form of Vorbis comments, and a note for each thing left out."""
    pairs, notes = comments(meta)
    return Written(text(pairs), notes)


def comments(meta: Metadata) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """``meta`` as Vorbis comments, each ``(name, value)`` raw, and a note for each left out.

    The form's escapes are ``write``'s, not a comment's: ffmpeg's -metadata takes values raw.
    """
    notes: list[str] = []
    pairs: list[tuple[str, str]] = []
    for tag in meta.tags:
        why = _unwritable(tag)
        if why is None and _a_chapters(tag.name):
            why = "a chapter's comment by its name, not a tag"
        if why is not None:
            notes.append(left_out(f"a tag '{tag.name}'", why))
            continue
        pairs.append((tag.name, tag.value))
    pairs += _chapter_pairs(meta.chapters, notes)
    if meta.streams:
        notes.append(left_out("streams' tags", "Vorbis comments are one list, a stream's own"))
    if meta.disc is not None:
        notes.append(
            left_out(
                "a cue sheet's disc",
                "Vorbis comments hold none (a conversion makes its tracks chapters)",
            )
        )
    return tuple(pairs), tuple(notes)


def text(pairs: Iterable[tuple[str, str]]) -> str:
    """Comments in ffman's form: a line each, a value's backslash and breaks escaped."""
    return "".join(_line(name, value) + "\n" for name, value in pairs)


def _line(name: str, value: str) -> str:
    return f"{name}={value.translate(_ESCAPES)}"


def _unwritable(tag: Tag) -> str | None:
    """Why ffman's form cannot hold ``tag``, if it cannot."""
    if _NAME.fullmatch(tag.name) is None:
        return "not a Vorbis name (ASCII 0x20-0x7D but '=' and '~')"
    if "\0" in tag.value:
        return "a NUL: the form holds none"
    return None


def _chapter_pairs(chapters: tuple[Chapter, ...], notes: list[str]) -> list[tuple[str, str]]:
    """The extension's comments for each chapter, numbered as written; the rest noted."""
    pairs: list[tuple[str, str]] = []
    nexts = [chapter.start for chapter in chapters[1:]] + ([None] if chapters else [])
    if any(c.end is not None and c.end != after for c, after in zip(chapters, nexts, strict=True)):
        # an end at the next start is no loss: a reader ends a chapter there
        notes.append(
            left_out(
                "chapter ends", "Vorbis comments hold none (a chapter ends where the next begins)"
            )
        )
    written = 0
    for position, chapter in enumerate(chapters, 1):
        ms = nearest(chapter.start, MILLISECONDS)
        if ms >= _HOURS * 3_600_000:
            notes.append(left_out(f"chapter {position}", "it starts past 99:59:59.999"))
            continue
        if written == CHAPTERS:
            notes.append(left_out(f"chapter {position}", f"past {CHAPTERS} chapters"))
            continue
        if exact(ms, MILLISECONDS) != chapter.start:
            notes.append(f"chapter {position} starts between milliseconds: at the nearest, {ms} ms")
        prefix = f"CHAPTER{written:03d}"
        pairs.append((prefix, _clock(ms)))
        pairs += _chapter_tags(chapter.tags, prefix, position, notes)
        written += 1
    return pairs


def _chapter_tags(
    tags: Tags, prefix: str, position: int, notes: list[str]
) -> list[tuple[str, str]]:
    """A chapter's ``NAME`` and ``URL``, once each; its other tags noted, left out."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tag in tags:
        kind = folded(tag.name)
        why = _unwritable(tag)
        if why is None and kind not in {"name", "url"}:
            why = "the extension holds a chapter's NAME and URL alone"
        elif why is None and kind in seen:
            why = "again: a chapter has one NAME and one URL"
        if why is not None:
            notes.append(left_out(f"chapter {position}'s tag '{tag.name}'", why))
            continue
        seen.add(kind)
        pairs.append((prefix + tag.name, tag.value))
    return pairs


def _clock(ms: int) -> str:
    """Milliseconds as ``HH:MM:SS.mmm``, by division (the vorbiscomment skill's rule)."""
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"
