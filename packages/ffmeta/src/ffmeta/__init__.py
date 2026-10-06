"""Metadata files: ffmetadata, Vorbis comments and cue sheets, read into one model, written from it.

Pure: text in, text out -- no ffmpeg, no file. The formats are ffman's skills'
(``.agents/skills/ffmetadata``, ``vorbiscomment``, ``cue``); what crosses between them is
``docs/ffman-mappings.md`` -- both in ffman's repository.
"""

from ffmeta._errors import Error
from ffmeta.convert import Converted, convert
from ffmeta.fields import Format
from ffmeta.files import read, write
from ffmeta.model import Chapter, Disc, File, Index, Metadata, Tag, Track, Written

__all__ = [
    "Chapter",
    "Converted",
    "Disc",
    "Error",
    "File",
    "Format",
    "Index",
    "Metadata",
    "Tag",
    "Track",
    "Written",
    "convert",
    "read",
    "write",
]

Error.__module__ = "ffmeta"  # tracebacks name the public ffmeta.Error, not its private module
