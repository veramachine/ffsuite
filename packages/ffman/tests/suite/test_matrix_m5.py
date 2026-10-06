"""matrix.sh's M5, burned subtitles: transcript format x mode x highlight, against its rules (G3).

Ids: the bash checks' numbers, M264 + format x 12 + mode x 3 + highlight. The oracle
is matrix.sh's: the documented rules in their order of precedence (options
checked against each other before any file is read). A refusal must be clean,
as M2's; a render shows text at 1.5 s, gold exactly when the mode highlights.
"""

import hashlib
import re
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import raw, tool

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
FORMATS: Final = (
    "regular.srt", "regular.vtt", "regular.lrc", "regular.csv", "diarized.csv", "regular.json", "words.srt",
    "words.ojf.json", "sentences.ojf.json", "styled.ass", "wx.srt", "wx.vtt", "wx.tsv", "wx.json",
    "wx-highlight.srt", "wx-highlight.vtt", "wx-gaps.json",
)  # fmt: skip
MODES: Final = ("plain", "chunk-word", "word", "word-highlight")
HIGHLIGHTS: Final = ("", "plain", "pop")
STYLED: Final = (
    "[Script Info]\nScriptType: v4.00+\nPlayResY: 180\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
    "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
    "MarginR, MarginV, Encoding\n"
    "Style: Default,IBM Plex Sans,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:00.10,0:00:02.00,Default,,0,0,0,,STYLED\n"
)


def wanted(name: str, mode: str, highlight: str) -> str | None:
    """matrix.sh's oracle: the refusal's words, or None for a render."""
    timed = (
        name.endswith(".ojf.json")
        or name in ("wx.json", "wx-gaps.json")
        or name.startswith("wx-highlight.")
    )
    multi = name.startswith("regular.") or name in ("diarized.csv", "wx.srt", "wx.vtt", "wx.tsv")
    if highlight and mode not in ("chunk-word", "word-highlight"):
        return "needs --overlay-mode chunk-word"
    if name == "styled.ass" and mode != "plain":
        return "only be burned with --overlay-mode plain"
    if mode == "chunk-word" and name == "words.ojf.json":
        return "word-level"
    if mode == "chunk-word" and not timed:
        return "needs word timings"
    if mode.startswith("word") and multi:
        return "needs word timings or one word per cue"
    return None


CASES: Final = [
    pytest.param(name, mode, highlight, id=f"M{264 + f * 12 + m * 3 + h}")
    for f, name in enumerate(FORMATS)
    for m, mode in enumerate(MODES)
    for h, highlight in enumerate(HIGHLIGHTS)
]


@pytest.fixture(scope="module")
def stage(files: Path) -> Path:
    """matrix.sh's clip.mp4 (720p: the word shown at 1.5 s large enough to count) and styled.ass."""
    picture = [
        "-f",
        "lavfi",
        "-i",
        "color=c=0x203040:s=1280x720:r=25:d=2.2",
        "-f",
        "lavfi",
        "-i",
        "sine=d=2.2:r=48000",
    ]
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        *picture,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(files / "m5clip.mp4"),
    )
    _ = (files / "styled.ass").write_text(STYLED)
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(("name", "mode", "highlight"), CASES)
def test_a_burn(
    stage: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ffmpeg: str,
    name: str,
    mode: str,
    highlight: str,
) -> None:
    subs = str(stage / name) if name == "styled.ass" else str(TRANSCRIPTS / name)
    out = f"m5_{name}_{mode}_{highlight or 'none'}.mkv"
    style = ["--highlight-mode", highlight] if highlight else []
    argv = [
        "convert",
        "-i",
        "m5clip.mp4",
        "--burn-subs",
        subs,
        "--overlay-mode",
        mode,
        *style,
        "--video-codec",
        "ffv1",
        "-o",
        out,
        "-y",
    ]
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp))
    before = hashlib.md5(Path("m5clip.mp4").read_bytes(), usedforsecurity=False).hexdigest()
    status = main(argv)
    said = capsys.readouterr().err
    refusal = wanted(name, mode, highlight)
    if refusal is not None:  # matrix.sh's expect_error
        assert status == 1, said
        assert re.search(refusal, said, re.IGNORECASE), said
        assert list(temp.iterdir()) == []
        assert (
            hashlib.md5(Path("m5clip.mp4").read_bytes(), usedforsecurity=False).hexdigest()
            == before
        )
        return
    assert status == 0, said
    frame = raw(
        ffmpeg,
        "-v",
        "error",
        "-ss",
        "1.5",
        "-i",
        out,
        "-frames:v",
        "1",
        "-vf",
        "format=rgb24",
        "-f",
        "rawvideo",
        "-",
    )
    pixels = [frame[i : i + 3] for i in range(0, len(frame), 3)]
    gold = sum(1 for r, g, b in pixels if r > 200 and g > 150 and b < 90)
    bright = sum(1 for p in pixels if p[0] > 200)
    assert bright >= 20, "nothing drawn at 1.5 s"
    if mode in ("chunk-word", "word-highlight"):
        assert gold >= 5, "no highlight colour"
    else:
        assert gold == 0, "highlight colour where none belongs"
