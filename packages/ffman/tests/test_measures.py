import math
from pathlib import Path
from typing import cast

import pytest

from tests.support.measures import frames_of
from tests.support.media import tool


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    ("pix_fmt", "stored", "shape", "bits"),
    [
        ("gray", "gray", (4, 6), 8),
        ("rgb24", "rgb24", (4, 6, 3), 8),
        ("gray16le", "gray16be", (4, 6), 16),
        ("rgb48le", "rgb48be", (4, 6, 3), 16),
    ],
)
def test_a_frame_decodes_at_its_depth(
    ffmpeg: str, tmp_path: Path, pix_fmt: str, stored: str, shape: tuple[int, ...], bits: int
) -> None:
    # 16 bits a component read as 8 doubles the values' count: a scrambled frame. A value
    # stored in the PNG's own format and read back in it or its byte swap: no colour
    # conversion, whose rounding is the platform's (arm64's runners read YUV white as 253);
    # 0x1234, not 0xffff, so a byte order read wrong shows
    sample = b"\xff" if bits == 8 else b"\x12\x34"  # stored big-endian, as PNG's
    raw = tmp_path / "frame.raw"
    _ = raw.write_bytes(sample * math.prod(shape))
    png = tmp_path / "frame.png"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        stored,
        "-s",
        "6x4",
        "-i",
        str(raw),
        str(png),
    )
    frames = frames_of(ffmpeg, str(png), pix_fmt, shape, 1)
    assert frames.shape == (1, *shape)
    assert cast("float", frames.max()) == int.from_bytes(sample)
