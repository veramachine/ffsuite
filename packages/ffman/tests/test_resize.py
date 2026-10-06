from fractions import Fraction
from typing import Final

from ffman.graph import NULL, Chain, Filter, Labels, Open
from ffman.graph.resize import Picture, bblur_sigma, blurred_fit, head
from ffman.graph.sizes import Displayed, Target
from ffman.jobs.convert.options import validate
from ffman.media.probe import Rational, Video
from ffman.options import CONVERT, parse
from ffman.plan.encode import attachment_args, parse_encoders

FLAGS = "flags=lanczos+accurate_rnd+full_chroma_int"


SQUARE: Final = Fraction(1)


def video(pix: str | None = "yuv420p") -> Video:
    return Video(
        "h264",
        640,
        360,
        None,
        Rational(1, 1),
        None,
        None,
        None,
        None,
        pix,
        None,
        None,
        None,
        None,
        None,
    )


def text(
    argv: list[str],
    *,
    sar: Fraction = SQUARE,
    moving: bool = True,
    pix: str | None = "yuv420p",
) -> str:
    o = validate(parse("convert", CONVERT, ["-i", "a.mp4", *argv]))
    picture = Picture(
        Displayed(640, 360, 640, 360, sar), Target(320, 320, None), video(pix), moving
    )
    opened, _ = head(o.resize_mode, o.bblur, picture, Labels())
    return opened.close("v").render()


def test_each_mode() -> None:
    assert (
        text(["-w", "320", "-H", "320", "-r", "stretch"])
        == f"[0:v:0]scale=320:320:{FLAGS},setsar=1[v]"
    )
    assert text(["-w", "320", "-H", "320", "-r", "cover"]) == (
        f"[0:v:0]scale=320:320:force_original_aspect_ratio=increase:{FLAGS},crop=320:320,setsar=1[v]"
    )
    fit = "scale=320:320:force_original_aspect_ratio=decrease:force_divisible_by=2"
    assert (
        text(["-w", "320", "-H", "320"])
        == f"[0:v:0]{fit}:{FLAGS},pad=320:320:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v]"
    )
    assert "force_divisible_by" not in text(
        ["-w", "320", "-H", "320"], moving=False
    )  # an image keeps odd sizes


def test_non_square_pixels_are_squared_first() -> None:
    assert text(["-w", "320", "-H", "320", "-r", "stretch"], sar=Fraction(32, 27)).startswith(
        f"[0:v:0]scale=iw*sar:ih:{FLAGS},setsar=1,scale=320"
    )


def test_blurred_bars() -> None:
    graph = text(["-w", "320", "-H", "320", "-b", "20"])
    assert graph.startswith("[0:v:0]split=2[bg][fg];[bg]format=gbrp16le,lutrgb=")
    assert "gblur=sigma=20:steps=6" in graph
    assert graph.endswith(
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2:format=auto,format=yuv420p,setsar=1[v]"
    )
    assert ",format=pal8" not in text(
        ["-w", "320", "-H", "320", "-b", "20"], pix="pal8"
    )  # scale never outputs it
    o = validate(parse("convert", CONVERT, ["-i", "a.mp4", "-w", "320", "-H", "320", "-b", "auto"]))
    picture = Picture(
        Displayed(640, 360, 640, 360, Fraction(1)), Target(320, 320, None), video(), moving=True
    )
    _, note = head(o.resize_mode, o.bblur, picture, Labels())
    assert note == "--bblur auto: sigma 9.2 for 640x360 into 320x320 (set it with --bblur N)"


def test_bblur_sigma() -> None:
    source = Displayed(640, 360, 640, 360, Fraction(1))
    assert bblur_sigma(Fraction("7.25"), source, Target(1, 1, None)) == "7.25"  # as given
    assert bblur_sigma(Fraction("012.50"), source, Target(1, 1, None)) == "12.5"  # its value
    assert bblur_sigma("auto", source, Target(640, 640, None)) == "18.5"  # 360 * 640/360 / 34.6
    assert bblur_sigma("auto", source, Target(20, 20, None)) == "1.0"  # at least 1
    assert (
        bblur_sigma(
            "auto", Displayed(2000, 2000, 2000, 2000, Fraction(1)), Target(40000, 40000, None)
        )
        == "1024.0"
    )


def test_an_open_graph() -> None:
    opened = Open(("0:v:0",)).then(Filter("hflip"))
    assert opened.close("v").render() == "[0:v:0]hflip[v]"
    assert Open(("0:v:0",)).close("v").render() == "[0:v:0]null[v]"  # nothing asked: null
    branched = Open(("a", "b"), (Filter("overlay"),), (Chain((NULL,), ("0:v:0",), ("a",)),))
    assert branched.close("v").render() == "[0:v:0]null[a];[a][b]overlay[v]"


def test_encoders_and_tracks() -> None:
    listing = "Encoders:\n V..... = Video\n ------\n V....D libx264              libx264 H.264\n A....D libfdk_aac  Fraunhofer\n"
    assert parse_encoders(listing) == frozenset(
        {"libx264", "libfdk_aac"}
    )  # the legend is no encoder
    assert attachment_args(carry=True) == ["-map", "0:t?", "-c:t", "copy"]
    assert attachment_args(carry=False) == []


def test_a_measured_head_is_the_render_s_with_its_bars_black() -> None:
    """measure: the blur's one filter filled black instead, all else the same -- so the picture
    measured is where the render puts it, by construction."""
    o = validate(parse("convert", CONVERT, ["-i", "a.mp4", "-w", "320", "-H", "320", "-b", "20"]))
    picture = Picture(
        Displayed(640, 360, 640, 360, Fraction(1)), Target(320, 320, None), video(), moving=True
    )
    rendered, _ = head(o.resize_mode, o.bblur, picture, Labels())
    measured, _ = head(o.resize_mode, o.bblur, picture, Labels(), measure=True)
    as_rendered = (
        rendered.close().render().replace("gblur=sigma=20:steps=6", "drawbox=color=black:t=fill")
    )
    assert measured.close().render() == as_rendered


def test_a_blurred_fit_is_a_fit_with_blur_on() -> None:
    """One rule for the head and the bar's note: a fit, bar blur on (cover has no bars)."""
    assert blurred_fit("fit", "auto")
    assert blurred_fit("fit", Fraction(5))
    assert not blurred_fit("fit", Fraction(0))
    assert not blurred_fit("cover", "auto")
