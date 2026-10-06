"""The metadata flow (spec 3.9): a metadata file, or a media file's, written as one.

Read, converted (``ffmeta``), each loss a note; written through a partial file.
"""

from ffmeta.convert import convert
from ffmeta.files import format_out, write

from ffman.jobs.meta.io import cue_media, read_input, write_output
from ffman.media.paths import ext_of, resolve_output
from ffman.media.run import Runner
from ffman.plan.request import ConvertOptions


def run(o: ConvertOptions, runner: Runner) -> None:
    """Read the input's metadata, convert it to the output's format, write it."""
    target = resolve_output(o.input, o.output, in_place=o.in_place, overwrite=o.overwrite)
    preset = o.preset if o.preset != "youtube" else None  # select_flow refused youtube here
    meta, source = read_input(o.input, runner)
    fmt = format_out(ext_of(str(target)), preset)
    media, guessed = cue_media(o.input, source, fmt, target)
    converted = convert(meta, source, fmt, media=media)
    written = write(converted.meta, fmt)
    notes = (*guessed, *converted.notes, *written.notes)
    write_output(written.text, notes, target, o.input, runner)
