"""The camcorder's stamp: PLAY, SP, the counter and a running clock, as ASS (bash's cam_prepare).

The clock starts at --date and --time; each left out comes from the file's
creation time -- as the bash ffman read it: ``date -d`` gave it in *local* time,
and that wall-clock text was then read as UTC (``date -u -d``); so the stamp
shows the local time of the recording -- else from now. The text is gawk's
under LC_ALL=C: English names, whatever the locale.
"""

import math
import re
import time
from datetime import UTC, datetime
from fractions import Fraction
from typing import Final

from ffman.effects.frame import Frame
from ffman.effects.spec import Effect, Param, Request, Stage
from ffman.errors import refuse
from ffman.fmt import calc, round_int
from ffman.graph import Filter, Labels, Open

_DATE: Final = re.compile(r"([0-9]{4})([-:])([0-9]{2})([-:])([0-9]{2})")
_TIME: Final = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]")

STAMP_FONT: Final = "IBM Plex Mono"  # the Style line's, bold (-1), no override
STAMP_FILE: Final = "IBMPlexMono-Bold.otf"  # its one weight, which ffman carries (6.7.3)


def _real_date(text: str) -> bool:
    """A real date, one separator throughout; from 0001-01-01 (GNU date also takes 0000)."""
    match = _DATE.fullmatch(text)
    if match is None or match[2] != match[4]:
        return False
    try:
        _ = datetime(int(match[1]), int(match[3]), int(match[5]), tzinfo=UTC)  # real, or ValueError
    except ValueError:
        return False
    return True


def _is_time(text: str) -> bool:
    return _TIME.fullmatch(text) is not None


EFFECT: Final = Effect(
    "camcorder",
    Stage.CAMCORDER,
    "a camcorder's stamp: PLAY, the counter, SP, a running clock",
    (
        Param(
            "date",
            _real_date,
            "date must be a real date, YYYY-MM-DD or YYYY:MM:DD",
            "the file's creation date, else today",
            auto=False,
        ),
        Param(
            "time",
            _is_time,
            "time must be HH:MM:SS (24-hour)",
            "the file's creation time, else now",
            auto=False,
        ),
    ),
    positional=False,
)


def build(graph: Open, _request: Request, frame: Frame, _: Labels) -> Open:
    """The stamp's script, burned (bash's CAMASS), with its fonts folder."""
    if frame.camcorder is None:
        msg = "the camcorder's script must be written first"
        raise ValueError(msg)
    stamp = frame.camcorder
    return graph.then(Filter("ass", (("filename", stamp.script), ("fontsdir", stamp.fonts))))


MARGIN: Final = 60  # px from the frame's edges, at 1080 lines
HEIGHT: Final = 1080  # the script's PlayResY: sizes are in its pixels
ASS_BREAK: Final = r"\N"  # a hard line break in an ASS event's text
_MONTHS: Final = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)
_HEAD: Final = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cam,{font},64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1.5,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""  # noqa: E501 -- the script's own lines


def clock(
    creation_time: str | None, date: str | None, time_of_day: str | None, now: datetime
) -> int:
    """The stamp's first second, as a UTC epoch (bash's ``e``)."""
    start = _local_wall_clock(creation_time) or now.strftime("%Y-%m-%d %H:%M:%S")
    day, _, hour = start.partition(" ")
    wall = f"{(date or day).replace(':', '-')} {time_of_day or hour}"
    try:
        return int(datetime.strptime(wall, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp())
    except ValueError:
        refuse("the camcorder clock could not be set")


def _local_wall_clock(creation_time: str | None) -> str | None:
    """``date -d CT '+%Y-%m-%d %H:%M:%S'``: the creation time, in local time; None if unreadable."""
    if not creation_time:
        return None
    try:
        moment = datetime.fromisoformat(creation_time)
    except ValueError:
        return None
    local = moment.astimezone() if moment.tzinfo else moment
    return local.strftime("%Y-%m-%d %H:%M:%S")


def width(frame_width: int, frame_height: int) -> int:
    """The script's PlayResX: the frame's shape at 1080 lines (bash's px)."""
    return round_int(calc(HEIGHT * frame_width / frame_height))


def script(epoch: int, duration: Fraction | None, play_width: int) -> str:
    """The ASS script: the fixed marks for the whole clip, a counter and clock a second."""
    seconds = float(duration) if duration is not None else 1.0
    n = max(math.ceil(seconds), 1)
    m, right, bottom = MARGIN, play_width - MARGIN, HEIGHT - MARGIN
    lines = [_HEAD.format(width=play_width, font=STAMP_FONT)]
    lines.append(_event(0, n, rf"{{\an7\pos({m},{m})}}PLAY {{\p1}}m 0 10 l 36 30 0 50{{\p0}}"))
    lines.append(_event(0, n, rf"{{\an1\pos({m},{bottom})}}SP"))
    for k in range(n):
        counter = f"{k // 3600}:{k % 3600 // 60:02d}:{k % 60:02d}"
        lines.append(_event(k, k + 1, rf"{{\an9\pos({right},{m})}}{counter}"))
        lines.append(_event(k, k + 1, rf"{{\an3\pos({right},{bottom})}}{_stamp(epoch + k)}"))
    return "".join(lines)


def _event(start: int, end: int, text: str) -> str:
    return f"Dialogue: 0,{_time(start)},{_time(end)},Cam,,0,0,0,,{text}\n"


def _time(s: int) -> str:
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}.00"


def _stamp(epoch: int) -> str:
    r"""Gawk's strftime("%I:%M:%S %p", e, 1) \N toupper(strftime("%b. %d %Y", e, 1)), C locale."""
    t = time.gmtime(epoch)
    hour = t.tm_hour % 12 or 12
    noon = "AM" if t.tm_hour < 12 else "PM"  # noqa: PLR2004 -- noon
    day = f"{_MONTHS[t.tm_mon - 1]}. {t.tm_mday:02d} {t.tm_year}"
    return f"{hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} {noon}{ASS_BREAK}{day}"
