"""Each reader against its rules, as recorded (docs/decisions.md's rows, the readers' docstrings).

Every expectation is worked by hand from a rule, not taken from a run: what a reader yields
before ffman's normalising (no trim, no sort but LRC's, no clamp, no cue dropped).
"""

import json
import re

import pytest
import subverter
from subverter import Cue, Reading, Timing

# --- the dispatcher: a .txt and an unknown format refused, in the words ffman's tests record


@pytest.mark.parametrize(
    ("fmt", "message"),
    [
        (
            "txt",
            "a .txt transcript has no timestamps; use whisper-cli -osrt, -ovtt, -olrc, -ocsv, -oj or -ojf, or WhisperX srt, vtt, tsv or json",
        ),
        ("xyz", "unsupported subtitle format '.xyz' (srt, vtt, lrc, csv, tsv, json)"),
    ],
)
def test_a_format_without_a_reader_is_refused(fmt: str, message: str) -> None:
    with pytest.raises(subverter.Error, match=f"^{re.escape(message)}$"):
        _ = subverter.read(fmt, b"x", f"a.{fmt}")


# --- SubRip and WebVTT: a cue opens at its --> line, closes at a blank line or the next cue


def test_srt_a_bom_and_crs_off_lines_joined_the_last_cue_closed_at_the_end() -> None:
    data = "\ufeff1\r\n00:00:01,000 --> 00:00:02,500\r\nHello\r\nthere\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nbye\r\n"
    assert subverter.read("srt", data.encode(), "a.srt") == Reading(
        ".srt", has_words=False, cues=(Cue(1000, 2500, "Hello there"), Cue(3000, 4000, "bye"))
    )


def test_vtt_minutes_alone_settings_ignored_tags_kept_the_next_cue_closing_one() -> None:
    data = "WEBVTT\n\n00:01.000 --> 00:02.000 align:start position:10%\n<i>hi</i>\n01:00:00.000 --> 01:00:01.500\nnext\n"
    assert subverter.read("vtt", data.encode(), "a.vtt").cues == (
        Cue(1000, 2000, "<i>hi</i>"),
        Cue(3_600_000, 3_601_500, "next"),
    )


def test_a_subrip_part_as_awk_reads_it_and_one_past_a_double_no_time() -> None:
    huge = "9" * 400  # its first digit past 10**308: no number, so no time
    data = f"1\nxx:00:01,000 --> {huge}:00:02,000\nx\n"  # "xx" has no leading number: 0
    assert subverter.read("srt", data.encode(), "a.srt").cues == (Cue(1000, None, "x"),)


def test_a_file_without_a_final_newline_loses_no_line() -> None:
    data = b"1\n00:00:01,000 --> 00:00:02,000\nlast"  # no newline after the last line
    assert subverter.read("srt", data, "a.srt").cues == (Cue(1000, 2000, "last"),)


# --- WhisperX --highlight_words: by structure, a run of one text a sentence, each <u> a word


def _srt(cues: list[tuple[str, str, str]]) -> bytes:
    return "".join(f"{n}\n{a} --> {z}\n{t}\n\n" for n, (a, z, t) in enumerate(cues, 1)).encode()


def test_highlighted_cues_become_sentences_and_words() -> None:
    data = _srt(
        [
            ("00:00:00,000", "00:00:00,500", "<u>Hello</u> world"),
            ("00:00:00,500", "00:00:01,000", "Hello <u>world</u>"),
            ("00:00:01,000", "00:00:01,500", "<u>Bye</u> now"),
            ("00:00:01,500", "00:00:02,000", "Bye <u>now</u>"),
        ]
    )
    assert subverter.read("srt", data, "a.srt") == Reading(
        "WhisperX --highlight_words .srt",
        has_words=True,
        cues=(Cue(0, 1000, "Hello world", "0"), Cue(1000, 2000, "Bye now", "1")),
        words=(
            Timing("0", 0, 500, "Hello"),
            Timing("0", 500, 1000, "world"),
            Timing("1", 1000, 1500, "Bye"),
            Timing("1", 1500, 2000, "now"),
        ),
    )


def test_an_underline_moving_back_starts_a_sentence_of_the_same_text() -> None:
    data = _srt(
        [
            ("00:00:00,000", "00:00:00,500", "<u>la</u> la"),
            ("00:00:00,500", "00:00:01,000", "la <u>la</u>"),
            ("00:00:01,000", "00:00:01,500", "<u>la</u> la"),
        ]
    )
    assert subverter.read("srt", data, "a.srt").cues == (
        Cue(0, 1000, "la la", "0"),
        Cue(1000, 1500, "la la", "1"),
    )


def test_an_underline_alone_is_no_highlighting() -> None:
    # <u> in a cue, but no two neighbours share a text: cues, as written
    data = _srt(
        [
            ("00:00:00,000", "00:00:01,000", "<u>one</u>"),
            ("00:00:01,000", "00:00:02,000", "two"),
        ]
    )
    reading = subverter.read("srt", data, "a.srt")
    assert (reading.has_words, reading.cues) == (
        False,
        (Cue(0, 1000, "<u>one</u>"), Cue(1000, 2000, "two")),
    )


def test_highlighted_a_cue_without_underline_adds_no_word_an_empty_run_no_sentence() -> None:
    data = _srt(
        [
            ("00:00:00,000", "00:00:00,500", "<u>a</u> b"),
            ("00:00:00,500", "00:00:01,000", "a <u>b</u>"),
            ("00:00:01,000", "00:00:01,500", "a b"),  # the same text, no underline: no word
            ("00:00:01,500", "00:00:02,000", ""),  # a run of no text: no sentence
            ("00:00:02,000", "00:00:02,500", ""),
        ]
    )
    reading = subverter.read("srt", data, "a.srt")
    assert reading.cues == (Cue(0, 1500, "a b", "0"),)
    assert reading.words == (Timing("0", 0, 500, "a"), Timing("0", 500, 1000, "b"))


# --- LRC: starts only, sorted; each line ends where the next starts, the last 3 s later


def test_lrc_lines_sorted_each_ending_at_the_next_the_last_3_s_later() -> None:
    huge = "9" * 400
    data = f"[00:03.50]b\n[00:01.00]a\nnot a line\n[{huge}:00.00]too far\n[00:05]c\n"
    assert subverter.read("lrc", data.encode(), "a.lrc").cues == (
        Cue(1000, 3500, "a"),
        Cue(3500, 5000, "b"),
        Cue(5000, 8000, "c"),
    )


def test_an_lrc_time_past_a_double_in_ms_drops_its_line() -> None:
    minutes = "9" * 306  # a number (under 10**308), but in ms (times 60 000) past a double's range
    data = f"[00:01.00]kept\n[{minutes}:00.00]dropped\n".encode()
    assert subverter.read("lrc", data, "a.lrc").cues == (Cue(1000, 4000, "kept"),)


# --- CSV and TSV: start, end, text in ms; a header names start and end, any order


@pytest.mark.parametrize(
    ("data", "cues"),
    [
        ('start,end,text\n0,1000,"a, b"\n', (Cue(0, 1000, "a, b"),)),  # RFC 4180 quoting
        ("speaker,end,start,text\nS1,2000,1000,hi\n", (Cue(1000, 2000, "hi"),)),  # by header
        ("500,900,x\n", (Cue(500, 900, "x"),)),  # no header: start, end, text
        ("start,end,text\nabc,900,y\n", (Cue(None, 900, "y"),)),  # no number: no time
        ("start,end,text\n1,2\n", ()),  # a record short of its text
    ],
)
def test_a_csv_read_by_its_columns(data: str, cues: tuple[Cue, ...]) -> None:
    assert subverter.read("csv", data.encode(), "a.csv").cues == cues


def test_a_tsv_quotes_nothing() -> None:
    data = 'start\tend\ttext\n0\t1000\t"as written"\n'
    assert subverter.read("tsv", data.encode(), "a.tsv").cues == (Cue(0, 1000, '"as written"'),)


def test_a_field_past_csvs_limit_is_refused_by_name() -> None:
    data = "start,end,text\n0,1," + "x" * (128 * 1024 + 1) + "\n"
    with pytest.raises(
        subverter.Error, match=r"^unreadable \.csv: big\.csv: field larger than field limit"
    ):
        _ = subverter.read("csv", data.encode(), "big.csv")


# --- whisper JSON: refused unless whisper-cli's or WhisperX's


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"{", "not valid JSON"),
        (b"[" * 100_000, "JSON nested too deeply to be a transcript"),
        (b"[]", "not a whisper-cli (.transcription) or WhisperX (.segments) JSON transcript"),
        (b'{"transcription": [{"tokens": [{"text": 5}]}]}', "unreadable whisper-cli -ojf JSON"),
    ],
)
def test_a_json_not_a_transcript_is_refused(data: bytes, message: str) -> None:
    with pytest.raises(subverter.Error, match=f"^{re.escape(message)}: a\\.json$"):
        _ = subverter.read("json", data, "a.json")


# --- whisper-cli: offsets in ms; with -ojf, words from tokens, DTW times where they hold


def _cli(entries: list[object], language: str = "en") -> bytes:
    return json.dumps({"result": {"language": language}, "transcription": entries}).encode()


def test_whisper_cli_without_tokens_is_cues_alone_their_text_as_written() -> None:
    data = _cli([{"offsets": {"from": 0, "to": 1500}, "text": " Hi"}])
    assert subverter.read("json", data, "a.json") == Reading(
        "whisper-cli JSON", has_words=False, cues=(Cue(0, 1500, " Hi", "0"),)
    )


def _token(text: object, start: int, end: int, dtw: object = None) -> dict[str, object]:
    token: dict[str, object] = {"text": text, "offsets": {"from": start, "to": end}}
    if dtw is not None:
        token["t_dtw"] = dtw
    return token


def test_words_from_tokens_timed_by_dtw_where_inside_and_in_order() -> None:
    # " He" + "llo" one word (a leading space starts one); [_TT_] skipped; t_dtw in 10 ms units
    tokens = [_token(" He", 0, 200, 5), _token("llo", 200, 400, 15), _token(" world", 400, 900, 50)]
    tokens.append(_token("[_TT_150]", 900, 1000))
    data = _cli([{"offsets": {"from": 0, "to": 1000}, "text": " Hello world", "tokens": tokens}])
    reading = subverter.read("json", data, "a.json")
    assert (reading.source, reading.has_words, reading.notes) == ("whisper-cli -ojf JSON", True, ())
    # each word from its DTW time to the next's; the last to the sentence's end
    assert reading.words == (Timing("0", 50, 500, " Hello"), Timing("0", 500, 1000, " world"))


def test_dtw_out_of_order_falls_back_to_the_offsets_and_says_so() -> None:
    tokens = [_token(" one", 0, 400, 60), _token(" two", 400, 900, 20)]  # 600 ms, then 200: back
    data = _cli([{"offsets": {"from": 0, "to": 1000}, "text": " one two", "tokens": tokens}])
    reading = subverter.read("json", data, "a.json")
    assert reading.words == (Timing("0", 0, 400, " one"), Timing("0", 400, 900, " two"))
    assert reading.notes == (
        "DTW word times were outside their sentence or not in order in 1 of 1 sentences: used token offsets there",
    )


def test_a_language_without_spaces_makes_every_token_a_word() -> None:
    tokens = [_token("東", 0, 300), _token("京", 300, 600)]
    data = _cli(
        [{"offsets": {"from": 0, "to": 600}, "text": "東京", "tokens": tokens}], language="ja"
    )
    assert subverter.read("json", data, "a.json").words == (
        Timing("0", 0, 300, "東"),
        Timing("0", 300, 600, "京"),
    )


# --- WhisperX: segments in seconds, their words their own; a value of the wrong kind is none


def test_whisperx_segments_and_words_in_seconds() -> None:
    words = [{"word": "Hi", "start": 0.5, "end": 0.8}, {"word": "there", "start": 0.9, "end": 1.25}]
    data = json.dumps(
        {"segments": [{"start": 0.5, "end": 1.25, "text": "Hi there", "words": words}]}
    )
    assert subverter.read("json", data.encode(), "a.json") == Reading(
        "WhisperX JSON",
        has_words=True,
        cues=(Cue(500, 1250, "Hi there", "0"),),
        words=(Timing("0", 500, 800, "Hi"), Timing("0", 900, 1250, "there")),
    )


def test_whisperx_values_as_typed() -> None:
    # a decimal string a number, rounded half up to the ms (1.0005 s: 1000.5 ms, 1001); true no
    # time; null text nothing; a number as text its JSON; a JSON number past a double no time
    segments = [
        {"start": "1.0005", "end": True, "text": None},
        {"start": 1e999, "end": 0, "text": 5},
    ]
    data = b'{"segments": ' + json.dumps(segments).replace("Infinity", "1e999").encode() + b"}"
    assert subverter.read("json", data, "a.json") == Reading(
        "WhisperX JSON", has_words=False, cues=(Cue(1001, None, "", "0"), Cue(None, 0, "5", "1"))
    )


@pytest.mark.parametrize(("seconds", "end"), [("1e305", 10**308), ("1e306", None)])
def test_a_time_past_a_doubles_range_is_none(seconds: str, end: int | None) -> None:
    # in ms: 10**308 is inside a double's range (its largest, ~1.8e308), 10**309 past it
    data = f'{{"segments": [{{"start": 0, "end": {seconds}, "text": "x"}}]}}'.encode()
    assert subverter.read("json", data, "a.json").cues == (Cue(0, end, "x", "0"),)


def test_a_token_or_word_not_an_object_is_no_value() -> None:
    tokens = [5, _token(" ok", 0, 500)]  # a malformed token: skipped
    cli = _cli([{"offsets": {"from": 0, "to": 500}, "text": " ok", "tokens": tokens}])
    assert subverter.read("json", cli, "a.json").words == (Timing("0", 0, 500, " ok"),)
    words = ["nope", {"word": "ok", "start": 0, "end": 0.5}]  # a malformed word: skipped
    wx = json.dumps({"segments": [{"start": 0, "end": 0.5, "text": "ok", "words": words}]}).encode()
    assert subverter.read("json", wx, "a.json").words == (Timing("0", 0, 500, "ok"),)
