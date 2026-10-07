"""The normalisers: cues to chunks, ordered and clamped; words placed in their chunk.

They read what the readers found, typed (a time not read is None). One
difference from bash, a correction: a word's share of a gap is by
characters, as bash's gawk gave it under a UTF-8 locale; under C it counted
bytes (docs/ffman-from-bash.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Final

from subverter.transcript import Chunk, Cue, Timing, Word

from ffman.subs.markup import clean


def cues(raw: Sequence[Cue]) -> tuple[Chunk, ...]:
    """Cues to chunks: ordered by start (stably, before clamping), cleaned, clamped at 0.

    The untimed, the empty and the reversed are dropped; each ends where the next starts.
    """
    timed = [(c.start, c.end, c) for c in raw if c.start is not None and c.end is not None]
    kept: list[tuple[int, int, str, str]] = []
    for start, end, cue in sorted(timed, key=lambda t: t[0]):
        text = clean(cue.text)
        if text:
            a, b = max(start, 0), max(end, 0)
            if b > a:
                kept.append((a, b, text, cue.segment))
    chunks: list[Chunk] = []
    for i, (a, b, text, segment) in enumerate(kept):
        end = min(b, kept[i + 1][0]) if i + 1 < len(kept) else b
        if end > a:
            chunks.append(Chunk(a, end, text, segment))
    return tuple(chunks)


def words(chunks: tuple[Chunk, ...], raw: Sequence[Timing]) -> tuple[tuple[Word, ...], int, int]:
    """The words placed in their sentences (_place); how many placed, how many sentences bare."""
    window = {c.segment: (c.start, c.end) for c in chunks if c.segment != ""}
    kept = [
        Timing(t.segment, t.start, t.end, text)
        for t in raw
        if (text := clean(t.text)) and t.segment in window
    ]
    out: list[Word] = []
    placed = bare = 0
    for segment, run in groupby(kept, key=lambda t: t.segment):
        sentence = list(run)
        spans = _place(sentence, *window[segment])
        if spans is None:
            bare += 1
            continue
        placed += spans.placed
        out += [
            Word(segment, a, z, t.text) for t, (a, z) in zip(sentence, spans.times, strict=True)
        ]
    return tuple(out), placed, bare


@dataclass(frozen=True, slots=True)
class _Spans:
    """A sentence's words placed: each one's (start, end) in ms; how many had no usable time."""

    times: list[tuple[int, int]]
    placed: int


_STEP: Final = 10  # ms: one ASS step, the least a shared word is given (when there is room)


def _place(run: list[Timing], lo: int, hi: int) -> _Spans | None:
    """One sentence's words in its window [lo, hi): the rules bash's place() kept.

    1. A start before ``lo`` counts from ``lo``; one at or past ``hi`` is no start.
    2. An anchor: a word with a start after the last anchor's -- a time to trust.
       No anchor: the sentence is bare (None); else every other word is placed.
    3. Words before the first anchor share [lo, its start); if it starts at
       ``lo``, they join its group.
    4. A group -- an anchor, and the words up to the next -- runs to the next
       anchor's start (else ``hi``). A word starting with its anchor ties it.
       Its own group, untied, with followers, its end inside: the anchor keeps
       its end, the followers share the rest; else the group shares it all.
    5. Shared: each word ``_STEP`` (less where there is no room), the rest by
       characters (_share).
    6. A word ends where the next starts (the last at ``hi``); an untied
       anchor keeps its own end, if it falls in (its start, that].
    """
    starts = [_within(t.start, lo, hi) for t in run]
    at = _anchors(starts)  # each anchor's index, its start
    if not at:
        return None
    texts = [t.text for t in run]
    anchors = list(at)
    begins: list[int] = [0] * len(run)
    tied: set[int] = set()
    group, group_start = anchors[0], at[anchors[0]]
    if group > 0:
        if group_start > lo:
            begins[:group] = _share(texts[:group], lo, group_start)
        else:
            group, group_start = 0, lo
    for k, m in zip(anchors, [*anchors[1:], len(run)], strict=True):
        stop = at[m] if m < len(run) else hi
        if any(starts[r] == at[k] for r in range(k + 1, m)):
            tied.add(k)
        own = run[k].end
        alone = group == k and m > k + 1 and k not in tied
        if alone and own is not None and group_start < own < stop:
            begins[k] = group_start
            begins[k + 1 : m] = _share(texts[k + 1 : m], own, stop)
        else:
            begins[group:m] = _share(texts[group:m], group_start, stop)
        group, group_start = m, stop
    times: list[tuple[int, int]] = []
    for k, t in enumerate(run):
        nxt = begins[k + 1] if k + 1 < len(run) else hi
        end = t.end
        if end is not None and k in at and k not in tied and begins[k] < end <= nxt:
            times.append((begins[k], end))
        else:
            times.append((begins[k], nxt))
    return _Spans(times, len(run) - len(at))


def _within(start: int | None, lo: int, hi: int) -> int | None:
    """Rule 1: a start before the window counts from its start; one at or past its end is none."""
    if start is None:
        return None
    start = max(start, lo)
    return start if start < hi else None


def _anchors(starts: list[int | None]) -> dict[int, int]:
    """Rule 2: the words whose start comes after the last anchor's, in order: index, start."""
    found: dict[int, int] = {}
    last = -1  # below any start: starts are at least the window's, and windows at least 0
    for k, start in enumerate(starts):
        if start is not None and start > last:
            found[k] = last = start
    return found


def _share(texts: list[str], start: int, stop: int) -> list[int]:
    """Rule 5: the words' starts across [start, stop).

    Each word ``_STEP`` first (less where there is no room), the rest by characters.
    """
    count, total = len(texts), sum(len(t) for t in texts)
    base = min(max((stop - start) // count, 0), _STEP)
    rest = (stop - start) - base * count
    starts: list[int] = []
    done = 0  # characters before this word
    for i, text in enumerate(texts):
        # rest * done / total, rounded half up: in integers, exactly
        starts.append(start + base * i + (2 * rest * done + total) // (2 * total))
        done += len(text)
    return starts
