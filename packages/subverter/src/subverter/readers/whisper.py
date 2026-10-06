"""whisper-cli's and WhisperX's JSON: chunks and word timings, their values as they are typed.

A time is a number (fields.number: a JSON number, or a decimal string); any other value
is no time. A text is the JSON string, or a non-string written as JSON (jq's tostring).
"""

import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Final, cast

from subverter._errors import refuse
from subverter.readers.fields import json_number, ms, number, time_ms
from subverter.transcript import Cue, Reading, Timing

__all__ = ["read"]


def read(data: bytes, name: str) -> Reading:
    """A whisper JSON's source name, word timings or not, its cues, its words, its notes."""
    try:
        root = cast("object", json.loads(data, parse_float=json_number))  # exact, bounded
    except ValueError:
        refuse(f"not valid JSON: {name}")
    except RecursionError:  # past Python's recursion limit: no transcript nests so
        refuse(f"JSON nested too deeply to be a transcript: {name}")
    doc = _obj(root)
    if isinstance(doc.get("transcription"), list):
        return _whisper_cli(doc, name)
    if not isinstance(doc.get("segments"), list):
        kinds = "a whisper-cli (.transcription) or WhisperX (.segments) JSON transcript"
        refuse(f"not {kinds}: {name}")
    cues, words = _whisperx(doc)
    return Reading("WhisperX JSON", has_words=bool(words), cues=cues, words=words)


def _obj(value: object) -> dict[str, object]:
    """``value`` if an object, else an empty one: a missing key and a wrong type alike."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _text(value: object) -> str:
    """``.text // "" | tostring``: a string as is, null or false nothing, else its JSON."""
    if value is None or value is False:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=float)


# whisper-cli: .transcription[] -- offsets in ms; with -ojf, its tokens (and their DTW times)

# the languages written without spaces between words: every token a word
_NO_SPACES: Final = frozenset({"zh", "yue", "ja", "th", "lo", "km", "my"})


def _whisper_cli(doc: dict[str, object], name: str) -> Reading:
    entries = _list(doc["transcription"])
    found: list[Cue] = []
    for key, entry in enumerate(entries):
        e = _obj(entry)
        offsets = _obj(e.get("offsets"))
        found.append(
            Cue(
                time_ms(offsets.get("from"), 1),
                time_ms(offsets.get("to"), 1),
                _text(e.get("text")),
                str(key),
            )
        )
    cues = tuple(found)
    if not any(isinstance(e, dict) and "tokens" in e for e in entries):
        return Reading("whisper-cli JSON", has_words=False, cues=cues)
    language = _text(_obj(doc.get("result")).get("language"))
    words, fallback, timed = _tokens(entries, no_spaces=language in _NO_SPACES, name=name)
    notes: tuple[str, ...] = ()
    if fallback:
        where = f"outside their sentence or not in order in {fallback} of {timed} sentences"
        notes = (f"DTW word times were {where}: used token offsets there",)
    return Reading("whisper-cli -ojf JSON", has_words=True, cues=cues, words=words, notes=notes)


def _tokens(
    entries: list[object], *, no_spaces: bool, name: str
) -> tuple[tuple[Timing, ...], int, int]:
    """Words from tokens, timed by DTW where its times sit in order inside their sentence."""
    words: list[Timing] = []
    fallback: set[int] = set()
    timed: set[int] = set()
    for key, entry in enumerate(entries):
        e = _obj(entry)
        offsets = _obj(e.get("offsets"))
        a, z = time_ms(offsets.get("from"), 1), time_ms(offsets.get("to"), 1)
        ws = _token_words(e.get("tokens"), no_spaces=no_spaces, name=name)
        # t_dtw: in 10 ms units
        dtws = [ms(w.dtw, 10) if w.dtw is not None and w.dtw >= 0 else None for w in ws]
        has = bool(dtws) and all(t is not None for t in dtws)
        times = [t for t in dtws if t is not None] if has else []
        inside = has and a is not None and z is not None and all(a <= t < z for t in times)
        dtw_ok = inside and all(times[i] > times[i - 1] for i in range(1, len(times)))
        for k, w in enumerate(ws):
            if dtw_ok:
                words.append(
                    Timing(str(key), times[k], times[k + 1] if k + 1 < len(ws) else z, w.text)
                )
            else:
                words.append(Timing(str(key), w.start, w.end, w.text))
        if ws and has:
            timed.add(key)
            if not dtw_ok:
                fallback.add(key)
    return tuple(words), len(fallback), len(timed)


@dataclass(slots=True)
class _Word:
    """A word gathered from its tokens: its text, its token offsets, its first token's DTW time."""

    text: str
    start: int | None
    end: int | None
    dtw: Fraction | None


def _token_words(tokens: object, *, no_spaces: bool, name: str) -> list[_Word]:
    """A sentence's words from its tokens: a leading space starts one ([_...] tokens dropped)."""
    ws: list[_Word] = []
    for token in _list(tokens):
        if not isinstance(token, dict):
            continue
        t = cast("dict[str, object]", token)
        text = t.get("text")
        if _text(text).startswith("[_"):
            continue
        if not isinstance(text, str):  # malformed: bash's jq stopped here, "unreadable"
            refuse(f"unreadable whisper-cli -ojf JSON: {name}")
        span = _obj(t.get("offsets"))
        if not ws or text.startswith(" ") or no_spaces:
            dtw = t.get("t_dtw")
            ws.append(
                _Word(
                    text,
                    time_ms(span.get("from"), 1),
                    time_ms(span.get("to"), 1),
                    number(dtw),
                )
            )
        else:
            ws[-1].text += text
            ws[-1].end = time_ms(span.get("to"), 1)
    return ws


# WhisperX: .segments[] -- seconds; their words, each its own


def _whisperx(doc: dict[str, object]) -> tuple[tuple[Cue, ...], tuple[Timing, ...]]:
    cues: list[Cue] = []
    words: list[Timing] = []
    for key, segment in enumerate(_list(doc["segments"])):
        s = _obj(segment)
        cues.append(
            Cue(
                time_ms(s.get("start"), 1000),
                time_ms(s.get("end"), 1000),
                _text(s.get("text")),
                str(key),
            )
        )
        for word in _list(s.get("words")):
            if isinstance(word, dict):
                w = cast("dict[str, object]", word)
                words.append(
                    Timing(
                        str(key),
                        time_ms(w.get("start"), 1000),
                        time_ms(w.get("end"), 1000),
                        _text(w.get("word")),
                    )
                )
    return tuple(cues), tuple(words)
