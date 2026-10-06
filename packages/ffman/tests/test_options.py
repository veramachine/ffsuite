import re

import pytest

from ffman.effects import parse_spec
from ffman.errors import FfmanError
from ffman.options import COMMON, CONVERT, MIGRATED, Parsed, format_help, parse


def p(*argv: str) -> Parsed:
    return parse("convert", CONVERT, list(argv))


@pytest.mark.parametrize(
    "argv",
    [["-w", "100"], ["-W", "100"], ["--width", "100"], ["--width=100"]],
)
def test_value_forms(argv: list[str]) -> None:
    assert p(*argv).value("width") == "100"


@pytest.mark.parametrize(
    ("argv", "name"),
    [
        (["--width"], "--width"),
        (["--width="], "--width"),
        (["-w"], "-w"),
        (["--bblur="], "--bblur"),
    ],
)
def test_missing_or_empty_value(argv: list[str], name: str) -> None:
    with pytest.raises(FfmanError, match=f"^option {name} requires a value$"):
        _ = p(*argv)


@pytest.mark.parametrize(
    ("argv", "bblur", "overwrite"),
    [
        (["-b"], "auto", False),
        (["-b", "6"], "6", False),
        (["-b", "-1"], "-1", False),  # a value, and a bad one: bash's optval
        (["-b", "-.5"], "-.5", False),
        (["-b", "-y"], "auto", True),
        (["-b", "--overwrite"], "auto", True),
        (["--bblur=6"], "6", False),
    ],
)
def test_optional_value(argv: list[str], bblur: str, overwrite: bool) -> None:
    parsed = p(*argv)
    assert parsed.value("bblur") == bblur
    assert parsed.flag("overwrite") is overwrite


def test_repeatable_keeps_order_and_last_value_wins() -> None:
    parsed = p("--add-subs", "a.srt", "--add-subs=b.srt", "-w", "1", "-w", "2")
    assert parsed.all("add_subs") == ["a.srt", "b.srt"]
    assert parsed.value("width") == "2"
    assert parsed.given == {"add_subs", "width"}


@pytest.mark.parametrize("token", ["--bogus", "-w=100", "x.mp4", "--overwrite=1", "-"])
def test_unknown_option(token: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = p(token)
    assert str(error.value) == f"convert: unknown option: {token} (see ffman convert --help)"


@pytest.mark.parametrize("old", sorted(MIGRATED))
def test_every_migrated_spelling_names_its_replacement(old: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = p(old, "x")
    assert str(error.value) == MIGRATED[old]


def test_migrated_with_equals() -> None:
    with pytest.raises(
        FfmanError, match=r"^--blur is now --vfx blur \(a value: --vfx blur:VALUE\)$"
    ):
        _ = p("--blur=8")


def test_help_stops_parsing_but_not_before_an_error() -> None:
    assert p("-h", "--bogus").help
    with pytest.raises(FfmanError, match="unknown option: --bogus"):
        _ = p("--bogus", "-h")


def test_help_lists_every_option_by_group() -> None:
    text = format_help("ffman convert -i INPUT [options]", "Summary.", CONVERT)
    assert text.startswith("Usage: ffman convert -i INPUT [options]\n\nSummary.\n")
    for option in CONVERT:
        assert ", ".join(option.names) in text
    groups = ["Input and output:", "Picture:", "Effects:", "Burned subtitles:", "Subtitle tracks:"]
    groups += ["Encoding:", "GIF:", "Common:"]
    positions = [text.index(g) for g in groups]
    assert positions == sorted(positions)


def test_help_skips_groups_without_options() -> None:
    text = format_help("ffman effects", "Summary.", COMMON)
    assert "Common:" in text
    assert "Picture:" not in text


# Placeholders in a suggestion, as a user would fill them.
FILLED = {"VALUE": "auto", "D": "1999-12-31", "T": "23:59:58"}


@pytest.mark.parametrize("old", sorted(k for k, m in MIGRATED.items() if "--vfx" in m))
def test_every_suggested_vfx_form_is_accepted(old: str) -> None:
    forms = [m[1] for m in re.finditer(r"--vfx ([a-z-]+(?::[^ )]+)?)", MIGRATED[old])]
    assert forms
    for form in forms:
        filled = re.sub(r"\b(VALUE|D|T)\b", lambda m: FILLED[m[1]], form)
        assert parse_spec(filled).effect.name == filled.partition(":")[0]
