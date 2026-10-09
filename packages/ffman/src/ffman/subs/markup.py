"""A transcript's markup: what its tags, override blocks and escapes leave of its text."""

import re
from typing import Final

from subverter.markup import decoded, untagged

_OVERRIDE: Final = re.compile(r"\{\\[^}]*\}")  # {\an8}: ASS override blocks, as some SRTs carry
_BREAK: Final = re.compile(r"\\[tn]|[\t\n\r]")  # a tab or a line break, escaped (\t, \n) or not
_DECODED_BREAK: Final = re.compile(r"[\t\n\f\r]")  # decoded (&#10;, &#12;) or a .vtt's own FF
_BLANKS: Final = re.compile(r"[ \t]+")
_TAG_MARK: Final = "\uffff"  # where a tag was: a noncharacter (a transcript's own, dropped)
_MARKED_OVERRIDE: Final = re.compile(r"\{\uffff*\\[^}]*\}")  # _OVERRIDE, _TAG_MARKs in it


def clean(text: str, *, references: bool) -> str:
    """Bash's CLEAN_AWK: breaks to spaces, tags and overrides off, blanks squeezed, trimmed.

    ``references`` (WebVTT's): each run between tags decoded, once the overrides are off --
    a decoded ``<`` or ``{`` text, a decoded break a space.
    """
    text = _BREAK.sub(" ", text)
    if references:
        runs = _MARKED_OVERRIDE.sub("", untagged(text, into=_TAG_MARK)).split(_TAG_MARK)
        text = _DECODED_BREAK.sub(" ", "".join(decoded(run) for run in runs))
    else:
        text = _OVERRIDE.sub("", untagged(text))
    return _BLANKS.sub(" ", text).removeprefix(" ").removesuffix(" ")
