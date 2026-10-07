import json
import re
import time
from fractions import Fraction
from pathlib import Path
from typing import Final

import pytest
from subverter.transcript import Chunk, Word

from ffman.errors import REFUSALS
from ffman.subs.ass import Style, script
from ffman.subs.srt import srt
from tests.support.ingesting import ingested
from tests.support.transcripts import HOSTILE


def put(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    _ = path.write_bytes(text.encode())
    return str(path)


def test_srt_crlf_bom_sorted_and_trimmed(tmp_path: Path) -> None:
    srt = "\ufeff1\r\n00:00:02,000 --> 00:00:04,000\r\n<i>Second</i>\r\n\r\n2\r\n00:00:01,000 --> 00:00:03,000\r\nFirst\r\n  line\r\n"
    t = ingested(put(tmp_path, "a.srt", srt))
    assert (t.fmt, t.source, t.has_words, t.words) == ("srt", ".srt", False, ())
    assert t.chunks == (
        Chunk(1000, 2000, "First line", ""),
        Chunk(2000, 4000, "Second", ""),
    )  # overlap ended by the next


def test_vtt_hours_settings_and_tags(tmp_path: Path) -> None:
    vtt = "WEBVTT\n\n1:00:01.500 --> 1:00:02.000 align:start\n{\\an8}Up \\N there\n"
    # {\an8} goes; ASS's \N stays (bash's clean() turns only jq's escaped \t and \n to spaces)
    assert ingested(put(tmp_path, "a.vtt", vtt)).chunks == (
        Chunk(3601500, 3602000, r"Up \N there", ""),
    )


def test_highlighted_cues_become_sentences_and_words(tmp_path: Path) -> None:
    cues = "".join(
        f"{i}\n00:00:0{i},000 --> 00:00:0{i + 1},000\n{text}\n\n"
        for i, text in enumerate(["<u>Hi</u> you", "Hi <u>you</u>", "<u>Hi</u> you"], 1)
    )
    t = ingested(put(tmp_path, "h.srt", cues))
    assert (t.source, t.has_words) == ("WhisperX --highlight_words .srt", True)
    assert [c.text for c in t.chunks] == [
        "Hi you",
        "Hi you",
    ]  # the underline moved back: a new sentence
    assert [(w.segment, w.text) for w in t.words] == [("0", "Hi"), ("0", "you"), ("1", "Hi")]


def test_lrc_and_tables(tmp_path: Path) -> None:
    lrc = ingested(put(tmp_path, "a.lrc", "[00:02.50]Two\n[00:01]One\nno stamp\n"))
    assert lrc.chunks == (
        Chunk(1000, 2500, "One", ""),
        Chunk(2500, 5500, "Two", ""),
    )  # the last: 3 s
    csv = ingested(put(tmp_path, "a.csv", 'start,end,text\n1000,2000,"a, ""b"""\n'))
    assert csv.chunks == (Chunk(1000, 2000, 'a, "b"', ""),)
    # a header names start and end, in any order (stage B; bash: only one starting with start)
    other = ingested(put(tmp_path, "b.csv", 'text,end,start\n"a",2000,1000\n'))
    assert other.chunks == (Chunk(1000, 2000, "a", ""),)
    # without one, the columns are start, end, text
    plain = ingested(put(tmp_path, "d.csv", "500,2000,1000\n"))
    assert plain.chunks == (Chunk(500, 2000, "1000", ""),)
    # a time that is not a number is no time (stage B; bash's awk read "x" as 0 ms)
    with pytest.raises(REFUSALS, match="no timed text found"):
        _ = ingested(put(tmp_path, "c.csv", "start,end,text\nx,2000,a\n"))
    tsv = ingested(put(tmp_path, "a.tsv", "0\t900\tno header\n"))
    assert tsv.chunks == (Chunk(0, 900, "no header", ""),)


def test_whisper_cli_words(tmp_path: Path) -> None:
    def token(text: str, a: int, z: int, dtw: float | None = None) -> dict[str, object]:
        made: dict[str, object] = {"text": text, "offsets": {"from": a, "to": z}}
        if dtw is not None:
            made["t_dtw"] = dtw
        return made

    doc = {"transcription": [
        {"offsets": {"from": 0, "to": 1000}, "text": " Hi there", "tokens": [token("[_BEG_]", 0, 0), token(" Hi", 0, 400, 10), token(" the", 400, 700, 50), token("re", 700, 1000, 70)]},
        {"offsets": {"from": 1000, "to": 2000}, "text": " Late", "tokens": [token(" Late", 1100, 1900, 500)]},
    ]}  # fmt: skip
    t = ingested(put(tmp_path, "a.json", json.dumps(doc)))
    assert (t.source, t.has_words) == ("whisper-cli -ojf JSON", True)
    assert t.words == (
        Word("0", 100, 500, "Hi"),
        Word("0", 500, 1000, "there"),
        Word("1", 1100, 1900, "Late"),
    )  # DTW, then offsets
    assert t.notes == (
        "DTW word times were outside their sentence or not in order in 1 of 2 sentences: used token offsets there",
    )
    plain = ingested(
        put(
            tmp_path,
            "b.json",
            json.dumps({"transcription": [{"offsets": {"from": "5", "to": 900}, "text": 7}]}),
        )
    )
    assert (plain.source, plain.chunks) == ("whisper-cli JSON", (Chunk(5, 900, "7", "0"),))


def test_whisperx_ties_and_gaps(tmp_path: Path) -> None:
    doc = {"segments": [{"start": 1, "end": 2, "text": "a b c", "words": [{"word": "a", "start": 1.0}, {"word": "b", "start": 1.0}, {"word": "c"}]}, {"start": 3, "end": 4, "text": "bare", "words": [{"word": "bare"}]}]}  # fmt: skip
    t = ingested(put(tmp_path, "x.json", json.dumps(doc)))
    assert [(w.text, w.start, w.end) for w in t.words] == [
        ("a", 1000, 1333),
        ("b", 1333, 1667),
        ("c", 1667, 2000),
    ]
    assert t.notes == (
        "2 words had no usable time of their own (untimed, tied, out of order or outside their sentence): placed between their neighbours",
        "1 sentences had no word timings: shown without word highlighting",
    )


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        ("a.txt", "x", "a .txt transcript has no timestamps"),
        ("a.xyz", "x", "unsupported subtitle format '.xyz'"),
        ("a.json", "{", "not valid JSON"),
        (
            "b.json",
            "[]",
            "not a whisper-cli (.transcription) or WhisperX (.segments) JSON transcript",
        ),
        (
            "c.json",
            '{"transcription": [{"tokens": [{"text": 5}]}]}',
            "unreadable whisper-cli -ojf JSON",
        ),
        ("a.srt", "1\n00:00:01,000 --> 00:00:01,000\nzero\n", "no timed text found"),
    ],
)
def test_refusals(tmp_path: Path, name: str, text: str, message: str) -> None:
    with pytest.raises(REFUSALS, match=re.escape(message)):
        _ = ingested(put(tmp_path, name, text))
    with pytest.raises(REFUSALS, match="no such file"):
        _ = ingested(str(tmp_path / "missing.srt"))


def test_ass_is_burned_as_it_is(tmp_path: Path) -> None:
    t = ingested(put(tmp_path, "a.ass", "[Script Info]\n"))
    assert (t.fmt, t.chunks, t.has_words) == ("ass", (), False)


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_what_holds_of_any_transcript(tmp_path: Path, name: str) -> None:
    try:
        t = ingested(put(tmp_path, name, HOSTILE[name]))
    except REFUSALS:
        return  # a refusal is an answer (stage A proved each one bash's)
    windows = {c.segment: (c.start, c.end) for c in t.chunks}
    assert all(c.start < c.end and c.text for c in t.chunks)
    assert all(
        a.end <= b.start for a, b in zip(t.chunks, t.chunks[1:], strict=False)
    )  # ordered, apart
    for w in t.words:
        start, end = windows[w.segment]
        assert start <= w.start <= w.end <= end, (w, start, end)
    for a, b in zip(t.words, t.words[1:], strict=False):
        assert a.segment != b.segment or a.start <= b.start


def test_a_reversed_cue_is_dropped(tmp_path: Path) -> None:
    srt = "1\n00:00:02,000 --> 00:00:01,000\nback\n\n2\n00:00:03,000 --> 00:00:04,000\nfore\n"
    assert ingested(put(tmp_path, "r.srt", srt)).chunks == (Chunk(3000, 4000, "fore", ""),)


def test_a_time_past_a_doubles_range_in_ms_is_no_time(tmp_path: Path) -> None:
    """1e306 s is a number, and 1e309 ms is none: that segment untimed, the other kept."""
    doc = {
        "segments": [
            {"start": 1e306, "end": 1e306, "text": "far"},
            {"start": 1, "end": 2, "text": "near"},
        ]
    }
    assert ingested(put(tmp_path, "x.json", json.dumps(doc))).chunks == (
        Chunk(1000, 2000, "near", "1"),
    )


def test_a_cue_the_next_one_starts_with_is_cut_to_nothing(tmp_path: Path) -> None:
    """Each cue ends where the next starts: one sharing its start is left no time, dropped."""
    srt = "1\n00:00:01,000 --> 00:00:03,000\nfirst\n\n2\n00:00:01,000 --> 00:00:02,000\nsecond\n"
    assert ingested(put(tmp_path, "s.srt", srt)).chunks == (Chunk(1000, 2000, "second", ""),)


def test_a_json_text_is_read_as_written(tmp_path: Path) -> None:
    """No @tsv between: a backslash stays one (bash's jq doubled it), a CR is a break (a literal \\r)."""
    doc = {
        "segments": [
            {"start": 1, "end": 2, "text": "a \\ b"},
            {"start": 2, "end": 3, "text": "c\rd"},
        ]
    }
    chunks = ingested(put(tmp_path, "t.json", json.dumps(doc))).chunks
    assert [c.text for c in chunks] == ["a \\ b", "c d"]


BACKSLASHED: Final = {  # one text with a backslash, in every format a transcript comes in
    "a.srt": "1\n00:00:01,000 --> 00:00:02,000\na\\b\n",
    "a.vtt": "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\na\\b\n",
    "a.lrc": "[00:01.00]a\\b\n",
    "a.csv": "start,end,text\n1000,2000,a\\b\n",
    "a.tsv": "start\tend\ttext\n1000\t2000\ta\\b\n",
    "cli.json": json.dumps(
        {
            "transcription": [
                {
                    "offsets": {"from": 1000, "to": 2000},
                    "text": "a\\b",
                    "tokens": [{"text": " a\\b", "offsets": {"from": 1000, "to": 2000}}],
                }
            ]
        }
    ),
    "wx.json": json.dumps(
        {
            "segments": [
                {
                    "start": 1,
                    "end": 2,
                    "text": "a\\b",
                    "words": [{"word": "a\\b", "start": 1, "end": 2}],
                }
            ]
        }
    ),
}


@pytest.mark.parametrize("name", list(BACKSLASHED))
def test_a_backslash_is_one_in_every_format(tmp_path: Path, name: str) -> None:
    """Read once, burned as one / (no override from the text), attached as itself."""
    t = ingested(put(tmp_path, name, BACKSLASHED[name]))
    assert [c.text for c in t.chunks] == ["a\\b"]
    assert all(w.text == "a\\b" for w in t.words)
    burned = script(t, 1920, 1080, Style())[0]
    assert "a/b" in burned
    assert "a//b" not in burned
    assert "\na\\b\n" in srt(t.chunks, None)


PAST_LIMITS: Final = {  # past what Python's float, int and csv hold, or JSON's depth: never a crash
    "a huge integer time": (
        "x.json",
        json.dumps({"segments": [{"start": 10**400, "end": 10**401, "text": "a"}]}),
    ),
    "nested 100000 deep": ("x.json", "[" * 100_000 + "]" * 100_000),
    "a 200 kB CSV field": ("x.csv", "start,end,text\n0,1000," + "a" * 200_000 + "\n"),
    "a 200 kB TSV field": ("x.tsv", "start\tend\ttext\n0\t1000\t" + "a" * 200_000 + "\n"),
    "LRC minutes past a double": ("x.lrc", "[" + "9" * 400 + ":00.00]a\n"),
    "SRT hours past a double": (
        "x.srt",
        "1\n" + "9" * 400 + ":00:00,000 --> " + "9" * 401 + ":00:00,000\na\n",
    ),
}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("a huge integer time", "no timed text found"),  # no number, so no time
        ("nested 100000 deep", "JSON nested too deeply to be a transcript"),
        ("a 200 kB CSV field", "unreadable .csv: .*field larger than field limit"),
        ("a 200 kB TSV field", "unreadable .tsv: .*field larger than field limit"),
        ("LRC minutes past a double", "no timed text found"),
        ("SRT hours past a double", "no timed text found"),
    ],
)
def test_what_python_cannot_hold_is_refused_not_a_crash(
    tmp_path: Path, case: str, message: str
) -> None:
    name, text = PAST_LIMITS[case]
    with pytest.raises(REFUSALS, match=message):
        _ = ingested(put(tmp_path, name, text))


def test_a_huge_dtw_time_is_none_and_the_offsets_used(tmp_path: Path) -> None:
    token = {"text": " a", "offsets": {"from": 0, "to": 900}, "t_dtw": 10**400}
    doc = {"transcription": [{"offsets": {"from": 0, "to": 900}, "text": " a", "tokens": [token]}]}
    t = ingested(put(tmp_path, "x.json", json.dumps(doc)))
    assert [(w.start, w.end) for w in t.words] == [(0, 900)]


@pytest.mark.parametrize(
    ("name", "text", "start"),
    [  # each read through a float before (stage A): 500, 500, 500, 999, 999
        ("a.srt", "1\n00:00:00,5005 --> 00:00:01,000\na\n", 501),
        ("a.lrc", "[00:00.5005]a\n[00:01.00]b\n", 501),
        ("wx.json", json.dumps({"segments": [{"start": 0.5005, "end": 1, "text": "a"}]}), 501),
        ("a.csv", "start,end,text\n999.5,2000,a\n", 1000),
        (
            "cli.json",
            json.dumps({"transcription": [{"offsets": {"from": 999.5, "to": 2000}, "text": "a"}]}),
            1000,
        ),
    ],
)
def test_a_time_is_its_decimal_rounded_half_up_to_the_ms(
    tmp_path: Path, name: str, text: str, start: int
) -> None:
    """Read exactly from the text, never a float; one rule, every format: half up, whole ms."""
    assert ingested(put(tmp_path, name, text)).chunks[0].start == start


def test_the_srt_clip_is_the_duration_floored_to_the_ms() -> None:
    """No cue outlasts the media: 1.005 s is 1005 ms (bash truncated a float: 1004)."""
    assert "00:00:00,000 --> 00:00:01,005" in srt((Chunk(0, 2000, "a", ""),), Fraction("1.005"))
    assert srt((Chunk(1005, 1500, "at the end", ""),), Fraction("1.005")) == ""
    assert "00:00:00,000 --> 00:00:02,000" in srt((Chunk(0, 2000, "a", ""),), None)


BOUNDLESS: Final = {  # a number no reader may expand: an exponent, or digits past int's 4300
    "x.csv": "start,end,text\n1e999999999,2000,a\n1e-999999999,1000,b\n" + "9" * 5000 + ",3000,c\n",
    "x.lrc": "[" + "9" * 5000 + ":00.00]a\n[00:01.00]b\n",
    "x.json": '{"segments": [{"start": 1e999999999, "end": 2, "text": "a"}, {"start": 0.'
    + "1" * 5000
    + ', "end": 1e-999999999, "text": "b"}, {"start": 0, "end": 1, "text": "c"}]}',
    "y.json": json.dumps(
        {
            "segments": [
                {"start": "1e999999999", "end": 2, "text": "a"},
                {"start": 0, "end": 1, "text": "b"},
            ]
        }
    ),
}


@pytest.mark.parametrize(
    ("name", "texts"), [("x.csv", ["b"]), ("x.lrc", ["b"]), ("x.json", ["c"]), ("y.json", ["b"])]
)
def test_a_huge_or_long_number_is_read_in_bounded_work(
    tmp_path: Path, name: str, texts: list[str]
) -> None:
    """Past a double, no time; under one, zero; 5000 digits read as 400 and a sticky 1 -- at once."""
    began = time.monotonic()
    assert [c.text for c in ingested(put(tmp_path, name, BOUNDLESS[name])).chunks] == texts
    assert time.monotonic() - began < 2  # 10**999999999 never built


def test_an_lrc_time_its_parts_in_range_past_a_double_is_none(tmp_path: Path) -> None:
    """10**306 minutes reads; as milliseconds (x 60 000) it is past a double: no line."""
    lrc = "[1" + "0" * 306 + ":00.00]a\n[00:01.00]b\n"
    assert [c.text for c in ingested(put(tmp_path, "x.lrc", lrc)).chunks] == ["b"]


@pytest.mark.parametrize("part", ["1e999999999", "9" * 5000])
def test_a_subrip_part_past_a_double_is_no_time(tmp_path: Path, part: str) -> None:
    with pytest.raises(REFUSALS, match="no timed text found"):
        _ = ingested(put(tmp_path, "x.srt", f"1\n00:00:{part} --> 00:00:02,000\na\n"))
