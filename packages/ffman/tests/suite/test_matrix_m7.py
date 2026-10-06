"""matrix.sh's M7, YouTube: source variety x forced normalisation, against its oracle (G3).

Ids: the bash checks' numbers, M552 + source x 2 + forced. The oracle is matrix.sh's:
the audio is copied exactly when it is AAC LC at 48 kHz in stereo and the
normalisation is not forced; a silent source stays silent; every upload meets
check.py's requirements.
"""

from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.measures import unmet
from tests.support.media import tool

pytestmark = pytest.mark.slow
PICTURE: Final = ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=1"]
A48: Final = ["-f", "lavfi", "-i", "sine=d=1:r=48000"]
H264: Final = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
SOURCES: Final = {  # matrix.sh's, each with what makes it what it is
    "c_ok.mp4": [*PICTURE, *A48, "-ac", "2", *H264, "-c:a", "aac", "-profile:a", "aac_low"],
    "c_441.mp4": [
        *PICTURE,
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=44100",
        "-ac",
        "2",
        *H264,
        "-c:a",
        "aac",
    ],
    "c_51.mp4": [
        *PICTURE,
        *A48,
        "-af",
        "pan=5.1|c0=c0|c1=c0|c2=c0|c3=c0|c4=c0|c5=c0",
        *H264,
        "-c:a",
        "aac",
    ],
    "c_opus.mkv": [*PICTURE, *A48, *H264, "-c:a", "libopus"],
    "c_silent.mp4": [*PICTURE, *H264],
    "c_vert60.mp4": [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=180x320:r=60:d=1",
        *A48,
        "-ac",
        "2",
        *H264,
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
    ],
    "c_23976.mp4": [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=24000/1001:d=1",
        *A48,
        "-ac",
        "2",
        *H264,
        "-c:a",
        "aac",
    ],
    "c_full.mp4": [
        *PICTURE,
        *A48,
        "-ac",
        "2",
        "-vf",
        "format=yuvj420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
    ],
    "c_10bit.mp4": [
        *PICTURE,
        *A48,
        "-ac",
        "2",
        "-vf",
        "format=yuv420p10le",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
    ],
}
COMPLIANT: Final = frozenset(
    {"c_ok.mp4", "c_vert60.mp4", "c_23976.mp4", "c_full.mp4", "c_10bit.mp4"}
)
CASES: Final = [
    pytest.param(source, forced, id=f"M{552 + s * 2 + forced}")
    for s, source in enumerate(SOURCES)
    for forced in (0, 1)
]


@pytest.fixture(scope="module")
def sources(files: Path) -> Path:
    for name, how in SOURCES.items():
        _ = tool("ffmpeg", "-v", "error", "-y", *how, str(files / name))
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "sources")
@pytest.mark.parametrize(("source", "forced"), CASES)
def test_an_upload(
    ffprobe: str, capsys: pytest.CaptureFixture[str], source: str, forced: int
) -> None:
    out = f"m7_{source}_{forced}.mp4"
    status = main(
        ["convert", "-i", source, "-o", out, "-p", "yt", *(["--normalize"] if forced else []), "-y"]
    )
    said = capsys.readouterr().err
    assert status == 0, said
    if source == "c_silent.mp4":
        audio = tool(
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            out,
        )
        assert audio.strip() == "", "audio appeared"
        return
    want = "copied" if source in COMPLIANT and not forced else "normalised"
    got = "normalised" if "normalising" in said else "copied"
    assert got == want
    assert unmet(ffprobe, out) == []
