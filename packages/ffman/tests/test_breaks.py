"""subs.breaks: where a line may break in unspaced text -- UAX #14's rules, Thai's syllables."""

import os
from pathlib import Path

import pytest

from ffman.subs.breaks import NO_END, NO_START, PREPOSED, SA, breakable, segments
from tests.support.linebreak import sets


@pytest.mark.parametrize(
    ("before", "after", "may"),
    [
        ("日", "本", True),  # ideographs: anywhere between (ID)
        ("日", "A", True),  # beside a wide character
        ("A", "B", False),  # Latin letters: never apart (AL)
        ("て", "、", False),  # no line opens on a comma (CL)
        ("す", "。", False),  # nor a full stop (CL)
        ("ト", "」", False),  # nor a closing bracket (CL)
        ("ね", "！", False),  # nor ! (EX)
        ("ち", "ょ", False),  # nor a small kana (CJ: strict)
        ("ス", "ー", False),  # nor the prolonged mark (CJ)
        ("時", "々", False),  # nor an iteration mark (NS)
        ("了", "…", False),  # nor an ellipsis (IN)
        ("０", "％", False),  # nor a postfix (PO)
        ("「", "明", False),  # no line ends on an opening bracket (OP)
        ("￥", "１", False),  # nor a prefix (PR)
        ("见", "”", False),  # a closing quote stays with its text
        ("“", "明", False),  # an opening quote with its
        ("ก", "ข", True),  # Thai: between syllables
        ("เ", "ช", False),  # never after a vowel written before its consonant
        ("ข", "า", False),  # never before one written after
        ("ใคร", "ๆ", False),  # nor a repetition mark
        ("\u0301", "日", True),  # a unit of a mark alone (a text opening on one): itself
    ],
)
def test_where_a_line_may_break(before: str, after: str, *, may: bool) -> None:
    assert breakable(before, after) is may


# ICU 74.2's line breaker, strict (createLineInstance, "ja@lb=strict", "zh@lb=strict"):
# recorded, ICU being no dependency -- 339 of 339 break positions agreed on 31 texts
ICU_STRICT = [
    "ちょっ|と|待っ|て、|「ABC|テ|ス|ト」|は|今|日|で|す。|え|え、|そ|う|で|す|ね！",
    "気|温|は|３|０℃、|湿|度|は|８|０％|で|す。",
    "価|格|は|￥１，|０|０|０|で|す。",
    "他|说：|“明|天|见。”|然|后|就|走|了……",
    "《三|体》|是|刘|慈|欣|写|的|科|幻|小|说；|非|常|好|看。",
    "えーっ|と、|何|だっ|け……|そ|う|そ|う、|思|い|出|し|た。",
]


@pytest.mark.parametrize("expected", ICU_STRICT)
def test_the_breaks_are_icus_strict_ones(expected: str) -> None:
    units, gaps = segments(expected.replace("|", ""))
    found = units[0]
    for before, after, gap in zip(units[:-1], units[1:], gaps[1:], strict=True):
        found += ("|" if gap or breakable(before, after) else "") + gap + after
    assert found == expected


def test_a_text_s_units_and_gaps() -> None:
    """Its clusters, and the gap before each: spaces collapse, a mark stays with its own."""
    assert segments(" cafe\u0301  日本 ") == (
        ["c", "a", "f", "e\u0301", "日", "本"],
        ["", "", "", "", " ", ""],
    )


UCD = Path(os.environ.get("FFMAN_UCD", "/usr/share/texlive/texmf-dist/tex/generic/unicode-data"))


@pytest.mark.skipif(
    not (UCD / "LineBreak.txt").is_file(), reason="the Unicode Character Database: FFMAN_UCD"
)
def test_the_table_is_unicodes() -> None:
    """breaks.py's table is what the generator makes of Unicode 15.1's LineBreak and PropList."""
    assert "LineBreak-15.1.0" in (UCD / "LineBreak.txt").read_text(encoding="utf-8")[:40]
    data = sets(UCD / "LineBreak.txt", UCD / "PropList.txt")
    committed = {"NO_START": NO_START, "NO_END": NO_END, "SA": SA, "PREPOSED": PREPOSED}
    assert {name: sorted(ord(c) for c in table) for name, table in committed.items()} == data
