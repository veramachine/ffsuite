"""subs/breaks.py's table, from the Unicode Character Database: the generator and its check.

Run with the UCD's LineBreak.txt and PropList.txt (the version Python's unicodedata reports)
to print the table; the test compares it with the one in src.
"""

import sys
import unicodedata
from pathlib import Path

# UAX #14: never before CL, CP, EX, IS (LB13), BA, HY, NS (LB21), IN (LB22), a postfix (PO:
# LB25's, wherever it is); CJ as NS (strict). Never after OP (LB14), BB (LB21), a prefix (PR)
NO_START_CLASSES = ("CL", "CP", "EX", "IS", "BA", "HY", "NS", "CJ", "IN", "PO")
NO_END_CLASSES = ("OP", "BB", "PR")


def _property(path: Path) -> dict[int, str]:
    found: dict[int, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        span, value = (x.strip() for x in line.split(";"))
        first, _, last = span.partition("..")
        for c in range(int(first, 16), int(last or first, 16) + 1):
            found[c] = value
    return found


def sets(linebreak: Path, proplist: Path) -> dict[str, list[int]]:
    """The table's four sets, as code points."""
    classes = _property(linebreak)
    quote = [c for c, v in classes.items() if v == "QU"]
    no_start = [c for c, v in classes.items() if v in NO_START_CLASSES]
    no_start += [c for c in quote if unicodedata.category(chr(c)) == "Pf"]  # a closing quote
    no_end = [c for c, v in classes.items() if v in NO_END_CLASSES]
    no_end += [c for c in quote if unicodedata.category(chr(c)) == "Pi"]  # an opening quote
    complex_context = [c for c, v in classes.items() if v == "SA"]  # Thai, Lao, Khmer, Burmese...
    preposed = [c for c, v in _property(proplist).items() if v == "Logical_Order_Exception"]
    found = {"NO_START": no_start, "NO_END": no_end, "SA": complex_context, "PREPOSED": preposed}
    return {name: sorted(points) for name, points in found.items()}


def ranges(points: list[int]) -> list[tuple[int, int]]:
    """Consecutive code points as (first, last) ranges."""
    out: list[tuple[int, int]] = []
    for c in points:
        if out and c == out[-1][1] + 1:
            out[-1] = (out[-1][0], c)
        else:
            out.append((c, c))
    return out


def source(linebreak: Path, proplist: Path) -> str:
    """The table as Python: each set a tuple of ranges, four to a line."""
    out: list[str] = []
    for name, points in sets(linebreak, proplist).items():
        rows = [
            ", ".join(f"(0x{a:04X}, 0x{b:04X})" for a, b in chunk)
            for chunk in _chunks(ranges(points), 4)
        ]
        out.append(f"{name}: Final = _points(\n" + "".join(f"    {r},\n" for r in rows) + ")")
    return "\n".join(out)


def _chunks(items: list[tuple[int, int]], n: int) -> list[list[tuple[int, int]]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


if __name__ == "__main__":
    _ = sys.stdout.write(source(Path(sys.argv[1]), Path(sys.argv[2])) + "\n")
