r"""The colours of the text ASS draws: the highlighted word's, the text's in motion, the box's.

A colour is written whole -- the word's opening block -- where nothing of it moves; else each
letter (a cluster) its own block: ``\1c`` and ``\3c`` chains through a motion's keyframes, by
absolute time, so a letter's hue runs on from one event into the next. ``Painter.held`` counts
the runs over ``MOTION_BUDGET`` keyframes, whose hues are held still (libass parses an event's
tags every frame).
"""

from collections.abc import Callable
from fractions import Fraction
from itertools import pairwise
from typing import Final, final

from ffman.subs.breaks import segments
from ffman.subs.colorize import (
    Colorize,
    Colour,
    Highlight,
    Motion,
    Rectangle,
    colour_at,
    keyframes,
    outline_for,
)
from ffman.subs.metrics import UNKNOWN, Metrics

# a lit run's keyframes at most: over, its letters hold their hues still (a hostile run of
# 2,000 letters lit 60 s in lsd made 19 MB of script; a long cue, 84 letters 7 s, ~3,500)
MOTION_BUDGET: Final = 10_000
# a space, in sizes, for a font unread: under Plex's 0.18, so a box fits beside a word -- the
# wrapping's estimate errs the other way (ass._EM, 0.55: lines break early); each, safe
_SPACE: Final = Fraction(3, 20)


def solid(paint: Colorize) -> Colour:
    """A colour for a style line: itself, or a motion's at its phase 0 (each letter its own)."""
    return paint if isinstance(paint, Colour) else colour_at(paint, 0, 1, 0)


@final
class Painter:
    """The text's colours, its outline's and the highlight's, for one script."""

    def __init__(  # noqa: PLR0913 -- the three colours, and the box's measures
        self,
        text: Colorize,
        outline: Colorize | None,
        highlight: Highlight,
        *,
        fs: Fraction,
        lh: Fraction,
        edge: Fraction,
        metrics: Metrics | None,
    ) -> None:
        """The colours given (``outline`` none: each fill's own), and the box's measures."""
        self.text, self.highlight = text, highlight
        self.held = 0  # runs over the budget: their hues held still
        # the outlines: the text's, and the lit word's own (each the style's, so once)
        self.outline = outline or outline_for(text)
        self.boxed = isinstance(highlight, Rectangle)
        own = (
            self.outline if isinstance(highlight, Rectangle) else outline or outline_for(highlight)
        )
        self.lit_outline = own
        # the box: its padding, half the room beside a word (the space, less a neighbour's
        # outline) and between lines; a pop's, the rest of it less a unit -- never over a word
        space = metrics.width(" ", fs, UNKNOWN) if metrics is not None else fs * _SPACE
        room = min(space - edge, lh - fs - edge)
        self.pad = max(min(edge, room / 2), Fraction(1))
        self.rise = max(room - self.pad - 1, Fraction(0))
        # what moves of the text itself: its colour, its outline (a motion's outline is fixed)
        self.moving_text = text if isinstance(text, Motion) else None
        self.moving_outline = outline if isinstance(outline, Motion) else None
        # the lit word's colours, the whole word's at once (lit) -- or, where any of it moves,
        # each letter's (letters): one rule, so the two never both write, nor neither
        still = self.moving_text is None and self.moving_outline is None
        self.whole = still and (self.boxed or isinstance(highlight, Colour))

    def lit(self, ms: int) -> str:
        """The highlighted word's colours (``--highlight-colorize``), whole, in over ``ms``.

        A colour's fade; the rectangle's reverse video, at once -- the word the outline's colour,
        its box the text's. Where any of it moves, none here: each letter's (``letters``).
        """
        if not self.whole:
            return ""
        highlight, text = self.highlight, solid(self.text)
        if isinstance(highlight, Colour):
            return self._fade(ms, highlight, text)
        return f"\\1c{solid(self.outline).ass()}\\3c{text.ass()}"  # the rectangle

    def letters(  # noqa: PLR0913 -- the word, its time and fade, its place among its letters
        self, word: str, s: int, dur: int, fade: int, first: int, letters: int
    ) -> str:
        r"""The highlighted word's text: as it is, or, where anything moves, each letter's own.

        From the font's colour at ``s`` (a motion's: the letter's own) to the highlight's over
        ``fade``, a motion's keyframes after; an outline's motion runs on through it. The
        rectangle's: each letter's chains, swapped -- the box (``\\3c``) the text's colour, the
        letter (``\\1c``) the outline's. ``first`` the word's first among its sentence's
        ``letters``; a run over the budget keeps each letter's first colour, still.
        """
        if self.whole:
            return word
        highlight, text, edge = self.highlight, self.text, self.outline
        units, gaps = segments(word)
        if isinstance(highlight, Rectangle):
            end = self._budget(len(units), dur, 0, self.moving_text, self.moving_outline)

            def boxed(_: int, letter: int) -> str:
                fill = self._chain(self.moving_outline, "1c", letter, letters, s, end)
                box = self._chain(self.moving_text, "3c", letter, letters, s, end)
                return (fill or f"\\1c{solid(edge).ass()}") + (box or f"\\3c{solid(text).ass()}")

            return _per_letter(units, gaps, first, boxed)
        end = self._budget(len(units), dur, fade, highlight, self.moving_outline)

        def tags(k: int, letter: int) -> str:
            start = text if isinstance(text, Colour) else colour_at(text, letter, letters, s)
            if isinstance(highlight, Colour):
                lit = self._fade(fade, highlight, start)
            else:
                frames = keyframes(highlight, k, len(units), fade, end)
                lit = self._fade(fade, frames[0][1], start) + _steps(frames, "1c")
            return lit + self._chain(self.moving_outline, "3c", letter, letters, s, end)

        return _per_letter(units, gaps, first, tags)

    def text_of(  # noqa: PLR0913 -- the text, its place among its letters, when, its budget
        self, text: str, first: int, letters: int, s: int, e: int, end: int | None = None
    ) -> str:
        """``text``, not highlighted: as it is, or, where the font or outline moves, each letter's.

        Each letter's chains by absolute time -- ``first`` the text's first among its sentence's
        ``letters``, from its event's ``s`` to ``e``; ``end``, the event's budget decided (its
        lines painted apart), else this text's own.
        """
        if self.moving_text is None and self.moving_outline is None:
            return text
        units, gaps = segments(text)
        if end is None:
            end = self._budget(len(units), e - s, 0, self.moving_text, self.moving_outline)

        def tags(_: int, letter: int) -> str:
            ink = self._chain(self.moving_text, "1c", letter, letters, s, end)
            return ink + self._chain(self.moving_outline, "3c", letter, letters, s, end)

        return _per_letter(units, gaps, first, tags)

    def text_budget(self, units: int, dur: int) -> int | None:
        """An event's budget for the text in it, ``units`` letters ``dur`` ms; none, unmoving."""
        if self.moving_text is None and self.moving_outline is None:
            return None
        return self._budget(units, dur, 0, self.moving_text, self.moving_outline)

    def _fade(self, ms: int, lit: Colour, start: Colour) -> str:
        r"""The text's colours, from ``start``, to ``lit`` over ``ms``; at once under 1.

        Its outline too, to the highlight's own (``outline_for``: a motion's one, whatever hue a
        letter starts on), written only where it differs. A ``\t`` ending at 0 runs to the
        event's end (ass_parse.c: ``t2 == 0`` is its duration), so none is written.
        """
        begin, end = f"\\1c{start.ass()}", f"\\1c{lit.ass()}"
        base, own = self.outline, self.lit_outline
        if isinstance(base, Colour) and isinstance(own, Colour) and own != base:
            begin += f"\\3c{base.ass()}"
            end += f"\\3c{own.ass()}"
        return f"{begin}\\t(0,{ms},{end})" if ms >= 1 else end

    @staticmethod
    def _chain(  # noqa: PLR0913 -- the motion, its tag, the letter among its letters, and when
        motion: Motion | None, tag: str, letter: int, letters: int, s: int, end: int
    ) -> str:
        """A letter's ``tag`` (1c, 3c) through ``motion``, from its event's ``s`` to ``end``."""
        if motion is None:
            return ""
        frames = keyframes(motion, letter, letters, 0, end, start=s)
        return f"\\{tag}{frames[0][1].ass()}{_steps(frames, tag)}"

    def _budget(self, units: int, dur: int, fade: int, *motions: Highlight | None) -> int:
        """Where the chains end: ``dur``, or, over ``MOTION_BUDGET`` keyframes, ``fade``.

        Over it, each letter keeps its first colour, still; the run is counted, and noted.
        """
        periods = [m.period for m in motions if isinstance(m, Motion)]
        if units * sum((dur - fade) * 6 // period + 2 for period in periods) > MOTION_BUDGET:
            self.held += 1
            return fade
        return dur


def _per_letter(
    units: list[str], gaps: list[str], first: int, tags: Callable[[int, int], str]
) -> str:
    """Each unit after its gap, in a block of its own: ``tags(k, first + k)``."""
    pairs = enumerate(zip(units, gaps, strict=True))
    return "".join(f"{gap}{{{tags(k, first + k)}}}{unit}" for k, (unit, gap) in pairs)


def _steps(frames: list[tuple[int, Colour]], tag: str) -> str:
    r"""A ``tag`` (1c, 3c) through ``frames``: a ``\t`` from each keyframe to the next."""
    return "".join(f"\\t({a},{b},\\{tag}{c.ass()})" for (a, _), (b, c) in pairwise(frames))
