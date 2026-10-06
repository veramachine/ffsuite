from fractions import Fraction

import pytest

from ffman.errors import FfmanError
from ffman.jobs.convert.options import validate
from ffman.options import CONVERT, parse
from ffman.plan.request import ConvertOptions
from ffman.subs.colorize import GOLD, MOTIONS, NAMES, RECTANGLE, WHITE, Colour


def v(*argv: str) -> ConvertOptions:
    return validate(parse("convert", CONVERT, ["-i", "in.mp4", *argv]))


def test_defaults() -> None:
    o = v()
    assert (o.input, o.output, o.resize_mode, o.bblur, o.bblur_on) == (
        "in.mp4",
        None,
        "fit",
        Fraction(0),
        False,
    )
    assert (o.font, o.font_size, o.margin_bottom, o.overlay_mode) == (
        "IBM Plex Sans",
        Fraction(57),
        Fraction("0.05573"),
        "plain",
    )
    assert (o.audio_codec, o.video_codec, o.preset, o.loop) == ("copy", None, None, "once")


def test_values() -> None:
    o = v(
        "-w", "1080", "-H", "1920", "-a", "2.39:1", "-b", "--video-codec", "FFV1", "--loop-reverse"
    )
    assert (o.width, o.height, o.aspect, o.aspect_text) == (
        1080,
        1920,
        (Fraction("2.39"), Fraction(1)),
        "2.39:1",
    )
    assert (o.bblur, o.bblur_on, o.video_codec, o.loop) == ("auto", True, "ffv1", "reverse")


def test_burn_defaults_and_percent_margin() -> None:
    o = v(
        "--burn-subs",
        "s.srt",
        "--overlay-mode",
        "chunk-word",
        "--margin-bottom",
        "5%",
        "--highlight-mode",
        "pop",
    )
    assert (o.font_size, o.margin_bottom, o.highlight_mode) == (
        Fraction(64),
        Fraction("0.05"),
        "pop",
    )


def test_preset_alias_and_tracks() -> None:
    o = v("-p", "YT", "--normalize")
    assert (o.preset, o.normalize) == ("youtube", True)
    o = v("--add-subs", "a.srt", "--language", "por", "--in-place")
    assert (o.add_subs, o.languages, o.in_place) == (("a.srt",), ("por",), True)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["-w", "0"], "--width must be a positive integer: 0"),
        (["-w", "012"], "--width must be a positive integer: 012"),
        (["-H", "1.5"], "--height must be a positive integer: 1.5"),
        (["-a", "16x9"], "--aspect-ratio must look like 16:9 or 2.39:1: 16x9"),
        (["-a", "0:9"], "--aspect-ratio parts must be positive: 0:9"),
        (["-r", "crop"], "--resize-mode must be stretch, cover or fit: crop"),
        (["-b", "-1"], "--bblur must be auto or a number from 0 to 1024: -1"),
        (["-b", "1025"], "--bblur must be auto or a number from 0 to 1024: 1025"),
        (
            ["-b", "-r", "cover"],
            "--bblur only applies to --resize-mode fit (the only mode with borders); got --resize-mode cover",
        ),
        (["--overlay-mode", "word"], "--overlay-mode needs --burn-subs"),
        (["--font", "X"], "--font needs --burn-subs"),
        (
            ["--burn-subs", "s", "--overlay-mode", "karaoke"],
            "--overlay-mode must be plain, chunk-word, word or word-highlight: karaoke",
        ),
        (
            ["--burn-subs", "s", "--highlight-mode", "glow"],
            "--highlight-mode must be plain or pop: glow",
        ),
        (
            ["--burn-subs", "s", "--highlight-mode", "pop"],
            "--highlight-mode needs --overlay-mode chunk-word or word-highlight",
        ),
        (
            ["--burn-subs", "s", "--highlight-colorize", "#00FF00"],
            "--highlight-colorize needs --overlay-mode chunk-word or word-highlight",
        ),
        (
            ["--burn-subs", "s", "--overlay-mode", "chunk-word", "--highlight-colorize", "glitter"],
            "--highlight-colorize must be #RRGGBB, a colour name, rainbow, lsd, iridescent or rectangle: glitter",
        ),
        (
            ["--burn-subs", "s", "--overlay-mode", "chunk-word", "--highlight-colorize", ""],
            "--highlight-colorize must be #RRGGBB, a colour name, rainbow, lsd, iridescent or rectangle: ",
        ),
        (["--highlight-colorize", "#00FF00"], "--highlight-colorize needs --burn-subs"),
        (["--font-color", "red"], "--font-color needs --burn-subs"),
        (
            ["--burn-subs", "s", "--font-color", "glitter"],
            "--font-color must be #RRGGBB, a colour name, rainbow, lsd or iridescent: glitter",
        ),
        (
            ["--burn-subs", "s", "--outline-color", "x"],
            "--outline-color must be #RRGGBB, a colour name, rainbow, lsd or iridescent: x",
        ),
        (["--burn-subs", "s", "--font-size", "0"], "--font-size must be a positive number: 0"),
        (["--burn-subs", "s", "--font", "A,B"], "--font must not contain a comma: A,B"),
        (
            ["--burn-subs", "s", "--margin-bottom", "150%"],
            "--margin-bottom must be a fraction in [0, 1) or a percentage: 1.5",
        ),
        (
            ["--burn-subs", "s", "--margin-bottom", "1"],
            "--margin-bottom must be a fraction in [0, 1) or a percentage: 1",
        ),
        (
            ["--burn-subs", "s", "--margin-bottom", "100%"],
            "--margin-bottom must be a fraction in [0, 1) or a percentage: 1",
        ),
        (
            ["--add-subs", "a", "--add-subs", "b"],
            "--add-subs given 2 times: one track per run, for now",
        ),
        (
            ["--add-subs", "a", "--language", "pt"],
            "--language must be a three-letter ISO 639-2 code (eng, por, ...): pt",
        ),
        (
            ["--language", "por"],
            "each --add-subs takes one --language: got 1 --language for 0 --add-subs",
        ),
        (["-p", "vimeo"], "unknown preset: vimeo (youtube, ffmetadata, vorbiscomment)"),
        (
            ["-p", "yt", "--lossless"],
            "--preset youtube sets the codecs: --lossless cannot be added",
        ),
        (
            ["-p", "yt", "--audio-codec", "aac"],
            "--preset youtube sets the codecs: --audio-codec cannot be added",
        ),
        (["--normalize"], "--normalize needs --preset youtube"),
        (
            ["--video-codec", "mpeg2"],
            "no lossless encoder for video codec 'mpeg2'; choose --video-codec h264, hevc, vp9, av1 or ffv1",
        ),
        (
            ["--audio-codec", "WMA"],
            "unsupported --audio-codec 'wma' (copy, none, flac, aac, opus, mp3, vorbis, alac, pcm)",
        ),
        (["--loop", "--loop-reverse"], "--loop and --loop-reverse exclude each other"),
        (["--in-place", "-o", "x.mp4"], "--in-place and --output exclude each other"),
    ],
)
def test_refusals(argv: list[str], message: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = v(*argv)
    assert str(error.value) == message


def test_input_is_required() -> None:
    with pytest.raises(FfmanError, match=r"^convert: --input is required$"):
        _ = validate(parse("convert", CONVERT, []))


def test_effects_are_parsed() -> None:
    o = v("--vfx", "crt", "--vfx=blur:8", "--vfx", "camcorder:date=1999:12:31,time=23:59:58")
    assert [(r.effect.name, dict(r.values)) for r in o.effects] == [
        ("crt", {}),
        ("blur", {"sigma": "8"}),
        ("camcorder", {"date": "1999:12:31", "time": "23:59:58"}),
    ]
    with pytest.raises(FfmanError, match=r"^--vfx crt given twice$"):
        _ = v("--vfx", "crt", "--vfx", "crt")


# An empty value given apart, as bash treated each option (probed on the bash
# ffman, 17 options; docs/ffman-spec.md section 1).
@pytest.mark.parametrize(
    ("argv", "field", "expected"),
    [
        (["-o", ""], "output", None),  # bash: the default output
        (["-w", "", "-H", "90"], "width", None),  # bash: the height alone
        (["-a", "", "-w", "80"], "aspect", None),
        (["-p", ""], "preset", None),
        (["--video-codec", ""], "video_codec", None),  # bash: ${VCODEC:-source}
        (["--audio-codec", ""], "audio_codec", "copy"),  # bash: ${ACODEC:-copy}
        (["--burn-subs", ""], "burn_subs", None),
        # bash: [[ -z ]] -> 57
        (["--burn-subs", "s.srt", "--font-size", ""], "font_size", Fraction(57)),
        (["--add-subs", ""], "add_subs", ()),
        (["--add-subs", "s.srt", "--language", ""], "languages", ()),  # bash: und
        (["--burn-subs", "s.srt", "--font", ""], "font", ""),  # bash kept it: an empty family
    ],
)
def test_empty_values_as_bash(argv: list[str], field: str, expected: object) -> None:
    assert getattr(v(*argv), field) == expected


@pytest.mark.parametrize(
    ("argv", "message"),
    [  # bash's own messages, the value empty
        (["-r", ""], "--resize-mode must be stretch, cover or fit: "),
        (["-b", ""], "--bblur must be auto or a number from 0 to 1024: "),
        (
            ["--burn-subs", "s.srt", "--overlay-mode", ""],
            "--overlay-mode must be plain, chunk-word, word or word-highlight: ",
        ),
        (
            ["--burn-subs", "s.srt", "--overlay-mode", "word-highlight", "--highlight-mode", ""],
            "--highlight-mode must be plain or pop: ",
        ),
        (
            ["--burn-subs", "s.srt", "--margin-bottom", ""],
            "--margin-bottom must be a fraction in [0, 1) or a percentage: ",
        ),
        (["--vfx", ""], "--vfx: unknown effect:  (see ffman effects)"),
    ],
)
def test_empty_values_refused_as_bash(argv: list[str], message: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = v(*argv)
    assert str(error.value) == message


def test_an_empty_input_is_no_input() -> None:
    with pytest.raises(FfmanError, match=r"^convert: --input is required$"):
        _ = validate(parse("convert", CONVERT, ["-i", ""]))


def test_the_highlight_colour() -> None:
    """Gold by default; the colour given, in either case, with or without its #."""
    burn = ("--burn-subs", "s.srt", "--overlay-mode", "chunk-word")
    assert v(*burn).highlight_colorize == GOLD
    assert v(*burn, "--highlight-colorize", "00ff00").highlight_colorize == Colour(0x00FF00)


@pytest.mark.parametrize(
    ("given", "name"), [("Rainbow", "rainbow"), ("LSD", "lsd"), ("Iridescence", "iridescent")]
)
def test_a_motion_by_name(given: str, name: str) -> None:
    """Either case; iridescence is iridescent."""
    burn = ("--burn-subs", "s.srt", "--overlay-mode", "word-highlight")
    assert v(*burn, "--highlight-colorize", given).highlight_colorize == MOTIONS[name]


def test_the_text_s_colours() -> None:
    """White and none (each fill's own outline) by default; any mode."""
    assert (v("--burn-subs", "s.srt").font_color, v("--burn-subs", "s.srt").outline_color) == (
        WHITE,
        None,
    )
    given = v("--burn-subs", "s.srt", "--font-color", "Teal", "--outline-color", "#FF0000")
    assert (given.font_color, given.outline_color) == (NAMES["teal"], Colour(0xFF0000))


def test_the_text_s_colours_may_move() -> None:
    given = v("--burn-subs", "s.srt", "--font-color", "Rainbow", "--outline-color", "iridescence")
    assert (given.font_color, given.outline_color) == (MOTIONS["rainbow"], MOTIONS["iridescent"])


def test_the_rectangle_is_the_highlight_s_alone() -> None:
    burn = ("--burn-subs", "s.srt", "--overlay-mode", "chunk-word")
    assert v(*burn, "--highlight-colorize", "Rectangle").highlight_colorize is RECTANGLE
    with pytest.raises(FfmanError, match="--font-color must be"):
        _ = v(*burn, "--font-color", "rectangle")
