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
    # 16 bits a component read as 8 doubles the values' count: a scrambled frame, not white.
    # White stored in the PNG's own format and read back in it or its byte swap: no colour
    # conversion, whose rounding is the platform's (arm64's swscale made 253 of YUV white)
    raw = tmp_path / "white.raw"
    _ = raw.write_bytes(b"\xff" * (math.prod(shape) * bits // 8))
    white = tmp_path / "white.png"
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
        str(white),
    )
    frames = frames_of(ffmpeg, str(white), pix_fmt, shape, 1)
    assert frames.shape == (1, *shape)
    assert cast("float", frames.max()) == 2**bits - 1
