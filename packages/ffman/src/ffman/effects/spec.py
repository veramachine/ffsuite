"""What an effect is: its stage, parameters and checks; a request, and its values."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import IntEnum
from fractions import Fraction

from ffman.values import is_num, is_uint


class Stage(IntEnum):
    """When an effect runs: the order footage came to be (subtitles sit after TAPE)."""

    PICTURE = 1
    LENS = 2  # lens and film
    MOSH = 3  # its own codec pass, after the lens and film
    CAMCORDER = 4
    TAPE = 5
    DISPLAY = 6


@dataclass(frozen=True, slots=True)
class Param:
    """One parameter: its check, the refusal's text, and what leaving it out means."""

    name: str
    check: Callable[[str], bool]
    must: str  # "must be ..." -- the refusal, without the flag
    unset: str  # what leaving it out means, for the catalogue
    auto: bool = True  # whether "auto" is a value


@dataclass(frozen=True, slots=True)
class Effect:
    """A video effect: its stage, its parameters (the first is the main one), its line."""

    name: str
    stage: Stage
    about: str
    params: tuple[Param, ...] = ()
    positional: bool = True  # whether the main parameter may be given without its key


@dataclass(frozen=True, slots=True)
class Request:
    """An effect as asked: the values given (absent ones are auto, or the default)."""

    effect: Effect
    values: Mapping[str, str]


def between(
    low: Fraction, high: Fraction, *, integer: bool, low_open: bool = False
) -> Callable[[str], bool]:
    """A value's check: a number (an integer if ``integer``) from ``low`` to ``high``."""

    def check(text: str) -> bool:
        if not (is_uint(text) if integer else is_num(text)):
            return False
        value = Fraction(text)
        return (low < value if low_open else low <= value) and value <= high

    return check


def asked(request: Request, key: str) -> str | None:
    """The value given, None when auto."""
    value = request.values.get(key)
    return None if value in (None, "auto") else value
