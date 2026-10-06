"""A font's widths, read from its file as libass scales it -- what ffman wraps lines by.

Each character's advance (``hmtx``, through ``cmap``), in a size of usWinAscent +
usWinDescent (``OS/2``): libass sizes a font so (``FT_SIZE_REQUEST_TYPE_REAL_DIM`` on those,
ass_font.c). No shaping: kerning and ligatures only narrow a line -- kerned widths were
0.961 to 1.0014 of the advances on the corpus's transcripts -- so their sum is a line's
width well within its rule (the BBC's 68%, inside libass's 90%). Shaping would matter only
for scripts the font lacks, which libass draws in fallback fonts ffman cannot know.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from ffman.subs.breaks import is_mark

_UNICODE: Final = 0x10FFFF  # the last code point: no font maps past it
# cmap subtables, preferred first: Unicode in full (format 12), then the BMP's (format 4)
_FULL: Final = ((3, 10), (0, 4), (0, 6))
_BMP: Final = ((3, 1), (0, 3))

UNKNOWN: Final = Fraction(1)  # a character the font lacks: a size (a fallback CJK glyph, ~0.77)


@dataclass(frozen=True, slots=True)
class Metrics:
    """A font's advances (font units, by code point) and the units libass's size spans."""

    advances: dict[int, int]
    height: int

    def width(self, text: str, size: Fraction, missing: Fraction) -> Fraction:
        """``text`` at ``size``, its advances summed; a character the font lacks, ``missing``.

        ``missing`` is in sizes: what a fallback font's glyph is taken to span -- but a mark's
        nothing: marks do not advance (Thai's vowels and tones, an accent), in any font.
        """
        units = others = 0
        for c in text:
            advance = self.advances.get(ord(c))
            if advance is None:
                others += 0 if is_mark(c) else 1
            else:
                units += advance
        return Fraction(units, self.height) * size + others * missing * size


def parse(data: bytes) -> Metrics:
    """A font file's metrics (OpenType or TrueType); ValueError if it is not one."""
    tables = _tables(data)
    hhea, hmtx, os2, cmap = (_table(tables, tag) for tag in ("hhea", "hmtx", "OS/2", "cmap"))
    count = _int(data, hhea + 34, 2)  # numberOfHMetrics
    if count == 0:
        msg = "a font with no horizontal metrics"
        raise ValueError(msg)
    advances = [_int(data, hmtx + 4 * i, 2) for i in range(count)]
    height = _int(data, os2 + 74, 2) + _int(data, os2 + 76, 2)  # usWinAscent + usWinDescent
    if height == 0:
        msg = "a font with no height (usWinAscent + usWinDescent is 0)"
        raise ValueError(msg)
    # a glyph past the hmtx's entries takes its last advance (the OpenType hmtx rule)
    widths = {c: advances[min(g, count - 1)] for c, g in _glyphs(data, cmap).items()}
    return Metrics(widths, height)


def _int(data: bytes, at: int, size: int, *, signed: bool = False) -> int:
    """A big-endian integer of ``size`` bytes at ``at``; ValueError past the file's end."""
    if at < 0 or at + size > len(data):
        msg = f"not a readable font: {size} bytes at {at}, past its {len(data)}"
        raise ValueError(msg)
    return int.from_bytes(data[at : at + size], "big", signed=signed)


def _tables(data: bytes) -> dict[str, int]:
    """The table directory: each tag's offset."""
    found: dict[str, int] = {}
    for i in range(_int(data, 4, 2)):
        entry = 12 + 16 * i
        _ = _int(data, entry, 16)  # the whole record is there
        found[data[entry : entry + 4].decode("latin-1")] = _int(data, entry + 8, 4)
    return found


def _table(tables: dict[str, int], tag: str) -> int:
    if tag not in tables:
        msg = f"a font without its {tag} table"
        raise ValueError(msg)
    return tables[tag]


def _glyphs(data: bytes, cmap: int) -> dict[int, int]:
    """Each code point's glyph: the full subtable's first, the BMP's for what it lacks."""
    subtables: dict[tuple[int, int], int] = {}
    for i in range(_int(data, cmap + 2, 2)):
        record = cmap + 4 + 8 * i
        key = (_int(data, record, 2), _int(data, record + 2, 2))
        _ = subtables.setdefault(key, cmap + _int(data, record + 4, 4))  # the first record wins
    found: dict[int, int] = {}
    for key in (*_FULL, *_BMP):
        if key in subtables:
            for c, g in _subtable(data, subtables[key]):
                if g and c not in found:
                    found[c] = g
    if not found:
        msg = "a font without a Unicode cmap (format 4 or 12)"
        raise ValueError(msg)
    return found


def _subtable(data: bytes, at: int) -> list[tuple[int, int]]:
    """A cmap subtable's (code point, glyph) pairs; formats 4 and 12, others none."""
    fmt = _int(data, at, 2)
    if fmt == 12:  # noqa: PLR2004 -- the format's number
        return _format12(data, at)
    if fmt == 4:  # noqa: PLR2004 -- the format's number
        return _format4(data, at)
    return []


def _format12(data: bytes, at: int) -> list[tuple[int, int]]:
    """Segmented coverage: groups of consecutive code points and glyphs."""
    pairs: list[tuple[int, int]] = []
    for k in range(_int(data, at + 12, 4)):
        group = at + 16 + 12 * k
        first, last, glyph = (_int(data, group + 4 * n, 4) for n in range(3))
        span = range(first, min(last, _UNICODE) + 1)
        _bounded(len(pairs) + len(span))  # before building them
        pairs += [(c, glyph + c - first) for c in span]
    return pairs


def _format4(data: bytes, at: int) -> list[tuple[int, int]]:
    """Segment mapping to delta values: the BMP's segments, by delta or by glyph array."""
    segments2 = _int(data, at + 6, 2)  # 2 x segCount
    ends = at + 14
    starts = ends + segments2 + 2  # past reservedPad
    deltas, ranges = starts + segments2, starts + 2 * segments2
    pairs: list[tuple[int, int]] = []
    for k in range(segments2 // 2):
        end, start = _int(data, ends + 2 * k, 2), _int(data, starts + 2 * k, 2)
        delta, offset = _int(data, deltas + 2 * k, 2, signed=True), _int(data, ranges + 2 * k, 2)
        for c in range(start, min(end, 0xFFFE) + 1):  # 0xFFFF: the closing segment's
            if offset == 0:
                pairs.append((c, (c + delta) & 0xFFFF))
                continue
            glyph = _int(data, ranges + 2 * k + offset + 2 * (c - start), 2)
            pairs.append((c, (glyph + delta) & 0xFFFF if glyph else 0))
        _bounded(len(pairs))
    return pairs


def _bounded(count: int) -> None:
    """A subtable maps each code point once: more pairs than Unicode has is not a font."""
    if count > _UNICODE + 1:
        msg = "a cmap mapping more than Unicode's code points"
        raise ValueError(msg)
