"""A minimal OpenType font, built to order: the tables subs.metrics reads, and maxp.

Each character is its own glyph (1, 2, ... in order; 0 is .notdef), so a test states
advances by character and reads them back. The OpenType specification's layouts:
https://learn.microsoft.com/typography/opentype/spec/ (hhea, hmtx, OS/2, cmap).
"""

import struct


def font(
    advances: dict[str, int],
    *,
    ascent: int = 1000,
    descent: int = 300,
    fmt: int = 4,
    metrics: int | None = None,
    by_array: bool = False,
    drop: str = "",
) -> bytes:
    """A font mapping each character to its advance; ``metrics``: hmtx's entries (default
    all), ``by_array``: format 4 through its glyph array, ``drop``: a table left out."""
    chars = sorted(advances)
    count = len(chars) + 1 if metrics is None else metrics
    widths = [0, *(advances[c] for c in chars)][:count]
    tables = {
        "hhea": bytes(34) + struct.pack(">H", count),
        # count longHorMetrics, then a left side bearing for each glyph past them
        "hmtx": b"".join(struct.pack(">Hh", w, 0) for w in widths)
        + bytes(2 * (len(chars) + 1 - count)),
        "OS/2": bytes(74) + struct.pack(">HH", ascent, descent),
        "cmap": _cmap([ord(c) for c in chars], fmt, by_array=by_array),
        "maxp": struct.pack(">IH", 0x00005000, len(chars) + 1),  # every font has one (numGlyphs)
    }
    _ = tables.pop(drop, None)  # the table a test leaves out
    return _sfnt(tables)


def _sfnt(tables: dict[str, bytes]) -> bytes:
    head = struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0)
    offset = 12 + 16 * len(tables)
    records, body = b"", b""
    for tag, data in tables.items():
        records += struct.pack(">4sIII", tag.encode("latin-1"), 0, offset + len(body), len(data))
        body += data + bytes(-len(data) % 4)
    return head + records + body


def _cmap(points: list[int], fmt: int, *, by_array: bool) -> bytes:
    if fmt == 12:
        groups = b"".join(struct.pack(">III", p, p, g) for g, p in enumerate(points, 1))
        sub = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(points)) + groups
        platform = (3, 10)
    elif fmt == 4:
        sub = _format4(points, by_array=by_array)
        platform = (3, 1)
    else:  # a format subs.metrics does not read
        sub = struct.pack(">HHH", fmt, 6, 0)
        platform = (3, 1)
    return struct.pack(">HHHHI", 0, 1, *platform, 12) + sub


def _format4(points: list[int], *, by_array: bool) -> bytes:
    """One segment a character, then the closing 0xFFFF; by its delta, or its glyph array."""
    segments = [*points, 0xFFFF]
    n = len(segments)
    ends = b"".join(struct.pack(">H", p) for p in segments)
    starts = ends
    if by_array:  # idDelta 0; segment k's glyph at array[k]: &offsets[k] + 2n reaches it
        deltas = b"".join(struct.pack(">h", 0) for _ in segments)
        offsets = struct.pack(">H", 2 * n) * len(points) + b"\0\0"
        array = b"".join(struct.pack(">H", g) for g in range(1, len(points) + 1))
    else:
        signed = (((g - p + 0x8000) % 0x10000) - 0x8000 for g, p in enumerate(points, 1))
        deltas = b"".join(struct.pack(">h", d) for d in signed)  # g - p, wrapping as 16 bits
        deltas += struct.pack(">h", 1)
        offsets, array = bytes(2 * n), b""
    body = ends + b"\0\0" + starts + deltas + offsets + array
    return struct.pack(">HHHHHHH", 4, 14 + len(body), 0, 2 * n, 0, 0, 0) + body
