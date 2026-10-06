"""``ffman meta``: read (or nothing), converted to the output's format, edited, written.

To a file, or with ``-o -`` to stdout (spec 8): one pipeline, two ends.
"""

from pathlib import Path
from typing import Final

from ffmeta.convert import convert
from ffmeta.edit import apply, in_output, in_source
from ffmeta.fields import Format
from ffmeta.files import EXTENSIONS, check_output, format_of, format_out, is_metadata, write
from ffmeta.model import Metadata, Written

from ffman.errors import refuse
from ffman.jobs.meta.io import cue_media, print_output, read_input, write_output
from ffman.jobs.meta.options import MetaOptions
from ffman.media.paths import ext_of, new_output, resolve_output
from ffman.media.run import Runner

STDOUT: Final = "-"  # -o -: the result to stdout
_UNNAMED: Final = Path("media")  # a new cue's FILE on stdout, the edits naming none: noted


def run(o: MetaOptions, runner: Runner) -> None:
    """The job ``o`` asks for (spec 8)."""
    if o.output == STDOUT:
        named = format_of(o.preset) if o.preset is not None else None
        meta, source = _read(o, runner, named or "ffmetadata")
        written, notes = _edited(meta, source, named or source, o, _UNNAMED)
        print_output(written.text, notes, runner)
        return
    target = _target(o)
    ext = ext_of(str(target))
    if not is_metadata(ext):
        refuse(f"meta writes a metadata file ({', '.join('.' + e for e in EXTENSIONS)}): {target}")
    check_output(ext, o.preset)
    fmt = format_out(ext, o.preset)
    meta, source = _read(o, runner, fmt)
    written, notes = _edited(meta, source, fmt, o, target)
    write_output(written.text, notes, target, o.input or "the edits", runner)


def _target(o: MetaOptions) -> Path:
    """The file written: the input's rules (3.1), or a new one's."""
    if o.input is not None:
        return resolve_output(o.input, o.output, in_place=o.in_place, overwrite=o.overwrite)
    if o.output is None or o.in_place:
        refuse("meta: --output is required without --input")
    return new_output(o.output, overwrite=o.overwrite)


def _read(o: MetaOptions, runner: Runner, empty: Format) -> tuple[Metadata, Format]:
    """The input's metadata and its format; without an input, none, in ``empty``."""
    return (Metadata(), empty) if o.input is None else read_input(o.input, runner)


def _edited(
    meta: Metadata, source: Format, fmt: Format, o: MetaOptions, fallback: Path
) -> tuple[Written, tuple[str, ...]]:
    """``meta``, in ``source``, edited into ``fmt``, and every note, in order.

    What goes, in the input's words before converting; what comes, in the output's after.
    """
    kept, removed_notes = apply(meta, in_source(o.edits), source)
    media, guessed = cue_media(o.input, source, fmt, fallback, o.edits.file)
    converted = convert(kept, source, fmt, media=media)
    edited, added_notes = apply(converted.meta, in_output(o.edits), fmt, media)
    written = write(edited, fmt)
    return written, (*removed_notes, *guessed, *converted.notes, *added_notes, *written.notes)
