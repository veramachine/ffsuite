"""The option registry and the parser every command shares.

Parsing follows the bash ffman exactly (docs/ffman-spec.md section 1):
``--opt VALUE`` or ``--opt=VALUE``; an empty ``--opt=`` or a missing value is
refused; an optional value is taken unless the next token starts with ``-``
and a letter or ``-`` (so ``-1`` is a value, and a bad one); a repeated
option keeps its last value, except the repeatable ones. The messages are the
spec's; argparse's own could not keep them.
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Final, NoReturn, overload

from ffman.effects import VIDEO
from ffman.effects.spec import Effect
from ffman.errors import PROG, refuse


class Arity(Enum):
    """How an option takes its value."""

    FLAG = auto()
    VALUE = auto()
    OPTIONAL = auto()  # bare means "auto"
    REPEAT = auto()


class Empty(Enum):
    """What an empty value given apart (``-o ""``) means, as bash tested each option.

    Probed on the bash ffman, option by option: most tested ``[[ -z ]]`` or
    ``${X:-default}`` (UNSET); a few kept it and validated it, or used it as
    given (VALUE).
    """

    UNSET = auto()
    VALUE = auto()


class Group(Enum):
    """The sections of a command's help, in order."""

    IO = "Input and output"
    PICTURE = "Picture"
    EFFECTS = "Effects"
    BURN = "Burned subtitles"
    TRACK = "Subtitle tracks"
    ENCODING = "Encoding"
    GIF = "GIF"
    TAGS = "Tags"
    CHAPTERS = "Chapters"
    CUE = "A cue sheet's own"
    COMMON = "Common"


@dataclass(frozen=True, slots=True)
class Option:
    """One option: its spellings, how it takes a value, and its help line."""

    names: tuple[str, ...]
    dest: str
    arity: Arity
    help: str
    group: Group
    metavar: str = ""
    empty: Empty = Empty.UNSET


@dataclass(slots=True)
class Parsed:
    """What the parser found: raw strings, validated later by the command."""

    values: dict[str, str] = field(default_factory=dict[str, str])
    lists: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    flags: set[str] = field(default_factory=set[str])
    given: set[str] = field(default_factory=set[str])
    help: bool = False

    @overload
    def value(self, dest: str) -> str | None: ...
    @overload
    def value(self, dest: str, default: str) -> str: ...
    def value(self, dest: str, default: str | None = None) -> str | None:
        """The last value given for ``dest``, or ``default`` (None: not given)."""
        return self.values.get(dest, default)

    def all(self, dest: str) -> list[str]:
        """Every value given for a repeatable ``dest``, in order."""
        return self.lists.get(dest, [])

    def flag(self, dest: str) -> bool:
        """Whether the flag ``dest`` was given."""
        return dest in self.flags


_FONT_COLOR_HELP: Final = (
    "the text's colour: white (default), a colour name, #RRGGBB, " + "rainbow, lsd or iridescent"
)
_OUTLINE_COLOR_HELP: Final = (
    "its outline's: black or white, whichever contrasts more (default), a colour name, "
    + "#RRGGBB, rainbow, lsd or iridescent"
)
_COLORIZE_HELP: Final = (
    "gold (default), a colour name, #RRGGBB, rainbow, lsd, iridescent or rectangle; "
    + "with chunk-word or word-highlight"
)

COMMON: Final = (
    Option(("-h", "--help"), "help", Arity.FLAG, "show this help", Group.COMMON),
    Option(
        ("-y", "--overwrite"), "overwrite", Arity.FLAG, "replace an existing output", Group.COMMON
    ),
    Option(
        ("--dry-run",),
        "dry_run",
        Arity.FLAG,
        "print the plan and the ffmpeg commands; write nothing",
        Group.COMMON,
    ),
)

CONVERT: Final = (
    Option(("-i", "--input"), "input", Arity.VALUE, "the source (required)", Group.IO, "FILE"),
    Option(
        ("-o", "--output"),
        "output",
        Arity.VALUE,
        "the output; its extension picks the container (default: STEM.ffman.EXT)",
        Group.IO,
        "FILE",
    ),
    Option(("--in-place",), "in_place", Arity.FLAG, "replace the input", Group.IO),
    Option(("-w", "-W", "--width"), "width", Arity.VALUE, "target width", Group.PICTURE, "N"),
    Option(("-H", "--height"), "height", Arity.VALUE, "target height", Group.PICTURE, "N"),
    Option(
        ("-a", "--aspect-ratio"),
        "aspect",
        Arity.VALUE,
        "target shape, e.g. 16:9, 9:16, 2.39:1",
        Group.PICTURE,
        "A:B",
    ),
    Option(
        ("-r", "--resize-mode"),
        "resize_mode",
        Arity.VALUE,
        "fit (default: borders), cover (crop), stretch",
        Group.PICTURE,
        "MODE",
        empty=Empty.VALUE,
    ),
    Option(
        ("-b", "--bblur"),
        "bblur",
        Arity.OPTIONAL,
        "fill fit's borders with the picture, blurred (default sigma: auto)",
        Group.PICTURE,
        "[SIGMA]",
        empty=Empty.VALUE,
    ),
    Option(
        ("--vfx",),
        "vfx",
        Arity.REPEAT,
        "a video effect, NAME[:VALUE]; repeatable (see ffman effects)",
        Group.EFFECTS,
        "SPEC",
        empty=Empty.VALUE,
    ),
    Option(
        ("--burn-subs",),
        "burn_subs",
        Arity.VALUE,
        "burn in a transcript: srt vtt lrc csv tsv json ass ssa",
        Group.BURN,
        "FILE",
    ),
    Option(
        ("--overlay-mode",),
        "overlay_mode",
        Arity.VALUE,
        "plain (default), chunk-word, word, word-highlight",
        Group.BURN,
        "MODE",
        empty=Empty.VALUE,
    ),
    Option(
        ("--highlight-mode",),
        "highlight_mode",
        Arity.VALUE,
        "plain (default) or pop; with chunk-word or word-highlight",
        Group.BURN,
        "MODE",
        empty=Empty.VALUE,
    ),
    Option(
        ("--highlight-colorize",),
        "highlight_colorize",
        Arity.VALUE,
        _COLORIZE_HELP,
        Group.BURN,
        "COLOUR",
        empty=Empty.VALUE,
    ),
    Option(
        ("--font-color",),
        "font_color",
        Arity.VALUE,
        _FONT_COLOR_HELP,
        Group.BURN,
        "COLOUR",
        empty=Empty.VALUE,
    ),
    Option(
        ("--outline-color",),
        "outline_color",
        Arity.VALUE,
        _OUTLINE_COLOR_HELP,
        Group.BURN,
        "COLOUR",
        empty=Empty.VALUE,
    ),
    Option(
        ("-f", "--font"),
        "font",
        Arity.VALUE,
        "font family (default: IBM Plex Sans)",
        Group.BURN,
        "NAME",
        empty=Empty.VALUE,
    ),
    Option(
        ("--font-size",),
        "font_size",
        Arity.VALUE,
        "points on a 1080-line frame (default: 57 plain, else 64)",
        Group.BURN,
        "N",
    ),
    Option(
        ("--margin-bottom",),
        "margin_bottom",
        Arity.VALUE,
        "text bottom to frame bottom: 0.05 or 5%",
        Group.BURN,
        "M",
        empty=Empty.VALUE,
    ),
    Option(
        ("--metadata",),
        "metadata",
        Arity.VALUE,
        "a metadata file's tags and chapters, applied: .ffmeta, .txt, .cue",
        Group.TRACK,
        "FILE",
    ),
    Option(
        ("--add-subs",),
        "add_subs",
        Arity.REPEAT,
        "add a transcript as a subtitle track",
        Group.TRACK,
        "FILE",
    ),
    Option(
        ("--language",),
        "language",
        Arity.REPEAT,
        "its ISO 639-2 code (eng, por, ...), one per --add-subs",
        Group.TRACK,
        "CODE",
    ),
    Option(
        ("-p", "--preset"),
        "preset",
        Arity.VALUE,
        "youtube (alias: yt); a .txt output's format: ffmetadata (default), vorbiscomment",
        Group.ENCODING,
        "NAME",
    ),
    Option(
        ("--video-codec",),
        "video_codec",
        Arity.VALUE,
        "h264, hevc, vp9, av1 or ffv1, lossless (default: a remux copies; a resize, the source's)",
        Group.ENCODING,
        "C",
    ),
    Option(
        ("--audio-codec",),
        "audio_codec",
        Arity.VALUE,
        "copy (default), none, flac, aac, opus, mp3, vorbis, alac, pcm",
        Group.ENCODING,
        "C",
    ),
    Option(
        ("--lossless",),
        "lossless",
        Arity.FLAG,
        "re-encode losslessly (the default for now)",
        Group.ENCODING,
    ),
    Option(
        ("--normalize",),
        "normalize",
        Arity.FLAG,
        "normalise the audio even when it already complies (with --preset)",
        Group.ENCODING,
    ),
    Option(("--loop",), "loop", Arity.FLAG, "play forever", Group.GIF),
    Option(
        ("--loop-reverse",),
        "loop_reverse",
        Arity.FLAG,
        "play forward, then backward, forever",
        Group.GIF,
    ),
    *COMMON,
)

# Old spellings, refused with their equivalent (D4; docs/ffman-spec.md section 7).


def _effect_migration(effect: Effect) -> str:
    """An old effect flag's message, from the registry: the --vfx form it takes."""
    now = f"--{effect.name} is now --vfx {effect.name}"
    if not effect.params:
        return now
    if effect.positional:
        return f"{now} (a value: --vfx {effect.name}:VALUE)"
    named = ",".join(f"{p.name}={p.name[0].upper()}" for p in effect.params)
    return f"{now} (its values: --vfx {effect.name}:{named})"


MIGRATED: Final[dict[str, str]] = {
    "--input-video": "--input-video is now --input",
    "--input-media": "--input-media is now --input",
    "--input-subs": "--input-subs is now --burn-subs (burn in) or --add-subs (a track)",
    "-l": "-l is now --language",
    "--date": "--date and --time are now parameters: --vfx camcorder:date=D,time=T",
    "--time": "--date and --time are now parameters: --vfx camcorder:date=D,time=T",
    "-s": "-s is now --overlay-mode plain",
    "--standard": "--standard is now --overlay-mode plain",
    "--chunk-word": "--chunk-word is now --overlay-mode chunk-word",
    "--word": "--word is now --overlay-mode word",
    "--word-highlight": "--word-highlight is now --overlay-mode word-highlight",
    **{f"--{e.name}": _effect_migration(e) for e in VIDEO},
}

# An optional value is taken unless the next token looks like an option (bash's optval).
_LOOKS_LIKE_OPTION: Final = re.compile(r"-[A-Za-z-]")

META: Final = (
    Option(
        ("-i", "--input"),
        "input",
        Arity.VALUE,
        "a metadata file or a media file (default: none -- a new file)",
        Group.IO,
        "FILE",
    ),
    Option(
        ("-o", "--output"),
        "output",
        Arity.VALUE,
        "the output: .ffmeta, .txt or .cue; - for stdout (default: STEM.ffman.EXT)",
        Group.IO,
        "FILE",
    ),
    Option(("--in-place",), "in_place", Arity.FLAG, "replace the input", Group.IO),
    Option(
        ("-p", "--preset"),
        "preset",
        Arity.VALUE,
        "a .txt's format: ffmetadata (default), vorbiscomment; for -o -, cue too",
        Group.IO,
        "NAME",
    ),
    Option(
        ("--set",),
        "set",
        Arity.REPEAT,
        "KEY's one value: ffmpeg's generic keys (title, artist, album_artist...), any case",
        Group.TAGS,
        "KEY=VALUE",
    ),
    Option(("--add",), "add", Arity.REPEAT, "one more value for KEY", Group.TAGS, "KEY=VALUE"),
    Option(("--unset",), "unset", Arity.REPEAT, "KEY's every value gone", Group.TAGS, "KEY"),
    Option(("--clear",), "clear", Arity.FLAG, "every tag gone (before the others)", Group.TAGS),
    Option(
        ("--chapter",),
        "chapter",
        Arity.REPEAT,
        "one more chapter (a cue's track); TIME: SECONDS, M:SS, H:MM:SS (.fraction) or FRAMESf",
        Group.CHAPTERS,
        "TIME[..END][=TITLE]",
    ),
    Option(
        ("--retitle",),
        "retitle",
        Arity.REPEAT,
        "the input's chapter N's title",
        Group.CHAPTERS,
        "N=TITLE",
    ),
    Option(
        ("--chapter-set",),
        "chapter_set",
        Arity.REPEAT,
        "a tag of the input's chapter N",
        Group.CHAPTERS,
        "N:KEY=VALUE",
    ),
    Option(
        ("--drop-chapter",),
        "drop_chapter",
        Arity.REPEAT,
        "the input's chapter N gone",
        Group.CHAPTERS,
        "N",
    ),
    Option(
        ("--clear-chapters",), "clear_chapters", Arity.FLAG, "every chapter gone", Group.CHAPTERS
    ),
    Option(
        ("--flags",),
        "flags",
        Arity.REPEAT,
        "the input cue's track N's: DCP, 4CH, PRE, SCMS, comma-separated (empty: none)",
        Group.CUE,
        "N=FLAGS",
    ),
    Option(
        ("--pregap",),
        "pregap",
        Arity.REPEAT,
        "the input cue's track N's INDEX 00, its pregap in the file (empty: none)",
        Group.CUE,
        "N=TIME",
    ),
    Option(("--file",), "file", Arity.VALUE, "the media the cue's FILE names", Group.CUE, "NAME"),
    *COMMON,
)


def parse(command: str, registry: tuple[Option, ...], argv: list[str]) -> Parsed:
    """Parse ``argv`` for ``command`` against ``registry``."""
    index = {name: option for option in registry for name in option.names}
    parsed = Parsed()
    i = 0
    while i < len(argv):
        token = argv[i]
        name, has_equals, attached = (
            token.partition("=") if token.startswith("--") else (token, "", "")
        )
        option = index.get(name)
        if option is None:
            _refuse_unknown(command, name)
        if has_equals and option.arity is Arity.FLAG:
            _refuse_unknown(command, token)
        if option.dest == "help":
            parsed.help = True
            return parsed
        if option.arity is Arity.FLAG:
            parsed.given.add(option.dest)
            parsed.flags.add(option.dest)
            i += 1
            continue
        value, i = _take_value(option, name, attached if has_equals else None, argv, i)
        if not value and option.empty is Empty.UNSET:
            continue  # bash: [[ -z ]] -- as if not given (docs/ffman-spec.md section 1)
        parsed.given.add(option.dest)
        if option.arity is Arity.REPEAT:
            parsed.lists.setdefault(option.dest, []).append(value)
        else:
            parsed.values[option.dest] = value
    return parsed


def _take_value(
    option: Option, name: str, attached: str | None, argv: list[str], i: int
) -> tuple[str, int]:
    """The value of the option at ``argv[i]``, and the index after it."""
    missing = f"option {name} requires a value"
    if attached is not None:
        if not attached:
            refuse(missing)
        return attached, i + 1
    nxt = argv[i + 1] if i + 1 < len(argv) else None
    if option.arity is Arity.OPTIONAL:
        if nxt is None or _LOOKS_LIKE_OPTION.match(nxt):
            return "auto", i + 1
        return nxt, i + 2
    if nxt is None:
        refuse(missing)
    return nxt, i + 2


def _refuse_unknown(command: str, token: str) -> NoReturn:
    if token in MIGRATED:
        refuse(MIGRATED[token])
    refuse(f"{command}: unknown option: {token} (see {PROG} {command} --help)")


def format_help(usage: str, summary: str, registry: tuple[Option, ...]) -> str:
    """The help text: usage, summary, then each group's options in registry order."""
    lines = [f"Usage: {usage}", "", summary]
    rows = [(option, _spelling(option)) for option in registry]
    width = max(len(spelling) for _, spelling in rows) + 2
    for group in Group:
        in_group = [(o, s) for o, s in rows if o.group is group]
        if in_group:
            lines += ["", f"{group.value}:"]
            lines += [f"  {s.ljust(width)}{o.help}" for o, s in in_group]
    return "\n".join(lines) + "\n"


def _spelling(option: Option) -> str:
    names = ", ".join(option.names)
    return f"{names} {option.metavar}" if option.metavar else names
