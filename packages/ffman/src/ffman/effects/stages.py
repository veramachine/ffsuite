"""The effects in order: stage by stage, the dither, the display (bash's fx_chain).

Each builder extends the open graph, in the registry's order -- the order the
bash ffman ran them (picture, lens and film, the tape; the display after the
subtitles). Numbers are the bash ffman's text (fmt.calc, fmt.round_int): each
step read the last one's %.6g text, not the exact value -- stage A's scaffolding,
which phase 6 replaces with exact arithmetic.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ffman.effects import (
    blur,
    camcorder,
    chromatic_aberration,
    crt,
    dither,
    halation,
    invert,
    pixelate,
    vhs,
)
from ffman.effects.frame import Frame
from ffman.effects.spec import Request, Stage
from ffman.errors import refuse
from ffman.graph import NULL, Filter, Labels, Open
from ffman.media.probe import Video

STAGE_A: Final = frozenset({Stage.PICTURE, Stage.LENS})  # baked into the datamosh pass
STAGE_B: Final = frozenset({Stage.CAMCORDER, Stage.TAPE})  # after it
ALL: Final = STAGE_A | STAGE_B


@dataclass(frozen=True, slots=True)
class Effects:
    """What is drawn on the picture: the effects asked for and the subtitles.

    With what they are sized by, and the graph's labels.
    """

    requests: tuple[Request, ...]
    frame: Frame
    labels: Labels
    subtitles: Filter | None = None  # burned after the picture's and the tape's effects


type Builder = Callable[[Open, Request, Frame, Labels], Open]
PRE: Final[dict[str, Builder]] = {  # fx_pre's, in the registry's (bash's) order
    blur.EFFECT.name: blur.build,
    pixelate.EFFECT.name: pixelate.build,
    invert.EFFECT.name: invert.build,
    chromatic_aberration.EFFECT.name: chromatic_aberration.build,
    halation.EFFECT.name: halation.build,
    camcorder.EFFECT.name: camcorder.build,
    vhs.EFFECT.name: vhs.build,
}
POST: Final[dict[str, Builder]] = {crt.EFFECT.name: crt.build}  # fx_post's: after the subtitles


def apply(
    builders: Mapping[str, Builder], fx: Effects, graph: Open, stages: frozenset[Stage]
) -> Open:
    """``graph`` through the effects asked of ``stages`` that ``builders`` has, in their order.

    The display's (its own stage) run whenever asked: they follow every pass.
    """
    wanted = {
        r.effect.name: r
        for r in fx.requests
        if r.effect.stage in stages or r.effect.stage is Stage.DISPLAY
    }
    for name, build in builders.items():
        if name in wanted:
            graph = build(graph, wanted[name], fx.frame, fx.labels)
    return graph


def before_dither(fx: Effects, graph: Open, stages: frozenset[Stage] = ALL) -> Open:
    """The effects up to the display's, then the subtitles (bash's DITHER_PRE); ``null`` if none."""
    graph = apply(PRE, fx, graph, stages)
    if fx.subtitles is not None and stages >= STAGE_B:  # drawn after the tape's: never in the mosh
        graph = graph.then(fx.subtitles)
    return graph if graph.filters or graph.chains else graph.then(NULL)


def chain(
    fx: Effects,
    graph: Open,
    *,
    restore: bool,
    stages: frozenset[Stage] = ALL,
    palette: str | None = None,
) -> Open:
    """The effects, where bash's fx_chain put them: stage by stage, the dither, then the display.

    ``palette``: the stream the dither's palette arrives on (``N:v``). With
    ``restore`` (a video codec) the source's pixel format comes back: the effects
    work in 4:4:4 or RGB.
    """
    if not fx.requests and fx.subtitles is None:
        return graph
    graph = before_dither(fx, graph, stages)
    if dither.dithered(fx.requests) is not None:
        if palette is None:
            msg = "a dither needs its palette's stream"
            raise ValueError(msg)
        graph = dither.use_palette(graph, palette, fx.labels)
    graph = apply(POST, fx, graph, stages)
    if not restore or not fx.requests:  # bash: fx_any -- subtitles alone keep the format
        return graph
    pix_fmt = fx.frame.video.pix_fmt
    if pix_fmt is None:
        msg = "an unknown pixel format to give back: check_restorable refuses it first"
        raise ValueError(msg)
    return graph.then(Filter("format", (pix_fmt,)))


def check_restorable(requests: Sequence[Request], video: Video, *, restore: bool) -> None:
    """Effects give the picture its format back: refused, before any work, when it is unknown."""
    if restore and requests and video.pix_fmt is None:  # bash wrote "format=", ffmpeg refused it
        refuse("the source's pixel format is unknown: the effects cannot give it back")
