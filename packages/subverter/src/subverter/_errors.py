"""The one way subverter refuses: a subverter.Error, its message the reason."""

from typing import Never


class Error(Exception):
    """subverter's refusal: the input cannot be read as it stands; the message says why."""


def refuse(message: str) -> Never:
    """Refuse with ``message``."""
    raise Error(message)
