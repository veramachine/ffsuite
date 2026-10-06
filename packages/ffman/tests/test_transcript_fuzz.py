"""fuzz.py, in Hypothesis: transcripts through ingest and the ASS renderer, against its invariants.

The generators are fuzz.py's -- hostile WhisperX and whisper-cli JSON (garbage
timing: overlaps, zero lengths, words outside their sentence, ties, untimed,
shuffled; nasty words), and plausible WhisperX -- drawn instead of random. A
refusal must be ffman's own (FfmanError); anything else raised is a crash.
"""

import itertools
import json
import re
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Final

from hypothesis import given, settings
from hypothesis import strategies as st
from subverter.transcript import Transcript

from ffman.errors import FfmanError
from ffman.subs.ass import Style, script
from tests.support.ingesting import ingested
from tests.support.subtitles import POS

NASTY: Final = ["hi", "5-Minute", "{\\b1}x", "a\\Nb", "tab\there", "new\nline", "<i>it</i>", "ção", "日本", "}", "{", "\\", "  ", "--> x", "'quote'", '"dq"', "%d", "$(x)", "a,b", "ok."]  # fmt: skip
PLAIN: Final = ["alpha", "be", "c", "delta", "echo", "fox", "g"]
WORD: Final = st.one_of(st.sampled_from(NASTY), st.sampled_from(PLAIN))
FRAMES: Final = [(1920, 1080), (1080, 1920), (640, 360), (300, 1000), (4096, 2160)]
MODES: Final = ["plain", "chunk-word", "word", "word-highlight"]
CS: Final = 10  # ASS's resolution: a span under 10 ms cannot be shown
type Doc = dict[str, object]


@st.composite
def hostile_whisperx(draw: st.DrawFn) -> Doc:
    """fuzz.py's gen_whisperx: sentences that overlap, go back, have no length; words anywhere."""
    segments: list[Doc] = []
    t = draw(st.integers(0, 3000))
    for _ in range(draw(st.integers(1, 7))):
        a = t + draw(st.integers(-800, 1500))
        b = a + draw(st.sampled_from([0, 1, 5, 300, 2000, 6000]))
        words: list[Doc] = []
        for k in range(draw(st.integers(0, 8))):
            w: Doc = {"word": draw(WORD)}
            last = words[-1].get("start") if words else None
            starts = {
                "sane": a + int((b - a) * k / 9),
                "before": a - draw(st.integers(1, 500)),
                "after": b + draw(st.integers(0, 900)),
                "tie": int(float(str(last)) * 1000) if last is not None else a,
                "untimed": None,
            }
            s = starts[draw(st.sampled_from(list(starts)))]
            if s is not None:
                w["start"], w["end"] = s / 1000, (s + draw(st.integers(0, 400))) / 1000
            if draw(st.integers(0, 19)) == 0:
                del w["word"]
            words.append(w)
        joined = " ".join(str(x.get("word", "")) for x in words)
        text = (
            joined
            if words and draw(st.integers(0, 9))
            else draw(st.sampled_from(["", " ", *PLAIN]))
        )
        segment: Doc = {"start": a / 1000, "end": b / 1000, "text": " " + text, "words": words}
        if draw(st.integers(0, 19)) == 0:
            del segment["text"]  # a missing text must never become the subtitle "null"
        segments.append(segment)
        t = b
    return {
        "segments": draw(st.permutations(segments)) if draw(st.integers(0, 4)) == 0 else segments,
        "language": "en",
    }


@st.composite
def hostile_whisper_cli(draw: st.DrawFn) -> Doc:
    """fuzz.py's gen_whisper_cli: tokens with DTW times inside, before, after, or none."""
    entries: list[Doc] = []
    t = draw(st.integers(0, 3000))
    for _ in range(draw(st.integers(1, 6))):
        a = t + draw(st.integers(-500, 1500))
        b = a + draw(st.sampled_from([0, 10, 400, 3000]))
        tokens: list[Doc] = [{"text": "[_BEG_]", "offsets": {"from": a, "to": a}, "t_dtw": -1}]
        o = a
        for k in range(draw(st.integers(0, 7))):
            text = (" " if draw(st.integers(0, 4)) else "") + draw(WORD)
            o2 = o + draw(st.sampled_from([0, 10, 200, -50]))
            dtw = draw(
                st.sampled_from(
                    [-1, o2 // 10, (b + 500) // 10, (a - 300) // 10, (o2 // 10) if k else -1]
                )
            )
            tokens.append(
                {
                    "text": text,
                    "offsets": {"from": o2, "to": o2 + draw(st.integers(0, 300))},
                    "t_dtw": dtw,
                }
            )
            o = o2
        tokens.append({"text": "[_TT_1]", "offsets": {"from": b, "to": b}, "t_dtw": -1})
        text = "".join(str(x["text"]) for x in tokens if not str(x["text"]).startswith("[_"))
        entries.append({"offsets": {"from": a, "to": b}, "text": text, "tokens": tokens})
        t = b
    return {"transcription": entries}


@st.composite
def plausible_whisperx(draw: st.DrawFn) -> Doc:
    """fuzz.py's gen_real: ordered, sentences of 300 ms and more, words 60 ms apart and more, some untimed or tied."""
    segments: list[Doc] = []
    t = draw(st.integers(0, 3000))
    for _ in range(draw(st.integers(1, 8))):
        n = draw(st.integers(1, 9))
        a = t + draw(st.integers(0, 800))
        step = draw(st.integers(60, 500))
        b = a + step * n + draw(st.integers(50, 600))
        words: list[Doc] = []
        for k in range(n):
            w: Doc = {"word": draw(WORD)}
            s = a + step * k
            kind = draw(st.sampled_from(["timed"] * 8 + ["tied", "untimed"]))
            if kind == "timed":
                w["start"], w["end"] = s / 1000, (s + step - 20) / 1000
            elif kind == "tied" and words and "start" in words[-1]:
                w["start"], w["end"] = words[-1]["start"], words[-1]["end"]
            words.append(w)
        text = " " + " ".join(str(x["word"]) for x in words)
        segments.append({"start": a / 1000, "end": b / 1000, "text": text, "words": words})
        t = b
    return {"segments": segments, "language": "en"}


class Malformed(Exception):  # noqa: N818 -- fuzz.py's name
    pass


def _ms(t: str) -> int:
    if not re.fullmatch(r"\d+:\d\d:\d\d\.\d\d", t):
        raise Malformed(t)
    h, m, s = t.split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def broken(t: Transcript, text: str, mode: str) -> list[str]:  # noqa: C901, PLR0912, PLR0915 -- fuzz.py's check, rule for rule
    """fuzz.py's check: every invariant the renderer holds, and which are broken."""
    errs: list[str] = []
    win = [(c.start, c.end) for c in t.chunks]
    if any(b <= a for a, b in win):
        errs.append("empty chunk window")
    if any(w2[0] < w1[1] for w1, w2 in itertools.pairwise(win)):
        errs.append("chunk windows overlap")
    events: list[tuple[int, int, int, str]] = []
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            f = line.split(",", 9)
            try:
                events.append((int(f[0][-1]), _ms(f[1]), _ms(f[2]), f[9]))
            except Malformed as m:
                return [f"malformed ASS time {m}"]
    if any(e <= s for _, s, e, _ in events):
        errs.append("zero-length event")

    def owner(s: int, e: int) -> int | None:
        return next((k for k, (a, b) in enumerate(win) if a - 5 <= s and e <= b + 5), None)

    own = [owner(s, e) for _, s, e, _ in events]
    if None in own and mode not in ("word", "word-highlight"):  # word modes bridge gaps on purpose
        errs.append(f"{own.count(None)} events outside every chunk window")
    overlapping = (
        own[i] is not None
        and own[j] is not None
        and own[i] != own[j]
        and events[j][1] < events[i][2]
        and events[i][1] < events[j][2]
        for i in range(len(events))
        for j in range(i + 1, len(events))
    )
    if any(overlapping):
        errs.append("two sentences on screen together")  # I1
    by_segment: dict[str, list[tuple[int, int]]] = {}
    for w in t.words:
        by_segment.setdefault(w.segment, []).append((w.start, w.end))
    window = {c.segment: (c.start, c.end) for c in t.chunks}
    for k, ws in by_segment.items():
        a, b = window.get(k, (0, 0))
        roomy = (b - a) >= CS * (len(ws) + 1)  # room for every word at ASS resolution
        if roomy and any(y[0] <= x[0] for x, y in itertools.pairwise(ws)):
            errs.append(f"sentence {k}: words not strictly increasing despite room")
        if roomy and any(e - s < 1 for s, e in ws):
            errs.append(f"sentence {k}: zero-length word despite room")
    if mode == "chunk-word":
        tops = sum(1 for layer, *_ in events if layer == 1)
        spans: list[int] = []  # a word's showable span: the next start, less its start
        for k, ws in by_segment.items():
            z = window.get(k, (0, 0))[1]
            spans += [(ws[i + 1][0] if i + 1 < len(ws) else z) - s for i, (s, _) in enumerate(ws)]
        need = sum(1 for d in spans if d >= CS + 5)
        if tops < need:
            errs.append(f"highlighted {tops}, but {need} words have a showable span")
        unseen = [k for k, (a, b) in enumerate(win) if b - a >= CS + 5 and k not in own]
        if unseen:
            errs.append(f"sentence {unseen[0]} never shown")
    if mode in ("word", "word-highlight"):
        items = [w.end - w.start for w in t.words] + [
            c.end - c.start for c in t.chunks if not by_segment.get(c.segment)
        ]
        need = sum(1 for d in items if d >= CS + 5)
        if len(events) < need:
            errs.append(f"word mode: {len(events)} events, but {need} items have a showable span")
        spans_on = sorted((s, e) for _, s, e, _ in events)
        if any(y[0] < x[1] for x, y in itertools.pairwise(spans_on)):
            errs.append("word mode: events overlap")
    if mode == "plain" and len(events) < sum(1 for a, b in win if b - a >= CS + 5):
        errs.append(f"plain: {len(events)} events for {len(t.chunks)} sentences")
    style = re.search(r"^Style: Default,[^,]*,([0-9.]+),", text, re.MULTILINE)
    size = float(style[1]) if style else 0.0
    for (
        *_,
        body,
    ) in events:  # no line box below the frame: its centre and half a line of 1.25 x size
        at = POS.search(body)
        if at and float(at[2]) + size * 1.25 / 2 > 1080 + 1:
            errs.append("a line below the frame")
            break
    if any(re.search(r"(^|})null($|{)", body) for *_, body in events):
        errs.append("a missing text rendered as the word null")
    for *_, body in events:  # the text must not smuggle ASS syntax
        bare = re.sub(r"\{[^}]*\}", "", body)
        if "{" in bare or "}" in bare or "\\" in bare.replace("\\N", ""):
            errs.append(f"unescaped ASS syntax in {body[:60]!r}")
            break
    return errs


def through(doc: Doc, mode: str, frame: tuple[int, int], size: int, bar: str | None) -> list[str]:
    """Ingest the document, render it in ``mode``: the invariants it breaks (a refusal breaks none)."""
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "t.json"
        _ = path.write_text(json.dumps(doc))
        try:
            t = ingested(str(path))
        except FfmanError:
            return []  # a clean refusal: fuzz.py's "refused"
    style = Style(mode, "pop", Fraction(size), bar_y=None if bar is None else Fraction(bar))
    return broken(t, script(t, *frame, style)[0], mode)


SETTINGS: Final = settings(max_examples=150, deadline=None)
LOOKS: Final = (
    st.sampled_from(MODES),
    st.sampled_from(FRAMES),
    st.sampled_from([8, 64, 200, 1000]),
    st.sampled_from([None, "1000", "900", "1060"]),
)


@SETTINGS
@given(st.one_of(hostile_whisperx(), hostile_whisper_cli()), *LOOKS)
def test_hostile_timing_breaks_no_invariant(
    doc: Doc, mode: str, frame: tuple[int, int], size: int, bar: str | None
) -> None:  # S158
    assert through(doc, mode, frame, size, bar) == []


@SETTINGS
@given(plausible_whisperx(), *LOOKS)
def test_plausible_whisperx_breaks_no_invariant(
    doc: Doc, mode: str, frame: tuple[int, int], size: int, bar: str | None
) -> None:  # S159
    assert through(doc, mode, frame, size, bar) == []
