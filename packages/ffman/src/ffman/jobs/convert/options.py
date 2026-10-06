"""``convert``'s options: validated and typed, with the spec's messages.

Rules that need the source (image or video, its size) are the planner's;
these are the ones the options alone decide (docs/ffman-spec.md section 3).
"""

import re
from fractions import Fraction
from typing import Final, Literal, NamedTuple

from ffmeta.files import TEXT_PRESETS

from ffman.effects import parse_specs
from ffman.errors import refuse
from ffman.fmt import awk_print
from ffman.graph.resize import BBLUR_MAX, RESIZE_MODES, BBlur, ResizeMode, bblur_on
from ffman.options import Parsed
from ffman.plan.encode import AUDIO_CODECS, VIDEO_ALIASES
from ffman.plan.geometry import parse_aspect
from ffman.plan.request import (
    HIGHLIGHT_MODES,
    OVERLAY_MODES,
    ConvertOptions,
    HighlightMode,
    OverlayMode,
    Preset,
)
from ffman.subs.ass import HIGHLIGHTING, MARGIN
from ffman.subs.colorize import GOLD, WHITE, Colorize, Highlight, parse_highlight
from ffman.subs.colorize import parse as parse_colorize
from ffman.subs.layout import font_size
from ffman.values import is_num, is_uint

_PERCENT: Final = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")
_LANGUAGE: Final = re.compile(r"[a-z]{3}")
_BURN_ONLY: Final = (
    "overlay_mode",
    "highlight_mode",
    "highlight_colorize",
    "font_color",
    "outline_color",
    "font",
    "font_size",
    "margin_bottom",
)
_COLOURS: Final = "#RRGGBB, a colour name, rainbow, lsd or iridescent"  # what a colour may be
_HIGHLIGHTS: Final = "#RRGGBB, a colour name, rainbow, lsd, iridescent or rectangle"
_HIGHLIGHTED: Final = ("highlight_mode", "highlight_colorize")  # the highlighted word's look
_PRESETS: Final[tuple[Preset, ...]] = ("youtube", *TEXT_PRESETS)


def validate(parsed: Parsed) -> ConvertOptions:
    """Check ``parsed`` against the spec, section by section; return the typed options."""
    input_path = parsed.value("input")
    if not input_path:
        refuse("convert: --input is required")
    width, height, aspect, mode, bblur = _picture(parsed)
    burn = _burn(parsed)
    add_subs, languages = _tracks(parsed)
    preset, video_codec, audio_codec = _encoding(parsed)
    if parsed.flag("loop") and parsed.flag("loop_reverse"):
        refuse("--loop and --loop-reverse exclude each other")
    if parsed.flag("in_place") and parsed.value("output") is not None:
        refuse("--in-place and --output exclude each other")
    return ConvertOptions(
        input=input_path,
        output=parsed.value("output"),
        in_place=parsed.flag("in_place"),
        overwrite=parsed.flag("overwrite"),
        dry_run=parsed.flag("dry_run"),
        width=width,
        height=height,
        aspect=aspect,
        aspect_text=parsed.value("aspect"),
        resize_mode=mode,
        bblur=bblur,
        effects=parse_specs(parsed.all("vfx")),
        burn_subs=parsed.value("burn_subs"),
        overlay_mode=burn.overlay_mode,
        highlight_mode=burn.highlight_mode,
        highlight_colorize=burn.colorize,
        font_color=burn.text,
        outline_color=burn.outline,
        font=burn.font,
        font_size=burn.font_size,
        margin_bottom=burn.margin,
        margin_bottom_given="margin_bottom" in parsed.given,
        add_subs=add_subs,
        metadata=parsed.value("metadata") or None,  # an empty value is none (spec 1)
        languages=languages,
        preset=preset,
        video_codec=video_codec,
        audio_codec=audio_codec,
        lossless=parsed.flag("lossless"),
        normalize=parsed.flag("normalize"),
        loop="reverse"
        if parsed.flag("loop_reverse")
        else "loop"
        if parsed.flag("loop")
        else "once",
    )


def _picture(
    parsed: Parsed,
) -> tuple[int | None, int | None, tuple[Fraction, Fraction] | None, ResizeMode, BBlur]:
    width, height = _uint(parsed, "width"), _uint(parsed, "height")
    aspect_text = parsed.value("aspect")
    aspect = parse_aspect(aspect_text) if aspect_text is not None else None
    given = parsed.value("resize_mode", "fit")
    mode: ResizeMode = _choice(
        given, RESIZE_MODES, f"--resize-mode must be stretch, cover or fit: {given}"
    )
    text = parsed.value("bblur", "0")
    if text != "auto" and not (is_num(text) and Fraction(text) <= BBLUR_MAX):
        refuse(f"--bblur must be auto or a number from 0 to 1024: {text}")
    bblur: BBlur = "auto" if text == "auto" else Fraction(text)
    if bblur_on(bblur) and mode != "fit":
        why = "(the only mode with borders)"
        refuse(f"--bblur only applies to --resize-mode fit {why}; got --resize-mode {mode}")
    return width, height, aspect, mode, bblur


class _Burn(NamedTuple):
    overlay_mode: OverlayMode
    highlight_mode: HighlightMode
    colorize: Highlight
    text: Colorize
    outline: Colorize | None
    font: str
    font_size: Fraction
    margin: Fraction


def _burn(parsed: Parsed) -> _Burn:
    if parsed.value("burn_subs") is None:
        for dest in _BURN_ONLY:
            if dest in parsed.given:
                refuse(f"--{dest.replace('_', '-')} needs --burn-subs")
    given = parsed.value("overlay_mode", "plain")
    overlay_mode: OverlayMode = _choice(
        given,
        OVERLAY_MODES,
        f"--overlay-mode must be plain, chunk-word, word or word-highlight: {given}",
    )
    given = parsed.value("highlight_mode", "plain")
    highlight_mode: HighlightMode = _choice(
        given, HIGHLIGHT_MODES, f"--highlight-mode must be plain or pop: {given}"
    )
    for dest in _HIGHLIGHTED:  # only a highlighting mode highlights a word
        if dest in parsed.given and overlay_mode not in HIGHLIGHTING:
            refuse(f"--{dest.replace('_', '-')} needs --overlay-mode chunk-word or word-highlight")
    given = parsed.value("highlight_colorize")
    colorize = GOLD if given is None else parse_highlight(given)
    if colorize is None:
        refuse(f"--highlight-colorize must be {_HIGHLIGHTS}: {given}")
    text = parsed.value("font_size")
    if text is not None and not (is_num(text) and Fraction(text) > 0):
        refuse(f"--font-size must be a positive number: {text}")
    size = font_size(None if text is None else Fraction(text), plain=overlay_mode == "plain")
    font = parsed.value("font", "IBM Plex Sans")  # bash kept an empty family as given
    if "," in font:
        refuse(f"--font must not contain a comma: {font}")
    text, outline = _colour(parsed, "font_color") or WHITE, _colour(parsed, "outline_color")
    margin = _margin(parsed.value("margin_bottom"))
    return _Burn(overlay_mode, highlight_mode, colorize, text, outline, font, size, margin)


def _colour(parsed: Parsed, dest: str) -> Colorize | None:
    """A colour option's value -- a hex, a colour's name or a motion -- or none, not given."""
    given = parsed.value(dest)
    if given is None:
        return None
    found = parse_colorize(given)
    if found is None:
        refuse(f"--{dest.replace('_', '-')} must be {_COLOURS}: {given}")
    return found


def _tracks(parsed: Parsed) -> tuple[tuple[str, ...], tuple[str, ...]]:
    add_subs, languages = parsed.all("add_subs"), parsed.all("language")
    if len(add_subs) > 1:
        refuse(f"--add-subs given {len(add_subs)} times: one track per run, for now")
    for language in languages:
        if not _LANGUAGE.fullmatch(language):
            refuse(f"--language must be a three-letter ISO 639-2 code (eng, por, ...): {language}")
    if languages and len(languages) != len(add_subs):
        counts = f"{len(languages)} --language for {len(add_subs)} --add-subs"
        refuse(f"each --add-subs takes one --language: got {counts}")
    return tuple(add_subs), tuple(languages)


def _encoding(parsed: Parsed) -> tuple[Preset | None, str | None, str]:
    preset = _preset(parsed)
    video_codec = parsed.value("video_codec")
    if video_codec is not None and video_codec.lower() not in (
        *VIDEO_ALIASES,
        "copy",
    ):  # copy: plan.streams decides (refused: the picture is re-rendered)
        choose = "choose --video-codec h264, hevc, vp9, av1 or ffv1"
        refuse(f"no lossless encoder for video codec '{video_codec.lower()}'; {choose}")
    audio_codec = parsed.value("audio_codec", "copy").lower()
    if audio_codec not in AUDIO_CODECS:
        refuse(f"unsupported --audio-codec '{audio_codec}' ({', '.join(AUDIO_CODECS)})")
    return preset, video_codec.lower() if video_codec is not None else None, audio_codec


def _choice[T: str](value: str, choices: tuple[T, ...], message: str) -> T:
    """The element of ``choices`` equal to ``value`` (typed as the choice), or refuse."""
    match = next((choice for choice in choices if choice == value), None)
    if match is None:
        refuse(message)
    return match


def _uint(parsed: Parsed, dest: Literal["width", "height"]) -> int | None:
    text = parsed.value(dest)
    if text is None:
        return None
    if not is_uint(text):
        refuse(f"--{dest} must be a positive integer: {text}")
    return int(text)


def _margin(text: str | None) -> Fraction:
    """The margin as a fraction; ``N%`` is N/100 as awk printed it (its value)."""
    if text is None:
        return MARGIN  # the default: docs/ffman-spec.md (A), bash MARGIN
    percent = _PERCENT.fullmatch(text)
    if percent is not None:
        text = awk_print(float(Fraction(percent[1]) / 100))
    if not (is_num(text) and Fraction(text) < 1):
        refuse(f"--margin-bottom must be a fraction in [0, 1) or a percentage: {text}")
    return Fraction(text)


def _preset(parsed: Parsed) -> Preset | None:
    """YouTube's (alias yt), or a .txt output's format; --normalize is YouTube's alone."""
    given = parsed.value("preset")
    preset: Preset | None = None
    if given is not None:
        name = {"yt": "youtube"}.get(given.lower(), given.lower())
        preset = next((known for known in _PRESETS if known == name), None)
        if preset is None:
            refuse(f"unknown preset: {given} ({', '.join(_PRESETS)})")
    if preset != "youtube":
        if parsed.flag("normalize"):
            refuse("--normalize needs --preset youtube")
        return preset
    for dest in ("lossless", "video_codec", "audio_codec"):
        if dest in parsed.given:
            refuse(f"--preset youtube sets the codecs: --{dest.replace('_', '-')} cannot be added")
    return "youtube"
