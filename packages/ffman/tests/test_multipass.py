import time
from datetime import datetime
from fractions import Fraction

import pytest

from ffman.effects import parse_specs
from ffman.effects.camcorder import clock, script, width
from ffman.effects.datamosh import cuts, mosh
from ffman.effects.dither import dithered, palette_graph
from ffman.effects.frame import Frame
from ffman.effects.stages import STAGE_A, STAGE_B, Effects, before_dither, chain
from ffman.errors import FfmanError
from ffman.graph import Filter, Labels, Open
from ffman.media.probe import Rational, Video

NOON: datetime = datetime(2021, 3, 4, 12, 0, 5)  # noqa: DTZ001 -- a local wall clock, as bash's date gave it


def video() -> Video:
    return Video(
        "h264",
        320,
        180,
        None,
        None,
        None,
        None,
        None,
        None,
        "yuv420p",
        None,
        None,
        None,
        None,
        None,
    )


def test_the_clock() -> None:
    assert clock(None, "2020-02-29", "23:59:30", NOON) == 1583020770  # given: read as UTC
    assert clock(None, "2020:02:29", None, NOON) == 1582977605  # the date's colons; now's time
    assert clock(None, None, None, NOON) == 1614859205  # now
    assert clock("not a time", None, None, NOON) == 1614859205  # unreadable: now, as bash's date
    with pytest.raises(FfmanError, match="the camcorder clock could not be set"):
        _ = clock(None, "2021-02-30", "00:00:00", NOON)


def test_the_script() -> None:
    text = script(1583020770, Fraction("1.5"), width(1920, 1080))
    assert "PlayResX: 1920\nPlayResY: 1080\n" in text
    assert text.count("Dialogue:") == 2 + 2 * 2  # PLAY and SP, then a counter and a clock a second
    assert r"{\an3\pos(1860,1020)}11:59:30 PM\NFEB. 29 2020" in text
    assert script(0, None, 1440).count("Dialogue:") == 4  # no duration: one second


def test_scene_cuts_and_the_mosh() -> None:
    log = "[scdet @ 0x1] lavfi.scd.score: 43, lavfi.scd.time: 1.2\nnoise\n[scdet] lavfi.scd.time: 3.36\n"
    assert cuts(log) == ["1.2", "3.36"]
    healed = mosh(["1.2"], "0.5", Rational.parse("30000/1001"))
    assert (healed.keys, healed.output) == (
        "1.2,1.7",
        ["-fps_mode", "cfr", "-r", "30000/1001", "-enc_time_base:v", "1001/30000"],
    )
    assert healed.drop == r"noise=drop='key*gt(n\,0)*not(0+lt(abs(pts*tb-1.7)\,0.0166833))'"
    melted = mosh([], None, Rational.parse("0/0"))  # no cut, never heals; an unknown rate is 25/1
    assert (melted.keys, melted.drop, melted.rate) == (
        "",
        r"noise=drop='key*gt(n\,0)*not(0)'",
        Rational(25, 1),
    )


def test_the_dither_and_its_palette() -> None:
    fx = Effects(parse_specs(["dither:8"]), Frame.resized(320, 180, video()), Labels())
    assert dithered(fx.requests) == "8"
    assert dithered(parse_specs(["dither"])) == "16"
    assert dithered(()) is None
    made = palette_graph(before_dither(fx, Open(("0:v:0",))), "8").render()
    assert made == "[0:v:0]null,palettegen=max_colors=8:stats_mode=full:reserve_transparent=0[p]"
    with pytest.raises(ValueError, match="a dither needs its palette's stream"):
        _ = chain(fx, Open(("0:v:0",)), restore=False)


def test_the_camcorder_needs_its_script_written() -> None:
    fx = Effects(parse_specs(["camcorder"]), Frame.resized(320, 180, video()), Labels())
    with pytest.raises(ValueError, match="the camcorder's script must be written first"):
        _ = chain(fx, Open(("0:v:0",)), restore=False)


def test_the_clock_from_the_files_creation_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    try:
        assert clock("2019-06-01T12:34:56.000000Z", None, None, NOON) == 1559392496  # in local time
        assert (
            clock("2019-06-01T12:34:56", None, "00:00:00", NOON) == 1559347200
        )  # no zone: as it is
    finally:
        monkeypatch.undo()
        time.tzset()


def test_the_subtitles_are_not_moshed() -> None:
    # bash's mosh_prepare: the picture's and the lens's effects only; the text is drawn after
    fx = Effects(
        (),
        Frame.resized(320, 180, video()),
        Labels(),
        subtitles=Filter("ass", (("filename", "s.ass"),)),
    )
    assert before_dither(fx, Open(("0:v:0",)), STAGE_A).close().render() == "[0:v:0]null"
    assert "ass=filename=s.ass" in before_dither(fx, Open(("0:v:0",)), STAGE_B).close().render()
    assert "ass=filename=s.ass" in before_dither(fx, Open(("0:v:0",))).close().render()
