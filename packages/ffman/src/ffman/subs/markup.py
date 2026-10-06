"""A transcript's markup: what its tags, override blocks and escapes leave of its text."""

import re
from typing import Final

from subverter.markup import untagged

_OVERRIDE: Final = re.compile(r"\{\\[^}]*\}")  # {\an8}: ASS override blocks, as some SRTs carry
_BREAK: Final = re.compile(r"\\[tn]|[\t\n\r]")  # a tab or a line break, escaped (\t, \n) or not
_BLANKS: Final = re.compile(r"[ \t]+")


def clean(text: str) -> str:
    """Bash's CLEAN_AWK: breaks to spaces, tags and overrides off, blanks squeezed, trimmed."""
    text = _OVERRIDE.sub("", untagged(_BREAK.sub(" ", text)))
    return _BLANKS.sub(" ", text).removeprefix(" ").removesuffix(" ")
