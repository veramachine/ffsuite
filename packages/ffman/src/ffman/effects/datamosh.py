"""Datamosh: each scene cut melted into the next (bash's mosh_prepare).

A pass of its own, after the picture, lens and film effects: MPEG-4 with a
keyframe forced at every cut, then every keyframe but the first dropped, so the
next scene's motion moves the last one's picture. With a duration, a keyframe
that long after each cut is kept: the picture heals.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from ffman.effects.spec import Effect, Param, Stage
from ffman.fmt import calc
from ffman.graph import Filter
from ffman.media.probe import Rational
from ffman.values import is_num


def _positive(text: str) -> bool:
    return is_num(text) and Fraction(text) > 0


EFFECT: Final = Effect(
    "datamosh",
    Stage.MOSH,
    "melt each scene cut into the next (a moving source)",
    (
        Param(
            "seconds",
            _positive,
            "must be auto or the seconds each mosh lasts",
            "never heals",
        ),
    ),
)


SCENE_CUTS: Final = Filter("scdet", (("threshold", "10"),))
_CUT: Final = re.compile(r"lavfi.scd.time: ([0-9.]+)")  # bash's grep -oE, its awk $2
_UNKNOWN_RATE: Final = Rational(25, 1)
MOSH_CODEC: Final = ("-an", "-sn", "-c:v", "mpeg4", "-q:v", "2", "-bf", "0", "-g", "9999")


def cuts(log: str) -> list[str]:
    """The scene cuts' times scdet logged, as their text."""
    return _CUT.findall(log)


@dataclass(frozen=True, slots=True)
class Mosh:
    """The mosh pass's keyframes and drop rule, and the render's frame rate after it."""

    keys: str  # -force_key_frames, "" for none
    drop: str  # -bsf:v's noise filter
    rate: Rational  # the source's, positive (25/1 when unknown)

    @property
    def output(self) -> list[str]:
        """The render's constant frame rate and time base (bash's MOSHOUT)."""
        tb = Rational(self.rate.den, self.rate.num)
        return ["-fps_mode", "cfr", "-r", self.rate.text(), "-enc_time_base:v", tb.text()]


def mosh(scene_cuts: list[str], seconds: str | None, avg_frame_rate: Rational | None) -> Mosh:
    """The keyframes to force and to keep: every cut, and each heal ``seconds`` later."""
    given = avg_frame_rate
    rate = given if given is not None and given.num > 0 and given.den > 0 else _UNKNOWN_RATE
    eps = calc(0.5 * rate.den / rate.num)  # half a frame
    heals = [calc(float(t) + float(seconds)) for t in scene_cuts] if seconds else []
    keep = "".join(f"+lt(abs(pts*tb-{t})\\,{eps})" for t in heals)
    return Mosh(",".join([*scene_cuts, *heals]), f"noise=drop='key*gt(n\\,0)*not(0{keep})'", rate)
