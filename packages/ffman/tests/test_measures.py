from pathlib import Path
from typing import cast

import pytest

from tests.support.measures import frames_of
from tests.support.media import tool


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    ("pix_fmt", "shape", "bits"),
    [
        ("gray", (4, 6), 8),
        ("rgb24", (4, 6, 3), 8),
        ("gray16le", (4, 6), 16),
        ("rgb48le", (4, 6, 3), 16),
    ],
)
def test_a_frame_decodes_at_its_depth(
    ffmpeg: str, tmp_path: Path, pix_fmt: str, shape: tuple[int, ...], bits: int
) -> None:
    # 16 bits a component read as 8 doubles the values' count: a scrambled frame, not white
    white = tmp_path / "white.png"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=white:s=6x4",
        "-frames:v",
        "1",
        str(white),
    )
    frames = frames_of(ffmpeg, str(white), pix_fmt, shape, 1)
    assert frames.shape == (1, *shape)
    top = cast("float", frames.max())
    assert top == 255 if bits == 8 else 60000 < top <= 65535, top
