"""One model for the three metadata formats: what each can hold, held exactly.

- **Tags** are kept as written -- order, repeats, a name's case -- so a format reads back as it
  was; what a name means (``DESCRIPTION`` is ffmpeg's ``comment``) is a conversion's to decide
  (the ``metadata-mappings`` skill).
- **Times** are exact seconds, as fractions: an ffmetadata ``TIMEBASE`` times its ``START``,
  Vorbis' milliseconds and a cue's frames (1/75 s) all fit without rounding.
- **A cue's disc** keeps its own shape -- files, tracks, indexes -- since a track's start needs
  its file's place in the stream, which only the media knows; its invariants are the format's
  (each number one more, an ``INDEX 01``, files in turn, time never back), so any disc built is
  one a cue sheet holds. Keywords are upper case, text as written.
"""

import string
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Final

from ffmeta._values import round_half_up

__all__ = [
    "FRAMES",
    "INDEXES",
    "MILLISECONDS",
    "TRACKS",
    "Chapter",
    "Disc",
    "File",
    "Index",
    "Metadata",
    "Tag",
    "Tags",
    "Track",
    "Written",
    "exact",
    "folded",
    "left_out",
    "nearest",
    "put",
    "set_where",
]

FRAMES: Final = 75  # a cue's frames a second (CDRWIN's mm:ss:ff; the Red Book's sectors)
MILLISECONDS: Final = 1000  # Vorbis' chapter times (the Chapter Extension's HH:MM:SS.mmm)
TRACKS: Final = range(1, 100)  # a cue's track numbers, 01-99
INDEXES: Final = range(100)  # a track's index numbers, 00-99

# Names compare without ASCII case: Vorbis' are ASCII (its specification), and ffmpeg folds
# only A-Z (libavutil's av_tolower) -- "TÍTULO" and "título" are two names to both.
_ASCII_LOWER: Final = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


@dataclass(frozen=True, slots=True)
class Tag:
    """A tag as written: its name and its value, the name's case kept."""

    name: str
    value: str


type Tags = tuple[Tag, ...]


def folded(name: str) -> str:
    """``name`` with its ASCII letters in lower case: equal for two names that are one."""
    return name.translate(_ASCII_LOWER)


def _not_negative(what: str, value: Fraction | int) -> None:
    if value < 0:
        msg = f"{what} is negative: {value}"
        raise ValueError(msg)


def _consecutive(what: str, numbers: list[int]) -> None:
    """Each number one more than the one before: CDRWIN's rule for tracks and indexes."""
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        msg = f"{what} do not count up by one: {numbers}"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Chapter:
    """A chapter: its start and end in seconds (no end: the format gave none), its tags."""

    start: Fraction
    end: Fraction | None
    tags: Tags = ()

    def __post_init__(self) -> None:
        """A chapter starts at 0 or after, and ends at its start or after."""
        _not_negative("a chapter's start", self.start)
        if self.end is not None and self.end < self.start:
            msg = f"a chapter ends before it starts: {self.end} < {self.start}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class File:
    """A cue's ``FILE``: its name, as written, and type (``WAVE``, ``MP3``, ``BINARY`` ...)."""

    name: str
    kind: str


@dataclass(frozen=True, slots=True)
class Index:
    """A cue's ``INDEX``: its number, its frames from its file's start, and which file."""

    number: int
    frames: int
    file: int  # its file's place in the disc's files: EAC writes a track over two files

    def __post_init__(self) -> None:
        """An index is numbered 00-99, at 0 frames or after (its disc checks its file)."""
        if self.number not in INDEXES:
            msg = f"an index number outside 0-99: {self.number}"
            raise ValueError(msg)
        _not_negative("an index's frames", self.frames)
        _not_negative("an index's file", self.file)


@dataclass(frozen=True, slots=True)
class Track:
    """A cue's ``TRACK`` and what its lines say: keywords upper case, text as written; frames."""

    number: int
    mode: str  # AUDIO, or a data mode (MODE1/2352 ...)
    indexes: tuple[Index, ...]
    cdtext: Tags = ()  # TITLE, PERFORMER, SONGWRITER: CD-Text's, by its command
    rems: tuple[str, ...] = ()  # each REM line's rest: a convention, not the format
    flags: tuple[str, ...] = ()  # DCP 4CH PRE SCMS
    isrc: str | None = None
    pregap: int | None = None  # silence before the track, in no file
    postgap: int | None = None  # silence after it

    def __post_init__(self) -> None:
        """A track is numbered 01-99; its indexes count up from 00 or 01, with an 01; gaps >= 0."""
        if self.number not in TRACKS:
            msg = f"a track number outside 1-99: {self.number}"
            raise ValueError(msg)
        numbers = [index.number for index in self.indexes]
        _consecutive("a track's index numbers", numbers)
        if 1 not in numbers[:2]:  # counting up from 00 or 01: so 01 first or second
            msg = f"track {self.number} has no INDEX 01 first or after its INDEX 00: {numbers}"
            raise ValueError(msg)
        if len({index.file for index in self.indexes if index.number}) > 1:
            # only INDEX 00 may be in the file before (EAC): no reader places a later one right
            msg = f"track {self.number}'s indexes from 01 on are in more than one file"
            raise ValueError(msg)
        for what, gap in (("a pregap", self.pregap), ("a postgap", self.postgap)):
            if gap is not None:
                _not_negative(what, gap)

    @property
    def start_index(self) -> Index:
        """The track's INDEX 01, its start: every track has one (its invariant)."""
        return next(index for index in self.indexes if index.number == 1)

    def index(self, number: int) -> Index | None:
        """The track's index ``number``, if it has one."""
        return next((index for index in self.indexes if index.number == number), None)


@dataclass(frozen=True, slots=True)
class Disc:
    """A cue sheet's disc: its files and tracks, and the lines that are the disc's own."""

    files: tuple[File, ...]
    tracks: tuple[Track, ...]
    cdtext: Tags = ()  # the disc's TITLE, PERFORMER, SONGWRITER
    rems: tuple[str, ...] = ()
    catalog: str | None = None
    cdtextfile: str | None = None

    def __post_init__(self) -> None:
        """Track numbers count up by one; indexes, in order, use every file in turn, never back.

        Each index is in the file of the index before it or the next one; within a file, an index is
        never earlier than the one before it.
        """
        _consecutive("the disc's track numbers", [track.number for track in self.tracks])
        indexes = [(track.number, index) for track in self.tracks for index in track.indexes]
        if indexes and indexes[0][1].file != 0:
            msg = f"the disc's first index is in file {indexes[0][1].file}, not its first"
            raise ValueError(msg)
        for (before, prior), (number, index) in pairwise(indexes):
            if index.file not in {prior.file, prior.file + 1}:
                msg = f"track {number}'s index {index.number}: file {index.file} after {prior.file}"
                raise ValueError(msg)
            if index.file == prior.file and index.frames < prior.frames:
                msg = (
                    f"track {number}'s index {index.number} goes back in its file: "
                    + f"{index.frames} < {prior.frames} (track {before}'s index {prior.number})"
                )
                raise ValueError(msg)
        used = indexes[-1][1].file + 1 if indexes else 0
        if len(self.files) != used:
            msg = f"the disc's files: {len(self.files)}; its indexes use {used}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Metadata:
    """A file's metadata: global tags, each stream's tags, chapters, and a cue's disc."""

    tags: Tags = ()
    streams: tuple[Tags, ...] = ()  # ffmetadata's [STREAM] sections, in the streams' order
    chapters: tuple[Chapter, ...] = ()  # as written: a writer orders them if its format must
    disc: Disc | None = None  # a cue sheet's; None from the others


@dataclass(frozen=True, slots=True)
class Written:
    """A writer's answer: the text, and a note for each thing its format cannot hold."""

    text: str
    notes: tuple[str, ...] = ()


def left_out(what: str, why: str) -> str:
    """A writer's note for what its format cannot hold: ``{what}: {why}: left out``."""
    return f"{what}: {why}: left out"


def exact(count: int, per_second: int) -> Fraction:
    """``count`` units of ``1/per_second`` seconds, in seconds: ``exact(19327, FRAMES)``."""
    return Fraction(count, per_second)


def nearest(seconds: Fraction, per_second: int) -> int:
    """``seconds`` in units of ``1/per_second``, to the nearest, a half rounded up.

    A cue's frames to milliseconds are never a half (a frame is 40/3 ms) and come back exactly;
    milliseconds to frames are off by 20/3 ms at most (metadata-mappings' record, D).
    """
    return round_half_up(seconds * per_second)


def put[T](held: list[T], value: T, same: Callable[[T], bool]) -> list[T]:
    """``value`` where the first of ``held`` it replaces stood, the others gone; else last."""
    at = next((i for i, item in enumerate(held) if same(item)), None)
    if at is None:
        return [*held, value]
    return [value if i == at else item for i, item in enumerate(held) if i == at or not same(item)]


def set_where(tags: list[Tag], tag: Tag, same: Callable[[Tag], bool], spelling: str) -> list[Tag]:
    """``tag``'s value where the first tag ``same`` accepts stood, else last, as ``spelling``.

    Where it stood, its spelling is kept and the others ``same`` accepts are gone.
    """
    stood = next((held for held in tags if same(held)), None)
    return put(tags, Tag(spelling if stood is None else stood.name, tag.value), same)
