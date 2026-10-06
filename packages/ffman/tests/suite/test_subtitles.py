"""Transcripts and burned subtitles: run.sh's checks, ported (G3). Ids: the bash checks' numbers.

The transcripts are the bash suite's fixtures, copied here (the Nix source has
no bash suite; phase 5 deletes the originals). Its pixel measures were numpy's;
they are counts, computed here in Python on the same frame.
"""

import colorsys
import json
import os
import re
from fractions import Fraction
from pathlib import Path
from typing import Final, cast

import pytest

from ffman.fmt import calc
from ffman.subs.ass import Style, script
from tests.support.ingesting import ingested
from tests.support.measures import pop, sync, text_band
from tests.support.media import ff, raw, tool
from tests.support.subtitles import POS

type Tokens = list[dict[str, object]]  # whisper-cli -ojf: a sentence's tokens
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"


def fixture(name: str) -> str:
    return str(TRANSCRIPTS / name)


# -- transcripts
def count(path: str) -> str:
    """run.sh's count: the format, chunks, words, chunks not trimmed, chunks overlapping the last."""
    t = ingested(path)
    untrimmed = sum(1 for c in t.chunks if c.text != c.text.strip(" "))
    overlaps = sum(1 for a, b in zip(t.chunks, t.chunks[1:], strict=False) if b.start < a.end)
    return f"{t.fmt} {len(t.chunks)} {len(t.words)} {untrimmed} {overlaps}"


@pytest.mark.parametrize(
    ("name", "counted"),
    [
        pytest.param("regular.srt", "srt 5 0 0 0", id="S036"),
        pytest.param("regular.vtt", "vtt 5 0 0 0", id="S037"),
        pytest.param("regular.lrc", "lrc 5 0 0 0", id="S038"),
        pytest.param("regular.csv", "csv 5 0 0 0", id="S039"),
        pytest.param("diarized.csv", "csv 5 0 0 0", id="S040"),
        pytest.param("regular.json", "json 5 0 0 0", id="S041"),
        pytest.param(
            "words.srt", "srt 85 0 0 0", id="S042"
        ),  # the empty cue dropped, overlaps clamped
        pytest.param("sentences.ojf.json", "json 5 85 0 0", id="S043"),
    ],
)
def test_transcripts(name: str, counted: str) -> None:
    assert count(fixture(name)) == counted


def test_whisper_cli_words(tmp_path: Path) -> None:
    words = "|" + "|".join(w.text for w in ingested(fixture("sentences.ojf.json")).words) + "|"
    assert "|5-Minute|English|Podcast,|" in words  # S044: a composite word, its punctuation merged
    assert "[_" not in words  # S045: special tokens skipped
    text = Path(fixture("sentences.ojf.json")).read_text()
    doc = cast("dict[str, list[dict[str, Tokens]]]", json.loads(text))
    for entry in doc["transcription"]:  # run.sh's jq: a DTW time 130 ms after each token's offset
        for token in entry["tokens"]:
            offsets = cast("dict[str, int]", token["offsets"])
            if not cast("str", token["text"]).startswith("[_"):
                token["t_dtw"] = offsets["from"] // 10 + 13
    dtw = tmp_path / "dtw.json"
    _ = dtw.write_text(json.dumps(doc))
    assert ingested(str(dtw)).words[0].start == 170  # S046: t_dtw preferred for word starts


# -- overlay
@pytest.fixture(scope="module")
def clip(files: Path) -> Path:
    """run.sh's clip.mp4: 2.2 s of dark gradients, 25 fps, a tone.

    The gradient pinned (``seed``) and still (``speed=0``): its defaults are a random seed
    and a rotation, so each session drew another moving background -- and the pop's check
    (only the word changes between two frames) failed for some (seeds 19 and 59 of 72).
    """
    path = files / "clip.mp4"
    picture = [
        "-f",
        "lavfi",
        "-i",
        "gradients=s=640x360:c0=0x203040:c1=0x405060:r=25:d=2.2:seed=1:speed=0",
    ]
    sound = [
        "-f",
        "lavfi",
        "-i",
        "sine=d=2.2:r=48000",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
    ]
    _ = tool("ffmpeg", "-v", "error", "-y", *picture, *sound, str(path))
    return path


def frame_at(ffmpeg: str, ffprobe: str, path: str, t: float) -> tuple[bytes, int, int]:
    """The frame showing time t -- the last at or before it -- as RGB; its width and height."""
    stamps = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        path,
    )
    times = [float(line.split(",")[0]) for line in stamps.split()]  # mp4 adds an empty field
    i = max(k for k, p in enumerate(times) if p <= t + 1e-6)
    size = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        path,
    )
    w, h = (int(v) for v in size.strip().split(","))
    one = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-vf",
        f"select=eq(n\\,{i})",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    return raw(*one), w, h


def text_on_screen(frame: bytes, w: int, h: int) -> bool:
    """run.sh's text_at: over 50 pixels far redder than the dark background, in the lower half."""
    lower = frame[(h // 2) * w * 3 :]
    return sum(1 for i in range(0, len(lower), 3) if lower[i] > 180) > 50


def highlighted(frame: bytes) -> bool:
    """run.sh's gold_at: over 20 pixels of the highlight's gold."""
    gold = sum(
        1
        for i in range(0, len(frame), 3)
        if frame[i] > 200 and frame[i + 1] > 150 and frame[i + 2] < 90
    )
    return gold > 20


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    ("name", "subs", "opts"),
    [
        pytest.param("std", "regular.srt", [], id="S048"),
        pytest.param("cw", "sentences.ojf.json", ["--overlay-mode", "chunk-word"], id="S049"),
        pytest.param(
            "cwpop",
            "sentences.ojf.json",
            ["--overlay-mode", "chunk-word", "--highlight-mode", "pop"],
            id="S050",
        ),
        pytest.param("word", "words.srt", ["--overlay-mode", "word"], id="S051"),
        pytest.param(
            "whpop",
            "words.ojf.json",
            ["--overlay-mode", "word-highlight", "--highlight-mode", "pop"],
            id="S052",
        ),
    ],
)
@pytest.mark.usefixtures("here")
def test_text_on_screen(
    clip: Path,
    ffmpeg: str,
    ffprobe: str,
    capsys: pytest.CaptureFixture[str],
    name: str,
    subs: str,
    opts: list[str],
) -> None:
    out = f"ov_{name}.mkv"
    assert (
        ff(
            capsys,
            "-i",
            str(clip),
            "--burn-subs",
            fixture(subs),
            *opts,
            "--video-codec",
            "ffv1",
            "-o",
            out,
            "-y",
        )[0]
        == 0
    )
    assert text_on_screen(*frame_at(ffmpeg, ffprobe, out, 1.5))


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_word_level_srt_highlights(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S054
    # each cue is a word, and must highlight (it once rendered plain)
    argv = [
        "-i",
        str(clip),
        "--burn-subs",
        fixture("words.srt"),
        "--overlay-mode",
        "word-highlight",
    ]
    assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_wsrt.mkv", "-y")[0] == 0
    assert highlighted(frame_at(ffmpeg, ffprobe, "ov_wsrt.mkv", 1.5)[0])


def coloured(frame: bytes, rgb: tuple[int, int, int]) -> int:
    """The pixels within 40 of ``rgb`` in each channel."""
    near = range(0, len(frame), 3)
    return sum(1 for i in near if all(abs(frame[i + c] - rgb[c]) <= 40 for c in range(3)))


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_the_highlight_takes_the_colour_given(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--highlight-colorize: the lit word burned in the colour given, none of it gold."""
    argv = [
        "-i",
        str(clip),
        "--burn-subs",
        fixture("words.srt"),
        "--overlay-mode",
        "word-highlight",
    ]
    argv += ["--highlight-colorize", "#00FF00", "--video-codec", "ffv1", "-o", "ov_green.mkv", "-y"]
    assert ff(capsys, *argv)[0] == 0
    frame = frame_at(ffmpeg, ffprobe, "ov_green.mkv", 1.5)[0]
    assert coloured(frame, (0, 255, 0)) > 20
    assert not highlighted(frame)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_black_text_is_outlined_white(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--font-color black: its outline white, by contrast (the clip's dark gradient has none)."""
    argv = ["-i", str(clip), "--burn-subs", fixture("regular.srt"), "--font-color", "black"]
    assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_black.mkv", "-y")[0] == 0
    assert coloured(frame_at(ffmpeg, ffprobe, "ov_black.mkv", 1.5)[0], (255, 255, 255)) > 50


def reddish(frame: bytes) -> set[int]:
    """The pixels where red leads green and blue by over 80, bright."""
    out: set[int] = set()
    for i in range(0, len(frame), 3):
        if frame[i] > 150 and frame[i] - max(frame[i + 1], frame[i + 2]) > 80:
            out.add(i)
    return out


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_the_text_takes_its_colour(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--font-color #FF0000: red where white was -- the same burn in white set apart, so only
    the text counts; thin strokes at 4:2:0 are red-led, not pure red."""
    burned: dict[str, set[int]] = {}
    for colour in ("white", "#FF0000"):
        argv = ["-i", str(clip), "--burn-subs", fixture("regular.srt"), "--font-color", colour]
        assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_red.mkv", "-y")[0] == 0
        burned[colour] = reddish(frame_at(ffmpeg, ffprobe, "ov_red.mkv", 1.5)[0])
    assert len(burned["#FF0000"] - burned["white"]) > 300


def hues(frame: bytes) -> int:
    """The hues (sixths of the wheel) with over 20 saturated, bright pixels."""
    found = [0] * 6
    for i in range(0, len(frame), 3):
        r, g, b = frame[i], frame[i + 1], frame[i + 2]
        top, low = max(r, g, b), min(r, g, b)
        if top > 200 and top - low > 120:
            h, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            found[int(h * 6) % 6] += 1
    return sum(1 for n in found if n > 20)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_rainbow_paints_its_letters_apart(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--highlight-colorize rainbow: the lit word's letters burned in hues apart."""
    argv = [
        "-i",
        str(clip),
        "--burn-subs",
        fixture("sentences.ojf.json"),
        "--overlay-mode",
        "chunk-word",
    ]
    argv += [
        "--highlight-colorize",
        "rainbow",
        "--video-codec",
        "ffv1",
        "-o",
        "ov_rainbow.mkv",
        "-y",
    ]
    assert ff(capsys, *argv)[0] == 0
    assert hues(frame_at(ffmpeg, ffprobe, "ov_rainbow.mkv", 1.5)[0]) >= 2


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_burned_and_resized(clip: Path, ffprobe: str, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["-i", str(clip), "--burn-subs", fixture("regular.srt"), "-a", "9:16", "-w", "180"]
    assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_v.mkv", "-y")[0] == 0  # S055
    size = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        "ov_v.mkv",
    )
    assert size.strip() == "180x320"  # S056


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_tmpdir_with_filter_syntax(
    clip: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # S068
    odd = tmp_path / "odd:dir,x"
    odd.mkdir()
    monkeypatch.setenv("TMPDIR", str(odd))
    argv = [
        "-i",
        str(clip),
        "--burn-subs",
        fixture("regular.srt"),
        "--video-codec",
        "ffv1",
        "-o",
        "odd.mkv",
        "-y",
    ]
    assert ff(capsys, *argv)[0] == 0


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("subs", "argv", "message"),
    [
        pytest.param(
            "regular.srt", ["--overlay-mode", "chunk-word"], "needs word timings", id="S057"
        ),
        pytest.param("words.ojf.json", ["--overlay-mode", "chunk-word"], "word-level", id="S058"),
        pytest.param("regular.srt", ["--overlay-mode", "word"], "one word per cue", id="S059"),
        pytest.param(
            "words.srt",
            ["--overlay-mode", "word", "--highlight-mode", "pop"],
            "needs --overlay-mode chunk-word or word-highlight",
            id="S060",
        ),
        pytest.param(
            "regular.srt",
            ["--overlay-mode", "standard"],
            "must be plain, chunk-word, word or word-highlight",
            id="S061",
        ),
        pytest.param("regular.srt", ["-s"], "is now --overlay-mode plain", id="S062"),
        pytest.param("regular.srt", ["--standard"], "is now --overlay-mode plain", id="S063"),
        pytest.param(
            "regular.srt", ["--chunk-word"], "is now --overlay-mode chunk-word", id="S064"
        ),
        pytest.param("regular.srt", ["--word"], "is now --overlay-mode word", id="S065"),
        pytest.param(
            "regular.srt", ["--word-highlight"], "is now --overlay-mode word-highlight", id="S066"
        ),
        pytest.param("regular.srt", ["--margin-bottom", "1.5"], "margin-bottom", id="S067"),
    ],
)
def test_refusals(
    clip: Path, capsys: pytest.CaptureFixture[str], subs: str, argv: list[str], message: str
) -> None:
    status, err = ff(capsys, "-i", str(clip), "--burn-subs", fixture(subs), *argv)
    assert (status, message in err) == (1, True)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_refusals_of_the_transcript(
    clip: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain.txt"
    _ = plain.write_text("plain words\n")
    status, err = ff(capsys, "-i", str(clip), "--burn-subs", str(plain))
    assert (status, "no timestamps" in err) == (1, True)  # S047
    ass = tmp_path / "s.ass"
    events = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.10,0:00:01.00,Default,,0,0,0,,x\n"
    _ = ass.write_text(f"[Script Info]\nScriptType: v4.00+\n\n[Events]\n{events}")
    status, err = ff(capsys, "-i", str(clip), "--burn-subs", str(ass), "--overlay-mode", "word")
    lines = [line for line in err.splitlines() if line]
    assert (status, len(lines), "overlay-mode plain" in lines[0]) == (
        1,
        1,
        True,
    )  # S069: one clean refusal


# -- chunk + word timing, and WhisperX's outputs
def chunk_ass(text: str, words: int) -> tuple[int, int]:
    """check.py's chunk_ass: base-layer events on one line that overlap; highlighted words."""
    events: list[tuple[int, float, float, str]] = []
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            f = line.split(",", 9)
            at = POS.search(f[9])
            events.append((int(f[0][-1]), _seconds(f[1]), _seconds(f[2]), at[2] if at else "-"))
    base = sorted((a, b, y) for layer, a, b, y in events if layer == 0)
    over = sum(1 for i, a in enumerate(base) for b in base[i + 1 :] if a[2] == b[2] and b[0] < a[1])
    return over, sum(1 for e in events if e[0] == 1) - words


def _seconds(t: str) -> float:
    return sum(float(x) * m for x, m in zip(t.split(":"), (3600, 60, 1), strict=True))


def rendered(path: str | Path, mode: str = "chunk-word", highlight: str = "pop") -> str:
    """run.sh's fn: SUBMODE, HLMODE; ingest_subs; write_ass 1920 1080."""
    return script(ingested(str(path)), 1920, 1080, Style(mode, highlight))[0]


def spoken(path: str) -> int:
    """run.sh's jq: the tokens that start a word (a leading space)."""
    doc = cast("dict[str, list[dict[str, Tokens]]]", json.loads(Path(path).read_text()))
    return sum(
        1
        for e in doc["transcription"]
        for t in e["tokens"]
        if cast("str", t["text"]).startswith(" ")
    )


def test_a_drifting_dtw(tmp_path: Path) -> None:
    drift = fixture("dtw-drift.ojf.json")
    nwords = spoken(drift)
    assert chunk_ass(rendered(drift), nwords) == (
        0,
        0,
    )  # S127: none drawn over the next; every word
    doc = cast("dict[str, list[dict[str, Tokens]]]", json.loads(Path(drift).read_text()))
    del doc["transcription"][0]  # the reported file's shape: no leading blank
    noblank = tmp_path / "drift-noblank.json"
    _ = noblank.write_text(json.dumps(doc))
    assert chunk_ass(rendered(noblank), nwords) == (0, 0)  # S128
    t = ingested(drift)
    assert any("in 3 of 3 sentences" in n for n in t.notes)  # S129: the fallback reported
    first = t.chunks[0]
    assert ((first.text, first.segment), (t.words[0].segment, t.words[0].text)) == (
        ("alpha bravo charlie delta echo", "1"),
        ("1", "alpha"),
    )  # S130: words stay with their sentence despite a leading blank
    good = cast("dict[str, list[dict[str, Tokens]]]", json.loads(Path(drift).read_text()))
    for token in good["transcription"][1]["tokens"]:  # run.sh's jq: DTW that holds, in sentence 1
        offsets = cast("dict[str, int]", token["offsets"])
        if not cast("str", token["text"]).startswith("[_"):
            token["t_dtw"] = offsets["from"] // 10 + 5
    held = tmp_path / "good.json"
    _ = held.write_text(json.dumps(good))
    assert ingested(str(held)).words[0].start == 72280  # S131: DTW used where it holds


def summary(path: str) -> str:
    """run.sh's ingest: SUBSRC|HAS_WORDS|chunks|words."""
    t = ingested(path)
    return f"{t.source}|{int(t.has_words)}|{len(t.chunks)}|{len(t.words)}"


@pytest.mark.parametrize(
    ("name", "found"),
    [
        pytest.param("wx.srt", ".srt|0|5|0", id="S132"),
        pytest.param("wx.vtt", ".vtt|0|5|0", id="S133"),
        pytest.param("wx.tsv", ".tsv|0|5|0", id="S134"),
        pytest.param("wx.json", "WhisperX JSON|1|5|94", id="S135"),
        pytest.param("wx-highlight.srt", "WhisperX --highlight_words .srt|1|5|94", id="S136"),
        pytest.param("wx-highlight.vtt", "WhisperX --highlight_words .vtt|1|5|94", id="S137"),
    ],
)
def test_whisperx_outputs(name: str, found: str) -> None:
    assert summary(fixture(name)) == found


def sentences(name: str) -> list[tuple[int, int, str]]:
    return [(c.start, c.end, c.text) for c in ingested(fixture(name)).chunks]


def words_of(name: str) -> list[tuple[int, int, str]]:
    return [(w.start, w.end, w.text) for w in ingested(fixture(name)).words]


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("wx.vtt", id="S138"),
        pytest.param("wx.tsv", id="S139"),
        pytest.param("wx.json", id="S140"),
        pytest.param("wx-highlight.srt", id="S141"),
        pytest.param("wx-highlight.vtt", id="S142"),
    ],
)
def test_the_same_sentences(name: str) -> None:
    assert sentences(name) == sentences("wx.srt")


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("wx-highlight.srt", id="S143"),
        pytest.param("wx-highlight.vtt", id="S144"),
        pytest.param("wx-diarized-wrapped.srt", id="S146"),  # diarised, line-wrapped
    ],
)
def test_the_same_words(name: str) -> None:
    assert words_of(name) == words_of("wx.json")


def test_whisperx_edges(tmp_path: Path) -> None:
    assert ingested(fixture("wx-hours.vtt")).chunks[0].start == 3600151  # S145: past one hour
    styled = tmp_path / "styled.srt"
    cues = "1\n00:00:01,000 --> 00:00:02,000\nplain <u>styled</u> text\n\n2\n00:00:03,000 --> 00:00:04,000\nanother line\n\n"
    _ = styled.write_text(cues)
    assert summary(str(styled)) == ".srt|0|2|0"  # S147: <u> styling is not highlighting
    gaps = ingested(fixture("wx-gaps.json"))
    counted = [re.match(r"[0-9]+ (words|sentences)", n) for n in gaps.notes]
    assert [m[0] for m in counted if m] == ["4 words", "1 sentences"]  # S148
    for a, b in zip(gaps.words, gaps.words[1:], strict=False):  # S149: bash's awk, strictly
        assert a.end > a.start
        assert a.segment != b.segment or b.start > a.start
    assert gaps.words[-1].end > gaps.words[-1].start
    by = {w.text: w for w in gaps.words}
    assert (
        by["keep"].start == by["we"].end
    )  # S150: an untimed word starts where the one before ends


@pytest.mark.parametrize(
    "name", [pytest.param("wx.json", id="S151"), pytest.param("wx-highlight.srt", id="S152")]
)
def test_chunk_word_from_whisperx(name: str) -> None:
    assert chunk_ass(rendered(fixture(name)), 94) == (0, 0)


def test_the_unalignable_sentence_in_word_mode() -> None:  # S153
    text = rendered(fixture("wx-gaps.json"), "word", "plain")
    assert len(re.findall(r"New episodes drop regularly, so .* on YouTube", text)) == 1


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("subs", "mode", "message"),
    [
        pytest.param("wx.srt", "chunk-word", "needs word timings", id="S154"),
        pytest.param("wx.tsv", "word", "needs word timings or one word per cue", id="S155"),
    ],
)
def test_whisperx_refusals(
    clip: Path, capsys: pytest.CaptureFixture[str], subs: str, mode: str, message: str
) -> None:
    status, err = ff(capsys, "-i", str(clip), "--burn-subs", fixture(subs), "--overlay-mode", mode)
    assert (status, message in err) == (1, True)


# -- review 3: hostile transcripts (S158, S159: fuzz.py's invariants, the Hypothesis port's to come)
def put(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    _ = path.write_bytes(text.encode())
    return str(path)


def test_hostile_transcripts(tmp_path: Path) -> None:
    bom = put(tmp_path, "bom.csv", '\ufeffstart,end,speaker,text\n1000,2000,0,"Hello"\n')
    assert [c.text for c in ingested(bom).chunks] == ["Hello"]  # S160: the text, not the speaker id
    types = put(
        tmp_path,
        "types.json",
        '{"segments": [{"start": "1", "end": "2", "text": "Hello"}, {"start": "x", "end": 3, "text": "Bad"}]}',
    )
    assert [c.text for c in ingested(types).chunks] == ["Hello"]  # S161: coerced or dropped
    words = '[{"word": "a", "start": 0.0, "end": 0.005}, {"word": "b"}, {"word": "abcdefghijklmnopqrst"}, {"word": "end", "start": 0.030, "end": 0.5}]'
    starve = put(
        tmp_path,
        "starve.json",
        f'{{"segments": [{{"start": 0.0, "end": 1.0, "text": "a b abcdefghijklmnopqrst end", "words": {words}}}], "language": "en"}}',
    )
    b = next(w for w in ingested(starve).words if w.text == "b")
    assert b.end - b.start == 10  # S162: one ASS step where the gap allows
    ja = rendered(fixture("wx-ja.json"), "chunk-word", "plain")
    first = next(line for line in ja.splitlines() if line.startswith("Dialogue: 0"))
    assert re.sub(r".*\}", "", first) == "日は良い天気です"  # S163: joined without spaces
    assert chunk_ass(ja, 9) == (0, 0)  # S164: every character highlighted once
    assert len(ingested(fixture("cli-ja.json")).words) == 9  # S165: each token a word
    bare = rendered(fixture("wx-gaps.json"), "chunk-word", "plain")
    assert (
        sum(1 for line in bare.splitlines() if "New episodes drop" in line and "an5\\pos" in line)
        == 1
    )  # S166
    sixteen = {
        "segments": [
            {
                "start": 1,
                "end": 9,
                "text": " ".join(["wonderful"] * 16),
                "words": [
                    {"word": "wonderful", "start": 1 + k / 2, "end": 1.4 + k / 2} for k in range(16)
                ],
            }
        ],
        "language": "en",
    }
    long = ingested(put(tmp_path, "long.json", json.dumps(sixteen)))
    notes = script(long, 1920, 1080, Style("chunk-word", size=Fraction(160)))[1]
    assert "wrap past the top" in notes[0]  # S167
    assert script(long, 1920, 1080, Style("chunk-word"))[1] == ()  # S172: none at the default size
    dash = tmp_path / "-dash.json"
    _ = dash.write_bytes(Path(fixture("wx.json")).read_bytes())
    assert len(ingested(str(dash)).words) == 94  # S168: once taken for jq's option
    null = put(
        tmp_path,
        "nulltext.json",
        '{"segments": [{"start": 1, "end": 2}, {"start": 2, "end": 3, "text": "ok", "words": [{"start": 2.1, "end": 2.5}]}]}',
    )
    t = ingested(null)
    assert ([c.text for c in t.chunks], len(t.words)) == (["ok"], 0)  # S170: never burned as "null"
    huge = script(ingested(fixture("regular.srt")), 608, 1080, Style("plain", size=Fraction(1000)))
    assert huge[1] is not None  # S171: reported, not a crash


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_invalid_json_is_called_so(
    clip: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # S169
    broken = put(tmp_path, "broken.json", '{"segments": [')
    status, err = ff(capsys, "-i", str(clip), "--burn-subs", broken)
    assert (status, "not valid JSON" in err) == (1, True)


def style_fields(text: str, *fields: int) -> str:
    line = next(line for line in text.splitlines() if line.startswith("Style:"))
    parts = line.split(",")
    return ",".join(parts[f - 1] for f in fields)


def test_the_styles() -> None:
    plain = rendered(fixture("regular.srt"), "plain", "plain")
    assert style_fields(plain, 2, 3, 8, 17, 18) == "IBM Plex Sans,57,0,2.475,0"  # S173: as mpv
    heavy = rendered(fixture("sentences.ojf.json"), "chunk-word", "plain")
    assert style_fields(heavy, 3, 8, 17) == "64,-1,4"  # S174
    sized = script(ingested(fixture("regular.srt")), 1920, 1080, Style("plain", size=Fraction(40)))[
        0
    ]
    assert style_fields(sized, 3) == "40"  # S175


# -- placement
@pytest.fixture(scope="module")
def placements(files: Path) -> Path:
    """run.sh's bars(): a letterbox, a pillarbox, a picture seen once; black; open."""
    gen = ["ffmpeg", "-v", "error", "-y"]
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    for size, at, extra, name in (
        ("640x200", "0:0", "", "lbox"),
        ("480x360", "80:0", "", "pbox"),
        ("640x250", "0:55", ":enable='between(t,1.8,2.2)'", "dark"),
    ):
        two = [
            "-f",
            "lavfi",
            "-i",
            "color=black:s=640x360:r=25:d=4",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s={size}:r=25:d=4",
        ]
        _ = tool(
            *gen,
            *two,
            "-filter_complex",
            f"[0][1]overlay={at}:shortest=1{extra}",
            *enc,
            str(files / f"{name}.mp4"),
        )
    _ = tool(
        *gen, "-f", "lavfi", "-i", "color=black:s=640x360:r=25:d=4", *enc, str(files / "black.mp4")
    )
    _ = tool(
        *gen,
        "-f",
        "lavfi",
        "-i",
        "color=0x203040:s=640x360:r=25:d=4",
        *enc,
        str(files / "open.mp4"),
    )
    return files


def place(
    capsys: pytest.CaptureFixture[str], files: Path, source: str, mode: str, subs: str, *extra: str
) -> int:
    """run.sh's place: burned into pl.mkv; how many notes of a black bar."""
    argv = ["-i", str(files / source), "--burn-subs", fixture(subs), "--overlay-mode", mode, *extra]
    status, err = ff(capsys, *argv, "--video-codec", "ffv1", "-o", "pl.mkv", "-y")
    assert status == 0, err
    return err.count("black bar")


def band(ffmpeg: str, ffprobe: str, path: str, ref: str, what: str) -> float:
    """check.py's text_band at 2.2 s (tests/support/measures.py); subtitle pixels must show."""
    found = text_band(ffmpeg, ffprobe, path, ref, 2.2, what)
    assert found is not None, "no subtitle pixels"
    return found


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("mode", "subs"),
    [
        pytest.param("plain", "regular.srt", id="S176-S177"),
        pytest.param("word", "words.srt", id="S178-S179"),
        pytest.param("chunk-word", "sentences.ojf.json", id="S180-S181"),
    ],
)
def test_a_letterbox(
    placements: Path,
    ffmpeg: str,
    ffprobe: str,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    subs: str,
) -> None:
    assert place(capsys, placements, "lbox.mp4", mode, subs) == 1  # the bar is found
    assert 0.755 <= band(ffmpeg, ffprobe, "pl.mkv", str(placements / "lbox.mp4"), "centre") <= 0.80


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_placement(
    placements: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    open_ = str(placements / "open.mp4")
    assert place(capsys, placements, "open.mp4", "plain", "regular.srt") == 0
    assert 0.92 <= band(ffmpeg, ffprobe, "pl.mkv", open_, "bottom") <= 0.945  # S182
    assert (
        place(capsys, placements, "pbox.mp4", "plain", "regular.srt") == 0
    )  # S183: side bars only
    assert place(capsys, placements, "black.mp4", "plain", "regular.srt") == 0  # S184: all black
    assert (
        place(capsys, placements, "dark.mp4", "plain", "regular.srt") == 1
    )  # S185: seen at one sample
    assert (
        place(capsys, placements, "lbox.mp4", "plain", "regular.srt", "--margin-bottom", "20%") == 0
    )  # S186
    lbox = str(placements / "lbox.mp4")
    assert (
        0.76 <= band(ffmpeg, ffprobe, "pl.mkv", lbox, "bottom") <= 0.80
    )  # S187: the margin applied
    assert (
        place(capsys, placements, "open.mp4", "plain", "regular.srt", "-a", "9:16") == 1
    )  # S188: fit's borders
    assert (
        place(capsys, placements, "open.mp4", "plain", "regular.srt", "-a", "9:16", "-b", "20") == 0
    )  # S189: blurred


# -- review 4: without a target, detection seeking, raw streams; a tall block
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(["--bblur"], id="S204"),
        pytest.param(["--bblur", "20"], id="S205"),
        pytest.param(["-r", "cover"], id="S206"),
    ],
)
def test_a_resize_without_a_target(
    placements: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    status, err = ff(
        capsys, "-i", str(placements / "open.mp4"), "--burn-subs", fixture("regular.srt"), *extra
    )
    assert (status, "need a size or a ratio" in err) == (1, True)  # was silently dropped


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_detection_seeks_to_keyframes(
    placements: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ffmpeg: str,
) -> None:  # S207
    # a shim ffmpeg records its arguments, as run.sh's did. /bin/sh, not /usr/bin/env: the Nix
    # sandbox has no /usr/bin/env, and a script whose interpreter is missing fails with ENOENT --
    # which a PATH search takes for "not here" and passes by, to the real ffmpeg, silently
    shim, record = tmp_path / "shim", tmp_path / "ffmpeg.args"
    shim.mkdir()
    _ = (shim / "ffmpeg").write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$*" >>"{record}"\nexec {ffmpeg} "$@"\n'
    )
    (shim / "ffmpeg").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    argv = [
        "-i",
        str(placements / "lbox.mp4"),
        "--burn-subs",
        fixture("regular.srt"),
        "--video-codec",
        "ffv1",
        "-o",
        "sh.mkv",
        "-y",
    ]
    assert ff(capsys, *argv)[0] == 0
    assert record.exists(), "the shim never ran: passed by on PATH (its interpreter missing?)"
    samples = [line for line in record.read_text().splitlines() if "cropdetect" in line]
    assert (sum(1 for line in samples if "-noaccurate_seek -ss" in line), len(samples)) == (7, 7)


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_raw_stream_has_its_bar_found(
    placements: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # S208
    raw = placements / "lbox.h264"
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(placements / "lbox.mp4"),
        "-c",
        "copy",
        "-bsf:v",
        "h264_mp4toannexb",
        str(raw),
    )
    assert (
        place(capsys, placements, "lbox.h264", "plain", "regular.srt") == 1
    )  # no duration: 50 frames


def test_a_tall_block_in_a_tall_bar() -> None:  # S209
    # centred regardless, an 11-line sentence in a 9:16 frame had lines at y 1134..1294
    bar_y = calc(1080 - 0.3438 * 1080 / 2)
    text = script(
        ingested(fixture("sentences.ojf.json")),
        360,
        640,
        Style("chunk-word", bar_y=Fraction(bar_y)),
    )[0]
    found: list[tuple[str, str]] = POS.findall(text)
    ys = [float(y) for _, y in found]
    assert ys
    assert not [y for y in ys if y + 40 > 1080 - 60 + 1]  # lifted to the margin: no line below it


# -- a GIF
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_burned_into_a_gif(files: Path, capsys: pytest.CaptureFixture[str], ffmpeg: str) -> None:
    g10 = files / "g10.mp4"
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=10:d=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(g10),
    )
    assert (
        ff(capsys, "-i", str(g10), "--burn-subs", fixture("regular.srt"), "-o", "sub.gif", "-y")[0]
        == 0
    )  # S220
    sums = tool(ffmpeg, "-v", "error", "-i", "sub.gif", "-map", "0:v", "-f", "framemd5", "-")
    frames = {
        line.rsplit(",", 1)[-1].strip() for line in sums.splitlines() if not line.startswith("#")
    }
    assert len(frames) == 10  # S221: it moves


# -- review regressions: line endings and order
def test_line_endings_and_order(tmp_path: Path) -> None:
    csv = put(tmp_path, "crlf.csv", 'start,end,text\r\n0,1000,"Hello"\r\n')
    assert [c.text for c in ingested(csv).chunks] == ["Hello"]  # S105: no quotes, no CR
    lrc = put(tmp_path, "crlf.lrc", "[by:x]\r\n[00:01.00] Hello\r\n")
    assert [c.text for c in ingested(lrc).chunks] == ["Hello"]  # S106: no CR
    cues = "1\n00:00:05,000 --> 00:00:06,000\nSECOND\n\n2\n00:00:01,000 --> 00:00:02,000\nFIRST\n\n"
    unsorted = put(tmp_path, "unsorted.srt", cues)
    assert [c.text for c in ingested(unsorted).chunks] == [
        "FIRST",
        "SECOND",
    ]  # S107: both, in time order


# -- A/V sync, picture to audio, through a burn
@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("rate", "ext", "codec"),
    [
        pytest.param(16000, "mkv", "ffv1", id="S089"),
        pytest.param(16000, "mp4", "h264", id="S090"),
        pytest.param(48000, "mkv", "ffv1", id="S091"),
        pytest.param(48000, "mp4", "h264", id="S092"),
    ],
)
def test_a_burn_keeps_picture_and_sound_together(
    files: Path,
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    rate: int,
    ext: str,
    codec: str,
) -> None:
    source = files / f"s{rate}.mp4"
    picture = ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2"]
    beep = ["-f", "lavfi", "-i", f"aevalsrc='if(between(t,1,1.2),sin(2*PI*1000*t),0)':s={rate}:d=2"]
    flash = "drawbox=x=0:y=0:w=24:h=24:color=white:t=fill:enable='gte(t,1)'"
    enc = ["-c:v", "libx264", "-bf", "2", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    _ = tool("ffmpeg", "-v", "error", "-y", *picture, *beep, "-vf", flash, *enc, str(source))
    cue = tmp_path / "sync.srt"
    _ = cue.write_text("1\n00:00:01,000 --> 00:00:02,000\nSYNC\n\n")
    out = f"sync{rate}.{ext}"
    assert (
        ff(
            capsys,
            "-i",
            str(source),
            "--burn-subs",
            str(cue),
            "--video-codec",
            codec,
            "-o",
            out,
            "-y",
        )[0]
        == 0
    )
    assert abs(sync(ffmpeg, ffprobe, out)) < 0.005  # flash and beep together


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_an_inverted_letterbox_keeps_its_bar(
    placements: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # S247, departed from: bash found no bar
    """The bar is read before the effects -- the source through the resize alone: inverted, it
    is white, and still the bar, the subtitles centred in it. bash read it after them and found
    none, so its text went to the margin -- on the same white bar (the margin lies in it). The
    note says black: the bar the picture has, before the effect recolours it and all else."""
    assert place(capsys, placements, "lbox.mp4", "plain", "regular.srt", "--vfx", "invert") == 1


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_pop_grows_only_the_word(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S053
    # between the pop's peak (1.39 s) and its settled frame (1.70 s): only the word changes, about its centre
    argv = [
        "-i",
        str(clip),
        "--burn-subs",
        fixture("sentences.ojf.json"),
        "--overlay-mode",
        "chunk-word",
        "--highlight-mode",
        "pop",
    ]
    assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_cwpop.mkv", "-y")[0] == 0
    ok, why = pop(ffmpeg, ffprobe, "ov_cwpop.mkv", 1.39, 1.70)
    assert ok, why


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_rainbow_font_paints_the_text(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--font-color rainbow: the text in hues apart (white shows none on the dark gradient)."""
    seen = {}
    for colour in ("white", "rainbow"):
        argv = ["-i", str(clip), "--burn-subs", fixture("regular.srt"), "--font-color", colour]
        assert ff(capsys, *argv, "--video-codec", "ffv1", "-o", "ov_font_motion.mkv", "-y")[0] == 0
        seen[colour] = hues(frame_at(ffmpeg, ffprobe, "ov_font_motion.mkv", 1.5)[0])
    assert seen == {"white": 0, "rainbow": seen["rainbow"]}
    assert seen["rainbow"] >= 3


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_the_rectangle_boxes_the_lit_word(
    clip: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--highlight-colorize rectangle: a white box where gold was -- the white text in both."""
    white: dict[str, int] = {}
    for look in ("gold", "rectangle"):
        argv = [
            "-i",
            str(clip),
            "--burn-subs",
            fixture("sentences.ojf.json"),
            "--overlay-mode",
            "chunk-word",
        ]
        argv += ["--highlight-colorize", look, "--video-codec", "ffv1", "-o", "ov_box.mkv", "-y"]
        assert ff(capsys, *argv)[0] == 0
        white[look] = coloured(frame_at(ffmpeg, ffprobe, "ov_box.mkv", 1.5)[0], (255, 255, 255))
    assert white["rectangle"] > white["gold"] + 500


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_blurred_bar_is_the_plan_s_as_rendered(
    ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--bblur fits 4:3 into 9:16: the bar under the picture, blurred, which no detection sees --
    the plan's, measured through the render's own head: the note's rows are the frame's.

    A white source, a grey band at its foot (grey: above cropdetect's black, so no bar of the
    source's own): in the frame, the band's last row is the picture's -- the blurred bar under
    it is bright. 4:2:0 at 640x480 into 360x640: 186."""
    band = "color=c=white:s=640x480:r=25:d=1,drawbox=y=ih-24:h=24:c=0x606060:t=fill"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        band,
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "ffv1",
        "edge.mkv",
    )
    argv = ["-i", "edge.mkv", "--burn-subs", fixture("regular.srt"), "--bblur", "-a", "9:16"]
    status, err = ff(
        capsys, *argv, "--margin-bottom", "99%", "--video-codec", "ffv1", "-o", "b.mkv", "-y"
    )
    assert status == 0, err
    _, err = ff(capsys, *argv, "--dry-run")  # the note: --margin-bottom silenced it above
    found = re.search(r"a blurred bar under the picture \((\d+) of 640 px\)", err)
    assert found, err
    frame, width, height = frame_at(ffmpeg, ffprobe, "b.mkv", 0.5)
    middle = [sum(frame[(y * width + x) * 3] for x in range(150, 210)) // 60 for y in range(height)]
    start = next(y for y in range(300, height) if middle[y] < 128)
    end = next(y for y in range(start, height) if middle[y] >= 128) - 1
    assert int(found[1]) == height - 1 - end == 186


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_source_s_own_bar_counts_in_a_blurred_fit(
    ffmpeg: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Read through the resize alone, its blur filled black: the source's own black bars (30
    rows of 240) count with the resize's, blurred fit or black -- the plan alone found 92."""
    boxed = "testsrc2=s=320x180:r=25:d=1,pad=320:240:0:30:color=black"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        boxed,
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "ffv1",
        "boxed.mkv",
    )
    rows = {}
    for blur in (["--bblur"], []):
        argv = [
            "-i",
            "boxed.mkv",
            "--burn-subs",
            fixture("regular.srt"),
            *blur,
            "-a",
            "9:16",
            "--dry-run",
        ]
        _, err = ff(capsys, *argv)
        found = re.search(r"a (blurred|black) bar under the picture \((\d+) of 320 px\)", err)
        assert found, err
        rows[found[1]] = int(found[2])
    assert rows["blurred"] == rows["black"] > 92


@pytest.mark.ffmpeg
@pytest.mark.parametrize("effect", ["invert", "blur", "chromatic-aberration"])
@pytest.mark.usefixtures("here")
def test_an_effect_does_not_hide_the_bar(
    ffmpeg: str, capsys: pytest.CaptureFixture[str], effect: str
) -> None:
    """The bar is read before the effects: an inverted one went unseen, a blur's spill took 6
    rows of 92, chromatic aberration's 1 -- each now the bar the resize left."""
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x240:r=25:d=1",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "ffv1",
        "four3.mkv",
    )
    argv = [
        "-i",
        "four3.mkv",
        "--burn-subs",
        fixture("regular.srt"),
        "-a",
        "9:16",
        "--vfx",
        effect,
        "--dry-run",
    ]
    _, err = ff(capsys, *argv)
    assert "a black bar under the picture (92 of 320 px)" in err, err
