"""``--vfx halation``: a red-orange glow around highlights, as on film.

decisions.md: Effects review.
"""

from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Request, Stage
from ffman.fmt import calc
from ffman.graph import Chain, Filter, Labels, Open

EFFECT: Final = Effect("halation", Stage.LENS, "a red-orange glow around highlights, as on film")


def build(graph: Open, _request: Request, frame: Frame, labels: Labels) -> Open:
    """The highlights, blurred and tinted red-orange, screened back over the picture."""
    whole, bright, glow, base = (labels.new(n) for n in ("ha", "hb", "hc", "hd"))
    split = graph.then(Filter("split")).end((whole, bright))
    highlights = Chain(
        (
            Filter("format", ("gray",)),
            Filter("lut", (("c0", "clip((val-179)*255/76,0,255)"),)),
            Filter("gblur", (("sigma", calc(frame.shorter / 40)), ("steps", "3"))),
            Filter("format", ("gbrp",)),
            Filter("colorchannelmixer", (("gg", "0.35"), ("bb", "0.12"))),
        ),
        (bright,),
        (glow,),
    )
    rgb = Chain((Filter("format", ("gbrp",)),), (whole,), (base,))
    blend = Filter("blend", (("all_mode", "screen"), ("all_opacity", "0.6")))
    return Open((base, glow), (blend,), (*split, highlights, rgb))
