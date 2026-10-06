"""``--vfx dither``: an N-colour palette made for the content, ordered dither.

decisions.md: Effects review.

Its palette is a pass of its own (``palette_graph``); the stages chain it.
"""

from fractions import Fraction
from typing import Final

from ffman.effects.spec import Effect, Param, Request, Stage, asked, between
from ffman.graph import Filter, Graph, Labels, Open

EFFECT: Final = Effect(
    "dither",
    Stage.DISPLAY,
    "an N-colour palette made for the content, ordered dither",
    (
        Param(
            "colours",
            between(Fraction(2), Fraction(256), integer=True),
            "must be auto or a palette size from 2 to 256 colours",
            "16",
        ),
    ),
)


def dithered(requests: tuple[Request, ...]) -> str | None:
    """The dither's palette size, if it runs (auto: 16)."""
    dither = next((r for r in requests if r.effect.name == "dither"), None)
    return None if dither is None else (asked(dither, "colours") or "16")


def palette_graph(before: Open, colours: str) -> Graph:
    """The palette pass: the picture as the dither sees it, its palette made (fx_palette)."""
    made = (("max_colors", colours), ("stats_mode", "full"), ("reserve_transparent", "0"))
    return before.then(Filter("palettegen", made)).close("p")


def use_palette(graph: Open, palette: str, labels: Labels) -> Open:
    """``graph`` dithered to the palette arriving on ``palette`` (bash's paletteuse)."""
    into = labels.new("di")
    use = Filter("paletteuse", (("dither", "bayer"), ("bayer_scale", "2")))
    return Open((into, palette), (use,), graph.end((into,)))
