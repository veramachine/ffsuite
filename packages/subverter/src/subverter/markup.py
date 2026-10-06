"""A transcript's markup: its tags, which a reader reads its words without."""

import re
from typing import Final

__all__ = ["untagged"]

_TAG: Final = re.compile(r"<[^>]*>")  # <u>, <i>, <font ...>: SubRip's and WebVTT's


def untagged(text: str) -> str:
    """``text`` without its tags."""
    return _TAG.sub("", text)
