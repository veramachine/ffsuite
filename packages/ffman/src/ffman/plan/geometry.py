"""The picture as displayed, and the size a resize targets: bash's rules, exact.

The rules are the bash ffman's (``geometry``, ``plan_dimensions``); the arithmetic
is exact (Fractions), rounding the true value half up -- what decisions.md's
"Sizes" row says. bash's own arithmetic broke those rules: awk's doubles, printed
``%.6g`` between steps (16:9 was 1.77778), rounded twice -- a height of 1938.996
became 1939, then the even 1940, not the nearest 1938 -- and refused sizes exactly
1 px from the ratio. A proven correction (docs/ffman-python.md, G4): the bash
comparison accepts a difference only where bash's answer is the wrong one.
"""

import re
from fractions import Fraction
from typing import Final

from ffman.errors import refuse
from ffman.graph.sizes import Displayed, Target
from ffman.media.probe import Video
from ffman.values import round_half_up

_ASPECT: Final = re.compile(r"([0-9]+(?:\.[0-9]+)?):([0-9]+(?:\.[0-9]+)?)")


def _sized(video: Video | None, path: str) -> tuple[Video, int, int]:
    """The picture stream and its size, set and not 0 -- else bash's refusal (``geometry``)."""
    if video is None or not video.width or not video.height:
        refuse(f"no picture stream in: {path}")
    return video, video.width, video.height


def picture_stream(video: Video | None, path: str) -> Video:
    """The picture stream, with a size (bash's ``geometry`` refused one without)."""
    return _sized(video, path)[0]


def displayed(video: Video | None, path: str) -> Displayed:
    """As bash's ``geometry``: the displayed size, the frame, the SAR; refuses no picture."""
    video, w, h = _sized(video, path)
    w0 = w
    sar = Fraction(1)
    given = video.sar
    if given is not None and given.num > 0 and given.den > 0 and given.num != given.den:
        sar = Fraction(given.num, given.den)
        w = round_half_up(w * sar)
    # bash: ${r%%.*} then ${r#-} -- the integer part, one leading minus off
    turned = (video.rotation or "").split(".", 1)[0].removeprefix("-") in ("90", "270")
    if turned:
        return Displayed(width=h, height=w, frame_width=h, frame_height=w0, sar=sar)
    return Displayed(width=w, height=h, frame_width=w0, frame_height=h, sar=sar)


def parse_aspect(text: str) -> tuple[Fraction, Fraction]:
    """An --aspect-ratio's two parts, with bash's refusals (its ``plan_dimensions``)."""
    match = _ASPECT.fullmatch(text)
    if match is None:
        refuse(f"--aspect-ratio must look like 16:9 or 2.39:1: {text}")
    a, b = Fraction(match[1]), Fraction(match[2])
    if a <= 0 or b <= 0:
        refuse(f"--aspect-ratio parts must be positive: {text}")
    return a, b


def target_size(
    source: Displayed,
    *,
    video: bool,
    width: int | None,
    height: int | None,
    aspect: str | None,
) -> Target | None:
    """As bash's ``plan_dimensions``: the target size, or None when nothing asks for one."""
    rnd = round_even if video else round_half_up
    w = Fraction(width) if width is not None else None
    h = Fraction(height) if height is not None else None
    if aspect is None:
        if w is not None and h is not None:
            pass
        elif w is not None:
            h = w * source.height / source.width
        elif h is not None:
            w = h * source.width / source.height
        else:
            return None
    else:
        a, b = parse_aspect(aspect)
        r = a / b
        if w is not None and h is not None:
            if not (abs(w - h * r) <= 1 or abs(h - w / r) <= 1):
                ratio = w / h  # reduced -- stated as --aspect-ratio states one
                shown = f"{ratio.numerator}:{ratio.denominator}"
                wanted = f"the requested --aspect-ratio {aspect}"
                refuse(f"--width {width} and --height {height} are {shown}, which is not {wanted}")
        elif w is not None:
            h = w / r
        elif h is not None:
            w = h * r
        else:  # the source's longest side anchors the target's longest side
            long = Fraction(max(source.width, source.height))
            w, h = (long, long / r) if r >= 1 else (long * r, long)
    tw, th = rnd(w), rnd(h)
    if tw <= 0 or th <= 0:
        refuse(f"computed size {tw}x{th} is not usable")
    changed = (width is not None and width != tw) or (height is not None and height != th)
    note = f"rounded to {tw}x{th}: video dimensions must be even" if video and changed else None
    return Target(tw, th, note)


def round_even(x: Fraction) -> int:
    """The nearest even integer, halves up, at least 2 (bash ``round_even``'s rule, exactly)."""
    return max(round_half_up(x / 2) * 2, 2)
