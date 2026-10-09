"""Helpers for tests on real media: the pinned tools, run as run.sh ran them."""

import hashlib
import json
import subprocess
from fractions import Fraction
from typing import cast

import pytest

from ffman.cli import main

CD_SECONDS = 600  # conftest's cd_flac: its length


def status(*argv: str) -> int:
    """A tool's exit status, unchecked: its answer, when failing is one."""
    return subprocess.run(list(argv), capture_output=True, check=False).returncode  # noqa: S603 -- the pinned tools


def tool(*argv: str) -> str:
    """A tool's stdout; it must succeed."""
    return subprocess.run(list(argv), capture_output=True, text=True, check=True).stdout  # noqa: S603 -- the pinned tools


def raw(*argv: str) -> bytes:
    """A tool's stdout as bytes (frames, samples); it must succeed."""
    return subprocess.run(list(argv), capture_output=True, check=True).stdout  # noqa: S603 -- the pinned tools


def ff(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    """``ffman convert ARGV``, in process: its status and stderr."""
    status = main(["convert", *argv])
    return status, capsys.readouterr().err


def probe(ffprobe: str, path: str, entries: str, streams: str = "v:0") -> str:
    """ffprobe's entries for the streams, as run.sh's csv read them (``x`` between)."""
    command = [ffprobe, "-v", "error", "-select_streams", streams, "-show_entries", entries]
    return tool(*command, "-of", "csv=p=0:s=x", path).strip()


def frames(ffmpeg: str, *args: str) -> str:
    """run.sh's vmd5: the md5 of each frame's md5, in order."""
    out = tool(ffmpeg, "-hide_banner", "-loglevel", "error", *args, "-f", "framemd5", "-")
    lines = [
        line.rsplit(",", 1)[-1].strip() for line in out.splitlines() if not line.startswith("#")
    ]
    # run.sh's md5sum: a fingerprint to compare, no security
    digest = hashlib.md5("".join(f"{x}\n" for x in lines).encode(), usedforsecurity=False)
    return digest.hexdigest()


type Seen = tuple[
    dict[str, str], list[dict[str, str]], list[tuple[Fraction, Fraction, dict[str, str]]]
]


def metadata_seen(ffprobe: str, path: str) -> Seen:
    """What ffprobe reads of a file's metadata: its tags, each stream's, chapters at exact times."""
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-of",
        "json",
        path,
    )
    root = cast("dict[str, object]", json.loads(shown))
    streams = cast("list[dict[str, dict[str, str]]]", root.get("streams", []))
    chapters = cast("list[dict[str, object]]", root.get("chapters", []))

    def at(chapter: dict[str, object], key: str) -> Fraction:
        return cast("int", chapter[key]) * Fraction(cast("str", chapter["time_base"]))

    return (
        cast("dict[str, dict[str, str]]", root["format"]).get("tags", {}),
        [stream.get("tags", {}) for stream in streams],
        [
            (at(c, "start"), at(c, "end"), cast("dict[str, str]", c.get("tags", {})))
            for c in chapters
        ],
    )
