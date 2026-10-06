"""Metadata files by their names: which format a file is, read and written in it (spec 3.9).

``.ffmeta`` is ffmetadata and ``.cue`` a cue sheet; a ``.txt`` is either text form -- read, by
its first line (ffmetadata's header, else Vorbis comments); written, by ``--preset``.
"""

from fractions import Fraction
from typing import Final, Literal

# the submodules, not the package: `from ffmeta import cue` would import ffmeta's root, which
# re-exports this module's read and write -- a cycle (basedpyright); an alias binds the module
import ffmeta.cue as cue  # noqa: PLR0402
import ffmeta.ffmetadata as ffmetadata  # noqa: PLR0402
import ffmeta.vorbis as vorbis  # noqa: PLR0402
from ffmeta._errors import refuse
from ffmeta.fields import Format
from ffmeta.model import Metadata, Written

__all__ = [
    "EXTENSIONS",
    "NAMES",
    "PRESETS",
    "TEXT_PRESETS",
    "Preset",
    "TextPreset",
    "check_output",
    "format_in",
    "format_of",
    "format_out",
    "is_metadata",
    "read",
    "write",
]

type TextPreset = Literal["ffmetadata", "vorbiscomment"]  # a .txt output's
type Preset = TextPreset | Literal["cue"]  # meta's -p: stdout takes a cue too

EXTENSIONS: Final = ("ffmeta", "txt", "cue")
TEXT_PRESETS: Final[tuple[TextPreset, ...]] = ("ffmetadata", "vorbiscomment")
_BY_EXTENSION: Final[dict[str, Format]] = {"ffmeta": "ffmetadata", "cue": "cue"}
PRESETS: Final[tuple[Preset, ...]] = (*TEXT_PRESETS, "cue")
_BY_PRESET: Final[dict[Preset, Format]] = {
    "ffmetadata": "ffmetadata",
    "vorbiscomment": "vorbis",
    "cue": "cue",
}
NAMES: Final[dict[Format, str]] = {
    "ffmetadata": "ffmetadata",
    "vorbis": "Vorbis comments",
    "cue": "a cue sheet",
}


def is_metadata(ext: str) -> bool:
    """Whether a file of extension ``ext`` (lowercased) is a metadata file."""
    return ext in EXTENSIONS


def check_output(ext: str, preset: Preset | None) -> None:
    """A preset is a .txt output's alone, and a .txt is ffmetadata or Vorbis comments.

    A .ffmeta is ffmetadata, a .cue a cue sheet; ``cue`` as a preset is stdout's.
    """
    if preset is not None and ext != "txt":
        refuse(f"--preset {preset}: a .{ext} output is {NAMES[format_out(ext, None)]}")
    if preset == "cue":
        refuse("--preset cue: a .txt output is ffmetadata or Vorbis comments")


def format_of(preset: Preset) -> Format:
    """The format ``preset`` names."""
    return _BY_PRESET[preset]


def format_in(ext: str, text: str) -> Format:
    """The format of a metadata file read: by its extension, a ``.txt`` by its first line."""
    return _BY_EXTENSION.get(ext) or (
        "ffmetadata" if text.startswith(ffmetadata.HEADER) else "vorbis"
    )


def format_out(ext: str, preset: Preset | None) -> Format:
    """The format of a metadata file written: by its extension, a ``.txt`` by ``preset``."""
    return _BY_EXTENSION.get(ext) or _BY_PRESET[preset or "ffmetadata"]


def read(text: str, fmt: Format, source: str) -> Metadata:
    """``text`` in ``fmt``, named ``source`` in messages."""
    return {
        "ffmetadata": ffmetadata.read,
        "vorbis": vorbis.read,
        "cue": cue.read,
    }[fmt](text, source)


def write(meta: Metadata, fmt: Format, duration: Fraction | None = None) -> Written:
    """``meta`` in ``fmt``; ffmetadata's last chapter ends at ``duration``, if it has none."""
    if fmt == "ffmetadata":
        return ffmetadata.write(meta, duration)
    return vorbis.write(meta) if fmt == "vorbis" else cue.write(meta)
