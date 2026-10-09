"""ffprobe's JSON, as the bash ffman read it: the fields it used, typed.

Stage A reads exactly what bash's ``pq`` read (``jq -r "QUERY // empty"``): a
field absent or null is None, and so is empty text (every use tested it with
``[[ -z ]]``/``-n``); strings stay text and integers integers, the numbers below
typed. The streams bash meant (its VSEL and ASEL): the first video that is not
an attached picture (cover art), and the first audio. The rotation: the display
matrix's -- always an integer, as ffprobe writes it (``print_int``,
fftools/ffprobe.c, n8.1.2) -- else the legacy ``rotate`` tag; text, as bash
read it, for geometry to interpret.

Numbers are typed here, once, in the forms ffprobe prints (fftools/textformat/
avtextformat.c, n8.1.2): a ratio is ``%d/%d`` or ``%d:%d`` -- a ``Rational``,
exact and unreduced, ``0/0`` (unknown) kept, since its users tell those apart;
a duration is ``%f`` -- a ``Fraction``; the sample rate an integer. JSON never
holds "N/A": an optional field is left out (the JSON writer does not declare
AV_TEXTFORMAT_FLAG_SUPPORTS_OPTIONAL_FIELDS), so absent is None.
"""

import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final, Literal, Protocol, Self, cast

from ffman.errors import refuse
from ffman.media.paths import file_url

_SECONDS: Final = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")  # %f, or any decimal (as awk read them)
_COUNT: Final = re.compile(r"0|[1-9][0-9]*")  # %d, unsigned: no leading zero
_INTEGER: Final = re.compile(r"0|-?[1-9][0-9]*")  # %d: no leading zero, no "-0"


@dataclass(frozen=True, slots=True)
class Rational:
    """A ratio as ffprobe printed it: two integers, as they were (``0/0`` is unknown)."""

    num: int
    den: int

    @classmethod
    def parse(cls, text: str | None, sep: Literal["/", ":"] = "/") -> Self | None:
        """``%d{sep}%d`` as ffprobe prints a ratio (avtext_print_rational); else None."""
        num, found, den = (text or "").partition(sep)
        if not found or not (_INTEGER.fullmatch(num) and _INTEGER.fullmatch(den)):
            return None
        return cls(int(num), int(den))

    def text(self) -> str:
        """``num/den``, as ffprobe printed a rate or a time base."""
        return f"{self.num}/{self.den}"


_UNSET: Final = Rational(0, 0)  # ffprobe's unknown rate


class Capturing(Protocol):
    """What reading needs of a runner: run a read-only tool, its output captured."""

    def capture(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run ``argv``; its status and output."""
        ...


@dataclass(frozen=True, slots=True)
class Video:
    """The picture stream's fields bash read."""

    codec: str | None
    width: int | None
    height: int | None
    rotation: str | None
    sar: Rational | None
    time_base: Rational | None
    duration: Fraction | None
    avg_frame_rate: Rational | None
    r_frame_rate: Rational | None
    pix_fmt: str | None
    field_order: str | None
    color_primaries: str | None
    color_transfer: str | None
    color_range: str | None
    color_space: str | None

    def frame_rate(self) -> Rational | None:
        """The rate its frames come at: the average, else (ffprobe's 0/0) the base rate.

        As bash's convert chose it.
        """
        average = self.avg_frame_rate
        return average if average is not None and average != _UNSET else self.r_frame_rate

    def frame_time(self) -> Fraction | None:
        """A frame's duration in seconds, at ``frame_rate``; None if unknown.

        Where the rate varies, the average frame's.
        """
        rate = self.frame_rate()
        if rate is None or rate.num <= 0 or rate.den <= 0:
            return None
        return Fraction(rate.den, rate.num)


@dataclass(frozen=True, slots=True)
class Audio:
    """The audio stream's fields bash read."""

    codec: str | None
    profile: str | None
    channels: int | None
    sample_rate: int | None


@dataclass(frozen=True, slots=True)
class Subtitle:
    """A subtitle stream: its codec, and what names it to a reader."""

    codec: str | None
    language: str | None
    title: str | None


@dataclass(frozen=True, slots=True)
class Attachment:
    """An attachment stream: the file it was, by name (a metadata file is told by it)."""

    filename: str | None


@dataclass(frozen=True, slots=True)
class Cover:
    """A picture marked attached_pic: its index among the video streams (``0:v:N``), codec, size."""

    index: int
    codec: str | None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Media:
    """A probed file: its picture and audio (None without one), counts, duration, creation, tags."""

    video: Video | None
    audio: Audio | None
    subtitles: tuple[Subtitle, ...]  # each subtitle stream, in order
    attachments: tuple[Attachment, ...]  # each attachment stream, in order
    duration: Fraction | None
    creation_time: str | None
    tags: tuple[tuple[str, str], ...] = ()  # the format's, as ffprobe reads them, in order
    covers: tuple[Cover, ...] = ()  # pictures marked attached_pic (a Matroska cover.* too)
    pictures: int = 0  # the video streams not covers: a cover's place in an output comes after


type _Json = dict[str, object]


def parse(text: str) -> Media:
    """Media from ffprobe's ``-show_streams -show_format -of json`` output."""
    root = _object(cast("object", json.loads(text)))
    streams = [_object(s) for s in _list(root.get("streams"))]
    video = next((s for s in streams if _kind(s) == "video" and _attached_pic(s) == 0), None)
    audio = next((s for s in streams if _kind(s) == "audio"), None)
    videos = [s for s in streams if _kind(s) == "video"]
    tags = _object(_object(root.get("format")).get("tags"))
    return Media(
        video=_video(video) if video is not None else None,
        audio=_audio(audio) if audio is not None else None,
        subtitles=tuple(_subtitle(s) for s in streams if _kind(s) == "subtitle"),
        attachments=tuple(_attachment(s) for s in streams if _kind(s) == "attachment"),
        duration=_seconds(_object(root.get("format")).get("duration")),
        creation_time=_text(tags.get("creation_time")),
        tags=tuple((name, value) for name, value in tags.items() if isinstance(value, str)),
        covers=tuple(_cover(i, s) for i, s in enumerate(videos) if _attached_pic(s) != 0),
        pictures=sum(1 for s in videos if _attached_pic(s) == 0),
    )


def tag_names(text: str) -> frozenset[str] | None:
    """The format's tag names, lower-cased: ffprobe's ``-show_entries format_tags -of json``.

    None where the text is not that shape (unreadable, not tagless).
    """
    root = _dict(cast("object", json.loads(text)))
    found = _dict(root.get("format", {})) if root is not None else None
    tags = _dict(found.get("tags", {})) if found is not None else None
    return None if tags is None else frozenset(name.lower() for name in tags)


def read(path: str, runner: Capturing) -> Media:
    """Probe ``path`` (read-only: it runs under --dry-run too), with bash's refusals."""
    if not Path(path).is_file():
        refuse(f"no such file: {path}")
    argv = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", "--"]
    result = runner.capture([*argv, file_url(path)])
    if result.returncode != 0:
        refuse(f"ffprobe cannot read: {path}")
    try:
        return parse(result.stdout)
    except ValueError:  # not JSON: bash's jq read nothing from it
        refuse(f"ffprobe cannot read: {path}")


def _video(s: _Json) -> Video:
    return Video(
        codec=_text(s.get("codec_name")),
        width=_int(s.get("width")),
        height=_int(s.get("height")),
        rotation=_rotation(s),
        sar=_rational(s.get("sample_aspect_ratio"), ":"),
        time_base=_rational(s.get("time_base"), "/"),
        duration=_seconds(s.get("duration")),
        avg_frame_rate=_rational(s.get("avg_frame_rate"), "/"),
        r_frame_rate=_rational(s.get("r_frame_rate"), "/"),
        pix_fmt=_text(s.get("pix_fmt")),
        field_order=_text(s.get("field_order")),
        color_primaries=_text(s.get("color_primaries")),
        color_transfer=_text(s.get("color_transfer")),
        color_range=_text(s.get("color_range")),
        color_space=_text(s.get("color_space")),
    )


def _audio(s: _Json) -> Audio:
    return Audio(
        codec=_text(s.get("codec_name")),
        profile=_text(s.get("profile")),
        channels=_int(s.get("channels")),
        sample_rate=_count(s.get("sample_rate")),
    )


def _rotation(s: _Json) -> str | None:
    """bash: ``[.side_data_list[]? | .rotation | numbers][0] // .tags.rotate``."""
    for entry in _list(s.get("side_data_list")):
        rotation = _object(entry).get("rotation")
        if _is_number(rotation):
            return _number_text(rotation)
    return _text(_object(s.get("tags")).get("rotate"))


def _subtitle(s: _Json) -> Subtitle:
    tags = _object(s.get("tags"))
    return Subtitle(
        _text(s.get("codec_name")), _text(tags.get("language")), _text(tags.get("title"))
    )


def _attachment(s: _Json) -> Attachment:
    tags = _object(s.get("tags"))
    return Attachment(_text(tags.get("filename")))


def _kind(s: _Json) -> object:
    return s.get("codec_type")


def _attached_pic(s: _Json) -> object:
    """bash: ``.disposition.attached_pic // 0``."""
    flag = _object(s.get("disposition")).get("attached_pic")
    return 0 if flag is None or flag is False else flag


def _dict(value: object) -> _Json | None:
    return cast("_Json", value) if isinstance(value, dict) else None


def _object(value: object) -> _Json:
    return _dict(value) or {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _text(value: object) -> str | None:
    """A string field as ``pq`` gave it; empty or not a string reads as None."""
    return value if isinstance(value, str) and value else None


def _rational(value: object, sep: Literal["/", ":"]) -> Rational | None:
    return Rational.parse(_text(value), sep)


def _seconds(value: object) -> Fraction | None:
    """A time as ffprobe prints it (``%f``), exactly; else None."""
    text = _text(value)
    return Fraction(text) if text is not None and _SECONDS.fullmatch(text) else None


def _count(value: object) -> int | None:
    """An unsigned integer printed as text (ffprobe's sample rate); else None."""
    text = _text(value)
    return int(text) if text is not None and _COUNT.fullmatch(text) else None


def _cover(index: int, s: _Json) -> Cover:
    return Cover(index, _text(s.get("codec_name")), _int(s.get("width")), _int(s.get("height")))


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _is_number(value: object) -> bool:
    """An int or a float, never a bool (jq's ``numbers``)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number_text(value: object) -> str:
    """A JSON number as ``jq -r`` prints it; ffprobe's rotation is always an integer."""
    return str(value)
