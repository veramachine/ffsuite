"""Light: the transfer curves undone and redone around a blur (lutrgb expressions, 16-bit).

Blurs average light, so they run on it (Poynton's Gamma FAQ: simulating a lens
needs linear light). The stream's transfer is undone, then redone: sRGB
(IEC 61966-2-1) for a stream so tagged, or an image untagged; else BT.1886,
the display's 2.4. The bash ffman's light_luts, its expressions raw -- ffman.graph
escapes them.
"""

from collections.abc import Mapping
from typing import Final, Literal

from ffman.graph import Filter
from ffman.media.probe import Video

type Transfer = Literal["srgb", "bt1886"]

_IMAGE_CODECS: Final = frozenset(
    {"png", "mjpeg", "webp", "gif", "bmp", "tiff", "jpeg2000", "jpegxl"}
)
_SRGB: Final = "iec61966-2-1"

# sRGB's piecewise curve on 16-bit values: linear below 0.04045 (2651/65535) encoded,
# 0.0031308 (205/65535) linear; the 2.4 power with its 0.055 offset above.
DECODE: Final[dict[Transfer, str]] = {
    "srgb": "if(lte(val,2651),val/12.92,pow((val/65535+0.055)/1.055,2.4)*65535)",
    "bt1886": "pow(val/65535,2.4)*65535",
}
ENCODE: Final[dict[Transfer, str]] = {
    "srgb": "if(lte(val,205),val*12.92,(1.055*pow(val/65535,1/2.4)-0.055)*65535)",
    "bt1886": "pow(val/65535,1/2.4)*65535",
}


def transfer(video: Video) -> Transfer:
    """The curve to undo: sRGB when tagged so, or an image untagged; else BT.1886 (light_luts)."""
    tag = video.color_transfer
    untagged_image = video.codec in _IMAGE_CODECS and tag in (None, "unknown")
    return "srgb" if tag == _SRGB or untagged_image else "bt1886"


def curves(curve: Mapping[Transfer, str], video: Video) -> Filter:
    """``curve`` (DECODE or ENCODE) applied to each RGB channel, for ``video``'s transfer."""
    expression = curve[transfer(video)]
    return Filter("lutrgb", (("r", expression), ("g", expression), ("b", expression)))
