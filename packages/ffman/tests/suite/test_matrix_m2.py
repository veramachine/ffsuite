"""matrix.sh's M2, gates: every refusal clean, with its own message (G3). Ids: the bash checks' numbers.

Each case is matrix.sh's command line as the harness adapts it (resize, overlay,
attach are convert now), and matrix.sh's checks of a refusal: exit 1, its
message (grep -qiE), no partial file or work dir left, the input unchanged. Six
messages moved with the CLI -- "--input-subs is required" and the like: the
subtitles are options now, "nothing to do" when nothing is asked (surface).
"""

import hashlib
import re
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import tool

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
CASES: Final = [
    pytest.param([], "Usage", id="M063"),  # no command
    pytest.param(["frob"], "unknown command", id="M064"),  # unknown command
    pytest.param(["convert", "-w", "10"], "--input is required", id="M065"),  # resize: no input
    pytest.param(
        ["convert", "-i", "v.mp4", "-o", "g.mp4"], "nothing to do", id="M066"
    ),  # resize: no size
    pytest.param(
        ["convert", "-i", "nope.mp4", "-w", "10", "-o", "./nope-resized.mp4"],
        "no such file",
        id="M067",
    ),  # resize: missing file
    pytest.param(
        ["convert", "-i", "v.mp4", "-o", "./v-resized.mp4", "-w"], "requires a value", id="M068"
    ),  # resize: value missing
    pytest.param(
        ["convert", "-i", "v.mp4", "--width=", "-o", "g.mp4"], "requires a value", id="M069"
    ),  # resize: empty value
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "0", "-o", "./v-resized.mp4"],
        "positive integer",
        id="M070",
    ),  # resize: width 0
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "-5", "-o", "./v-resized.mp4"],
        "positive integer",
        id="M071",
    ),  # resize: width negative
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "1.5", "-o", "./v-resized.mp4"],
        "positive integer",
        id="M072",
    ),  # resize: width fraction
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "abc", "-o", "./v-resized.mp4"],
        "positive integer",
        id="M073",
    ),  # resize: width text
    pytest.param(
        ["convert", "-i", "v.mp4", "-H", "x", "-o", "./v-resized.mp4"],
        "positive integer",
        id="M074",
    ),  # resize: height text
    pytest.param(
        ["convert", "-i", "v.mp4", "-a", "16x9", "-o", "g.mp4"], "must look like", id="M075"
    ),  # resize: aspect x
    pytest.param(
        ["convert", "-i", "v.mp4", "-a", "0:9", "-o", "g.mp4"], "must be positive", id="M076"
    ),  # resize: aspect zero
    pytest.param(
        ["convert", "-i", "v.mp4", "-a", "16:", "-o", "g.mp4"], "must look like", id="M077"
    ),  # resize: aspect half
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "1000", "-H", "700", "-a", "16:9", "-o", "g.mp4"],
        "not the requested",
        id="M078",
    ),  # resize: aspect conflict
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-r", "zoom", "-o", "./v-resized.mp4"],
        "must be stretch, cover or fit",
        id="M079",
    ),  # resize: mode
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-b", "-1", "-o", "./v-resized.mp4"],
        "auto or a number from 0 to 1024",
        id="M080",
    ),  # resize: blur negative
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-b", "1025", "-o", "./v-resized.mp4"],
        "from 0 to 1024",
        id="M081",
    ),  # resize: blur too big
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-b", "soft", "-o", "./v-resized.mp4"],
        "from 0 to 1024",
        id="M082",
    ),  # resize: blur text
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-r", "cover", "-b", "5", "-o", "./v-resized.mp4"],
        "only applies",
        id="M083",
    ),  # resize: blur with cover
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-r", "stretch", "-b", "5", "-o", "./v-resized.mp4"],
        "only applies",
        id="M084",
    ),  # resize: blur with stretch
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-r", "cover", "--bblur", "-o", "./v-resized.mp4"],
        "only applies",
        id="M085",
    ),  # resize: blur auto with cover
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--bblur=", "-o", "./v-resized.mp4"],
        "requires a value",
        id="M086",
    ),  # resize: blur empty =
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--loop", "-o", "x.mp4"],
        "need a .gif output",
        id="M087",
    ),  # resize: loop into mp4
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--loop-reverse", "-o", "x.mkv"],
        "need a .gif output",
        id="M088",
    ),  # resize: loop-reverse into mkv
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-o", "g.png"],
        "cannot be resized into an image",
        id="M089",
    ),  # resize: video to image
    pytest.param(
        ["convert", "-i", "img.png", "-w", "10", "-o", "g.mp4"],
        "cannot be resized into a video",
        id="M090",
    ),  # resize: image to video
    pytest.param(
        ["convert", "-i", "img.png", "-w", "10", "-o", "g.bmp"],
        "unsupported image output",
        id="M091",
    ),  # resize: image format
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-o", "noext"], "needs an extension", id="M092"
    ),  # resize: no extension
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--video-codec", "copy", "-o", "g.mp4"],
        "impossible",
        id="M093",
    ),  # resize: video codec copy
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--video-codec", "mpeg2", "-o", "g.mp4"],
        "no lossless encoder",
        id="M094",
    ),  # resize: video codec unknown
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "--audio-codec", "wma", "-o", "g.mp4"],
        "unsupported --audio-codec",
        id="M095",
    ),  # resize: audio codec unknown
    pytest.param(
        ["convert", "-i", "v.mp4", "--nope", "-o", "./v-resized.mp4"], "unknown option", id="M096"
    ),  # resize: unknown option
    pytest.param(
        ["convert", "-i", "v.mp4", "-w", "10", "-o", "img.png"], "output exists", id="M097"
    ),  # resize: exists
    pytest.param(
        ["convert", "--burn-subs", "x.srt"], "--input is required", id="M098"
    ),  # overlay: no video
    pytest.param(
        ["convert", "-i", "v.mp4", "-o", "./v-subtitled.mp4"], "nothing to do", id="M099"
    ),  # overlay: no subs
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--font-size",
            "0",
            "-o",
            "./v-subtitled.mp4",
        ],
        "positive number",
        id="M100",
    ),  # overlay: font size 0
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--font-size",
            "big",
            "-o",
            "./v-subtitled.mp4",
        ],
        "positive number",
        id="M101",
    ),  # overlay: font size text
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "-f", "a,b", "-o", "./v-subtitled.mp4"],
        "comma",
        id="M102",
    ),  # overlay: font comma
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--margin-bottom",
            "1",
            "-o",
            "./v-subtitled.mp4",
        ],
        "margin-bottom",
        id="M103",
    ),  # overlay: margin 1
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--margin-bottom",
            "100%",
            "-o",
            "./v-subtitled.mp4",
        ],
        "margin-bottom",
        id="M104",
    ),  # overlay: margin 100%
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--margin-bottom",
            "low",
            "-o",
            "./v-subtitled.mp4",
        ],
        "margin-bottom",
        id="M105",
    ),  # overlay: margin text
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--overlay-mode",
            "word-highlight",
            "--highlight-mode",
            "glow",
            "-o",
            "./v-subtitled.mp4",
        ],
        "plain or pop",
        id="M106",
    ),  # overlay: highlight value
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--highlight-mode",
            "pop",
            "-o",
            "./v-subtitled.mp4",
        ],
        "needs --overlay-mode chunk-word",
        id="M107",
    ),  # overlay: highlight without mode
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--overlay-mode",
            "karaoke",
            "-o",
            "./v-subtitled.mp4",
        ],
        "must be plain, chunk-word, word or word-highlight",
        id="M108",
    ),  # overlay: unknown mode
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "--bblur", "-o", "./v-subtitled.mp4"],
        "need a size or a ratio",
        id="M109",
    ),  # overlay: blur without a target
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--bblur",
            "20",
            "-o",
            "./v-subtitled.mp4",
        ],
        "need a size or a ratio",
        id="M110",
    ),  # overlay: blur value without a target
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "-r",
            "cover",
            "-o",
            "./v-subtitled.mp4",
        ],
        "need a size or a ratio",
        id="M111",
    ),  # overlay: cover without a target
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "--standard", "-o", "./v-subtitled.mp4"],
        "is now --overlay-mode plain",
        id="M112",
    ),  # overlay: old --standard
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "-s", "-o", "./v-subtitled.mp4"],
        "is now --overlay-mode plain",
        id="M113",
    ),  # overlay: old -s
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--chunk-word",
            "-o",
            "./v-subtitled.mp4",
        ],
        "is now --overlay-mode chunk-word",
        id="M114",
    ),  # overlay: old --chunk-word
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "--word", "-o", "./v-subtitled.mp4"],
        "is now --overlay-mode word",
        id="M115",
    ),  # overlay: old --word
    pytest.param(
        [
            "convert",
            "-i",
            "v.mp4",
            "--burn-subs",
            "x.srt",
            "--word-highlight",
            "-o",
            "./v-subtitled.mp4",
        ],
        "is now --overlay-mode word-highlight",
        id="M116",
    ),  # overlay: old --word-highlight
    pytest.param(
        ["convert", "-i", "img.png", "--burn-subs", "x.srt", "-o", "./img-subtitled.png"],
        "needs a video",
        id="M117",
    ),  # overlay: image input
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "missing.srt", "-o", "./v-subtitled.mp4"],
        "no such file",
        id="M118",
    ),  # overlay: subs missing
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "plain.txt", "-o", "./v-subtitled.mp4"],
        "no timestamps",
        id="M119",
    ),  # overlay: txt
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.sub", "-o", "./v-subtitled.mp4"],
        "unsupported subtitle format",
        id="M120",
    ),  # overlay: unsupported format
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "foreign.json", "-o", "./v-subtitled.mp4"],
        "not a whisper-cli .* or WhisperX",
        id="M121",
    ),  # overlay: foreign json
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "untimed.srt", "-o", "./v-subtitled.mp4"],
        "no timed text",
        id="M122",
    ),  # overlay: untimed srt
    pytest.param(
        ["convert", "-i", "v.mp4", "--burn-subs", "x.srt", "-o", "g.png"],
        "must be a video",
        id="M123",
    ),  # overlay: image output
    pytest.param(
        ["convert", "--add-subs", "x.srt", "--in-place"], "--input is required", id="M124"
    ),  # attach: no media
    pytest.param(
        ["convert", "-i", "v.mp4", "--in-place"], "nothing to do", id="M125"
    ),  # attach: no subs
    pytest.param(
        ["convert", "-i", "v.mp4", "--add-subs", "x.srt", "--language", "english", "--in-place"],
        "three-letter",
        id="M126",
    ),  # attach: language
    pytest.param(
        ["convert", "-i", "v.mp4", "--add-subs", "x.srt", "--language", "ENG", "--in-place"],
        "three-letter",
        id="M127",
    ),  # attach: language case
    pytest.param(
        ["convert", "-i", "e.mp3", "--add-subs", "x.srt", "--in-place"],
        "cannot carry a subtitle track",
        id="M128",
    ),  # attach: mp3 in place
    pytest.param(
        ["convert", "-i", "v.mp4", "--add-subs", "x.srt", "-o", "g.wav"],
        "cannot carry a subtitle track",
        id="M129",
    ),  # attach: wav output
    pytest.param(["convert", "-p", "yt"], "--input is required", id="M130"),  # convert: no input
    pytest.param(
        ["convert", "-i", "v.mp4", "-o", "./v-youtube.mp4"], "nothing to do", id="M131"
    ),  # convert: no preset
    pytest.param(
        ["convert", "-i", "v.mp4", "-p", "vimeo", "-o", "./v-youtube.mp4"],
        "unknown preset",
        id="M132",
    ),  # convert: unknown preset
    pytest.param(
        ["convert", "-i", "v.mp4", "-p", "yt", "-o", "g.mkv"], "container is MP4", id="M133"
    ),  # convert: mkv output
    pytest.param(
        ["convert", "-i", "pq.mp4", "-p", "yt", "-o", "g.mp4"], "HDR input", id="M134"
    ),  # convert: HDR PQ
    pytest.param(
        ["convert", "-i", "hlg.mp4", "-p", "yt", "-o", "g.mp4"], "HDR input", id="M135"
    ),  # convert: HDR HLG
    pytest.param(
        ["convert", "-i", "b2020.mp4", "-p", "yt", "-o", "g.mp4"],
        "unsupported colour matrix",
        id="M136",
    ),  # convert: BT.2020 SDR
    pytest.param(
        ["convert", "-i", "img.png", "-p", "yt", "-o", "g.mp4"], "needs a video", id="M137"
    ),  # convert: image
]


@pytest.fixture(scope="module")
def gates(files: Path) -> Path:
    """matrix.sh M2's sources, beside v.mp4: transcripts good and bad, an MP3, HDR and BT.2020 clips, an image."""
    gen = ["ffmpeg", "-v", "error", "-y"]
    _ = (files / "x.srt").write_bytes((TRANSCRIPTS / "regular.srt").read_bytes())
    _ = (files / "plain.txt").write_text("words only\n")
    _ = (files / "x.sub").write_text("x\n")
    _ = (files / "foreign.json").write_text('{"a": 1}\n')
    _ = (files / "untimed.srt").write_text("nothing timed here\n")
    _ = tool(*gen, "-f", "lavfi", "-i", "sine=d=0.3", "-c:a", "libmp3lame", str(files / "e.mp3"))
    _ = tool(
        *gen,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:d=1",
        "-frames:v",
        "1",
        str(files / "img.png"),
    )
    for name, trc, pri, mat in (
        ("pq", "smpte2084", "bt2020", "bt2020nc"),
        ("hlg", "arib-std-b67", "bt2020", "bt2020nc"),
        ("b2020", "bt2020-10", "bt2020", "bt2020nc"),
    ):
        tags = (
            f"format=yuv420p10le,setparams=color_trc={trc}:color_primaries={pri}:colorspace={mat}"
        )
        hevc = ["-c:v", "libx265", "-x265-params", "log-level=error"]
        _ = tool(
            *gen,
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=25:d=0.2",
            "-vf",
            tags,
            *hevc,
            str(files / f"{name}.mp4"),
        )
    return files


def md5(path: str) -> str:
    return hashlib.md5(Path(path).read_bytes(), usedforsecurity=False).hexdigest()


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here", "gates")
@pytest.mark.parametrize(("argv", "pattern"), CASES)
def test_a_gate_refuses_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    pattern: str,
) -> None:
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp))
    before = md5("v.mp4")
    assert main(argv) == 1
    said = capsys.readouterr().err
    assert re.search(pattern, said, re.IGNORECASE), said
    assert list(Path().rglob(".ffman.*")) == []  # matrix.sh's leftovers: no partial
    assert list(temp.iterdir()) == []  # nor a work dir
    assert md5("v.mp4") == before  # a failed run leaves its input as it was
