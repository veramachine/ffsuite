"""``--vfx blur``: the picture blurred in light, round on screen (decisions.md: Blurs review)."""

from fractions import Fraction
from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Param, Request, Stage, asked, between
from ffman.fmt import calc, round_int
from ffman.graph import Filter, Labels, Open
from ffman.graph.light import DECODE, ENCODE, curves

EFFECT: Final = Effect(
    "blur",
    Stage.PICTURE,
    "blur the picture, in light (a near-Gaussian)",
    (
        Param(
            "sigma",
            between(Fraction(0), Fraction(1024), integer=False, low_open=True),
            "must be auto or a sigma above 0, up to 1024",
            "1% of the displayed shorter side",
        ),
    ),
)


def build(graph: Open, request: Request, frame: Frame, _: Labels) -> Open:
    """In light, 16-bit RGB; round on screen: sigma across divided by the SAR."""
    sar = calc(float(frame.sar))
    across = min(round_int(calc(frame.width * float(sar))), frame.height)
    sigma = asked(request, "sigma") or calc(across / 100)
    gblur = Filter(
        "gblur", (("sigma", calc(float(sigma) / float(sar))), ("sigmaV", sigma), ("steps", "6"))
    )
    rgb16 = Filter("format", ("gbrp16le",))
    return graph.then(rgb16, curves(DECODE, frame.video), gblur, curves(ENCODE, frame.video))
