"""Cue sheets: read into the model's disc, written from it.

The format is the cue skill's: CDRWIN's commands as GNU's ccd2cue manual gives them, read as
the readers in use agree -- commands without case, a UTF-8 BOM skipped, CR LF or LF; a quoted
string to the next quote (there is no escape), an unquoted one to the end of its line; the
disc's lines before its first TRACK; every INDEX in the FILE it follows, EAC's track over two
files too. Anything else is refused, naming the line: an unknown command (mpv refuses the
sheet), one out of its place or repeated, a malformed value, a track without INDEX 01, a FILE
no INDEX uses, a time going back within its file. libcue's own CD-Text commands are read;
the writer, which writes what every reader in use accepts, notes and leaves them out.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from ffmeta._errors import refuse_at, shown
from ffmeta.model import (
    FRAMES,
    TRACKS,
    Disc,
    File,
    Index,
    Metadata,
    Tag,
    Tags,
    Track,
    Written,
    left_out,
)

__all__ = [
    "FLAGS",
    "LAST_FRAME",
    "LAST_TIME",
    "are_flags",
    "is_catalog",
    "is_file_name",
    "is_isrc",
    "read",
    "write",
]

_CDTEXT: Final = ("TITLE", "PERFORMER", "SONGWRITER")  # CDRWIN's: the disc's or a track's
# libcue's besides (cue_scanner.l): mpv refuses a sheet with one, so they are read, not written
_LIBCUE_CDTEXT: Final = (
    "COMPOSER", "ARRANGER", "MESSAGE", "DISC_ID", "GENRE", "TOC_INFO1", "TOC_INFO2", "UPC_EAN",
    "SIZE_INFO",
)  # fmt: skip
FLAGS: Final = ("DCP", "4CH", "PRE", "SCMS")
_CDTEXT_CHARACTERS: Final = 80  # CD-Text's: the readers in use keep more
_BOM: Final = "\ufeff"
_LINE: Final = re.compile(r"[ \t]*(\S+)[ \t]*(.*?)[ \t]*")  # a command and the rest of its line
_TIME: Final = re.compile(r"([0-9]{1,6}):([0-9]{2}):([0-9]{2})")
_MINUTES: Final = 999_999  # what _TIME reads, so what the writer writes
_SECONDS: Final = 60
_NUMBER: Final = re.compile(r"[0-9]{1,2}")
_CATALOG: Final = re.compile(r"[0-9]{13}")  # UPC/EAN
_ISRC: Final = re.compile(r"[A-Z0-9]{5}[0-9]{7}")  # CCOOOYYSSSSS
_BREAKS: Final = ("\n", "\r", "\0")  # what no cue line holds
_UNQUOTABLE: Final = ('"', *_BREAKS)  # what no cue string holds


LAST_FRAME: Final = (_MINUTES + 1) * _SECONDS * FRAMES - 1  # 999999:59:74, MM:SS:FF's last
LAST_TIME: Final = f"{_MINUTES}:{_SECONDS - 1}:{FRAMES - 1}"


def is_catalog(text: str) -> bool:
    """A ``CATALOG``'s form: 13 digits, a UPC/EAN."""
    return _CATALOG.fullmatch(text) is not None


def is_isrc(text: str) -> bool:
    """An ``ISRC``'s form: CCOOOYYSSSSS, 12 characters."""
    return _ISRC.fullmatch(text) is not None


def is_file_name(name: str) -> bool:
    """A name a cue's ``FILE`` holds: no line break or NUL, no space at either end, no quote first.

    A quote within it is written unquoted, noted.
    """
    return (
        bool(name)
        and not any(char in name for char in _BREAKS)
        and name == name.strip()
        and name[:1] != '"'
    )


def are_flags(flags: tuple[str, ...]) -> bool:
    """Flags a track holds: each ``DCP``, ``4CH``, ``PRE`` or ``SCMS``, once (none: none)."""
    return all(flag in FLAGS for flag in flags) and len(set(flags)) == len(flags)


@dataclass
class _Track:
    """A track as its lines are read: where its TRACK was, and what has come since."""

    line: int
    number: int
    mode: str
    indexes: list[Index] = field(default_factory=list[Index])
    cdtext: list[Tag] = field(default_factory=list[Tag])
    rems: list[str] = field(default_factory=list[str])
    flags: tuple[str, ...] = ()
    isrc: str | None = None
    pregap: int | None = None
    postgap: int | None = None

    def frozen(self) -> Track:
        return Track(
            self.number,
            self.mode,
            tuple(self.indexes),
            tuple(self.cdtext),
            tuple(self.rems),
            self.flags,
            self.isrc,
            self.pregap,
            self.postgap,
        )


@dataclass
class _Sheet:
    """A cue sheet as its lines are read."""

    source: str
    files: list[File] = field(default_factory=list[File])
    file_line: int = 0  # the line of the last FILE, until an INDEX follows it
    tracks: list[_Track] = field(default_factory=list[_Track])
    cdtext: list[Tag] = field(default_factory=list[Tag])
    rems: list[str] = field(default_factory=list[str])
    catalog: str | None = None
    cdtextfile: str | None = None
    last: Index | None = None  # the last INDEX read, in the disc's order

    def disc(self) -> Disc:
        return Disc(
            tuple(self.files),
            tuple(track.frozen() for track in self.tracks),
            tuple(self.cdtext),
            tuple(self.rems),
            self.catalog,
            self.cdtextfile,
        )


def read(text: str, source: str) -> Metadata:
    """``text``, a cue sheet named ``source`` in messages: its disc; refusals name the line."""
    sheet = _Sheet(source)
    lines = text.removeprefix(_BOM).split("\n")
    if lines[-1] == "":
        del lines[-1]  # the last line's break
    for number, raw in enumerate(lines, 1):
        line = raw.removesuffix("\r")
        for char, why in (
            ("\r", "a carriage return alone: lines end with LF or CR LF"),
            ("\0", "a NUL"),
        ):
            if char in line:
                refuse_at(source, number, why)
        if not line.strip(" \t"):
            continue  # a blank line
        command = _LINE.fullmatch(line)
        if command is None:  # led by whitespace but space and tab: a no-break space, a form feed
            refuse_at(source, number, f"not a cue line: {shown(line)}")
        name = command[1].upper()
        handler = _HANDLERS.get(name)
        if handler is None:
            refuse_at(source, number, f"not a cue command: {shown(command[1])}")
        handler(sheet, name, command[2], number)
    if not sheet.tracks:
        refuse_at(source, max(len(lines), 1), "no TRACK: a cue sheet lays out tracks")
    _close(sheet)
    _unused_file(sheet)  # a FILE ending the sheet
    return Metadata(disc=sheet.disc())


def _rem(sheet: _Sheet, _command: str, rest: str, _number: int) -> None:
    """A REM line's rest: the disc's before its first TRACK, else the track's."""
    (sheet.tracks[-1].rems if sheet.tracks else sheet.rems).append(rest)


def _cdtext_line(sheet: _Sheet, command: str, rest: str, number: int) -> None:
    """``TITLE``, ``PERFORMER``, ``SONGWRITER`` (and libcue's): the disc's or a track's, once."""
    where = sheet.source, number
    track = sheet.tracks[-1] if sheet.tracks else None
    if track and track.indexes:
        refuse_at(*where, f"{command} after an INDEX: a track's comes before")
    held = track.cdtext if track else sheet.cdtext
    if any(tag.name == command for tag in held):
        refuse_at(*where, f"{command} again: once the disc's, once each track's")
    held.append(Tag(command, _string(rest, command, where)))


def _disc_line(sheet: _Sheet, command: str, rest: str, number: int) -> None:
    """``CATALOG`` (13 digits) or ``CDTEXTFILE``: the disc's, once, before its first TRACK."""
    where = sheet.source, number
    if sheet.tracks:
        refuse_at(*where, f"{command} after a TRACK: it is the disc's")
    if (sheet.catalog if command == "CATALOG" else sheet.cdtextfile) is not None:
        refuse_at(*where, f"{command} again")
    if command == "CDTEXTFILE":
        sheet.cdtextfile = _string(rest, command, where)
    elif not is_catalog(rest):
        refuse_at(*where, f"CATALOG is 13 digits: {shown(rest)}")
    else:
        sheet.catalog = rest


def _file_line(sheet: _Sheet, _command: str, rest: str, number: int) -> None:
    """``FILE "name" TYPE`` (or a name unquoted, the last word its type): the INDEX lines' file."""
    where = sheet.source, number
    _unused_file(sheet)
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end < 0:
            refuse_at(*where, f"FILE's quote not closed: {shown(rest)}")
        name, kind = rest[1:end], rest[end + 1 :].strip()
    else:
        match rest.rsplit(None, 1):  # the last word, after spaces or tabs: the type
            case [name, kind]:
                pass
            case _:
                name = kind = ""
    if not name or not kind or len(kind.split()) != 1:
        refuse_at(*where, f"FILE is a name and a type: {shown(rest)}")
    sheet.files.append(File(name, kind.upper()))
    sheet.file_line = number


def _unused_file(sheet: _Sheet) -> None:
    """A FILE is for INDEX lines: one that none follows is refused."""
    if sheet.file_line:
        refuse_at(sheet.source, sheet.file_line, "a FILE no INDEX follows")


def _track(sheet: _Sheet, _command: str, rest: str, number: int) -> None:
    """``TRACK nn MODE``: after a FILE, one more than the track before, that one closed."""
    where = sheet.source, number
    match rest.split():
        case [digits, mode] if _NUMBER.fullmatch(digits) and int(digits) in TRACKS:
            numbered = int(digits)
        case _:
            refuse_at(*where, f"TRACK is a number 01-99 and a mode: {shown(rest)}")
    if not sheet.files:
        refuse_at(*where, "TRACK before any FILE")
    if sheet.tracks:
        previous = sheet.tracks[-1]
        _close(sheet)
        if numbered != previous.number + 1:
            refuse_at(*where, f"TRACK {digits} after TRACK {previous.number:02d}: one more each")
    sheet.tracks.append(_Track(number, numbered, mode.upper()))


def _close(sheet: _Sheet) -> None:
    """The last track read ends: it has its INDEX 01 (a FILE may wait, for the next track's)."""
    track = sheet.tracks[-1]
    if not any(index.number == 1 for index in track.indexes):
        refuse_at(sheet.source, track.line, f"TRACK {track.number:02d} without INDEX 01")


def _before_index(sheet: _Sheet, command: str, rest: str, number: int) -> None:
    """``FLAGS``, ``ISRC`` or ``PREGAP``: a track's, once each, before its INDEX."""
    where = sheet.source, number
    if not sheet.tracks or sheet.tracks[-1].indexes:
        refuse_at(*where, f"{command} outside a TRACK's lines before its INDEX")
    track = sheet.tracks[-1]
    if command == "FLAGS":
        flags = tuple(flag.upper() for flag in rest.split())
        if track.flags:
            refuse_at(*where, "FLAGS again")
        if not flags or not are_flags(flags):
            refuse_at(*where, f"FLAGS are {', '.join(FLAGS)}, each once: {shown(rest)}")
        track.flags = flags
    elif command == "ISRC":
        if track.isrc is not None:
            refuse_at(*where, "ISRC again")
        if not is_isrc(rest):
            refuse_at(*where, f"ISRC is 12 characters, CCOOOYYSSSSS: {shown(rest)}")
        track.isrc = rest
    else:
        if track.pregap is not None:
            refuse_at(*where, "PREGAP again")
        track.pregap = _frames(rest, where)


def _index(sheet: _Sheet, _command: str, rest: str, number: int) -> None:
    """``INDEX nn mm:ss:ff``: a track's, counting up from 00 or 01, in its FILE, never back."""
    where = sheet.source, number
    if not sheet.tracks:
        refuse_at(*where, "INDEX before any TRACK")
    track = sheet.tracks[-1]
    match rest.split():
        case [digits, time] if _NUMBER.fullmatch(digits):
            numbered, frames = int(digits), _frames(time, where)
        case _:
            refuse_at(*where, f"INDEX is a number 00-99 and a time: {shown(rest)}")
    expected = {track.indexes[-1].number + 1} if track.indexes else {0, 1}
    if numbered not in expected:
        refuse_at(
            *where, f"INDEX {digits} here: {' or '.join(f'{n:02d}' for n in sorted(expected))}"
        )
    if track.postgap is not None:
        refuse_at(*where, "INDEX after POSTGAP")
    index = Index(numbered, frames, len(sheet.files) - 1)
    if numbered > 1 and index.file != track.indexes[-1].file:
        refuse_at(
            *where, f"INDEX {digits} in a FILE after its INDEX 01's: libcue reads it in that one"
        )
    if sheet.last is not None and sheet.last.file == index.file and frames < sheet.last.frames:
        refuse_at(*where, f"INDEX {digits} goes back in its FILE: {time}")
    track.indexes.append(index)
    sheet.last, sheet.file_line = index, 0


def _postgap(sheet: _Sheet, _command: str, rest: str, number: int) -> None:
    """``POSTGAP``: a track's, once, after its INDEX."""
    where = sheet.source, number
    if not sheet.tracks or not sheet.tracks[-1].indexes:
        refuse_at(*where, "POSTGAP before its TRACK's INDEX")
    track = sheet.tracks[-1]
    if track.postgap is not None:
        refuse_at(*where, "POSTGAP again")
    track.postgap = _frames(rest, where)


_HANDLERS: Final[dict[str, Callable[[_Sheet, str, str, int], None]]] = {
    "REM": _rem,
    "CATALOG": _disc_line,
    "CDTEXTFILE": _disc_line,
    "FILE": _file_line,
    "TRACK": _track,
    "FLAGS": _before_index,
    "ISRC": _before_index,
    "PREGAP": _before_index,
    "INDEX": _index,
    "POSTGAP": _postgap,
} | dict.fromkeys(_CDTEXT + _LIBCUE_CDTEXT, _cdtext_line)


def _string(rest: str, command: str, where: tuple[str, int]) -> str:
    """A string: quoted, to the next quote; else the rest of the line."""
    if not rest.startswith('"'):
        if not rest:
            refuse_at(*where, f"{command} without its value")
        return rest
    end = rest.find('"', 1)
    if end < 0:
        refuse_at(*where, f"{command}'s quote not closed: {shown(rest)}")
    if rest[end + 1 :].strip():
        refuse_at(*where, f"{command}: text after its quoted value: {shown(rest)}")
    return rest[1:end]


def _frames(time: str, where: tuple[str, int]) -> int:
    """``mm:ss:ff`` in frames: seconds under 60, frames under 75."""
    match = _TIME.fullmatch(time)
    if match is None:
        refuse_at(*where, f"a time is mm:ss:ff: {shown(time)}")
    minutes, seconds, frames = (int(part) for part in match.groups())
    if seconds >= _SECONDS or frames >= FRAMES:
        refuse_at(*where, f"a time's seconds run to 59, its frames to 74: {time}")
    return (minutes * _SECONDS + seconds) * FRAMES + frames


def write(meta: Metadata) -> Written:
    """``meta``'s disc as a cue sheet the readers in use accept, and a note for what is not."""
    notes: list[str] = []
    for held, what in (
        (meta.tags, "the global tags"),
        (meta.streams, "streams' tags"),
        (meta.chapters, "chapters"),
    ):
        if held:
            notes.append(
                left_out(what, "a cue sheet holds its disc alone (a conversion makes its lines)")
            )
    disc = meta.disc
    if disc is None or not disc.tracks:
        notes.append("no disc with tracks: no cue sheet")
        return Written("", tuple(notes))
    lines = [_rem_line(rem, "") for rem in _rems(disc.rems, "the disc's REM", notes)]
    if disc.catalog is not None:
        if is_catalog(disc.catalog):
            lines.append(f"CATALOG {disc.catalog}")
        else:
            notes.append(left_out(f"the CATALOG '{disc.catalog}'", "not 13 digits"))
    if disc.cdtextfile is not None and (name := _quoted(disc.cdtextfile, "the CDTEXTFILE", notes)):
        lines.append(f"CDTEXTFILE {name}")
    lines += _cdtext(disc.cdtext, "the disc's", "", notes)
    file = -1
    for track in disc.tracks:
        indexes = _written_indexes(track, notes)
        if indexes[0].file != file:
            lines.append(_file_command(disc.files[indexes[0].file], notes))
        lines += _track_lines(track, indexes, notes)
        file = indexes[-1].file
    return Written("".join(line + "\n" for line in lines), tuple(notes))


def _written_indexes(track: Track, notes: list[str]) -> tuple[Index, ...]:
    """A track's indexes, but an INDEX 00 in the file before its INDEX 01's: EAC's layout."""
    zero, one = track.index(0), track.index(1)
    if zero is None or one is None or zero.file == one.file:
        return track.indexes
    why = "in the file before its INDEX 01's: Kodi and foobar2000 refuse that, libcue "
    notes.append(
        left_out(f"track {track.number:02d}'s INDEX 00", why + "misplaces the tracks after")
    )
    return track.indexes[1:]


def _track_lines(track: Track, indexes: tuple[Index, ...], notes: list[str]) -> list[str]:
    """A track's lines, as EAC lays them out."""
    what = f"track {track.number:02d}'s"
    lines = [f"  TRACK {track.number:02d} {track.mode.upper()}"]
    if track.flags:
        flags = [flag.upper() for flag in track.flags]
        if are_flags(tuple(flags)):
            lines.append(f"    FLAGS {' '.join(flags)}")
        else:
            notes.append(
                left_out(f"{what} FLAGS '{' '.join(track.flags)}'", f"flags are {', '.join(FLAGS)}")
            )
    if track.isrc is not None:
        if is_isrc(track.isrc):
            lines.append(f"    ISRC {track.isrc}")
        else:
            notes.append(left_out(f"{what} ISRC '{track.isrc}'", "not CCOOOYYSSSSS"))
    lines += _cdtext(track.cdtext, what, "    ", notes)
    lines += [_rem_line(rem, "    ") for rem in _rems(track.rems, f"{what} REM", notes)]
    if track.pregap is not None:
        lines.append(f"    PREGAP {_clock(track.pregap)}")
    lines += [f"    INDEX {index.number:02d} {_clock(index.frames)}" for index in indexes]
    if track.postgap is not None:
        lines.append(f"    POSTGAP {_clock(track.postgap)}")
    return lines


def _file_command(file: File, notes: list[str]) -> str:
    r"""``FILE "name" TYPE``; unquoted if a quote cannot hold the name safely, noted.

    A quote in it, or a '\' ending it (libcue's escape: quoted, libcue fails the whole sheet).
    Unquoted, mpv reads no name, nor libcue one with a space (measured: the cue skill).
    """
    name, kind = file.name, file.kind.upper()
    if not is_file_name(name):
        msg = f"a FILE name no cue sheet holds: {name!r}"  # the reader reads none
        raise ValueError(msg)
    if '"' not in name and not name.endswith("\\"):
        return f'FILE "{name}" {kind}'
    lost = "mpv and libcue read no name" if any(c.isspace() for c in name) else "mpv reads no name"
    notes.append(f"the FILE '{name}': unquoted, for a quote or a final '\\' in it: {lost}")
    return f"FILE {name} {kind}"


def _cdtext(tags: Tags, what: str, indent: str, notes: list[str]) -> list[str]:
    """The CD-Text lines: CDRWIN's, once each; libcue's and the rest, noted, left out."""
    lines: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        command, name = tag.name.upper(), f"{what} {tag.name}"
        if command not in _CDTEXT:
            why = (
                "libcue's alone: mpv refuses a sheet with it"
                if command in _LIBCUE_CDTEXT
                else "no cue command"
            )
            notes.append(left_out(name, why))
        elif command in seen:
            notes.append(left_out(name, "again: once each"))
        elif value := _quoted(tag.value, name, notes):
            seen.add(command)
            lines.append(f"{indent}{command} {value}")
    return lines


def _quoted(value: str, what: str, notes: list[str]) -> str | None:
    """``value`` in quotes; None, noted, if it holds what no cue string can."""
    if any(char in value for char in _UNQUOTABLE):
        notes.append(left_out(what, "a quote, a line break or a NUL, which no cue string holds"))
        return None
    if value.endswith("\\"):
        notes.append(left_out(what, "it ends in '\\': libcue reads the rest of the sheet into it"))
        return None
    if len(value) > _CDTEXT_CHARACTERS:
        notes.append(f"{what}: over {_CDTEXT_CHARACTERS} characters, CD-Text's most: kept")
    return f'"{value}"'


def _rems(rems: tuple[str, ...], what: str, notes: list[str]) -> list[str]:
    """REM texts, a line each: a line break or a NUL in one, noted, left out; its ends trimmed.

    Readers take a line's rest without spaces at either end: trimmed, the change noted.
    """
    written: list[str] = []
    for rem in rems:
        if any(char in rem for char in _BREAKS):
            notes.append(left_out(f"{what} '{shown(rem)}'", "a line break or a NUL"))
            continue
        trimmed = rem.strip(" \t")
        if trimmed != rem:
            notes.append(
                f"{what} '{shown(rem)}': spaces at either end, which readers drop: trimmed"
            )
        written.append(trimmed)
    return written


def _rem_line(rem: str, indent: str) -> str:
    return f"{indent}REM {rem}" if rem else f"{indent}REM"


def _clock(frames: int) -> str:
    """Frames as ``mm:ss:ff``, minutes as many digits as they need, to 999999."""
    minutes, rest = divmod(frames, _SECONDS * FRAMES)
    if frames > LAST_FRAME:
        msg = f"a cue time past {_MINUTES} minutes: {frames} frames"
        raise ValueError(msg)
    seconds, frame = divmod(rest, FRAMES)
    return f"{minutes:02d}:{seconds:02d}:{frame:02d}"
