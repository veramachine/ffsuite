"""The ASS script every overlay mode burns: the bash ffman's write_ass, event for event.

Plain follows mpv (57 at 1080 lines, outline 1.65/38 of it, no shadow, not
bold); the highlighting modes are heavier (bold, 64). A highlighted word is
drawn without jitter: layer 0 draws the line with that word invisible (alpha
keeps the metrics), layer 1 only the word. Each wrapped line is its own event,
anchored at its middle. In a bar under the picture the text is centred in it,
lifted only as far as a tall block needs. Places and sizes are exact: what
libass reads as an integer rounded half up, as a double written as near as it
holds (_number) -- it places text to a fraction of a pixel. Lengths are
characters (bash pinned C.UTF-8 here).
"""

import itertools
import math
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Final, final

from subverter.transcript import Chunk, Transcript, Word

from ffman.subs.breaks import breakable, is_mark, segments
from ffman.subs.colorize import (
    GOLD,
    WHITE,
    Colorize,
    Highlight,
    Rectangle,
    outline_for,
)
from ffman.subs.layout import CANVAS, font_size
from ffman.subs.metrics import UNKNOWN, Metrics
from ffman.subs.paint import Painter, solid
from ffman.values import decimal, div_half_up, finite_decimal, round_half_up

# the text box's bottom above the frame's, of its height (the owner's)
MARGIN: Final = Fraction("0.05573")
FONT: Final = "IBM Plex Sans"
_FORMAT: Final = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
    "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
_EVENTS: Final = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
_EM: Final = Fraction("0.55")  # a glyph's width, in font sizes: the estimate, for a font unread
_LINE: Final = Fraction(6, 5)  # the BBC's line: 68% of a 16:9 width, 90% of a 4:3 -- 1.2 heights
_SAFE: Final = Fraction(9, 10)  # libass's width: the canvas less ffman's 5% margins
FONT_FILES: Final = {
    False: "IBMPlexSans-Regular.otf",
    True: "IBMPlexSans-Bold.otf",
}  # FONT, shipped
# the pop (bash's): a peak of 1 + 0.45/chars -- each side's growth near 45% of a space,
# so it never reaches a neighbour (a flat 118% covered a letter; 0.76/chars touched it)
_GROWTH: Final = Fraction(45)  # %, over the word's characters
_PEAK: Final = Fraction(118)  # %: the most -- a lone word's
_RISE: Final = 90  # ms to the peak, at most (half a shorter word)
_SETTLE: Final = 150  # ms back to 100%, at most: never past the word's end
_FADE: Final = 80  # ms: plain's colour fade, at most
HIGHLIGHTING: Final = ("chunk-word", "word-highlight")  # the modes that highlight a word


@dataclass(frozen=True, slots=True)
class Style:
    """How the text looks and where it sits (bash's SUBMODE, HLMODE, FONTSIZE, MARGIN, BARY)."""

    mode: str = "plain"
    highlight: str = "plain"  # plain or pop
    size: Fraction | None = None  # --font-size, else the mode's
    margin: Fraction = MARGIN
    bar_y: Fraction | None = None  # the bar's centre, when the text sits in one
    font: str = FONT
    colorize: Highlight = GOLD  # --highlight-colorize
    text: Colorize = WHITE  # --font-color
    outline: Colorize | None = None  # --outline-color; none: each fill's own (outline_for)

    def text_outline(self) -> Colorize:
        """The text's outline: given, or the one that contrasts most with its colour."""
        return self.outline or outline_for(self.text)


def script(  # noqa: PLR0913 -- the transcript; its frames' size; its style; their timing, font
    transcript: Transcript,
    width: int,
    height: int,
    style: Style,
    *,
    frame: Fraction | None = None,
    metrics: Metrics | None = None,
) -> tuple[str, tuple[str, ...]]:
    """The ASS script for frames of ``width`` x ``height``, and its notes.

    Notes: text past the top; lit runs whose hues are held still (``_MOTION_BUDGET``).

    ``frame``: a frame's duration, s (None: unknown) -- a word's animation ends a frame early.
    ``metrics``: the font's, which lines are measured by (None: estimated, ``_EM`` a glyph).
    """
    fs = font_size(style.size, plain=style.mode == "plain")
    px = round_half_up(Fraction(CANVAS * width, height))  # PlayResX: an integer to libass
    mv = round_half_up(style.margin * CANVAS)  # MarginV: an integer
    frame_ms = math.ceil(frame * 1000) if frame is not None else 0  # up: never under a frame
    events = _Events(transcript, style, fs=fs, px=px, mv=mv, frame_ms=frame_ms, metrics=metrics)
    text = _header(style, fs, px, mv) + events.render()
    notes: list[str] = []
    if events.over:
        where = (
            f"{events.over} sentences wrap past the top of the frame at --font-size {decimal(fs)}"
        )
        notes.append(f"{where}: use a smaller --font-size")
    if style.mode in HIGHLIGHTING and style.colorize == style.text:
        notes.append("the highlight is the text's colour: it shows nothing")
    if events.paint.held:
        notes.append(f"{events.paint.held} runs too long to move: their hues held still")
    return text, tuple(notes)


def _estimate(c: str) -> Fraction:
    """A character's width in sizes, the font unread.

    A mark nothing (marks do not advance), a wide one (an ideograph, kana) a size, any other
    ``_EM``.
    """
    if is_mark(c):
        return Fraction(0)
    return Fraction(1) if unicodedata.east_asian_width(c) in ("W", "F") else _EM


def bold(style: Style) -> bool:
    """Whether the style is bold: the highlighting modes are, plain is not (its FONT_FILES)."""
    return style.mode != "plain"


def _number(value: Fraction) -> str:
    """A number libass reads as a double, written as near it as libass can hold.

    Its decimal exactly when it has one, else the shortest text of the double
    nearest it (Python's repr: the double it reads back as).
    """
    text = finite_decimal(value)
    return text if text is not None else repr(float(value))


def _edges(style: Style, fs: Fraction) -> tuple[Fraction, Fraction]:
    """The outline's width and the shadow's depth, canvas units (bash's: plain's thinner)."""
    if style.mode == "plain":
        return fs * Fraction("1.65") / 38, Fraction(0)
    return fs / 16, fs / 42


def _header(style: Style, fs: Fraction, px: int, mv: int) -> str:
    width, depth = _edges(style, fs)
    outline, shadow = _number(width), _number(depth)
    weight = "-1" if bold(style) else "0"
    ml = round_half_up(Fraction(px, 20))  # MarginL and R: 5% of the width, integers
    fill, edge = solid(style.text).code(), solid(style.text_outline()).code()
    colours = f"{fill},&H000000FF,{edge},&H80000000"
    # Encoding -1: the text's own direction (libass: FRIBIDI_PAR_ON, and its whole-text layout)
    look = f"{weight},0,0,0,100,100,0,0,1,{outline},{shadow},2,{ml},{ml},{mv},-1"
    styles = f"Style: Default,{style.font},{_number(fs)},{colours},{look}\n"
    if isinstance(style.colorize, Rectangle):  # the lit word's: a box (BorderStyle 3), no shadow
        boxed = f"{edge},&H000000FF,{fill},&H80000000"  # reverse video: the text the outline's
        styles += f"Style: Box,{style.font},{_number(fs)},{boxed},{weight},0,0,0,100,100,0,0,3,"
        styles += f"{outline},0,2,{ml},{ml},{mv},-1\n"
    return (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {px}\nPlayResY: 1080\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\nKerning: yes\nYCbCr Matrix: None\n\n"
        f"[V4+ Styles]\n{_FORMAT}\n{styles}\n"
        f"[Events]\n{_EVENTS}\n"
    )


def _cs10(ms: int) -> int:
    """Milliseconds to ASS's centiseconds, rounded half up; never negative."""
    return max(div_half_up(ms, 10), 0)


def _ts(ms: int) -> str:
    cs = _cs10(ms)
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


def _esc(text: str) -> str:
    """No override tags from the text: a backslash to /, braces to parentheses."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


@dataclass(slots=True)
class _Lines:
    """A sentence laid out: its words, each word's line, each line's y.

    ``gaps``: what comes before each word, " " or "" (unspaced text, a cluster's neighbour).
    """

    words: list[str]
    gaps: list[str]
    first: list[int] = field(default_factory=list)  # each word's first letter, in the sentence
    letters: int = 0  # the sentence's letters (clusters)
    line_of: list[int] = field(default_factory=list)
    ys: list[Fraction] = field(default_factory=list)

    def texts(self) -> list[str]:
        """Each line's text: its words, each after its gap but the line's first."""
        lines: list[str] = ["" for _ in range(max(self.line_of, default=-1) + 1)]
        for word, gap, n in zip(self.words, self.gaps, self.line_of, strict=True):
            lines[n] += (gap if lines[n] else "") + word
        return lines


@final
class _Events:
    """bash's ASS_AWK: the events, in its order, and how many blocks start above the frame."""

    def __init__(  # noqa: PLR0913 -- the transcript, its style, and the canvas's measures
        self,
        t: Transcript,
        style: Style,
        *,
        fs: Fraction,
        px: int,
        mv: int,
        frame_ms: int,
        metrics: Metrics | None,
    ) -> None:
        self.t, self.style, self.fs, self.px, self.mv = t, style, fs, px, mv
        self.frame_ms, self.metrics = frame_ms, metrics
        self.limit = min(_LINE * CANVAS, _SAFE * px)  # a line's width, at most (canvas units)
        self.lh = fs * Fraction(5, 4)  # a line: 1.25 font sizes
        self.ybot = CANVAS - mv - fs * Fraction(3, 5)  # the last line's centre
        self.bary = style.bar_y
        self.cx = _number(Fraction(px, 2))  # every line's x: the canvas' centre
        self._y_text: dict[Fraction, str] = {}  # a line's y, written once: its events share it
        self.over = 0
        self.paint = Painter(
            style.text,
            style.outline,
            style.colorize,
            fs=fs,
            lh=self.lh,
            edge=_edges(style, fs)[0],
            metrics=metrics,
        )
        self.out: list[str] = []
        self.words: dict[str, list[Word]] = defaultdict(list)
        for w in t.words:
            self.words[w.segment].append(w)

    def render(self) -> str:
        match self.style.mode:
            case "plain":
                self._plain()
            case "word" | "word-highlight":
                self._word()
            case _:
                self._chunk_word()
        return "".join(self.out)

    # -- geometry
    def _width(self, text: str) -> Fraction:
        """``text``'s width, canvas units: by the font's metrics, else estimated (``_estimate``)."""
        if self.metrics is not None:
            return self.metrics.width(text, self.fs, UNKNOWN)
        return sum(map(_estimate, text), Fraction(0)) * self.fs

    def _mid(self, bary: Fraction, nl: int) -> Fraction:
        """A block's centre in the bar: its centre, lifted no further than a tall block needs."""
        lo = min(max(bary + self.lh / 2, CANVAS - self.mv), CANVAS)
        return lo - nl * self.lh / 2 if bary + nl * self.lh / 2 > lo else bary

    def _base(self, nl: int) -> Fraction:
        """The first line's y: centred in the bar, else stacked up from the margin."""
        if self.bary is not None:
            return self._mid(self.bary, nl) - (nl - 1) * self.lh / 2
        return self.ybot - (nl - 1) * self.lh

    def _at(self, y: Fraction) -> str:
        """Centred at the canvas' centre and ``y``, exactly: libass places to a fraction of a px."""
        if (text := self._y_text.get(y)) is None:
            text = self._y_text[y] = _number(y)
        return f"\\an5\\pos({self.cx},{text})"

    def _ev(self, layer: int, s: int, e: int, text: str, style: str = "Default") -> None:
        if _cs10(e) > _cs10(s):
            self.out.append(f"Dialogue: {layer},{_ts(s)},{_ts(e)},{style},,0,0,0,,{text}\n")

    def _in(self, dur: int) -> int:
        """The highlight's fade-in, ms: plain's 80, pop's rise; 0, at once -- by the last frame."""
        window = dur - self.frame_ms  # the last frame shows at window or later
        if self.style.highlight != "pop":
            return max(min(_FADE, window), 0)
        # half the window, as bash's rise was half a short word
        return max(min(window // 2, _RISE), 0)

    def _box(self, dur: int, up: int, *, room: bool) -> str:
        r"""The rectangle's tags: its colours, its padding -- a pop's in it, never the text's.

        libass draws a box per glyph from each glyph's origin and scales it twice (VSFilter's
        way, ``ass_render.c``): a scaled word's box covered its neighbours' outlines (rendered,
        to 119 px), so the padding pops instead, into the room the word has; abutting, 1.
        """
        pad = self.paint.pad if room else Fraction(1)
        tags = self.paint.lit(up) + f"\\bord{_number(pad)}"
        if self.style.highlight != "pop" or up < 1 or not room or self.paint.rise == 0:
            return tags
        back = min(up + _SETTLE, dur - self.frame_ms)
        rise = f"\\t(0,{up},0.5,\\bord{_number(pad + self.paint.rise)})"
        return tags + rise + f"\\t({up},{back},1.5,\\bord{_number(pad)})"

    def _hl_tags(self, dur: int, chars: int, *, room: bool = True) -> str:
        r"""A highlighted word's tags: gold, and for pop a smooth scale -- done by its last frame.

        libass draws no event after its end (``\t``'s progress counts from its start), and the
        word's last frame shows a frame or less before it: an animation still running there is
        cut, a jump. So each is done by ``window``, a frame before the end (bash's settle ran
        150 ms past the peak: cut on every word under 240 ms, a jump of up to 9% on words to
        ~270 ms at 24-30 fps).

        The peak grows each side into ~45% of a space (bash's rule): a word with no space beside
        it -- abutting its neighbour, in unspaced text -- has no ``room``, and is not scaled
        (rendered, a Japanese pop covered its neighbours' ink; a spaced one, none).
        """
        up = self._in(dur)
        if self.paint.boxed:
            return self._box(dur, up, room=room)
        if self.style.highlight != "pop" or up < 1 or not room:  # no time, or no room: unscaled
            return self.paint.lit(up)
        back = min(up + _SETTLE, dur - self.frame_ms)
        pk = _number(min(100 + _GROWTH / chars, _PEAK) if chars > 0 else _PEAK)
        rise = f"\\t(0,{up},0.5,\\fscx{pk}\\fscy{pk})"
        settle = f"\\t({up},{back},1.5,\\fscx100\\fscy100)"
        return self.paint.lit(up) + rise + settle

    # -- layout
    def _breaks(self, words: list[str], gaps: list[str]) -> _Lines:
        """Greedy lines, each within ``limit``, broken only where a break may fall (``breakable``).

        ffman breaks every line itself: libass breaks only at spaces here (nixpkgs builds it
        without libunibreak), and the highlight layers must break alike. Units no break may
        part are glued; a glued run wider than a line starts a line of its own and is broken
        between its units there, rather than run past the frame (CSS's overflow-wrap: break-word)
        -- but a timed word is one unit, its highlight one: alone on its line, it stays whole.
        """
        counts = [len(segments(word)[0]) for word in words]
        lines = _Lines(words, gaps, list(itertools.accumulate(counts, initial=0))[:-1], sum(counts))
        used, nl = Fraction(0), 0
        for run in self._glued(words, gaps):
            wide = self._span(lines, run) > self.limit
            if wide and lines.line_of:  # an emergency: on a line of its own first (CSS's way)
                nl, used = nl + 1, Fraction(0)
            for part in [[k] for k in run] if wide else [run]:  # then unit by unit
                gap = self._width(gaps[part[0]]) if used else Fraction(0)
                size = self._span(lines, part)
                if used and used + gap + size > self.limit:
                    nl, used = nl + 1, size
                else:
                    used += gap + size
                lines.line_of += [nl] * len(part)
        return lines

    def _span(self, lines: _Lines, part: list[int]) -> Fraction:
        """Consecutive words' width, with the gaps between them (not the gap before the first)."""
        inner = sum((self._width(lines.gaps[k]) for k in part[1:]), Fraction(0))
        return inner + sum((self._width(lines.words[k]) for k in part), Fraction(0))

    @staticmethod
    def _glued(words: list[str], gaps: list[str]) -> list[list[int]]:
        """The words in runs no break may part: a space parts them, else ``breakable``."""
        runs: list[list[int]] = []
        for k, word in enumerate(words):
            if k == 0 or gaps[k] or breakable(words[k - 1], word):
                runs.append([k])
            else:
                runs[-1].append(k)
        return runs

    def _place(self, lines: _Lines) -> _Lines:
        """Each line's y, for lines drawn as events of their own (a bar, chunk-word)."""
        nl = max(lines.line_of, default=0) + 1
        base = self._base(nl)
        lines.ys = [base + i * self.lh for i in range(nl)]
        if lines.ys[0] - self.lh / 2 < 0:
            self.over += 1
        return lines

    def _wrap(self, words: list[str], gaps: list[str]) -> _Lines:
        return self._place(self._breaks(words, gaps))

    def _line(  # noqa: PLR0913 -- the lines, which one, which word, which layer, and when
        self, lines: _Lines, n: int, k: int, *, top: bool, s: int, e: int
    ) -> str:
        """Line ``n``'s words, in an event from ``s`` to ``e``.

        Layer 0 (not ``top``) hides word ``k``; layer 1 shows only it.
        """
        out = ""
        end = None if top else self._line_budget(lines, n, k, e - s)
        for m, word in enumerate(lines.words):
            if lines.line_of[m] != n:
                continue
            sp = lines.gaps[m] if out else ""  # each word after its gap, but the line's first
            if m == k and not top:
                out += f"{sp}{{\\alpha&HFF&}}{word}{{\\alpha&H00&}}"
            elif m == k:
                last = m + 1 == len(lines.words) or lines.line_of[m + 1] != n
                # space, or the line's edge, on each side
                room = (not out or sp == " ") and (last or lines.gaps[m + 1] == " ")
                glyphs = sum(1 for c in word if not is_mark(c))  # what the peak is over: not a mark
                tags = self._hl_tags(e - s, glyphs, room=room)
                fade = self._in(e - s)
                shown = self.paint.letters(word, s, e - s, fade, lines.first[m], lines.letters)
                out += (
                    f"{sp}{{\\alpha&H00&{tags}}}{shown}{{\\r\\alpha&HFF&}}"  # \r: the scale stops
                )
            elif top:  # hidden on layer 1: no colours to move
                out += f"{sp}{word}"
            else:
                out += f"{sp}{self.paint.text_of(word, lines.first[m], lines.letters, s, e, end)}"
        return out

    def _line_budget(self, lines: _Lines, n: int, k: int, dur: int) -> int | None:
        """Line ``n``'s budget, one for its event: over the letters it shows (all but ``k``)."""
        shown = [w for m, w in enumerate(lines.words) if lines.line_of[m] == n and m != k]
        return self.paint.text_budget(sum(len(segments(word)[0]) for word in shown), dur)

    def _block(self, lines: _Lines, s: int, e: int, k: int = -1) -> None:
        for n, y in enumerate(lines.ys):
            self._ev(0, s, e, f"{{{self._at(y)}}}{self._line(lines, n, k, top=False, s=s, e=e)}")

    # -- the modes
    def _plain(self) -> None:
        for c in self.t.chunks:
            units = segments(_esc(c.text))
            if self.bary is None:  # libass places the block at the margin; its lines broken here
                texts = self._breaks(*units).texts()
                if CANVAS - self.mv - len(texts) * self.lh < 0:
                    self.over += 1
                counts = [len(segments(text)[0]) for text in texts]
                total = sum(counts)
                # each line's first letter across the subtitle; the budget once, the event's
                firsts = list(itertools.accumulate(counts, initial=0))
                end = self.paint.text_budget(total, c.end - c.start)
                painted = [
                    self.paint.text_of(t, f, total, c.start, c.end, end)
                    for t, f in zip(texts, firsts[:-1], strict=True)
                ]
                self._ev(0, c.start, c.end, "\\N".join(painted))
                continue
            self._block(self._wrap(*units), c.start, c.end)

    def _word(self) -> None:
        queue: list[tuple[int, int, str, bool]] = []
        for c in self.t.chunks:
            words = self.words.get(c.segment, []) if c.segment != "" else []
            if words:
                queue += [(w.start, w.end, w.text, True) for w in words]
            else:
                queue.append((c.start, c.end, c.text, not self.t.has_words))
        for i, (s, e, text, lit) in enumerate(queue):
            after = queue[i + 1][0] if i + 1 < len(queue) else None
            # no flicker in a short gap: held to the next when it follows within 400 ms
            end = after if after is not None and e < after < e + 400 else e
            shown = _esc(text)
            letters = len(segments(shown)[0])
            tags, look = "", "Default"
            if self.style.mode == "word-highlight" and lit:
                tags = self._hl_tags(end - s, 0)
                shown = self.paint.letters(shown, s, end - s, self._in(end - s), 0, letters)
                look = "Box" if self.paint.boxed else look
            else:
                shown = self.paint.text_of(shown, 0, letters, s, end)
            self._ev(0, s, end, f"{{{self._at(self._base(1))}{tags}}}{shown}", look)

    def _chunk_word(self) -> None:
        for c in self.t.chunks:
            timed = self.words.get(c.segment, []) if c.segment != "" else []
            if not timed:  # laid out like the others, never highlighted
                self._block(self._wrap(*segments(_esc(c.text))), c.start, c.end)
                continue
            words = [_esc(w.text) for w in timed]
            # unspaced text: its timed words abut
            sep = "" if len(words) > 1 and " " not in c.text else " "
            lines = self._wrap(words, ["", *[sep] * (len(words) - 1)])
            self._chunk_events(c, timed, lines)

    def _chunk_events(self, c: Chunk, timed: list[Word], lines: _Lines) -> None:
        """Every event inside the chunk's window, whatever the word times say."""
        first = min(max(timed[0].start, c.start), c.end)
        self._block(lines, c.start, first)
        for k, word in enumerate(timed):
            s = min(max(word.start, c.start), c.end)
            e = max(min(timed[k + 1].start if k + 1 < len(timed) else c.end, c.end), s)
            self._block(lines, s, e, k)
            n = lines.line_of[k]
            shown = self._line(lines, n, k, top=True, s=s, e=e)
            lit = "Box" if self.paint.boxed else "Default"
            self._ev(1, s, e, f"{{{self._at(lines.ys[n])}\\alpha&HFF&}}{shown}", lit)
