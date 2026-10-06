from dataclasses import replace
from fractions import Fraction

import pytest

from ffman.effects import parse_specs
from ffman.effects.crt import crt_frame_height
from ffman.effects.frame import Frame
from ffman.effects.stages import Effects, chain, check_restorable
from ffman.errors import FfmanError
from ffman.graph import Labels, Open
from ffman.graph.sizes import Displayed, Target
from ffman.jobs.convert.passes import frame_for
from ffman.media.probe import Video


def video(pix: str | None = "yuv420p") -> Video:
    return Video(
        "h264", 320, 180, None, None, None, None, None, None, pix, None, None, None, None, None
    )


@pytest.mark.parametrize(
    ("height", "rendered"),
    [(180, 720), (480, 720), (719, 720), (840, 960), (1079, 960), (1080, 1200)],
)
def test_crt_renders_whole_rows_a_line(height: int, rendered: int) -> None:
    # 240k nearest (a half rounds up: 1079 is 960, 1080 is 1200), at least 720
    assert crt_frame_height(height) == rendered


def test_fx_sar_and_the_text_chromatic_aberration_prints() -> None:
    """The frame's SAR typed; CA prints it as bash's FX_SAR text: 1 squared, else N/M."""
    square = Displayed(320, 180, 320, 180, Fraction(1))
    resized = frame_for(square, Target(160, 90, None), video())
    kept = frame_for(square, None, video())
    wide = frame_for(Displayed(640, 480, 720, 480, Fraction(32, 27)), None, video())
    assert (resized.sar, resized.squared, kept.sar, kept.squared) == (1, True, 1, False)
    assert (wide.width, wide.height, wide.sar, wide.squared) == (720, 480, Fraction(32, 27), False)
    for frame, text in ((resized, "setsar=1["), (kept, "setsar=1/1["), (wide, "setsar=32/27[")):
        fx = Effects(parse_specs(["chromatic-aberration"]), frame, Labels())
        assert text in chain(fx, Open(("0:v:0",)), restore=False).close("v").render()


def test_a_squared_frame_has_sar_1() -> None:
    with pytest.raises(ValueError, match="a squared frame has SAR 1, not 4/3"):
        _ = Frame(320, 180, Fraction(4, 3), video(), squared=True)
    with pytest.raises(ValueError, match="a squared frame has SAR 1"):
        _ = replace(Frame(320, 180, Fraction(4, 3), video()), squared=True)
    assert Frame.resized(160, 90, video()) == Frame(160, 90, Fraction(1), video(), squared=True)


def test_the_display_alone_starts_with_null() -> None:
    graph = chain(
        Effects(parse_specs(["crt"]), Frame.resized(320, 180, video()), Labels()),
        Open(("0:v:0",)),
        restore=False,
    )
    assert graph.close("v").render().startswith("[0:v:0]null,format=gbrp16le,")


def test_nothing_asked_nothing_added() -> None:
    start = Open(("0:v:0",))
    assert (
        chain(
            Effects((), Frame.resized(320, 180, video()), Labels()),
            start,
            restore=True,
        )
        is start
    )


def test_an_unknown_pixel_format_cannot_be_given_back() -> None:
    """Refused before any work; the chain, called anyway, holds the rule as an invariant."""
    asked = parse_specs(["invert"])
    with pytest.raises(FfmanError, match="the source's pixel format is unknown"):
        check_restorable(asked, video(None), restore=True)
    check_restorable(asked, video(None), restore=False)  # a GIF keeps the palette's format
    check_restorable((), video(None), restore=True)  # no effects: nothing re-rendered
    check_restorable(asked, video(), restore=True)
    with pytest.raises(ValueError, match="check_restorable refuses it first"):
        _ = chain(
            Effects(asked, Frame.resized(320, 180, video(None)), Labels()),
            Open(("0:v:0",)),
            restore=True,
        )


def built(specs: list[str], width: int = 320, height: int = 180) -> str:
    frame = Frame.resized(width, height, video())
    return (
        chain(Effects(parse_specs(specs), frame, Labels()), Open(("0:v:0",)), restore=False)
        .close("v")
        .render()
    )


def test_each_effect_builds() -> None:
    # stage A proved them equal to bash's; these keep every line run here too
    assert "gblur=sigma=1.8:sigmaV=1.8:steps=6" in built(["blur"])  # 1% of 180
    assert "gblur=sigma=4:sigmaV=4:steps=6" in built(["blur:4"])
    assert "mergeplanes=map0s=0:map0p=0:map1s=1:map1p=0:map2s=2:map2p=0:format=gbrp" in built(
        ["chromatic-aberration"]
    )
    assert "blend=all_mode=screen:all_opacity=0.6" in built(["halation"])


def test_vhs_noise_takes_two_passes_at_1080() -> None:
    assert built(["vhs"], 1920, 1080).count("noise=") == 2  # one pass tops out at strength 99
    assert built(["vhs"]).count("noise=") == 1


def test_crt_at_720_needs_no_rescale() -> None:
    assert ":flags=area,format=gbrp16le,lutrgb" not in built(["crt"], 960, 720)
    assert "scale=320:180:flags=area,format=gbrp16le" in built(["crt"])
