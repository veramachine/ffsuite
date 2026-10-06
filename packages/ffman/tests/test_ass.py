import re
import unicodedata
from fractions import Fraction

import pytest
from subverter.transcript import Chunk, Transcript, Word

from ffman.jobs.convert.options import validate
from ffman.options import CONVERT, parse
from ffman.subs.ass import Style, script
from ffman.subs.colorize import GOLD, MOTIONS, RECTANGLE, WHITE, Colour, colour_at
from ffman.subs.metrics import Metrics

ONE = Transcript(
    "srt", ".srt", has_words=False, chunks=(Chunk(1000, 2000, "a {b} \\c", ""),), words=(), notes=()
)
SIXTY_WORDS = Transcript(
    "srt",
    ".srt",
    has_words=False,
    chunks=(Chunk(0, 1000, "word " * 60, ""),),
    words=(),
    notes=(),
)  # past the top of a narrow frame
WORDED = Transcript(
    "json", "WhisperX JSON", has_words=True, chunks=(Chunk(0, 1000, "hi you", "0"), Chunk(1000, 1500, "bare", "1")),
    words=(Word("0", 0, 100, "hi"), Word("0", 100, 1000, "you")), notes=(),
)  # fmt: skip


def events(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("Dialogue:")]


def test_the_plain_header_follows_mpv() -> None:
    text, notes = script(ONE, 1920, 1080, Style())
    # ffman breaks the lines (WrapStyle 2: libass does not), kerned (libass's default is not)
    assert (
        "PlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\nKerning: yes\n"
        in text
    )
    # 57; not bold; outline 57 * 1.65 / 38; no shadow; margins 5% of 1920 and 5.573% of 1080
    assert (
        "Style: Default,IBM Plex Sans,57,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2.475,0,2,96,96,60,-1"
        in text
    )
    assert events(text) == [
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,a (b) /c"
    ]  # no override tags from text
    assert notes == ()


def test_the_highlighting_header() -> None:
    text, _ = script(ONE, 1920, 1080, Style("chunk-word"))
    assert "WrapStyle: 2\n" in text
    assert (
        ",64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1.5238095238095237,2,96,96,60,-1"
        in text
    )


def test_a_popped_word() -> None:
    text, _ = script(WORDED, 1920, 1080, Style("word-highlight", "pop"))
    first = events(text)[0]
    # 100 ms, no frame given: up half of it, back by its end (bash's settle ran 100 ms past it)
    assert first.startswith(
        # at 64 the line is at 1080 - 60 - 64 * 0.6 = 981.6, exactly
        "Dialogue: 0,0:00:00.00,0:00:00.10,Default,,0,0,0,,{\\an5\\pos(960,981.6)\\1c&H00FFFFFF&\\t(0,50,"
    )
    assert "\\fscx118\\fscy118)\\t(50,100,1.5,\\fscx100\\fscy100)}hi" in first  # a lone word: 118%
    assert events(text)[-1].endswith("}bare")  # a sentence without word timings: plain, as it is


def test_chunk_word_draws_the_word_on_its_own_layer() -> None:
    lines = events(script(WORDED, 1920, 1080, Style("chunk-word"))[0])
    assert (
        # the same 981.6 as a wrapped line's y: rounded, 982
        "Dialogue: 0,0:00:00.10,0:00:01.00,Default,,0,0,0,,{\\an5\\pos(960,981.6)}hi {\\alpha&HFF&}you{\\alpha&H00&}"
        in lines
    )
    assert any(
        line.startswith("Dialogue: 1,0:00:00.10,0:00:01.00") and "}you{\\r\\alpha&HFF&}" in line
        for line in lines
    )


def test_in_a_bar_and_without_spaces() -> None:
    lines = events(script(ONE, 1920, 1080, Style(bar_y=Fraction(1040)))[0])
    assert lines == [
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an5\\pos(960,1040)}a (b) /c"
    ]
    ja_words = (Word("0", 0, 300, "日本"), Word("0", 300, 900, "語"))
    ja = Transcript(
        "json",
        "x",
        has_words=True,
        chunks=(Chunk(0, 900, "日本語", "0"),),
        words=ja_words,
        notes=(),
    )
    assert "}日本{\\alpha&HFF&}語{\\alpha&H00&}" in "\n".join(
        events(script(ja, 1920, 1080, Style("chunk-word"))[0])
    )


def test_text_past_the_top_is_noted() -> None:
    _, notes = script(SIXTY_WORDS, 320, 1080, Style(size=Fraction(200)))
    assert notes == (
        "1 sentences wrap past the top of the frame at --font-size 200: use a smaller --font-size",
    )


def test_a_size_is_written_as_its_value() -> None:
    """``--font-size 0200.0`` is 200 in the style and the note: bash wrote the text as typed."""

    def size(text: str) -> Style:
        argv = ["-i", "a.mp4", "--burn-subs", "s.srt", "--font-size", text]
        return Style(size=validate(parse("convert", CONVERT, argv)).font_size)

    text, notes = script(SIXTY_WORDS, 320, 1080, size("0200.0"))
    assert "\nStyle: Default,IBM Plex Sans,200," in text
    assert " at --font-size 200: " in notes[0]
    assert "\nStyle: Default,IBM Plex Sans,57.5," in script(ONE, 1920, 1080, size("057.50"))[0]


def test_a_long_sentence_wraps_and_is_noted() -> None:
    words = tuple(Word("0", 100 * k, 100 * k + 100, f"word{k}") for k in range(40))
    text = " ".join(w.text for w in words)
    long = Transcript(
        "json", "x", has_words=True, chunks=(Chunk(0, 4000, text, "0"),), words=words, notes=()
    )
    script_text, notes = script(long, 320, 1080, Style("chunk-word", size=Fraction(120)))
    ys = {
        line.split("pos(")[1].split(")")[0]
        for line in events(script_text)
        if line.startswith("Dialogue: 0,")
    }
    assert len(ys) > 1  # wrapped: one event a line, each at its own y
    assert notes == (
        "1 sentences wrap past the top of the frame at --font-size 120: use a smaller --font-size",
    )


def test_the_centre_is_placed_exactly() -> None:
    """A 1900 x 1034 frame: a 1985-wide canvas, so its centre is 992.5 (bash truncated: 992)."""
    text = script(ONE, 1900, 1034, Style("word"))[0]  # placed by \\pos (plain: by the margins)
    assert "PlayResX: 1985\n" in text
    assert "\\pos(992.5," in text


def lines_of(text: str, mode: str = "chunk-word", metrics: Metrics | None = None) -> list[str]:
    """``text``'s lines as the script breaks it at 1920 x 1080 (size 64; plain, 57)."""
    chunk = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 1000, text, ""),), words=(), notes=()
    )
    rendered = script(chunk, 1920, 1080, Style(mode), metrics=metrics)[0]
    bodies = [
        re.sub(r"\{[^}]*\}", "", line.split(",", 9)[9])
        for line in rendered.splitlines()
        if line.startswith("Dialogue: 0,")
    ]
    return [part for body in bodies for part in body.split("\\N")]


def test_a_line_holds_the_bbc_width_estimated() -> None:
    """No metrics: 0.55 sizes a glyph; the BBC's line, 1.2 x 1080 = 1296 (inside 1728) --
    36 glyphs of 35.2 are 1267.2, 37 are 1302.4."""
    fits, over = "abcdefgh abcdefg abcdefg abcdefg abc", "abcdefgh abcdefg abcdefg abcdefg abcd"
    assert (len(fits), len(over)) == (36, 37)
    assert (len(lines_of(fits)), len(lines_of(over))) == (1, 2)


def test_a_line_holds_the_bbc_width_measured() -> None:
    """Metrics: a spans a size (64), a space nothing -- 4 words of 5 (1280) fit, 5 do not."""
    metrics = Metrics({ord("a"): 1300, ord(" "): 0}, 1300)
    assert lines_of(" ".join(["aaaaa"] * 8), metrics=metrics) == ["aaaaa aaaaa aaaaa aaaaa"] * 2


def test_plain_breaks_its_lines_in_one_event() -> None:
    """libass breaks only at spaces here, so plain's lines are broken by ffman: \\N, WrapStyle 2."""
    text = " ".join(["subtitles"] * 12)
    chunk = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 1000, text, ""),), words=(), notes=()
    )
    events = [
        line
        for line in script(chunk, 1920, 1080, Style())[0].splitlines()
        if line.startswith("Dialogue:")
    ]
    assert len(events) == 1
    assert "\\N" in events[0]


def test_unspaced_text_breaks_between_characters() -> None:
    """Japanese has no space: it breaks between characters (libass would not: no libunibreak)."""
    lines = lines_of("日本語の文章は単語の間にスペースを入れないので一行がとても長くなる", "plain")
    assert len(lines) == 2  # 33 characters, a size each (57): 22 a line
    assert "".join(lines) == "日本語の文章は単語の間にスペースを入れないので一行がとても長くなる"


@pytest.mark.parametrize(
    "unit",
    [
        "e\u0301",  # a decomposed accent
        "\u0e27\u0e31",  # Thai: a vowel mark of combining class 0
        "\u0e2a\u0e4d",  # Thai: a mark of class 0 again
        "\u0938\u094d\u0924\u0947",  # Devanagari: a conjunct (sa, virama, ta) and its vowel sign
        "\U0001f468\u200d\U0001f469\u200d\U0001f467",  # an emoji family: joiners
    ],
)
def test_a_line_never_breaks_inside_a_cluster(unit: str) -> None:
    """Unspaced text breaks between characters, never inside a cluster: no line opens on a
    mark or a joiner, none ends on a virama or a joiner (an x first: breaks fall mid-unit)."""
    text = "x" + unit * 60
    lines = lines_of(text, "plain")
    assert len(lines) > 1
    assert "".join(lines) == text
    for line in lines:
        assert not unicodedata.category(line[0]).startswith("M")
        assert line[0] != "\u200d"
        assert line[-1] not in ("\u200d", "\u094d")


def test_a_pop_is_done_by_its_last_frame() -> None:
    """100 ms at 25 fps: its last frame shows at 60 ms or later -- up 30, back by 60."""
    first = events(
        script(WORDED, 1920, 1080, Style("word-highlight", "pop"), frame=Fraction(1, 25))[0]
    )[0]
    rise, settle = "\\t(0,30,0.5,\\fscx118\\fscy118)", "\\t(30,60,1.5,\\fscx100\\fscy100)"
    assert f"\\1c&H00FFFFFF&\\t(0,30,\\1c&H0000D7FF&){rise}{settle}}}hi" in first


def test_a_word_no_longer_than_a_frame_is_gold_at_once() -> None:
    """No time to animate before its last frame: gold, unscaled -- and no \\t ending at 0,
    which libass would run to the event's end."""
    first = events(
        script(WORDED, 1920, 1080, Style("word-highlight", "pop"), frame=Fraction(1, 10))[0]
    )[0]
    assert "\\1c&H0000D7FF&}hi" in first
    assert "\\t(" not in first


def test_plain_fades_by_its_last_frame() -> None:
    first = events(script(WORDED, 1920, 1080, Style("word-highlight"), frame=Fraction(1, 25))[0])[0]
    assert (
        "\\1c&H00FFFFFF&\\t(0,60,\\1c&H0000D7FF&)}hi" in first
    )  # 80 ms, but its last frame is at 60


def test_the_peak_is_exact() -> None:
    """1 + 0.45/chars: 7 letters, 106.43% (bash: 106)."""
    assert "\\fscx106.42857142857143\\fscy106.42857142857143" in popped(
        ["abcdefg", "hi"], "abcdefg hi"
    )


JAPANESE = "日本語の文章は単語の間にスペースを入れないので一行がとても長くなることがありますね、そうでしょう。"


def test_an_unspaced_run_breaks_inside_spaced_text() -> None:
    """A run wider than a line breaks inside, where UAX #14 allows: no line opens on 、 or 。."""
    lines = lines_of("Whisper says: " + JAPANESE, "plain")
    assert len(lines) > 2
    assert not any(line[0] in "、。" for line in lines)
    assert all(
        len(line) <= 1296 // 57 + 1 for line in lines[1:]
    )  # a size a character (57): 22 a line


def test_a_word_wider_than_a_line_breaks_rather_than_overflow() -> None:
    """Latin letters never part -- but a word wider than a line does, between its letters."""
    lines = lines_of("a" * 80, "plain")  # 80 x 0.55 x 57 = 2508, the line 1296
    assert [len(line) for line in lines] == [41, 39]  # 41 x 31.35 = 1285.35


def test_timed_words_keep_their_punctuation() -> None:
    """Whisper times 、 as a word: no line opens on it. At 64, a line holds 1296 / 64 = 20.25
    wide characters: 20 one-character words fill it, and the 21st, 、, goes down with the 20th."""
    texts = ["日"] * 20 + ["、", "本"]
    words = tuple(Word("0", 100 * k, 100 * k + 90, t) for k, t in enumerate(texts))
    chunk = Chunk(0, 100 * len(texts), "".join(texts), "0")
    t = Transcript("json", ".json", has_words=True, chunks=(chunk,), words=words, notes=())
    rendered = script(t, 1920, 1080, Style("chunk-word"))[0]
    starts = [line for line in rendered.splitlines() if line.startswith("Dialogue: 0,0:00:00.00")]
    lines = [re.sub(r"\{[^}]*\}", "", line.split(",", 9)[9]) for line in starts]
    assert lines == ["日" * 19, "日、本"]


def test_a_word_wider_than_a_line_starts_one_of_its_own() -> None:
    """CSS's overflow-wrap: break-word -- moved to a line of its own first, then broken there."""
    lines = lines_of("Hi " + "a" * 80, "plain")
    assert lines == ["Hi", "a" * 41, "a" * 39]


def test_a_mark_is_estimated_as_nothing() -> None:
    """40 decomposed accented letters: 40 glyphs of 0.55 x 57 = 1254, within 1296 -- one line
    (the marks counted as glyphs, two)."""
    assert len(lines_of("e\u0301" * 40, "plain")) == 1


def popped(texts: list[str], joined: str) -> str:
    """A chunk-word pop script: each word a second."""
    words = tuple(Word("0", 1000 * k, 1000 * k + 1000, t) for k, t in enumerate(texts))
    chunk = Chunk(0, 1000 * len(texts), joined, "0")
    t = Transcript("json", ".json", has_words=True, chunks=(chunk,), words=words, notes=())
    return script(t, 1920, 1080, Style("chunk-word", "pop"))[0]


def test_a_word_with_no_space_beside_it_is_not_scaled() -> None:
    """A pop grows into the space beside it: abutting words (unspaced text) have none -- gold,
    timed, unscaled (rendered, a scaled one covered its neighbours' ink); spaced words grow."""
    unspaced = popped(["日", "本", "語"], "日本語")
    assert "Dialogue: 1," in unspaced
    assert "\\fscx" not in unspaced
    assert "\\fscx" in popped(["word", "pop"], "word pop")


def test_the_peak_counts_glyphs_not_marks() -> None:
    """A decomposed é is one glyph: café peaks alike, however it is encoded."""
    peak = re.compile(r"\\fscx([0-9.]+)")
    composed = peak.findall(popped(["caf\u00e9", "x"], "caf\u00e9 x"))
    assert composed == peak.findall(popped(["cafe\u0301", "x"], "cafe\u0301 x"))
    assert composed[0] != "100"


def test_the_highlight_takes_the_colour_given() -> None:
    """--highlight-colorize: the lit word fades to it, not to gold."""
    t = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 1000, "hi", ""),), words=(), notes=()
    )
    lit = script(t, 1920, 1080, Style("word-highlight", colorize=Colour(0x00FF00)))[0]
    assert "\\t(0,80,\\1c&H0000FF00&)}hi" in lit
    assert GOLD.ass() not in lit


def test_a_motion_paints_each_letter() -> None:
    """Each letter its block: white, faded in to its colour, then its keyframes; the pop's scale
    in the block before them all."""
    words = (Word("0", 0, 1000, "wave"), Word("0", 1000, 2000, "on"))
    t = Transcript(
        "json",
        ".json",
        has_words=True,
        chunks=(Chunk(0, 2000, "wave on", "0"),),
        words=words,
        notes=(),
    )
    lit = next(
        line
        for line in script(t, 1920, 1080, Style("chunk-word", "pop", colorize=MOTIONS["rainbow"]))[
            0
        ].splitlines()
        if line.startswith("Dialogue: 1,0:00:00.00")
    )
    found = re.finditer(r"\{([^}]*)\}([^{]*)", lit.split(",", 9)[9])
    blocks = [(str(m[1]), str(m[2])) for m in found]
    painted = [(tags, text) for tags, text in blocks if tags.startswith("\\1c&H00FFFFFF&")]
    assert "".join(text for _, text in painted) == "wave"
    assert all("\\t(" in tags for tags, _ in painted)
    assert "\\fscx" in blocks[1][0]  # the block before the letters: alpha, the pop


def test_a_motion_keeps_a_lit_chunk_s_spaces() -> None:
    """word-highlight, no word timings: the whole chunk lit, its spaces between the letters."""
    t = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 1000, "a b", ""),), words=(), notes=()
    )
    lit = script(t, 1920, 1080, Style("word-highlight", colorize=MOTIONS["lsd"]))[0]
    text = re.sub(
        r"\{[^}]*\}",
        "",
        next(line for line in lit.splitlines() if line.startswith("Dialogue:")).split(",", 9)[9],
    )
    assert text == "a b"


def lit_run(text: str, ms: int) -> tuple[list[int], tuple[str, ...]]:
    """word-highlight, no word timings, in lsd: each letter's \\t count, and the notes."""
    t = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, ms, text, ""),), words=(), notes=()
    )
    lit, notes = script(t, 1920, 1080, Style("word-highlight", colorize=MOTIONS["lsd"]))
    event = next(line for line in lit.splitlines() if line.startswith("Dialogue:")).split(",", 9)[9]
    blocks = [str(m[0]) for m in re.finditer(r"\{\\1c&H00FFFFFF&[^}]*\}", event)]
    return [block.count("\\t(") for block in blocks], notes


def test_a_run_too_long_to_move_holds_its_hues() -> None:
    """Over the budget (a hostile 2,000 letters lit 60 s: 19 MB of script), each letter keeps
    its fade alone, and the user is told; a cue moves."""
    held, notes = lit_run("a" * 2000, 60_000)
    assert set(held) == {1}
    assert notes == ("1 runs too long to move: their hues held still",)
    moving, notes = lit_run("a cue of some length", 4000)
    assert min(moving) > 1
    assert notes == ()


NAVY = Colour(0x1E3A8A)  # dark: its outline white


def highlighted(style: Style) -> str:
    words = (Word("0", 0, 1000, "one"), Word("0", 1000, 2000, "two"))
    t = Transcript(
        "json",
        ".json",
        has_words=True,
        chunks=(Chunk(0, 2000, "one two", "0"),),
        words=words,
        notes=(),
    )
    return script(t, 1920, 1080, style)[0]


def test_the_text_s_colours_in_the_style() -> None:
    """--font-color, and its outline: given, or black or white, whichever contrasts more."""
    assert ",&H008A3A1E,&H000000FF,&H00FFFFFF,&H80000000," in highlighted(
        Style("chunk-word", text=NAVY)
    )
    given = highlighted(Style("chunk-word", text=NAVY, outline=Colour(0xFF0000)))
    assert ",&H008A3A1E,&H000000FF,&H000000FF,&H80000000," in given


def test_the_highlight_fades_in_from_the_text_s_colours() -> None:
    """From navy and its white outline to gold and gold's own, black: not from white."""
    lit = highlighted(Style("chunk-word", text=NAVY))
    assert "\\1c&H008A3A1E&\\3c&H00FFFFFF&\\t(0,80,\\1c&H0000D7FF&\\3c&H00000000&)" in lit


def test_the_default_writes_no_outline() -> None:
    """White text and gold: both outlined black -- no \\3c."""
    assert "\\3c" not in highlighted(Style("chunk-word"))


def test_a_given_outline_is_everyone_s() -> None:
    assert "\\3c" not in highlighted(Style("chunk-word", text=NAVY, outline=WHITE))


def test_a_motion_s_letters_share_its_outline() -> None:
    """Whatever hue each starts on: the motion's one (black), from the text's (white)."""
    lit = highlighted(Style("chunk-word", text=NAVY, colorize=MOTIONS["rainbow"]))
    outlines = set(re.findall(r"\\t\(0,\d+,\\1c&H[0-9A-F]+&\\3c(&H[0-9A-F]+&)\)", lit))
    assert outlines == {"&H00000000&"}


def test_a_highlight_the_text_s_colour_is_noted() -> None:
    _, notes = script(ONE, 1920, 1080, Style("word-highlight", text=GOLD))
    assert notes == ("the highlight is the text's colour: it shows nothing",)
    assert script(ONE, 1920, 1080, Style("plain", text=GOLD))[1] == ()  # no highlight there


def dialogues(text: str) -> list[tuple[int, str, str]]:
    """Each event's layer, start and text."""
    found: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            found.append((int(fields[0].split()[1]), fields[1], fields[9]))
    return found


def first_colours(event: str, tag: str) -> list[str]:
    """Each painted letter's first ``tag`` colour, in order."""
    return [
        str(m[1])
        for m in re.finditer(r"\{\\" + tag + r"(&H[0-9A-F]+&)(?:\\t\([^}]*)?\}[^{\\]", event)
    ]


def test_a_font_in_motion_paints_every_letter() -> None:
    """Each letter its chain, its place across the subtitle: a rainbow over all of it."""
    t = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(500, 3000, "ab cd", ""),), words=(), notes=()
    )
    ((_, _, event),) = dialogues(script(t, 1920, 1080, Style(text=MOTIONS["rainbow"]))[0])
    expected = [colour_at(MOTIONS["rainbow"], k, 4, 500).ass() for k in range(4)]
    assert first_colours(event, "1c") == expected
    assert event.count("\\t(") >= 4


def test_a_letter_s_hue_runs_on_from_event_to_event() -> None:
    """chunk-word redraws the line each word: a letter starts each event where it was."""
    words = (Word("0", 0, 700, "one"), Word("0", 700, 1400, "two"))
    t = Transcript(
        "json",
        ".json",
        has_words=True,
        chunks=(Chunk(0, 1400, "one two", "0"),),
        words=words,
        notes=(),
    )
    layer0 = [
        e
        for e in dialogues(script(t, 1920, 1080, Style("chunk-word", text=MOTIONS["lsd"]))[0])
        if e[0] == 0
    ]
    second = next(text for _, start, text in layer0 if start == "0:00:00.70")
    # "one" (letters 0-2 of 6) is shown in the second event, from 700 ms
    assert first_colours(second, "1c")[:3] == [
        colour_at(MOTIONS["lsd"], k, 6, 700).ass() for k in range(3)
    ]


def test_an_outline_in_motion_runs_through_the_highlight() -> None:
    """Every visible letter's outline its chain, the lit word's too; no switch -- it is given."""
    lit = highlighted(Style("chunk-word", outline=MOTIONS["iridescent"]))
    layer1 = [text for layer, _, text in dialogues(lit) if layer == 1]
    assert all("\\3c" in text for text in layer1)
    assert "\\t(0,80,\\1c&H0000D7FF&)" in lit  # the gold fade, no \3c switch in it
    assert all(first_colours(text, "3c") for layer, _, text in dialogues(lit) if layer == 0)


def test_the_lit_word_fades_from_each_letter_s_own_colour() -> None:
    """A font in motion: each lit letter from its colour then, to gold."""
    lit = highlighted(Style("chunk-word", text=MOTIONS["rainbow"]))
    first = next(
        text for layer, start, text in dialogues(lit) if layer == 1 and start == "0:00:00.00"
    )
    starts = re.findall(r"\\1c(&H[0-9A-F]+&)\\t\(0,80,\\1c&H0000D7FF&\)", first)
    assert starts == [colour_at(MOTIONS["rainbow"], k, 6, 0).ass() for k in range(3)]


def test_a_long_text_in_motion_holds_its_hues() -> None:
    """The budget is the text's too: a long subtitle, long shown, in lsd, held and noted."""
    t = Transcript(
        "srt",
        ".srt",
        has_words=False,
        chunks=(Chunk(0, 60_000, "a" * 400, ""),),
        words=(),
        notes=(),
    )
    text, notes = script(t, 1920, 1080, Style(text=MOTIONS["lsd"]))
    assert notes == ("1 runs too long to move: their hues held still",)
    assert "\\t(" not in text


def boxed(style: Style, texts: tuple[str, ...] = ("one", "two"), joined: str = "one two") -> str:
    words = tuple(Word("0", 1000 * k, 1000 * k + 1000, w) for k, w in enumerate(texts))
    t = Transcript(
        "json",
        ".json",
        has_words=True,
        chunks=(Chunk(0, 1000 * len(texts), joined, "0"),),
        words=words,
        notes=(),
    )
    return script(t, 1920, 1080, style)[0]


def test_the_rectangle_s_style() -> None:
    """A second style, BorderStyle 3, no shadow, its colours swapped -- the default has none."""
    text = boxed(Style("chunk-word", colorize=RECTANGLE))
    assert (
        "\nStyle: Box,IBM Plex Sans,64,&H00000000,&H000000FF,&H00FFFFFF,&H80000000,-1,0,0,0,100,100,0,0,3,4,0,2,"
        in text
    )
    assert "Style: Box" not in boxed(Style("chunk-word"))


def test_the_lit_word_is_boxed_in_reverse_video() -> None:
    """Its event in Box; the word the outline's colour, the box the text's; the padding 2.8 --
    a font unread: room min(0.15 x 64 - 4, 80 - 64 - 4) = 5.6, half of it."""
    lit = [
        line
        for line in boxed(Style("chunk-word", colorize=RECTANGLE)).splitlines()
        if line.startswith("Dialogue: 1,")
    ]
    assert all(",Box,," in line for line in lit)
    assert "\\1c&H00000000&\\3c&H00FFFFFF&\\bord2.8}one" in lit[0]


def test_a_boxed_pop_grows_its_padding_not_its_text() -> None:
    """To 2.8 + (5.6 - 2.8 - 1) = 4.6 and back: libass double-scales a box, so the text keeps its size."""
    popped = boxed(Style("chunk-word", "pop", colorize=RECTANGLE))
    assert "\\bord2.8\\t(0,90,0.5,\\bord4.6)\\t(90,240,1.5,\\bord2.8)" in popped
    assert "\\fscx" not in popped


def test_an_abutting_word_s_box_is_a_unit_and_still() -> None:
    popped = boxed(Style("chunk-word", "pop", colorize=RECTANGLE), ("日", "本"), "日本")
    assert "\\bord1}" in popped
    assert "\\t(0,90,0.5,\\bord" not in popped


def test_word_highlight_s_box() -> None:
    lit = script(ONE, 1920, 1080, Style("word-highlight", colorize=RECTANGLE))[0]
    assert (
        next(line for line in lit.splitlines() if line.startswith("Dialogue:")).count(",Box,,") == 1
    )


def test_a_boxed_word_in_motion() -> None:
    """The font's motion is the box's (\\3c per letter); the outline's, the letters' (\\1c)."""
    font = boxed(Style("chunk-word", colorize=RECTANGLE, text=MOTIONS["lsd"]))
    lit = next(line for line in font.splitlines() if line.startswith("Dialogue: 1,"))
    assert lit.count("\\3c") >= 3
    assert "\\t(" in lit
    edge = boxed(Style("chunk-word", colorize=RECTANGLE, outline=MOTIONS["lsd"]))
    lit = next(line for line in edge.splitlines() if line.startswith("Dialogue: 1,"))
    assert lit.count("\\1c") >= 3


def test_a_line_s_budget_is_its_event_s() -> None:
    """chunk-word draws a line per event: its letters' chains are one budget, not each word's
    (its first form: a 76-letter line, 26,980 \\t, each word under the budget). 24 letters
    shown 120 s, estimated: 24 x (720 + 2) keyframes, over 10,000."""
    windows = [(0, 120_000)] + [(119_000 + k, 119_001 + k) for k in range(1, 40)]
    words = tuple(Word("0", a, b, "iiii") for a, b in windows)
    joined = " ".join(w.text for w in words)
    t = Transcript(
        "json",
        ".json",
        has_words=True,
        chunks=(Chunk(0, 120_100, joined, "0"),),
        words=words,
        notes=(),
    )
    text, notes = script(t, 1920, 1080, Style("chunk-word", text=MOTIONS["lsd"]))
    assert max(line.count("\\t(") for line in text.splitlines()) <= 10_000
    assert notes
    assert notes[0].endswith("runs too long to move: their hues held still")


def test_an_outline_s_motion_counts_in_a_lit_run() -> None:
    """A gold highlight under an outline in motion: its chains are the run's too."""
    t = Transcript(
        "srt",
        ".srt",
        has_words=False,
        chunks=(Chunk(0, 60_000, "a" * 300, ""),),
        words=(),
        notes=(),
    )
    text, notes = script(t, 1920, 1080, Style("word-highlight", outline=MOTIONS["lsd"]))
    assert notes == ("1 runs too long to move: their hues held still",)
    assert text.count("\\t(") < 10_000


def test_word_mode_paints_its_word() -> None:
    """--overlay-mode word: a word an event, nothing lit -- a font in motion still paints each
    letter, and a word too long to move is held."""
    t = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 1000, "ab", ""),), words=(), notes=()
    )
    ((_, _, event),) = dialogues(script(t, 1920, 1080, Style("word", text=MOTIONS["lsd"]))[0])
    assert first_colours(event, "1c") == [
        colour_at(MOTIONS["lsd"], k, 2, 0).ass() for k in range(2)
    ]
    long = Transcript(
        "srt", ".srt", has_words=False, chunks=(Chunk(0, 60_000, "a" * 50, ""),), words=(), notes=()
    )
    assert script(long, 1920, 1080, Style("word", text=MOTIONS["lsd"]))[1] == (
        "1 runs too long to move: their hues held still",
    )
