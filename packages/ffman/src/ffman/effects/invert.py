"""``--vfx invert``: the colours inverted, in RGB (decisions.md: Effects review)."""

from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Request, Stage
from ffman.graph import Filter, Labels, Open

EFFECT: Final = Effect("invert", Stage.PICTURE, "invert the colours, in RGB")


def build(graph: Open, _request: Request, _frame: Frame, _: Labels) -> Open:
    """The colours inverted, in RGB: ``negate`` on the picture as ``gbrp``."""
    return graph.then(Filter("format", ("gbrp",)), Filter("negate"))
