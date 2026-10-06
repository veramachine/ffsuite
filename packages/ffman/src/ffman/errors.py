"""The one way ffman refuses or fails."""

from typing import Final, Never

import ffmeta
import subverter

PROG: Final = "ffman"  # the program's name, in its messages
_SHOWN: Final = 60  # input quoted in a message: its characters, at most
_ESCAPED: Final = {"\r": "\\r", "\n": "\\n", "\t": "\\t"}


class FfmanError(Exception):
    """A refusal or a failure: reported as ``ffman: error: MESSAGE``, exit status 1."""


# every refusal ffman words as its own: its own, and its libraries' (6.7.5: each refuses with its
# own error; ffman's words for them unchanged)
REFUSALS: Final = (FfmanError, ffmeta.Error, subverter.Error)


def refuse(message: str) -> Never:
    """Refuse with ``message`` (the spec's words)."""
    raise FfmanError(message)


def shown(text: str) -> str:
    r"""Input quoted in a message: on one line, each character visible, 60 characters at most.

    A line break or tab as its escape; any other character that prints nothing (a NUL, a BOM, a
    no-break space) as Python writes it, ``\x00``, ``\ufeff``.
    """
    one = "".join(
        _ESCAPED.get(char, char if char.isprintable() else repr(char)[1:-1]) for char in text
    )
    return one if len(one) <= _SHOWN else one[: _SHOWN - 3] + "..."


def refuse_at(source: str, line: int, message: str) -> Never:
    """Refuse at ``source``'s ``line``: ``SOURCE:LINE: message``, lines from 1.

    The GNU Coding Standards' form for a program reading a file (4.4, "Formatting Error
    Messages"), after ffman's own ``ffman: error:``.
    """
    if line < 1:
        msg = f"lines count from 1, not {line}"
        raise ValueError(msg)
    refuse(f"{source}:{line}: {message}")
