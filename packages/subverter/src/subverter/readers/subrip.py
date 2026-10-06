"""SubRip and WebVTT: cues; WhisperX's highlighted cues, read back into words."""

import re
from fractions import Fraction
from typing import Final

from subverter.markup import untagged
from subverter.readers.fields import ms, prefix
from subverter.transcript import Cue, Timing

__all__ = ["highlighted", "is_highlighted", "rows"]

_ARROW: Final = re.compile(r"[ \t]*-->[ \t]*")  # a cue's times, either side
_BLANKS: Final = re.compile(r"[ \t]")  # after the end time: its settings (WebVTT)
_BLANK_LINE: Final = re.compile(r"[ \t]*")  # a cue's end
_UNDERLINE: Final = re.compile(r"<u>([^<]*)</u>")  # WhisperX --highlight_words: the word


def _time(text: str) -> int | None:
    """subs_srt_vtt's ms(): HH:MM:SS,mmm or MM:SS.mmm, each part as awk read it, exactly."""
    parts = text.replace(",", ".").split(":")
    if len(parts) == 3:  # noqa: PLR2004 -- hours, minutes, seconds
        h, m, s = (prefix(p) for p in parts)
    else:
        h, m, s = Fraction(0), prefix(parts[0]), prefix(parts[1] if len(parts) > 1 else "")
    if h is None or m is None or s is None:  # a part past a double's range: no time
        return None
    return ms(h * 3600 + m * 60 + s, 1000)


def rows(lines: list[str]) -> list[Cue]:
    """Cues, their text kept with its tags (a WhisperX <u> marks a word).

    A cue opens at its "-->" line and closes at a blank line, or at the next cue
    (bash's intext and its set st, which always changed together).
    """
    found: list[Cue] = []
    cue: tuple[int | None, int | None] | None = None
    text = ""
    for line in lines:
        if "-->" in line:
            if cue is not None:
                found.append(Cue(*cue, text))
            left, right = _ARROW.split(line, maxsplit=1)
            cue, text = (_time(left), _time(_BLANKS.split(right)[0])), ""
        elif cue is not None and _BLANK_LINE.fullmatch(line):
            found.append(Cue(*cue, text))
            cue, text = None, ""
        elif cue is not None:
            text = f"{text} {line}" if text else line
    if cue is not None:
        found.append(Cue(*cue, text))
    return found


def is_highlighted(cues: list[Cue]) -> bool:
    """WhisperX --highlight_words, by structure: <u> somewhere, most neighbours one text."""
    plains = [untagged(c.text) for c in cues]
    underlined = any("<u>" in c.text for c in cues)
    same = sum(1 for i in range(1, len(plains)) if plains[i] == plains[i - 1])
    return underlined and len(cues) > 1 and same / (len(cues) - 1) >= 0.5  # noqa: PLR2004 -- most


def highlighted(cues: list[Cue]) -> tuple[list[Cue], list[Timing]]:
    """One sentence a run of one text (new when the underline moves back); each <u> a word."""
    sentences: list[Cue] = []
    words: list[Timing] = []
    current, cs, ce, last, sid = "", None, None, -1, -1
    for cue in cues:
        plain = untagged(cue.text)
        underline = _UNDERLINE.search(cue.text)
        offset = len(untagged(cue.text[: underline.start()])) if underline else -1
        if plain != current or (underline and offset <= last):
            if current:
                sentences.append(Cue(cs, ce, current, str(sid)))
            sid, current, cs, last = sid + 1, plain, cue.start, -1
        ce = cue.end
        if underline:
            words.append(Timing(str(sid), cue.start, cue.end, underline[1]))
            last = offset
    if current:
        sentences.append(Cue(cs, ce, current, str(sid)))
    return sentences, words
