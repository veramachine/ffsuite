"""A FLAC's Vorbis comments, read from its own block: exact, whatever a value holds.

A text export (``metaflac --export-tags-to``) writes a value's line break as one, so a value
holding one cannot be told from two comments; the block keeps each comment's length.
FLAC format: ``fLaC``, then metadata blocks -- a byte (last-block flag, type), a 24-bit
big-endian length -- the VORBIS_COMMENT block (type 4) little-endian lengths and UTF-8.
"""

from pathlib import Path
from typing import BinaryIO, Final

_MAGIC: Final = b"fLaC"
_HEADER: Final = 4  # a metadata block's: its flag and type, a 24-bit length
_VORBIS_COMMENT: Final = 4
_CUESHEET: Final = 5  # metaflac --list: "type: 5 (CUESHEET)"


def comments(path: str) -> tuple[tuple[str, str], ...] | None:
    """``path``'s Vorbis comments as ``(name, value)`` pairs; None unless a FLAC holding them."""
    block = _read(path, _VORBIS_COMMENT)
    return None if block is None else _parsed(block)


def has_cuesheet(path: str) -> bool:
    """Whether ``path`` is a FLAC holding a CUESHEET block (type 5): metaflac asked only then."""
    return _read(path, _CUESHEET) is not None


def _read(path: str, kind: int) -> bytes | None:
    """The first metadata block of ``kind`` in ``path``; None unless a FLAC holding one."""
    try:
        with Path(path).open("rb") as file:
            return _block(file, kind) if file.read(4) == _MAGIC else None
    except OSError:
        return None


def _block(file: BinaryIO, kind: int) -> bytes | None:
    """The first ``kind`` among the metadata blocks after the magic, its bytes."""
    while len(header := file.read(_HEADER)) == _HEADER:
        size = int.from_bytes(header[1:], "big")
        if header[0] & 0x7F == kind:
            return file.read(size)
        if header[0] & 0x80:  # the last metadata block: none was it
            return None
        _ = file.seek(size, 1)
    return None


def _parsed(block: bytes) -> tuple[tuple[str, str], ...] | None:
    """The block's comments; None if it is not one (truncated, or not UTF-8)."""
    vendor = _u32(block, 0)
    count = None if vendor is None else _u32(block, 4 + vendor)
    if vendor is None or count is None:
        return None
    offset, pairs = 8 + vendor, list[tuple[str, str]]()
    for _ in range(count):
        size = _u32(block, offset)
        if size is None or offset + 4 + size > len(block):
            return None
        try:
            text = block[offset + 4 : offset + 4 + size].decode("utf-8")
        except UnicodeDecodeError:
            return None
        offset += 4 + size
        name, equals, value = text.partition("=")
        if equals:  # a comment is NAME=value: none without one
            pairs.append((name, value))
    return tuple(pairs)


def _u32(block: bytes, offset: int) -> int | None:
    """A little-endian 32-bit length at ``offset``; None past the block's end."""
    if offset + 4 > len(block):
        return None
    return int.from_bytes(block[offset : offset + 4], "little")
