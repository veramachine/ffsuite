"""Soft subtitle tracks (--add-subs, bash's attach): run.sh's checks, ported (G3). Ids: the bash checks' numbers."""

import shutil
from pathlib import Path
from typing import Final

import pytest

from tests.support.media import ff, tool

TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"


def fixture(name: str) -> str:
    return str(TRANSCRIPTS / name)


@pytest.fixture(scope="module")
def sources(files: Path) -> Path:
    """run.sh's v.mp4 (0.4 s, stereo AAC), v9.webm, e.mp3."""
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
        *gen, *av, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(files / "v.mp4")
    )
    _ = tool(
        *gen,
        "-i",
        str(files / "v.mp4"),
        "-c:v",
        "libvpx-vp9",
        "-b:v",
        "500k",
        "-c:a",
        "libopus",
        str(files / "v9.webm"),
    )
    _ = tool(*gen, "-f", "lavfi", "-i", "sine=d=1", "-c:a", "libmp3lame", str(files / "e.mp3"))
    return files


def streams(ffprobe: str, path: str, kind: str) -> str:
    """run.sh's streams: codec,language of each stream of a kind."""
    out = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        kind,
        "-show_entries",
        "stream=codec_name:stream_tags=language",
        "-of",
        "csv=p=0",
        path,
    )
    return " ".join(out.split())


def picture_and_sound(ffmpeg: str, path: str) -> str:
    return tool(
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-c",
        "copy",
        "-f",
        "streamhash",
        "-hash",
        "md5",
        "-",
    )


def added(
    capsys: pytest.CaptureFixture[str], media: str, subs: str, *extra: str
) -> tuple[int, str]:
    """``--add-subs``, as run.sh's attach: the status, and what was said."""
    return ff(capsys, "-i", media, "--add-subs", subs, *extra)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_tracks_in_matroska(
    sources: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = tool("ffmpeg", "-v", "error", "-y", "-i", str(sources / "v.mp4"), "-c", "copy", "a.mkv")
    before = picture_and_sound(ffmpeg, "a.mkv")
    assert (
        added(capsys, "a.mkv", fixture("regular.srt"), "--language", "eng", "--in-place")[0] == 0
    )  # S070
    assert streams(ffprobe, "a.mkv", "s") == "subrip,eng"  # S071
    assert picture_and_sound(ffmpeg, "a.mkv") == before  # S071: untouched
    assert (
        added(capsys, "a.mkv", fixture("sentences.ojf.json"), "--language", "por", "--in-place")[0]
        == 0
    )  # S072
    assert streams(ffprobe, "a.mkv", "s") == "subrip,eng subrip,por"  # S073
    duration = tool(
        ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "a.mkv"
    )
    assert duration.strip()[:3] == "0.4"  # S074: the cues clipped to the media


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_tracks_in_mp4_and_webm(
    sources: Path, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = shutil.copyfile(sources / "v.mp4", "b.mp4")
    assert added(capsys, "b.mp4", fixture("regular.vtt"), "--in-place")[0] == 0  # S075
    assert streams(ffprobe, "b.mp4", "s") == "mov_text,und"  # S076
    _ = shutil.copyfile(sources / "v9.webm", "c.webm")
    assert added(capsys, "c.webm", fixture("regular.csv"), "--in-place")[0] == 0  # S077
    assert streams(ffprobe, "c.webm", "s") == "webvtt"  # S078


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_tracks_refused(sources: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mp3 = str(sources / "e.mp3")
    status, err = added(capsys, mp3, fixture("regular.srt"), "--in-place")
    assert (status, "cannot carry a subtitle track" in err) == (1, True)  # S079
    assert added(capsys, mp3, fixture("regular.srt"), "-o", "e.mka", "-y")[0] == 0  # S080
    bad = tmp_path / "bad.srt"
    _ = bad.write_text("nothing timed here\n")
    _ = shutil.copyfile(sources / "v.mp4", "f.mp4")
    status, err = added(capsys, "f.mp4", str(bad), "--in-place")
    assert (status, "no timed text" in err) == (1, True)  # S081
    assert Path("f.mp4").read_bytes() == (sources / "v.mp4").read_bytes()  # S082: the input kept
    assert list(Path().rglob(".ffman.*")) == []  # S082: no partial left (run.sh: find .)
    status, err = added(
        capsys, "f.mp4", fixture("regular.srt"), "--language", "english", "--in-place"
    )
    assert (status, "three-letter" in err) == (1, True)  # S083


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_highlighted_srt_is_added_as_sentences(
    sources: Path, ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = shutil.copyfile(sources / "v.mp4", "wxa.mp4")
    assert added(capsys, "wxa.mp4", fixture("wx-highlight.srt"), "--in-place")[0] == 0  # S156
    cues = tool(ffmpeg, "-v", "error", "-i", "wxa.mp4", "-map", "0:s", "-f", "srt", "-")
    assert cues.count("-->") == 1  # S157: sentences, not one cue a word (0.4 s: one sentence fits)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_across_families(
    sources: Path, ffprobe: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # an MKV with an ASS track and a font-like attachment, into MP4: what fits is kept
    ass = tmp_path / "e.ass"
    events = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.10,0:00:00.30,Default,,0,0,0,,x\n"
    _ = ass.write_text(f"[Script Info]\nScriptType: v4.00+\n\n[Events]\n{events}")
    attached = ["-attach", fixture("regular.srt"), "-metadata:s:t", "mimetype=text/plain"]
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(sources / "v.mp4"),
        "-i",
        str(ass),
        *attached,
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "fam.mkv",
    )
    assert added(capsys, "fam.mkv", fixture("regular.srt"), "-o", "fam.mp4")[0] == 0  # S110
    assert (
        streams(ffprobe, "fam.mp4", "s") == "mov_text,und mov_text,und"
    )  # S111: every text track converted
