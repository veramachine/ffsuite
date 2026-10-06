"""The one way ffmeta refuses: an ffmeta.Error, its message the reason; input shown safe."""

from typing import Final, Never

_SHOWN: Final = 60  # input quoted in a message: its characters, at most
_ESCAPED: Final = {"\r": "\\r", "\n": "\\n", "\t": "\\t"}


class Error(Exception):
    """ffmeta's refusal: the input cannot be read, converted or written as it stands.

    The message says why.
    """


def refuse(message: str) -> Never:
    """Refuse with ``message``."""
    raise Error(message)


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
    Messages").
    """
    if line < 1:
        msg = f"lines count from 1, not {line}"
        raise ValueError(msg)
    refuse(f"{source}:{line}: {message}")
