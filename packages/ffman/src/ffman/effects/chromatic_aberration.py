"""``--vfx chromatic-aberration``: red and blue apart, growing to the edges.

decisions.md: Effects review.
"""

from fractions import Fraction
from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Param, Request, Stage, asked, between
from ffman.fmt import calc, round_int
from ffman.graph import Chain, Filter, Labels, Open

EFFECT: Final = Effect(
    "chromatic-aberration",
    Stage.LENS,
    "lateral chromatic aberration: red and blue apart, growing to the edges",
    (
        Param(
            "px",
            between(Fraction(1), Fraction(255), integer=True),
            "must be auto or a shift from 1 to 255 px",
            "red and blue 1/135 of the shorter side apart at the edges",
        ),
    ),
)


def build(graph: Open, request: Request, frame: Frame, labels: Labels) -> Open:
    """Green and blue scaled up from the centre, red kept: the shift grows to the edges."""
    w, h = frame.width, frame.height
    px = asked(request, "px") or str(max((frame.shorter + 67) // 135, 1))
    k = float(calc(int(px) / w))
    green, blue, red = (labels.new(n) for n in ("cg", "cb", "cr"))
    green2, blue2, red2 = (labels.new(n) for n in ("cg2", "cb2", "cr2"))
    split = graph.then(Filter("format", ("gbrp",)), Filter("extractplanes", ("g+b+r",))).end(
        (green, blue, red)
    )
    shown = "1" if frame.squared else f"{frame.sar.numerator}/{frame.sar.denominator}"
    sar = Filter("setsar", (shown,))

    def grown(plane: str, by: float, out: str) -> Chain:
        size = (str(round_int(calc(w * (1 + by * k)))), str(round_int(calc(h * (1 + by * k)))))
        scaled = Filter("scale", (*size, ("flags", "bicubic")))
        return Chain((scaled, Filter("crop", (str(w), str(h))), sar), (plane,), (out,))

    planes = (grown(green, 1, green2), grown(blue, 2, blue2), Chain((sar,), (red,), (red2,)))
    maps = tuple((f"map{i}{part}", str(v)) for i in range(3) for part, v in (("s", i), ("p", 0)))
    merge = Filter("mergeplanes", (*maps, ("format", "gbrp")))
    return Open((green2, blue2, red2), (merge,), (*split, *planes))
