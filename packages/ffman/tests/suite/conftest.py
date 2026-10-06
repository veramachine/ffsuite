from pathlib import Path

import pytest

from tests.support.media import tool


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory, ffmpeg: str) -> Path:
    """run.sh's sources: v.mp4 (320x180, 25 fps, 0.4 s, stereo AAC), its HEVC and VP9 twins."""
    d = tmp_path_factory.mktemp("suite")
    gen = [ffmpeg, "-v", "error", "-y"]
    lavfi = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=0.4",
        "-f",
        "lavfi",
        "-i",
        "sine=d=0.4:r=48000",
    ]
    v = str(d / "v.mp4")
    _ = tool(*gen, *lavfi, "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", v)
    hevc = ["-c:v", "libx265", "-x265-params", "log-level=error", "-c:a", "copy"]
    _ = tool(*gen, "-i", v, *hevc, str(d / "v265.mp4"))
    _ = tool(
        *gen, "-i", v, "-c:v", "libvpx-vp9", "-b:v", "500k", "-c:a", "libopus", str(d / "v9.webm")
    )
    return d


@pytest.fixture
def here(files: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The job-level tests run in the sources' folder, as run.sh did."""
    monkeypatch.chdir(files)
    return files
