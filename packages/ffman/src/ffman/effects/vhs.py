"""``--vfx vhs``: a VHS tape -- its bandwidth, noise and head switching.

decisions.md: VHS, bar blur.
"""

import math
from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Request, Stage
from ffman.fmt import calc, round_int
from ffman.graph import Chain, Filter, Labels, Open

EFFECT: Final = Effect("vhs", Stage.TAPE, "a VHS tape: its bandwidth, noise and head switching")


# VHS: the tape's bandwidth and noise at 480 lines (decisions.md: 906, 1811, 113.2, 452.8)
def _vhs_noise(target: float, sx: str, sy: str) -> tuple[int, int]:
    """The noise filter's passes and strength for ``target`` RMS after the blur (vhs_noise)."""

    def ss(s: float) -> float:
        if s < 0.3:  # noqa: PLR2004 -- bash's: no blur to speak of
            return 1
        r, a, b = int(4 * s) + 1, 0.0, 0.0
        for i in range(-r, r + 1):
            g = math.exp(-i * i / (2 * s * s))
            a += g
            b += g * g
        return b / (a * a)

    v = 12 * (target / math.sqrt(ss(float(sx)) * ss(float(sy)))) ** 2 + 1
    n = 1
    while math.sqrt(v / n) > 99:  # noqa: PLR2004 -- the noise filter's strength ceiling, bash's
        n += 1
    # the odd strength 2*floor(r/2) + 1; bash then added 2 when r - s > 1, which cannot
    # be: r - s = (r - 2*floor(r/2)) - 1 lies in [-1, 1). Its dead line is not ported.
    return n, int(math.sqrt(v / n) / 2) * 2 + 1


def build(graph: Open, _request: Request, frame: Frame, labels: Labels) -> Open:
    """Noise, the tape's blur (luma, chroma apart), chroma shifted, the head switching."""
    w, h = frame.width, frame.height
    sy, sv, sc, scv = (calc(h / d) for d in (906, 1811, 113.2, 452.8))
    c = max(w // 240, 1)
    d = round_int(calc(h / 480))
    hb = max(round_int(calc(h * 7 / 480)), 2)
    js = max(round_int(calc(w / 50)), 1)
    (luma_n, luma_s), (chroma_n, chroma_s) = _vhs_noise(1.55, sy, sv), _vhs_noise(2.24, sc, scv)
    noise = [
        Filter(
            "noise",
            (
                ("c0s", str(luma_s if i < luma_n else 0)),
                ("c0f", "t+u"),
                ("c1s", str(chroma_s if i < chroma_n else 0)),
                ("c1f", "t+u"),
                ("c2s", str(chroma_s if i < chroma_n else 0)),
                ("c2f", "t+u"),
                ("all_seed", str(i + 1)),
            ),
        )
        for i in range(max(luma_n, chroma_n))
    ]
    blurs = (
        Filter("gblur", (("sigma", sy), ("sigmaV", sv), ("steps", "3"), ("planes", "1"))),
        Filter("gblur", (("sigma", sc), ("sigmaV", scv), ("steps", "3"), ("planes", "6"))),
        Filter("chromashift", (("cbh", str(c)), ("crh", str(c)), ("cbv", str(d)), ("crv", str(d)))),
    )
    whole, band, shifted = (labels.new(n) for n in ("va", "vb", "vc"))
    split = graph.then(Filter("format", ("yuv444p",)), *noise, *blurs, Filter("split")).end(
        (whole, band)
    )
    head_switching = Chain(
        (
            Filter("crop", ("iw", str(hb), "0", f"ih-{hb}")),
            Filter("pad", (f"iw+{js}", str(hb), str(js), "0")),
            Filter("crop", (f"iw-{js}", str(hb), "0", "0")),
        ),
        (band,),
        (shifted,),
    )
    return Open(
        (whole, shifted), (Filter("overlay", ("0", "main_h-overlay_h")),), (*split, head_switching)
    )
