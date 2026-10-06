"""A FLAC's Vorbis comments, written in its bytes (RFC 9639, 8.1 and 8.6): ffmpeg's to read."""

import struct
from typing import Final

_MAGIC: Final = b"fLaC"
_COMMENTS: Final = 4  # the VORBIS_COMMENT block's type
_PADDING: Final = 1
_LAST: Final = 0x80  # a block header's flag: no block follows


def with_comments(flac: bytes, comments: list[bytes]) -> bytes:
    """``flac`` with ``comments`` as its one comment block, its padding dropped."""
    if not flac.startswith(_MAGIC):
        msg = "not a FLAC stream"
        raise ValueError(msg)
    kept: list[tuple[int, bytes]] = []  # each block but comments and padding: type, body
    at, last = len(_MAGIC), False
    while not last:
        header, size = flac[at], int.from_bytes(flac[at + 1 : at + 4], "big")
        last, kind = bool(header & _LAST), header & ~_LAST
        if kind not in {_COMMENTS, _PADDING}:
            kept.append((kind, flac[at + 4 : at + 4 + size]))
        at += 4 + size
    vendor = b"ffman tests"
    body = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    body += b"".join(struct.pack("<I", len(comment)) + comment for comment in comments)
    blocks = [*kept, (_COMMENTS, body)]
    out = bytearray(_MAGIC)
    for number, (kind, data) in enumerate(blocks, 1):
        out += (
            bytes([kind | (_LAST if number == len(blocks) else 0)])
            + len(data).to_bytes(3, "big")
            + data
        )
    return bytes(out + flac[at:])
