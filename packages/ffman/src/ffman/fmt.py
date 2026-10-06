"""The bash ffman's number text: awk's print, and its calc and round_int (stage A).

Scaffolding for stage A's call equivalence (G1): the bash ffman computed with awk
and printed each number as text (%.6g), the next step reading that text, not
the exact value -- so its filter arguments, and some sizes, depend on it.
Phase 6 replaces all of it with exact arithmetic and one formatter for ffmpeg's
numbers (docs/ffman-python.md), and this module goes.
"""

import math


def awk_print(x: float) -> str:
    """Format ``x`` as awk's ``print`` does: integral values as integers, others ``%.6g``.

    The bash ffman computed with ``awk "BEGIN { print EXPR }"`` (its ``calc``), so its
    messages and filter arguments carry this format (OFMT ``%.6g``): 1.5, 0.333333, 2.
    gawk prints any integral double as its exact integer, at every magnitude (2**100
    in full; 9223372036854775807 as the double it rounds to, ...808), and the
    non-finite as +inf, -inf, +nan, -nan -- probed.
    """
    if math.isinf(x):
        return "+inf" if x > 0 else "-inf"
    if math.isnan(x):  # gawk shows the sign: log(-1) is -nan
        return "-nan" if math.copysign(1.0, x) < 0 else "+nan"
    if x.is_integer():
        return str(int(x))
    return format(x, ".6g")


def calc(x: float) -> str:
    """A number as the bash ffman's calc printed it (``awk "BEGIN { print EXPR }"``)."""
    return awk_print(x)


def round_int(text: str) -> int:
    """A calc's text as the bash ffman's round_int rounded it: awk's ``int(x + 0.5)``."""
    return int(float(text) + 0.5)
