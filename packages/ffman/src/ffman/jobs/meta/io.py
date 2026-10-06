"""A metadata job's input and output (spec 3.9, 8): convert's metadata flow's and meta's."""

import sys
from collections.abc import Iterable
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from ffmeta.convert import convert
from ffmeta.fields import Format
from ffmeta.files import EXTENSIONS, format_in, is_metadata, read, write
from ffmeta.model import Metadata, Tag, folded

from ffman.errors import refuse
from ffman.media.paths import ext_of, file_url, partial_output, read_file
from ffman.media.probe import read as probe
from ffman.media.run import Runner, note

# ffmpeg's ffmetadata export: +bitexact, or ffmpeg adds its own encoder (mux.c) to the tags
_EXPORT = ("-fflags", "+bitexact", "-f", "ffmetadata", "-")


def cue_media(
    path: str | None, source: Format, target: Format, fallback: Path, named: str | None = None
) -> tuple[str, tuple[str, ...]]:
    """The media a cue written from ``path`` names in its FILE, and a note if it is a guess.

    A media file names itself; a metadata file knows no media, so its stem stands in, noted.
    Only a cue made from another format names one: a cue read keeps its own. ``named``
    (meta's --file) names it outright.
    """
    if named is not None:  # meta's --file: the media named, no guess
        return named, ()
    if target != "cue" or (source == "cue" and path is not None):
        return Path(path or fallback).name, ()
    if path is None:  # a new cue: the edits name no media either
        stem = Path(fallback).stem
        return stem, (f"the cue's FILE: {stem}, the media the edits do not name -- check it",)
    if not is_metadata(ext_of(path)):
        return Path(path).name, ()
    stem = Path(path).stem
    return stem, (f"the cue's FILE: {stem}, the media a metadata file does not name -- check it",)


def write_output(
    text: str, notes: Iterable[str], target: Path, source: str, runner: Runner
) -> None:
    """The notes told, then ``text`` written through a partial file and its path printed.

    Under --dry-run nothing is written; an empty ``text`` is refused.
    """
    _tell(notes)
    if not text:
        refuse(f"nothing to write: no tag or chapter of {source} is one {target} holds")
    if runner.dry_run:
        return
    with partial_output(target) as partial:
        _ = partial.write_text(text, encoding="utf-8")
    _ = sys.stdout.write(f"{target}\n")


def print_output(text: str, notes: Iterable[str], runner: Runner) -> None:
    """The notes told (stderr), then ``text`` on stdout.

    Nothing under --dry-run; an empty ``text`` prints nothing -- a pipe takes it, no file made.
    """
    _tell(notes)
    if not runner.dry_run:  # UTF-8, as a metadata file is, whatever the locale's encoding
        _ = sys.stdout.flush()
        _ = sys.stdout.buffer.write(text.encode("utf-8"))


def _tell(notes: Iterable[str]) -> None:
    for line in notes:
        note(line)


def read_input(path: str, runner: Runner) -> tuple[Metadata, Format]:
    """The input's metadata and its format: a metadata file read, a media file's exported."""
    ext = ext_of(path)
    if is_metadata(ext):
        raw = read_file(path)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            refuse(f"not UTF-8: {path} (byte {error.start})")
        fmt = format_in(ext, text)
        return read(text, fmt, path), fmt
    media = probe(path, runner)  # the probe's refusals, as every flow's: no such file, not media
    exported = runner.capture(["ffmpeg", "-v", "error", "-i", file_url(path), *_EXPORT]).stdout
    meta = read(exported, "ffmetadata", f"{path} (ffmpeg's ffmetadata of it)")
    return _with_dropped(meta, media.tags), "ffmetadata"


def _with_dropped(meta: Metadata, tags: tuple[tuple[str, str], ...]) -> Metadata:
    """``meta`` with the source's tags ffmpeg's export drops, as the probe read them.

    ffmpeg deletes ``creation_time``, ``company_name``, ``product_name``, ``product_version``
    in its default copy (``ffmpeg_mux_init.c``), and ``encoder`` in its muxer (``mux.c``).
    """
    exported = {folded(tag.name) for tag in meta.tags}
    dropped = [Tag(name, value) for name, value in tags if folded(name) not in exported]
    return Metadata((*meta.tags, *dropped), meta.streams, meta.chapters, meta.disc)


def applied(path: str, runner: Runner, duration: Fraction | None) -> tuple[Path, tuple[str, ...]]:
    """A metadata file as ffmetadata, for ffmpeg to apply (spec 3.10), and its notes.

    The notes are the caller's to tell, with the job's others, after its refusals (F6).

    Refused unless a metadata file, or a cue over several files (several media).
    """
    if not is_metadata(ext_of(path)):
        refuse(
            f"--metadata takes a metadata file ({', '.join('.' + e for e in EXTENSIONS)}): {path}"
        )
    meta, source = read_input(path, runner)
    if meta.disc is not None and len(meta.disc.files) > 1:
        count = len(meta.disc.files)
        refuse(f"--metadata: a cue over {count} files describes {count} media")
    streams = ("the file's stream sections: not applied -- each stream keeps its own tags",)
    converted = convert(replace(meta, streams=()), source, "ffmetadata")
    written = write(converted.meta, "ffmetadata", duration)
    file = runner.workdir / "applied.ffmeta"
    _ = file.write_text(written.text, encoding="utf-8")
    return file, (*(streams if meta.streams else ()), *converted.notes, *written.notes)
