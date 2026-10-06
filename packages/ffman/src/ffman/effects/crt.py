"""``--vfx crt``: a CRT television at 240 lines, scanlines from the beam (decisions.md: CRT)."""

from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Request, Stage
from ffman.graph import Chain, Filter, Labels, Open

EFFECT: Final = Effect(
    "crt", Stage.DISPLAY, "a CRT television at 240 lines: scanlines from the beam"
)


# CRT: 240 lines, each a Gaussian beam whose width follows the light (decisions.md: sigma 0.02-0.3)
LINES: Final = 240
BEAMS: Final = ("0.02", "0.05", "0.1", "0.2", "0.3")
WIDE: Final = 3  # the beams from here (0.2, 0.3) reach the lines above and below


def crt_frame_height(height: int) -> int:
    """The height the CRT renders at: whole rows a line, 240k nearest, 720 at least (fx_post)."""
    k = height // LINES
    if height - k * LINES >= LINES // 2:
        k += 1
    return LINES * max(k, 3)


def _mask(shift: int, beam: str, height: int, width: int, k: str) -> tuple[Filter, ...]:
    """One beam's profile down a line, 16 samples a row, from a 1-px column (bash's mask)."""
    samples = "".join(
        f"+exp(-pow((Y+({j}+0.5)/16)*{LINES}/H-(floor((Y+0.5)*{LINES}/H)+({shift})+0.5),2)/(2*{beam}*{beam}))"
        for j in range(16)
    )
    x = f"(0{samples})/16/({beam}*2.5066283)/{k}"
    return (
        Filter("nullsrc", (("s", f"1x{height}"), ("d", "1"))),
        Filter("format", ("gbrpf32le",)),
        Filter("geq", (("r", x), ("g", x), ("b", x))),
        Filter("scale", (str(width), str(height), ("flags", "neighbor"))),
        Filter("loop", ("-1", "1")),
    )


def build(graph: Open, _request: Request, frame: Frame, labels: Labels) -> Open:
    """The picture at 240 lines, each a Gaussian beam whose width follows the light."""
    w, oh = frame.width, frame.height
    big_h = crt_frame_height(oh)
    k = f"{max(big_h / LINES, 1 / (0.3 * 2.5066283)) * 1.01:.6f}"
    s = "(0.02+0.28*pow(val/65535,1/3))"
    to_light = "pow(val/65535,2.4)*65535"
    lines, up0, down0, up, down = (
        labels.new(n) for n in ("kcl0", "kclu0", "kcld0", "kclu", "kcld")
    )
    chains = graph.then(
        Filter("format", ("gbrp16le",)),
        Filter("lutrgb", (("r", to_light), ("g", to_light), ("b", to_light))),
        Filter("scale", ("iw", str(LINES), ("flags", "area"))),
        Filter("split", ("3",)),
    ).end((lines, up0, down0))
    chains += (
        Chain(
            (
                Filter("pad", ("iw", str(LINES + 1), "0", "1")),
                Filter("crop", ("iw", str(LINES), "0", "0")),
            ),
            (up0,),
            (up,),
        ),
        Chain(
            (
                Filter("crop", ("iw", str(LINES - 1), "0", "1")),
                Filter("pad", ("iw", str(LINES), "0", "0")),
            ),
            (down0,),
            (down,),
        ),
    )
    terms: list[str] = []
    for i, beam in enumerate(BEAMS):
        weight = "0"
        if i > 0:
            lo, hi = BEAMS[i - 1], beam
            weight += f"+between({s},{lo},{hi})*(pow({s},2)-{lo}*{lo})/({hi}*{hi}-{lo}*{lo})"
        if i < len(BEAMS) - 1:
            lo, hi = beam, BEAMS[i + 1]
            weight += (
                f"+between({s},{lo},{hi})*lt({s},{hi})*({hi}*{hi}-pow({s},2))/({hi}*{hi}-{lo}*{lo})"
            )
        terms.append(f"val*({weight})")
    sources = [labels.new(f"kcs{i}") for i in range(len(BEAMS))]
    ups, downs = [labels.new("kcu3"), labels.new("kcu4")], [labels.new("kcd3"), labels.new("kcd4")]
    chains += (
        Chain((Filter("split", (str(len(BEAMS)),)),), (lines,), tuple(sources)),
        Chain((Filter("split", ("2",)),), (up,), tuple(ups)),
        Chain((Filter("split", ("2",)),), (down,), tuple(downs)),
    )
    products: list[str] = []
    for i, beam in enumerate(BEAMS):
        for shift, source in (
            (0, sources[i]),
            (-1, ups[i - WIDE] if i >= WIDE else None),
            (1, downs[i - WIDE] if i >= WIDE else None),
        ):
            if source is None:
                continue
            weighted, mask, product = labels.new("ka"), labels.new("km"), labels.new("kp")
            term = terms[i]
            chains += (
                Chain(
                    (
                        Filter("lutrgb", (("r", term), ("g", term), ("b", term))),
                        Filter("scale", ("iw", str(big_h), ("flags", "neighbor"))),
                        Filter("format", ("gbrpf32le",)),
                    ),
                    (source,),
                    (weighted,),
                ),
                Chain(_mask(shift, beam, big_h, w, k), (), (mask,)),
                Chain(
                    (Filter("blend", (("all_mode", "multiply"), ("shortest", "1"))),),
                    (weighted, mask),
                    (product,),
                ),
            )
            products.append(product)
    last = products[0]
    for product in products[1:-1]:
        added = labels.new("kq")
        chains += (
            Chain(
                (Filter("blend", (("all_mode", "addition"), ("shortest", "1"))),),
                (last, product),
                (added,),
            ),
        )
        last = added
    tail = [Filter("blend", (("all_mode", "addition"), ("shortest", "1")))]
    if oh != big_h:
        tail.append(Filter("scale", (str(w), str(oh), ("flags", "area"))))
    back = f"pow(min(1,{k}*val/65535),1/2.4)*65535"
    tail += [
        Filter("format", ("gbrp16le",)),
        Filter("lutrgb", (("r", back), ("g", back), ("b", back))),
    ]
    return Open((last, products[-1]), tuple(tail), chains)
