from fractions import Fraction

from ffman.subs.layout import (
    Bar,
    bar_args,
    bar_centre,
    bar_rows,
    bar_times,
    font_size,
)


def printed(*rows: tuple[str, str]) -> str:
    """metadata=print's lines for frames of (y1, y2), as f_metadata.c writes them."""
    out = ""
    for n, (y1, y2) in enumerate(rows):
        out += f"frame:{n:<4} pts:{n:<7} pts_time:{n}\nlavfi.cropdetect.x1=0\nlavfi.cropdetect.x2=1919\n"
        out += (
            f"lavfi.cropdetect.y1={y1}\nlavfi.cropdetect.y2={y2}\nlavfi.cropdetect.limit=0.094118\n"
        )
    return out


def test_the_size() -> None:
    assert (
        font_size(None, plain=True),
        font_size(None, plain=False),
        font_size(Fraction(40), plain=True),
    ) == (Fraction(57), Fraction(64), Fraction(40))


def test_where_it_looks() -> None:
    assert bar_times(Fraction(16)) == (
        ["2", "4", "6", "8", "10", "12", "14"],
        5,
    )  # the eighths, 5 frames each
    assert bar_times(None) == ([None], 50)  # no duration: 50 frames from the start
    assert bar_args("a.mp4", "2", 5, "scale=640:360,") == [
        "-v", "error", "-noaccurate_seek", "-ss", "2", "-i", "file:a.mp4", "-map", "0:v:0",
        "-frames:v", "5", "-vf",
        "scale=640:360,cropdetect=round=2:reset=0:skip=0,metadata=mode=print:file=-",
        "-f", "null", "-",
    ]  # fmt: skip
    assert "-ss" not in bar_args("a.mp4", None, 50, "")


def test_what_it_finds() -> None:
    assert bar_rows(printed(("0", "900"), ("0", "998"))) == 998  # the lowest picture row
    assert bar_rows(printed(("1079", "0"))) is None  # black frames only: no picture seen
    assert bar_rows(printed(("1079", "0"), ("0", "900"))) == 900  # black, then the picture
    assert bar_rows("") is None  # nothing printed: ffmpeg failed (bash: || true)
    assert bar_rows(printed(("0", "x9"), ("0", "-5"))) is None  # not rows: skipped, never a crash
    stray = "lavfi.cropdetect.y2=5\n" + printed(("0", "900"))
    assert bar_rows(stray) == 900  # a line before any frame's: no frame's, ignored
    assert bar_centre(1080, 998, Fraction(57)) == Bar(
        Fraction("1039.5"),
        "a black bar under the picture (81 of 1080 px): subtitles centred in it (--margin-bottom overrides)",
    )  # 81 rows: 1080 - 81 / 2
    assert bar_centre(1080, 1010, Fraction(57)) is None  # 69 rows: under 57 * 1.25


def test_a_bar_exactly_as_tall_as_the_text_needs_is_used() -> None:
    """19 of 288 rows is 57 x 1.25 / 1080 exactly: found (bash's six-digit text fell under it)."""
    assert bar_centre(288, 268, Fraction(57)) is not None
    assert bar_centre(288, 269, Fraction(57)) is None  # a row less: not


def test_the_bar_centre_is_exact() -> None:
    bar = bar_centre(1001, 801, Fraction(57))
    assert bar is not None
    assert bar.y == 1080 - Fraction(199, 1001) * 540  # 972.647352... (bash: 972.647)


def test_the_sample_times_are_exact_seconds() -> None:
    times, frames = bar_times(Fraction("3601.234567"))
    assert (times[0], frames) == ("450.154320875", 5)  # bash's %.6g: 450.154


def test_a_bar_says_what_fills_it() -> None:
    assert bar_centre(1080, 998, Fraction(57)) == bar_centre(1080, 998, Fraction(57), "black")
    blurred = bar_centre(320, 227, Fraction(57), "blurred")
    assert blurred is not None
    assert blurred.note.startswith("a blurred bar under the picture (92 of 320 px): ")
