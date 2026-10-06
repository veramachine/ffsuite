"""Every kind of stream into every target (6.6.5, proven): each held, or noted -- never lost silently.

One Matroska source carries them all: video, audio, an SRT subtitle, a font and a cue attached,
a cover, chapters, a custom tag. Each case is what ffman was measured to do (real ffmpeg).
"""

from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from tests.support.media import tool

pytestmark = pytest.mark.slow

CUE: Final = (
    'TITLE "Set"\nFILE "x" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n'
)
META: Final = (
    ";FFMETADATA1\ntitle=All\nMOOD=calm\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle=A\n"
)
APPLIED: Final = "the attached set.cue: its tags and chapters applied, in place of the media's"
SUBS_MOV_TEXT: Final = "subtitle track 1: subrip converted to mov_text"


def not_carried(ext: str) -> str:
    return f"attachments are not carried into .{ext} (another container family)"


def refused(ext: str) -> str:
    return f"error: a .{ext} holds no h264 video, the source's: --video-codec to give one it holds"


@pytest.fixture(scope="module")
def everything(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("proven")
    files = {
        "s.srt": "1\n00:00:00,100 --> 00:00:00,900\nhello\n",
        "set.cue": CUE,
        "m.ffmeta": META,
        "f.ttf": "\x00font",
    }
    for name, text in files.items():
        _ = (folder / name).write_text(text)
    cover = folder / "cover.png"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=red:s=32x32",
        "-frames:v",
        "1",
        str(cover),
    )
    lavfi = [
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=1:s=64x48:r=25",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=48000",
    ]
    given = [
        "-i",
        str(folder / "s.srt"),
        "-i",
        str(folder / "m.ffmeta"),
        "-map",
        "0",
        "-map",
        "1",
        "-map",
        "2",
    ]
    coded = [
        "-map_metadata",
        "3",
        "-map_chapters",
        "3",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-c:s",
        "srt",
    ]
    attach = ["-attach", str(folder / "f.ttf"), "-metadata:s:t:0", "mimetype=font/ttf"]
    attach += ["-attach", str(folder / "set.cue"), "-metadata:s:t:1", "mimetype=text/plain"]
    attach += [
        "-attach",
        str(cover),
        "-metadata:s:t:2",
        "mimetype=image/png",
        "-metadata:s:t:2",
        "filename=cover.png",
    ]
    path = folder / "all.mkv"
    _ = tool(ffmpeg, "-v", "error", *lavfi, *given, *coded, *attach, str(path))
    return path


type Case = tuple[str, str | None, list[str] | None, list[str]]
CASES: Final[
    list[Case]
] = [  # target, its audio codec (None: copied), the streams held (* a cover), the notes
    (
        "mp4",
        None,
        ["h264", "aac", "mov_text", "bin_data", "png*"],
        [APPLIED, SUBS_MOV_TEXT, not_carried("mp4")],
    ),
    (
        "mov",
        None,
        ["h264", "aac", "mov_text", "bin_data"],
        [
            APPLIED,
            SUBS_MOV_TEXT,
            "the cover (png): a .mov drops it, its muxer silent: left out",
            not_carried("mov"),
        ],
    ),
    (
        "m4a",
        None,
        ["h264", "aac", "mov_text", "bin_data", "png*"],
        [APPLIED, SUBS_MOV_TEXT, not_carried("m4a")],
    ),
    ("mkv", "flac", ["h264", "flac", "subrip", "unknown", "unknown", "png*"], []),
    ("mka", None, ["h264", "aac", "subrip", "unknown", "unknown", "png*"], []),
    (
        "flac",
        "flac",
        ["flac", "png*"],
        [
            APPLIED,
            "the picture (h264): a .flac holds covers alone: left out",
            "subtitle track 1: subrip -- a .flac holds it neither as it is nor as text: left out",
            not_carried("flac"),
        ],
    ),
    ("webm", None, None, [refused("webm")]),
    ("mp3", "mp3", None, [refused("mp3")]),
    ("ogg", "vorbis", None, [refused("ogg")]),
]


@pytest.mark.parametrize(("ext", "codec", "held", "notes"), CASES, ids=[case[0] for case in CASES])
def test_every_kind_held_or_noted(
    capsys: pytest.CaptureFixture[str],
    everything: Path,
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    codec: str | None,
    held: list[str] | None,
    notes: list[str],
) -> None:
    out = tmp_path / f"o.{ext}"
    status = main(
        [
            "convert",
            "-i",
            str(everything),
            "-o",
            str(out),
            *(["--audio-codec", codec] if codec else []),
        ]
    )
    said = [
        line.removeprefix("ffman: ")
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("ffman: ")
    ]
    assert (status, said) == (0 if held is not None else 1, notes)
    if held is not None:
        shown = tool(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name:stream_disposition=attached_pic",
            "-of",
            "csv=p=0",
            str(out),
        )
        assert [line.removesuffix(",0").replace(",1", "*") for line in shown.split()] == held
