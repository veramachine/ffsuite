"""matrix.sh's M1, option spellings: each spelling, its matrix.sh assertion (G3). Ids: the bash checks' numbers.

resize, overlay and attach are convert now. A spelling the new CLI renamed
(--input-subs, --input-video, --input-media, -l) is tested as its new one
(a surface row), and the old one must name it.
"""

import shutil
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import tool

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
SRT: Final = str(TRANSCRIPTS / "regular.srt")
WORDS: Final = str(TRANSCRIPTS / "words.srt")
OVERLAY: Final = ["-i", "v.mp4", "--burn-subs", SRT, "--video-codec", "ffv1", "-o", "m1o.mkv", "-y"]


@pytest.fixture(scope="module")
def media(files: Path) -> Path:
    """matrix.sh's v.mp4 (320x180, 0.4 s, AAC LC stereo) and red.mp4 (lossless red)."""
    gen = ["ffmpeg", "-v", "error", "-y"]
    av = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=0.4",
        "-f",
        "lavfi",
        "-i",
        "sine=d=0.4:r=48000",
        "-ac",
        "2",
    ]
    _ = tool(
        *gen,
        *av,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        str(files / "v.mp4"),
    )
    red = [
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x180:r=25:d=0.2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",
        "-qp",
        "0",
    ]
    _ = tool(*gen, *red, str(files / "red.mp4"))
    return files


def dims(ffprobe: str, path: str) -> str:
    return tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        path,
    ).strip()


def codec(ffprobe: str, path: str, stream: str) -> str:
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        stream,
        "-show_entries",
        "stream=codec_name",
        "-of",
        "csv=p=0",
        path,
    )
    return shown.split()[0]


RESIZE: Final = [
    *[
        (w, f"M{n:03d}")
        for w, n in (
            (["-w", "160"], 1),
            (["-W", "160"], 2),
            (["--width", "160"], 3),
            (["--width=160"], 4),
        )
    ],
    *[
        (h, f"M{n:03d}")
        for h, n in ((["-H", "90"], 5), (["--height", "90"], 6), (["--height=90"], 7))
    ],
]
ASPECT: Final = [
    (a, f"M{n:03d}")
    for a, n in ((["-a", "1:1"], 8), (["--aspect-ratio", "1:1"], 9), (["--aspect-ratio=1:1"], 10))
]
INPUT: Final = [
    (i, f"M{n:03d}")
    for i, n in ((["-i", "v.mp4"], 11), (["--input", "v.mp4"], 12), (["--input=v.mp4"], 13))
]
OUTPUT: Final = [
    (o, f"M{n:03d}")
    for o, n in ((["-o", "m1b.mp4"], 14), (["--output", "m1b.mp4"], 15), (["--output=m1b.mp4"], 16))
]
MODE: Final = [
    (r, f"M{n:03d}")
    for r, n in (
        (["-r", "cover"], 17),
        (["--resize-mode", "cover"], 18),
        (["--resize-mode=cover"], 19),
    )
]
BBLUR: Final = [
    (b, f"M{n:03d}")
    for b, n in (
        (["-b", "10"], 20), (["--bblur", "10"], 21), (["--bblur=10"], 22), (["-b"], 23), (["--bblur"], 24),
        (["-b", "auto"], 25), (["--bblur", "auto"], 26), (["--bblur=auto"], 27),
    )
]  # fmt: skip


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize("spelling", [pytest.param(s, id=i) for s, i in RESIZE])
def test_a_size(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", "-i", "v.mp4", "-o", "m1.mp4", *spelling, "-y"]) == 0
    assert dims(ffprobe, "m1.mp4") == "160x90"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize("spelling", [pytest.param(s, id=i) for s, i in ASPECT])
def test_a_ratio(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", "-i", "v.mp4", "-o", "m1.mp4", *spelling, "-y"]) == 0
    assert dims(ffprobe, "m1.mp4") == "320x320"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize("spelling", [pytest.param(s, id=i) for s, i in INPUT])
def test_an_input(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", *spelling, "-o", "m1.mp4", "-w", "160", "-y"]) == 0
    assert dims(ffprobe, "m1.mp4") == "160x90"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize("spelling", [pytest.param(s, id=i) for s, i in OUTPUT])
def test_an_output(ffprobe: str, spelling: list[str]) -> None:
    Path("m1b.mp4").unlink(missing_ok=True)
    assert main(["convert", "-i", "v.mp4", *spelling, "-w", "160"]) == 0
    assert dims(ffprobe, "m1b.mp4") == "160x90"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize("spelling", [pytest.param(s, id=i) for s, i in MODE])
def test_a_resize_mode(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", "-i", "red.mp4", "-o", "m1.mp4", "-a", "1:1", *spelling, "-y"]) == 0
    assert dims(ffprobe, "m1.mp4") == "320x320"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling",
    [*[pytest.param(s, id=i) for s, i in BBLUR], pytest.param(["-y", "--bblur"], id="M028")],
)
def test_a_bar_blur(ffprobe: str, spelling: list[str]) -> None:
    # M028: --bblur as the last argument is auto
    assert main(["convert", "-i", "v.mp4", "-o", "m1.mp4", "-a", "1:1", *spelling, "-y"]) == 0
    assert dims(ffprobe, "m1.mp4") == "320x320"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    ("spelling", "stream", "want"),
    [
        pytest.param(["--video-codec", "ffv1"], "v:0", "ffv1", id="M029"),
        pytest.param(["--video-codec=ffv1"], "v:0", "ffv1", id="M030"),
        pytest.param(["--audio-codec", "flac"], "a:0", "flac", id="M031"),
        pytest.param(["--audio-codec=flac"], "a:0", "flac", id="M032"),
    ],
)
def test_a_codec(ffprobe: str, spelling: list[str], stream: str, want: str) -> None:
    assert main(["convert", "-i", "v.mp4", "-o", "m1.mkv", "-w", "160", *spelling, "-y"]) == 0
    assert codec(ffprobe, "m1.mkv", stream) == want


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling", [pytest.param("-y", id="M033"), pytest.param("--overwrite", id="M034")]
)
def test_an_overwrite(ffprobe: str, spelling: str) -> None:
    _ = shutil.copyfile("v.mp4", "m1.mp4")  # there to be replaced
    assert main(["convert", "-i", "v.mp4", "-o", "m1.mp4", "-w", "160", spelling]) == 0
    assert dims(ffprobe, "m1.mp4") == "160x90"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling",
    [  # M035-M040: --input-video is --input now, --input-subs --burn-subs (surface)
        pytest.param(["-i", "v.mp4", "--burn-subs", SRT], id="M035"),
        pytest.param(["-i", "v.mp4", f"--burn-subs={SRT}"], id="M036"),
        pytest.param(["--input", "v.mp4", "--burn-subs", SRT], id="M037"),
        pytest.param(["--input", "v.mp4", f"--burn-subs={SRT}"], id="M038"),
        pytest.param(["--input=v.mp4", "--burn-subs", SRT], id="M039"),
        pytest.param(["--input=v.mp4", f"--burn-subs={SRT}"], id="M040"),
    ],
)
def test_subtitles_burned(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", *spelling, "--video-codec", "ffv1", "-o", "m1o.mkv", "-y"]) == 0
    assert codec(ffprobe, "m1o.mkv", "v:0") == "ffv1"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(s, id=f"M{n:03d}")
        for s, n in (
            (["-f", "DejaVu"], 41), (["--font", "DejaVu"], 42), (["--font=DejaVu"], 43),
            (["--font-size", "50"], 44), (["--font-size=50"], 45),
            (["--margin-bottom", "0.2"], 46), (["--margin-bottom=20%"], 47),
            (["--overlay-mode", "plain"], 48), (["--overlay-mode=plain"], 49),
        )
    ],
)  # fmt: skip
def test_a_burns_look(spelling: list[str]) -> None:
    assert main(["convert", *OVERLAY, *spelling]) == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(["--highlight-mode", "pop"], id="M050"),
        pytest.param(["--highlight-mode=pop"], id="M051"),
    ],
)
def test_a_highlight_mode(spelling: list[str]) -> None:
    words = ["-i", "v.mp4", "--burn-subs", WORDS, "--overlay-mode", "word-highlight"]
    assert main(["convert", *words, *spelling, "--video-codec", "ffv1", "-o", "m1o.mkv", "-y"]) == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    ("source", "language"),
    [  # -l and --input-media are --language and --input now (surface: M052, M055-M057)
        pytest.param(["-i", "a.mkv"], ["--language", "eng"], id="M052"),
        pytest.param(["-i", "a.mkv"], ["--language", "eng"], id="M053"),
        pytest.param(["-i", "a.mkv"], ["--language=eng"], id="M054"),
        pytest.param(["--input", "a.mkv"], ["--language", "eng"], id="M055"),
        pytest.param(["--input", "a.mkv"], ["--language", "eng"], id="M056"),
        pytest.param(["--input", "a.mkv"], ["--language=eng"], id="M057"),
    ],
)
def test_a_track_language(ffprobe: str, source: list[str], language: list[str]) -> None:
    _ = tool("ffmpeg", "-v", "error", "-y", "-i", "v.mp4", "-c", "copy", "a.mkv")
    assert main(["convert", *source, "--add-subs", SRT, *language, "--in-place"]) == 0
    tags = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream_tags=language",
        "-of",
        "csv=p=0",
        "a.mkv",
    )
    assert tags.strip() == "eng"


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "media")
@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(["-p", "youtube"], id="M058"),
        pytest.param(["--preset", "youtube"], id="M059"),
        pytest.param(["--preset=yt"], id="M060"),
        pytest.param(["-p", "YouTube"], id="M061"),
        pytest.param(["-p", "YT"], id="M062"),
    ],
)
def test_a_preset(ffprobe: str, spelling: list[str]) -> None:
    assert main(["convert", "-i", "v.mp4", "-o", "m1c.mp4", *spelling, "-y"]) == 0
    assert codec(ffprobe, "m1c.mp4", "v:0") == "h264"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("--input-video", "--input"),
        ("--input-media", "--input"),
        ("--input-subs", "--burn-subs"),
        ("-l", "--language"),
    ],
)
def test_a_renamed_spelling_names_its_replacement(
    capsys: pytest.CaptureFixture[str], old: str, new: str
) -> None:
    assert main(["convert", "-i", "v.mp4", old, "x"]) == 1
    assert f"{old} is now {new}" in capsys.readouterr().err
