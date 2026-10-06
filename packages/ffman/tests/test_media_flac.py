"""A FLAC's Vorbis comments read from its own block: every way a file may not be one."""

from pathlib import Path

import pytest

from ffman.media import flac


def block(kind: int, body: bytes, *, last: bool = False) -> bytes:
    return bytes([kind | (0x80 if last else 0)]) + len(body).to_bytes(3, "big") + body


def comments(*texts: bytes, vendor: bytes = b"v") -> bytes:
    held = b"".join(len(text).to_bytes(4, "little") + text for text in texts)
    return len(vendor).to_bytes(4, "little") + vendor + len(texts).to_bytes(4, "little") + held


def written(tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "f.flac"
    _ = path.write_bytes(data)
    return str(path)


def test_the_comments_exact_a_block_skipped_to_them(tmp_path: Path) -> None:
    body = comments(b"NAME=line\none", "TITLE=café".encode(), b"no equals sign")
    data = b"fLaC" + block(0, b"\x00" * 34) + block(4, body, last=True)
    assert flac.comments(written(tmp_path, data)) == (
        ("NAME", "line\none"),
        ("TITLE", "café"),
    )  # line break kept


@pytest.mark.parametrize(
    "data",
    [
        b"OggS",  # not a FLAC
        b"fLaC\x00\x00",  # a header cut short
        b"fLaC" + block(0, b"\x00" * 34, last=True),  # no comment block
        b"fLaC" + block(4, b"\x01\x00"),  # its vendor length cut short
        b"fLaC" + block(4, b"\x09\x00\x00\x00v"),  # its count past the block
        b"fLaC" + block(4, b"\x01\x00\x00\x00v\x01\x00\x00\x00"),  # a comment's length missing
        b"fLaC"
        + block(
            4, b"\x01\x00\x00\x00v\x01\x00\x00\x00\x09\x00\x00\x00ab"
        ),  # a comment past the block
        b"fLaC" + block(4, comments(b"NAME=\xff\xfe")),  # not UTF-8
    ],
)
def test_not_a_flacs_comments_is_none(tmp_path: Path, data: bytes) -> None:
    assert flac.comments(written(tmp_path, data)) is None


def test_no_file_is_none(tmp_path: Path) -> None:
    assert flac.comments(str(tmp_path / "missing.flac")) is None


@pytest.mark.parametrize(
    ("data", "held"),
    [
        (
            b"fLaC" + block(0, b"\x00" * 34) + block(5, b"\x00" * 8, last=True),
            True,
        ),  # skipped to it
        (
            b"fLaC" + block(4, comments(b"A=b")) + block(1, b"", last=True),
            False,
        ),  # none: the last passed
        (b"OggS", False),  # not a FLAC
    ],
)
def test_a_cuesheet_block_found_by_its_type(tmp_path: Path, data: bytes, held: bool) -> None:
    assert flac.has_cuesheet(written(tmp_path, data)) is held


def test_no_file_holds_no_cuesheet(tmp_path: Path) -> None:
    assert flac.has_cuesheet(str(tmp_path / "missing.flac")) is False
