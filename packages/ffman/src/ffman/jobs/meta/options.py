"""``meta``'s options: validated and typed, with the spec's messages (section 8)."""

from dataclasses import dataclass, replace
from typing import Final

from ffmeta.chapters import ChapterText, parse_chapters
from ffmeta.cue import is_file_name
from ffmeta.edit import Edits, parse
from ffmeta.files import PRESETS, Preset

from ffman.errors import refuse, shown
from ffman.options import Parsed

_PRESETS: Final = ", ".join(PRESETS)


@dataclass(frozen=True, slots=True)
class MetaOptions:
    """What a meta job writes: from what (None: nothing), where, in which .txt form, edited."""

    input: str | None
    output: str | None
    in_place: bool
    overwrite: bool
    dry_run: bool
    preset: Preset | None
    edits: Edits


def validate(parsed: Parsed) -> MetaOptions:
    """Check ``parsed`` against the spec; return the typed options."""
    output = parsed.value("output") or None  # an empty value is none, as convert's (spec 1)
    if parsed.flag("in_place") and output is not None:
        refuse("--in-place and --output exclude each other")
    file = parsed.value("file") or None  # an empty value is none (spec 1)
    if file is not None and not is_file_name(file):
        rule = "a cue's FILE name has no line break or NUL, no space at either end, no quote first"
        refuse(f"--file: {rule}: {shown(file)}")
    given = parsed.value("preset")
    preset: Preset | None = None
    if given is not None:
        preset = next((known for known in PRESETS if known == given.lower()), None)
        if preset is None:
            refuse(f"unknown preset: {given} ({_PRESETS})")
    return MetaOptions(
        input=parsed.value("input") or None,
        output=output,
        in_place=parsed.flag("in_place"),
        overwrite=parsed.flag("overwrite"),
        dry_run=parsed.flag("dry_run"),
        preset=preset,
        edits=replace(
            parse(
                parsed.all("set"),
                parsed.all("add"),
                parsed.all("unset"),
                clear=parsed.flag("clear"),
            ),
            chapters=parse_chapters(
                ChapterText(
                    new=parsed.all("chapter"),
                    retitles=parsed.all("retitle"),
                    sets=parsed.all("chapter_set"),
                    drops=parsed.all("drop_chapter"),
                    flags=parsed.all("flags"),
                    pregaps=parsed.all("pregap"),
                    clear=parsed.flag("clear_chapters"),
                )
            ),
            file=file,
        ),
    )
