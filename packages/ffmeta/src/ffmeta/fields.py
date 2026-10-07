"""The three formats' words for one field: ffmetadata's key, Vorbis' name, a cue's command.

One table, the mappings' (the ``metadata-mappings`` skill), which the converter maps by and the
editor (``edit.py``) resolves a key with -- so the two cannot drift.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ffmeta.model import Tag, Tags, folded, left_out

__all__ = [
    "BARCODE",
    "DISC",
    "DISC_BY_CUE",
    "GENERIC",
    "RENAMED",
    "TRACK",
    "TRACK_BY_CUE",
    "Field",
    "Format",
    "Table",
    "joined",
    "key",
    "rem_field",
    "rem_text",
    "spelled",
]

type Format = Literal["ffmetadata", "vorbis", "cue"]


@dataclass(frozen=True, slots=True)
class Field:
    """A field in each format's words: ffmetadata's key, Vorbis' name, the cue's command.

    Vorbis' is None where it has no place; a cue's ``REM`` and its word stand for a convention's.
    """

    ffmetadata: str
    vorbis: str | None
    cue: str
    quoted: bool = False  # a REM text quoted when it holds a space (never a number or a gain)

    def name(self, target: Format) -> str | None:
        """The field's name in ``target``'s words: None where it has no place."""
        return self.ffmetadata if target == "ffmetadata" else self.vorbis


@dataclass(frozen=True, slots=True)
class Table:
    """A table of fields, and what holds one of each in a cue: the disc or a track."""

    holder: str
    fields: tuple[Field, ...]


# the disc's fields (tables 2 and 3); CATALOG as Picard's BARCODE (not CATALOGNUMBER, a label's)
DISC: Final = Table(
    "a cue",
    (
        Field("album", "ALBUM", "TITLE"),
        Field("album_artist", "ALBUMARTIST", "PERFORMER"),
        Field("genre", "GENRE", "REM GENRE", quoted=True),
        Field("date", "DATE", "REM DATE"),
        Field("disc", "DISCNUMBER", "REM DISCNUMBER"),
        Field("REPLAYGAIN_ALBUM_GAIN", "REPLAYGAIN_ALBUM_GAIN", "REM REPLAYGAIN_ALBUM_GAIN"),
        Field("REPLAYGAIN_ALBUM_PEAK", "REPLAYGAIN_ALBUM_PEAK", "REM REPLAYGAIN_ALBUM_PEAK"),
        Field("BARCODE", "BARCODE", "CATALOG"),
    ),
)
# a track's, a chapter's: Vorbis' chapters hold a title alone (the Chapter Extension's NAME)
TRACK: Final = Table(
    "a track",
    (
        Field("title", "NAME", "TITLE"),
        Field("performer", None, "PERFORMER"),  # mpv's name for a track's PERFORMER
        Field("ISRC", None, "ISRC"),
        Field("REPLAYGAIN_TRACK_GAIN", None, "REM REPLAYGAIN_TRACK_GAIN"),
        Field("REPLAYGAIN_TRACK_PEAK", None, "REM REPLAYGAIN_TRACK_PEAK"),
    ),
)
# ffmpeg's generic keys and Vorbis' names for them (ff_vorbiscomment_metadata_conv)
RENAMED: Final = (
    ("album_artist", "ALBUMARTIST"),
    ("track", "TRACKNUMBER"),
    ("disc", "DISCNUMBER"),
    ("comment", "DESCRIPTION"),
)
DISC_BY_CUE: Final = {field.cue: field for field in DISC.fields}
TRACK_BY_CUE: Final = {field.cue: field for field in TRACK.fields}
BARCODE: Final = "BARCODE"  # the CATALOG's name in both


def joined(tags: Tags, what: str, notes: list[str]) -> Tags:
    """Each name once, its values joined with ';' in order (ffmpeg's ``AV_DICT_APPEND``).

    Noted: ';' in a value and two values then read alike.
    """
    values: dict[str, list[str]] = {}
    spelled: dict[str, str] = {}
    for tag in tags:
        key = folded(tag.name)
        if key not in values:
            values[key], spelled[key] = [], tag.name
        values[key].append(tag.value)
    for key, held in values.items():
        if len(held) > 1:
            notes.append(f"{what} '{spelled[key]}': {len(held)} values joined with ';', one a key")
    return tuple(Tag(spelled[key], ";".join(held)) for key, held in values.items())


def rem_field(rem: str) -> tuple[str, str]:
    """A REM line's field, ``REM WORD``, and its value, unquoted."""
    match rem.split(None, 1):
        case [word, value]:
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] == '"':
                value = value[1:-1]
            return f"REM {word.upper()}", value
        case [word]:
            return f"REM {word.upper()}", ""
        case _:
            return "REM", ""


def rem_text(field: Field, tag: Tag, notes: list[str]) -> str | None:
    r"""``tag`` as its REM line's text: quoted when it holds a space, if its field's is.

    Left out, noted, what a quote cannot hold: a ``"``, or a final ``\`` (libcue's escape, as
    the cue writer's strings).
    """
    value = tag.value
    if field.quoted and " " in value:
        if '"' in value:
            notes.append(left_out(f"the tag '{tag.name}'", "a quote and a space: no REM quotes it"))
            return None
        if value.endswith("\\"):
            why = "it ends in '\\': libcue reads the rest of the sheet into it"
            notes.append(left_out(f"the tag '{tag.name}'", why))
            return None
        value = f'"{value}"'
    return f"{field.cue.removeprefix('REM ')} {value}".rstrip()


# ffmpeg's generic keys (avformat.h, "a list of generic tag names")
GENERIC: Final = frozenset(
    (
        "album", "album_artist", "artist", "comment", "composer", "copyright", "creation_time",
        "date", "disc", "encoder", "encoded_by", "filename", "genre", "language", "performer",
        "publisher", "service_name", "service_provider", "title", "track", "variant_bitrate",
    )
)  # fmt: skip
_FROM_VORBIS: Final = {folded(vorbis): generic for generic, vorbis in RENAMED}
_TO_VORBIS: Final = dict(RENAMED)


def key(name: str) -> str:
    """A key as ffman compares it: without case, Vorbis' four as ffmpeg's generic ones."""
    name = folded(name)
    return _FROM_VORBIS.get(name, name)


def spelled(name: str, fmt: Format) -> str:
    """``name`` in ``fmt``'s spelling: a generic key ffmetadata's or Vorbis', another as given."""
    generic = key(name)
    if generic not in GENERIC:
        return name
    return generic if fmt == "ffmetadata" else _TO_VORBIS.get(generic, generic.upper())
