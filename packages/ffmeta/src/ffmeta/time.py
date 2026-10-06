"""A time as ``meta`` takes one (spec 8): exact, in one of four forms, never ambiguous.

``SECONDS``, ``M:SS`` or ``H:MM:SS`` -- each with an optional ``.FRACTION`` -- or ``FRAMESf``
(1/75 s, a cue's). Not ``MM:SS:FF``: it would read as ``H:MM:SS``. Every run of digits is
bounded (seconds to 31 years, a fraction to nanoseconds), so no text costs unbounded work.
"""

import re
from fractions import Fraction
from typing import Final

from ffmeta._errors import refuse, shown
from ffmeta.model import FRAMES

__all__ = ["parse"]

_FRACTION: Final = r"(?:\.([0-9]{1,9}))?"
_SECONDS: Final = re.compile(rf"([0-9]{{1,9}}){_FRACTION}", re.ASCII)
_MINUTES: Final = re.compile(rf"([0-9]{{1,7}}):([0-5][0-9]){_FRACTION}", re.ASCII)
_HOURS: Final = re.compile(rf"([0-9]{{1,5}}):([0-5][0-9]):([0-5][0-9]){_FRACTION}", re.ASCII)
_FRAMES: Final = re.compile(r"([0-9]{1,12})f", re.ASCII)


def parse(text: str) -> Fraction:
    """``text`` in seconds, exactly; refused unless it is one of the four forms."""
    if frames := _FRAMES.fullmatch(text):
        return Fraction(int(frames[1]), FRAMES)
    forms = ((_SECONDS, (1,)), (_MINUTES, (60, 1)), (_HOURS, (3600, 60, 1)))
    found = next(((match, scale) for form, scale in forms if (match := form.fullmatch(text))), None)
    if found is None:
        refuse(
            f"a time is SECONDS, M:SS or H:MM:SS (each with a .fraction) or FRAMESf: {shown(text)}"
        )
    match, scale = found
    *units, fraction = match.groups()
    whole = sum(int(unit) * weight for unit, weight in zip(units, scale, strict=True))
    return whole + (Fraction(f"0.{fraction}") if fraction else Fraction(0))
