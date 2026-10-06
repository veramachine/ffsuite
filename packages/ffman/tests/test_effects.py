import pytest

from ffman.effects import VIDEO, format_catalogue, parse_spec, parse_specs
from ffman.effects.spec import Stage
from ffman.errors import FfmanError


@pytest.mark.parametrize(
    ("spec", "values"),
    [
        ("blur", {}),
        ("blur:8", {"sigma": "8"}),
        ("blur:sigma=8", {"sigma": "8"}),
        ("blur:auto", {"sigma": "auto"}),
        ("camcorder:date=1999:12:31,time=23:59:58", {"date": "1999:12:31", "time": "23:59:58"}),
        ("camcorder:time=00:00:00", {"time": "00:00:00"}),
        ("dither:colours=2", {"colours": "2"}),
    ],
)
def test_the_grammar(spec: str, values: dict[str, str]) -> None:
    request = parse_spec(spec)
    assert request.effect.name == spec.partition(":")[0]
    assert dict(request.values) == values


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("glow", "--vfx: unknown effect: glow (see ffman effects)"),
        ("invert:1", "--vfx invert takes no value: invert:1"),
        (
            "camcorder:1999-12-31",
            "--vfx camcorder takes named values (date=, time=): camcorder:1999-12-31",
        ),
        (
            "blur:sigma=2,3",
            "--vfx blur: only the first value may go without a name: blur:sigma=2,3",
        ),
        ("blur:radius=2", "--vfx blur: unknown parameter: radius (sigma)"),
        ("halation:x=1", "--vfx halation: unknown parameter: x (none)"),
        ("blur:8,sigma=9", "--vfx blur: sigma given twice"),
        ("blur:", "--vfx blur: must be auto or a sigma above 0, up to 1024: "),
        ("blur:0", "--vfx blur: must be auto or a sigma above 0, up to 1024: 0"),
        ("pixelate:1", "--vfx pixelate: must be auto or a block size from 2 to 1024 px: 1"),
        (
            "chromatic-aberration:256",
            "--vfx chromatic-aberration: must be auto or a shift from 1 to 255 px: 256",
        ),
        ("dither:257", "--vfx dither: must be auto or a palette size from 2 to 256 colours: 257"),
        ("datamosh:0", "--vfx datamosh: must be auto or the seconds each mosh lasts: 0"),
        (
            "camcorder:date=auto",
            "--vfx camcorder: date must be a real date, YYYY-MM-DD or YYYY:MM:DD: auto",
        ),
        (
            "camcorder:date=1999-12:31",
            "--vfx camcorder: date must be a real date, YYYY-MM-DD or YYYY:MM:DD: 1999-12:31",
        ),
        (
            "camcorder:date=2023-02-29",
            "--vfx camcorder: date must be a real date, YYYY-MM-DD or YYYY:MM:DD: 2023-02-29",
        ),
        (
            "camcorder:date=0000-01-01",
            "--vfx camcorder: date must be a real date, YYYY-MM-DD or YYYY:MM:DD: 0000-01-01",
        ),
        ("camcorder:time=24:00:00", "--vfx camcorder: time must be HH:MM:SS (24-hour): 24:00:00"),
    ],
)
def test_refusals(spec: str, message: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = parse_spec(spec)
    assert str(error.value) == message


# Accept (True) or refuse, each as bash's fx_validate decided (cross-checked on 124 values).
BASH = [
    ("blur", "0.5", True),
    ("blur", "1024", True),
    ("blur", "1025", False),
    ("blur", "1e3", False),
    ("blur", ".5", False),
    ("blur", "1.", False),
    ("blur", "-1", False),
    ("blur", "1.0", True),
    ("pixelate", "2", True),
    ("pixelate", "012", False),
    ("pixelate", "8.0", False),
    ("chromatic-aberration", "1", True),
    ("chromatic-aberration", "255", True),
    ("dither", "256", True),
    ("dither", "1", False),
    ("datamosh", "0.5", True),
    ("datamosh", "0.0", False),
]


@pytest.mark.parametrize(("name", "value", "accepted"), BASH)
def test_ranges_are_bashs(name: str, value: str, accepted: bool) -> None:
    key = next(e for e in VIDEO if e.name == name).params[0].name
    if accepted:
        assert parse_spec(f"{name}:{key}={value}").values[key] == value
    else:
        with pytest.raises(FfmanError):
            _ = parse_spec(f"{name}:{key}={value}")


def test_an_effect_twice_is_refused() -> None:
    assert [r.effect.name for r in parse_specs(["crt", "vhs"])] == ["crt", "vhs"]
    with pytest.raises(FfmanError, match=r"^--vfx blur given twice$"):
        _ = parse_specs(["blur", "blur:8"])


def test_stages_follow_the_physics() -> None:
    order = [e.name for e in sorted(VIDEO, key=lambda e: e.stage)]
    assert order.index("blur") < order.index("chromatic-aberration") < order.index("datamosh")
    assert (
        order.index("datamosh") < order.index("camcorder") < order.index("vhs") < order.index("crt")
    )
    assert {e.stage for e in VIDEO} == set(Stage)


def test_the_catalogue() -> None:
    text = format_catalogue()
    assert text.startswith("Video effects, in the order they run")
    for effect in VIDEO:
        assert f"  {effect.name}" in text
    assert (
        "sigma: auto or a sigma above 0, up to 1024 (auto: 1% of the displayed shorter side)"
        in text
    )
    one = format_catalogue("camcorder")
    assert one.startswith("  camcorder")
    assert "date: a real date, YYYY-MM-DD or YYYY:MM:DD (left out:" in one
    with pytest.raises(FfmanError, match=r"^unknown effect: glow \(see ffman effects\)$"):
        _ = format_catalogue("glow")


def test_invert_is_in_rgb_as_bash() -> None:
    # bash: format=gbrp,negate (encoded RGB), unlike blur, which works in light
    assert "invert the colours, in RGB" in format_catalogue("invert")
