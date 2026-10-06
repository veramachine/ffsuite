"""A GIF's end of the graph (the bash ffman's gif_chain).

A palette a frame, the most colour a GIF holds (palettegen stats_mode=single,
paletteuse new=1; ffmpeg's default error diffusion), all 256 colours
(palettegen keeps one for transparency unless told not to). --loop-reverse
plays forward, then back, repeating neither end frame; it holds the clip in
memory, as GIFs are short.
"""

from typing import Final, Literal

from ffman.graph import Filter, Labels, Open

_FROM_ZERO: Final = Filter("setpts", ("PTS-STARTPTS",))
_NOT_THE_FIRST: Final = Filter("trim", (("start_frame", "1"),))


def gif_tail(graph: Open, loop: Literal["once", "loop", "reverse"], labels: Labels) -> Open:
    """``graph`` into a GIF's frames, left open for its output label."""
    if loop == "reverse":
        forward, backward, reversed_ = (labels.new(n) for n in ("gf", "gr", "grv"))
        split = graph.then(Filter("split")).end((forward, backward))
        back = Open((backward,)).then(
            _NOT_THE_FIRST, _FROM_ZERO, Filter("reverse"), _NOT_THE_FIRST, _FROM_ZERO
        )
        concat = Filter("concat", (("n", "2"), ("v", "1"), ("a", "0")))
        graph = Open((forward, reversed_), (concat,), (*split, *back.end((reversed_,))))
    frames, sampled, palette = (labels.new(n) for n in ("ga", "gb", "gp"))
    split = graph.then(Filter("split")).end((frames, sampled))
    generated = Open((frames,)).then(
        Filter("palettegen", (("stats_mode", "single"), ("reserve_transparent", "0")))
    )
    use = Filter("paletteuse", (("new", "1"),))
    return Open((sampled, palette), (use,), (*split, *generated.end((palette,))))
