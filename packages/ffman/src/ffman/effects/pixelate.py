"""``--vfx pixelate``: blocks of one colour (decisions.md: Effects review)."""

from fractions import Fraction
from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Param, Request, Stage, asked, between
from ffman.graph import Filter, Labels, Open

EFFECT: Final = Effect(
    "pixelate",
    Stage.PICTURE,
    "blocks of one colour",
    (
        Param(
            "size",
            between(Fraction(2), Fraction(1024), integer=True),
            "must be auto or a block size from 2 to 1024 px",
            "~64 blocks across the shorter side",
        ),
    ),
)


def build(graph: Open, request: Request, frame: Frame, _: Labels) -> Open:
    """Blocks of ``size`` px (auto: ~64 across the shorter side): ``pixelize``."""
    size = asked(request, "size") or str(max(frame.shorter // 64, 2))
    return graph.then(Filter("pixelize", (("w", size), ("h", size))))
