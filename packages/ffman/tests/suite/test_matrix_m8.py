"""matrix.sh's M8, encodings: every text format as CRLF, with a BOM, and both (G3).

Ids: the bash checks' numbers, M570 + format x 3 + variant. Each variant must ingest
to exactly what its LF original gives (a BOM once hid a CSV header, so the
speaker id became the text): its chunks' times and texts, its words'.
"""

from pathlib import Path
from typing import Final

import pytest

from tests.support.ingesting import ingested

pytestmark = pytest.mark.slow
TRANSCRIPTS: Final = Path(__file__).parents[1] / "fixtures" / "transcripts"
FORMATS: Final = (
    "regular.srt", "regular.vtt", "regular.lrc", "regular.csv", "diarized.csv", "wx.srt", "wx.vtt",
    "wx.tsv", "wx-highlight.srt", "wx.json", "sentences.ojf.json",
)  # fmt: skip
BOM: Final = b"\xef\xbb\xbf"
CASES: Final = [
    pytest.param(name, variant, id=f"M{570 + f * 3 + v}")
    for f, name in enumerate(FORMATS)
    for v, variant in enumerate(("crlf", "bom", "bomcrlf"))
]


def crlf(data: bytes) -> bytes:
    """sed 's/$/\\r/': a CR before each newline, and after a last line without one (shown on GNU sed)."""
    if not data:
        return data  # no line, nothing printed
    ends = data.endswith(b"\n")
    lines = (data[:-1] if ends else data).split(b"\n")
    return b"\n".join(line + b"\r" for line in lines) + (b"\n" if ends else b"")


def digest(path: Path) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """matrix.sh's digest: the chunks' start, end, text; the words' start, end, word."""
    t = ingested(str(path))
    return [(c.start, c.end, c.text) for c in t.chunks], [(w.start, w.end, w.text) for w in t.words]


@pytest.mark.parametrize(("name", "variant"), CASES)
def test_an_encoding(tmp_path: Path, name: str, variant: str) -> None:
    original = (TRANSCRIPTS / name).read_bytes()
    data = {"crlf": crlf(original), "bom": BOM + original, "bomcrlf": BOM + crlf(original)}[variant]
    encoded = tmp_path / f"enc-{variant}{Path(name).suffix}"
    _ = encoded.write_bytes(data)
    assert digest(encoded) == digest(TRANSCRIPTS / name)


@pytest.mark.parametrize(
    ("data", "want"), [(b"a\nb\n", b"a\r\nb\r\n"), (b"a\nb", b"a\r\nb\r"), (b"", b"")]
)
def test_crlf_is_seds(data: bytes, want: bytes) -> None:
    assert crlf(data) == want
