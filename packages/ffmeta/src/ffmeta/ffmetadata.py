r"""ffmetadata, ffmpeg's text form of tags, streams' tags and chapters: read and written.

The format is the ffmetadata skill's: FFmpeg n8.1.2's ``ffmetadec.c`` and ``ffmetaenc.c``,
read and measured. ffman reads what ffmpeg reads, and refuses, naming the line, what ffmpeg
reads otherwise than it is written -- a line without ``=`` (dropped), ``[chapter]`` (its
lines become global tags), a key repeated (the last kept), a line ending in an escaped ``\``
or a comment ending in ``\`` (the next line read into it), a carriage return alone (it ends
a tag's line but not a chapter's), a NUL (the line ends there), a chapter's times missing or
out of their order. A chapter's time lines have one form here, whole numbers (``TIMEBASE=N/D``,
``START=N``, ``END=N``), where ffmpeg's ``sscanf`` also takes a sign and spaces, and garbage
after the number (``START=12abc`` read as 12). The writer escapes what ffmpeg's forgets (a
carriage return), gives each chapter exact times, and notes what the format cannot hold.
"""

import bisect
import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from ffmeta._errors import refuse_at, shown
from ffmeta._values import round_half_up
from ffmeta.model import MILLISECONDS, Chapter, Metadata, Tag, Tags, Written, folded, left_out

__all__ = ["CHAPTER", "HEADER", "STREAM", "read", "write"]

HEADER: Final = ";FFMETADATA"  # ffmpeg knows the format by this prefix (ffmeta.h's ID_STRING)
_VERSION: Final = "1"  # the one version; ffmpeg reads the header as a comment and checks none
STREAM: Final = "[STREAM]"
CHAPTER: Final = "[CHAPTER]"
_NANOSECONDS: Final = 10**9  # a chapter's time base without a TIMEBASE line (ffmetadec.c)
_INT32: Final = 2**31 - 1  # a TIMEBASE term: sscanf's %d
_INT64: Final = 2**63 - 1  # START and END: SCNd64
_DIGITS: Final = len(str(_INT64))  # more, and a number is past it: 19
_ESCAPES: Final = str.maketrans({c: "\\" + c for c in "\\=;#\n\r"})  # the CR: ffmpeg's forgot
# an escape (a '\' and the character it makes literal, a line break too), a line's end, a
# run of plain text, or a '\' ending the text
_TOKENS: Final = re.compile(r"\\.|\r\n|\r|\n|[^\\\r\n]+|\\", re.DOTALL)
_ESCAPED: Final = re.compile(r"\\(.)", re.DOTALL)  # a '\' and the character it makes literal
_TO_EQUALS: Final = re.compile(r"(?:\\.|[^\\=])*=", re.DOTALL)  # up to the first unescaped '='
_TIMEBASE: Final = re.compile(r"TIMEBASE=([0-9]+)/([0-9]+)")
_START: Final = re.compile(r"START=([0-9]+)")
_END: Final = re.compile(r"END=([0-9]+)")


@dataclass(frozen=True, slots=True)
class _Line:
    """A line as ffmpeg's reader joins it: its first line's number, its text, escapes kept."""

    number: int
    raw: str
    ended: bool = True  # a line break ended it: all but, perhaps, the file's last


def read(text: str, source: str) -> Metadata:
    """``text``, an ffmetadata file named ``source`` in messages, as ffmpeg reads it.

    Refuses, naming the line, what ffmpeg would read otherwise than it is written.
    """
    if not text.startswith(HEADER):  # ffmpeg's probe: the file's first bytes
        first = text.split("\n", 1)[0]
        found = shown(first) if text else "an empty file"
        refuse_at(source, 1, f"not ffmetadata: the first line must begin {HEADER}: {found}")
    lines = _lines(text, source)
    for line in lines:
        if _comment(line) and "\n" in line.raw:
            refuse_at(
                source, line.number, "a comment ending in '\\': ffmpeg reads the next line into it"
            )
    last = lines[-1]
    if _comment(last) and not last.ended and _first_equals(last.raw) is not None:
        # ffmpeg skips a comment unless the file ends with it: then, read as a tag
        refuse_at(
            source, last.number, "a comment with '=' ending the file: ffmpeg reads it as a tag"
        )
    body = [line for line in lines[1:] if line.raw and not _comment(line)]
    return _sections(iter(body), source)


def _comment(line: _Line) -> bool:
    return line.raw[:1] in {";", "#"}


def _lines(text: str, source: str) -> list[_Line]:
    """``text``'s lines, each escaped line break kept in the line it joins (ffmetadec.c)."""
    if (nul := text.find("\0")) >= 0:
        refuse_at(source, text.count("\n", 0, nul) + 1, "a NUL: ffmpeg ends the line there")
    lines: list[_Line] = []
    pieces: list[str] = []
    number = start = 1  # the line read, and the line its text began on
    for token in _TOKENS.finditer(text):
        piece = token.group()
        if piece == "\\":
            refuse_at(source, number, "a '\\' ending the file: it escapes nothing")
        if piece == "\r":
            refuse_at(source, number, "a carriage return alone: end lines with LF or CR LF")
        if piece in {"\n", "\r\n"}:
            # ffmpeg's reader looks one byte back: a line break after an escaped '\' is
            # escaped to it, and the next line joins this one
            if pieces[-1:] == ["\\\\"]:
                refuse_at(
                    source, start, "a line ending in '\\': ffmpeg reads the next line into it"
                )
            lines.append(_Line(start, "".join(pieces)))
            pieces.clear()
            start = number + 1
        else:
            pieces.append(piece)
        number += piece.endswith("\n")  # a line break, escaped or not
    if pieces:
        lines.append(_Line(start, "".join(pieces), ended=False))
    return lines


def _sections(body: Iterator[_Line], source: str) -> Metadata:
    """The global tags, then each section's: ``[STREAM]``'s, ``[CHAPTER]``'s after its times."""
    tags: list[Tag] = []
    streams: list[list[Tag]] = []
    chapters: list[tuple[Fraction, Fraction, list[Tag]]] = []
    section: list[Tag] = tags
    seen: dict[str, int] = {}  # the section's keys, folded, and the lines they came on
    for line in body:
        if line.raw == STREAM:
            streams.append([])
            section, seen = streams[-1], {}
        elif line.raw == CHAPTER:
            start, end = _times(line, body, source)
            chapters.append((start, end, []))
            section, seen = chapters[-1][2], {}
        else:
            tag = _tag(line, source)
            key = folded(tag.name)
            if key in seen:
                refuse_at(
                    source,
                    line.number,
                    f"the key '{tag.name}' again (line {seen[key]}): ffmpeg keeps only the last",
                )
            seen[key] = line.number
            section.append(tag)
    return Metadata(
        tuple(tags),
        tuple(tuple(stream) for stream in streams),
        tuple(Chapter(start, end, tuple(chapter)) for start, end, chapter in chapters),
    )


def _times(header: _Line, body: Iterator[_Line], source: str) -> tuple[Fraction, Fraction]:
    """A chapter's start and end: ``TIMEBASE=N/D`` if given, then ``START=``, then ``END=``."""
    line = next(body, None)
    num, den = 1, _NANOSECONDS
    if line is not None and line.raw.startswith("TIMEBASE="):
        num, den = _whole(_TIMEBASE, line, source, "TIMEBASE=N/D, two whole numbers")
        if not (0 < num <= _INT32 and 0 < den <= _INT32):
            refuse_at(source, line.number, f"TIMEBASE's terms run 1 to {_INT32}: {shown(line.raw)}")
        line = next(body, None)
    start, _ = _bound(line, header, _START, "START", source)
    end, end_line = _bound(next(body, None), header, _END, "END", source)
    if end < start:
        refuse_at(
            source, end_line.number, f"a chapter ending before it starts: END={end} < START={start}"
        )
    return Fraction(start * num, den), Fraction(end * num, den)


def _bound(
    line: _Line | None, header: _Line, pattern: re.Pattern[str], name: str, source: str
) -> tuple[int, _Line]:
    """A chapter's ``START`` or ``END`` and its line: the line expected next, a whole number."""
    if line is None or not line.raw.startswith(f"{name}="):
        at = header.number if line is None else line.number
        refuse_at(source, at, f"[CHAPTER] (line {header.number}) needs {name}= here")
    (value,) = _whole(pattern, line, source, f"{name}= and a whole number")
    if value > _INT64:
        refuse_at(source, line.number, f"{name} past {_INT64}: {value}")
    return value, line


def _whole(pattern: re.Pattern[str], line: _Line, source: str, form: str) -> tuple[int, ...]:
    """The whole numbers ``pattern`` finds in ``line``, which it must match entirely."""
    match = pattern.fullmatch(line.raw)
    if match is None:
        refuse_at(source, line.number, f"not {form}: {shown(line.raw)}")
    # past _DIGITS significant digits a number is past any bound here; and int() refuses
    # 4300 digits (sys.int_info): so before it
    if any(len(group.lstrip("0")) > _DIGITS for group in match.groups()):
        refuse_at(source, line.number, f"a number past {_INT64}: {shown(line.raw)}")
    return tuple(int(group) for group in match.groups())


def _tag(line: _Line, source: str) -> Tag:
    """A tag line: split at its first unescaped ``=``, each side unescaped."""
    at = _first_equals(line.raw)
    if at is None:
        if line.raw.startswith("[") and line.raw.endswith("]"):
            refuse_at(
                source,
                line.number,
                f"not a section ({STREAM} or {CHAPTER}, in capitals): {shown(line.raw)}",
            )
        refuse_at(
            source, line.number, f"no '=': not a tag (ffmpeg drops the line): {shown(line.raw)}"
        )
    return Tag(_unescape(line.raw[:at]), _unescape(line.raw[at + 1 :]))


def _first_equals(raw: str) -> int | None:
    """Where ``raw``'s first unescaped ``=`` is, if it has one."""
    match = _TO_EQUALS.match(raw)
    return None if match is None else match.end() - 1


def _unescape(raw: str) -> str:
    """``raw`` without its escaping backslashes: each makes the next character literal."""
    return _ESCAPED.sub(r"\1", raw)


def write(meta: Metadata, duration: Fraction | None = None) -> Written:
    """``meta`` as an ffmpeg-readable ffmetadata file, and a note for each thing left out.

    A chapter without an end ends where the next begins, the last at ``duration`` (the media's).
    """
    notes: list[str] = []
    out = [HEADER + _VERSION, *_tag_lines(meta.tags, "a global tag", notes)]
    for number, tags in enumerate(meta.streams):
        out += [STREAM, *_tag_lines(tags, f"stream {number}'s tag", notes)]
    ends = _ends(meta.chapters, duration, notes)
    for number, (chapter, end) in enumerate(zip(meta.chapters, ends, strict=True), 1):
        times = _time_lines(chapter.start, end, number, notes)
        if times:
            out += [CHAPTER, *times, *_tag_lines(chapter.tags, f"chapter {number}'s tag", notes)]
    if meta.disc is not None:
        notes.append(
            left_out(
                "a cue sheet's disc",
                "ffmetadata holds none (a conversion makes its tracks chapters)",
            )
        )
    return Written("\n".join(out) + "\n", tuple(notes))


def _tag_lines(tags: Tags, what: str, notes: list[str]) -> list[str]:
    """Each tag ``key=value``, escaped; what ffmpeg cannot read back, left out and noted."""
    lines: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        why = None
        if "\0" in tag.name or "\0" in tag.value:
            why = "a NUL: ffmpeg ends the line there"
        elif tag.value.endswith("\\"):
            why = "it ends in '\\': ffmpeg reads the next line into it"
        elif folded(tag.name) in seen:
            why = "its key again: ffmpeg keeps only the last"
        if why is not None:
            notes.append(left_out(f"{what} '{tag.name}'", why))
            continue
        seen.add(folded(tag.name))
        lines.append(f"{tag.name.translate(_ESCAPES)}={tag.value.translate(_ESCAPES)}")
    return lines


def _ends(
    chapters: Sequence[Chapter], duration: Fraction | None, notes: list[str]
) -> list[Fraction]:
    """Each chapter's end: its own, else the next chapter's start, else ``duration``."""
    starts = sorted({chapter.start for chapter in chapters})  # to find the next by halving
    ends: list[Fraction] = []
    for number, chapter in enumerate(chapters, 1):
        after = bisect.bisect_right(starts, chapter.start)
        if chapter.end is not None:
            ends.append(chapter.end)
        elif after < len(starts):
            ends.append(starts[after])
        elif duration is not None and duration >= chapter.start:
            ends.append(duration)
        else:
            notes.append(
                f"chapter {number} has no end, nor a chapter after it, nor a duration: "
                + "it ends where it starts"
            )
            ends.append(chapter.start)
    return ends


def _time_lines(start: Fraction, end: Fraction, number: int, notes: list[str]) -> list[str]:
    """``TIMEBASE``, ``START``, ``END``: exact in 1/1000 or the least time base that is, else ns.

    None -- the chapter left out, noted -- past what ffmpeg reads (SCNd64).
    """
    den = math.lcm(start.denominator, end.denominator)
    if MILLISECONDS % den == 0:
        den = MILLISECONDS
    if den > _INT32:
        notes.append(
            f"chapter {number}'s times need a time base of 1/{den}: rounded to nanoseconds"
        )
        den = _NANOSECONDS
        first, last = round_half_up(start * den), round_half_up(end * den)
    else:
        first, last = (
            start.numerator * (den // start.denominator),
            end.numerator * (den // end.denominator),
        )
    if last > _INT64:
        notes.append(
            left_out(f"chapter {number}", f"it ends past what ffmpeg reads ({_INT64} of 1/{den} s)")
        )
        return []
    return [f"TIMEBASE=1/{den}", f"START={first}", f"END={last}"]
