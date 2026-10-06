import pytest

from ffman.errors import FfmanError, refuse, refuse_at, shown


def test_refuse_says_the_message() -> None:
    with pytest.raises(FfmanError, match=r"^convert: --input is required$"):
        refuse("convert: --input is required")


def test_refuse_at_names_the_file_and_line_as_gnu_does() -> None:
    with pytest.raises(FfmanError, match=r"^album\.cue:12: a TRACK number outside 01-99: 100$"):
        refuse_at("album.cue", 12, "a TRACK number outside 01-99: 100")
    with pytest.raises(FfmanError, match=r"^tags\.txt:1: no '=' in a comment$"):
        refuse_at("tags.txt", 1, "no '=' in a comment")


def test_refuse_at_counts_lines_from_one() -> None:
    with pytest.raises(ValueError, match=r"^lines count from 1, not 0$"):
        refuse_at("a.cue", 0, "x")


def test_shown_puts_input_on_one_line_of_60_characters_at_most() -> None:
    assert shown("short") == "short"
    assert shown("a\r\nb") == "a\\r\\nb"  # one line: the breaks, written
    assert shown("x" * 60) == "x" * 60
    assert shown("x" * 61) == "x" * 57 + "..."
    assert len(shown("y" * 1000)) == 60
    # what prints nothing, visible
    assert shown("\ufeffa\tb\x00c\xa0d") == "\\ufeffa\\tb\\x00c\\xa0d"
