"""The tools ffmeta's oracles run -- ffmpeg, ffprobe, metaflac: test oracles, never its runtime."""

import json
import subprocess
from fractions import Fraction
from typing import cast

CD_SECONDS = 600  # conftest's cd_flac: its length


def tool(*argv: str) -> str:
    """A tool's stdout; it must succeed."""
    return subprocess.run(list(argv), capture_output=True, text=True, check=True).stdout  # noqa: S603 -- the pinned tools


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
