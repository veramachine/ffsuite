"""Tags and chapters kept (spec 3.13).

The tags an output holds not, told; chapters as Vorbis comments where ffmpeg's muxers write
none (Ogg, FLAC).
"""

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Final

import ffmeta
from ffmeta import vorbis
from ffmeta.convert import convert
from ffmeta.fields import Format
from ffmeta.files import is_metadata
from ffmeta.model import Chapter, Metadata

from ffman.errors import FfmanError, refuse
from ffman.jobs.convert import output
from ffman.jobs.meta.io import applied, read_input
from ffman.media import flac
from ffman.media.paths import ext_of
from ffman.media.probe import Media
from ffman.media.run import Runner
from ffman.plan.encode import family
from ffman.plan.request import ConvertOptions

COMMENTED: Final = frozenset({"ogg", "oga", "ogv", "spx", "opus", "flac"})  # oggenc.c, flacenc.c
_CHAPTER: Final = re.compile(r"CHAPTER[0-9]{3}(?:NAME|URL)?", re.IGNORECASE)  # a name
_MILLISECOND: Final = Fraction(1, 1000)
_MUXERS: Final = frozenset(
    {"encoder", "major_brand", "minor_version", "compatible_brands"}
)  # theirs


@dataclass(frozen=True, slots=True)
class Given:
    """Where a job's tags and chapters come from: --metadata's file, else the input."""

    media: Media
    source: str  # the input's path
    applied: Path | None = None  # --metadata's file, as ffmetadata


@dataclass(frozen=True, slots=True)
class Tagging:
    """The arguments that write the chapters as comments, and every note."""

    args: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def tagging(runner: Runner, given: Given, held: list[str], ext: str) -> Tagging:
    """The job's tags and chapters into a .``ext``.

    ``held``: the job's trial, its metadata mapped, already known held (3.11).
    """
    meta = read_input(str(given.applied), runner)[0] if given.applied is not None else None
    names = [tag.name for tag in meta.tags] if meta else [name for name, _ in given.media.tags]
    notes = list(_dropped(runner, names, held, ext))
    if ext not in COMMENTED:
        return Tagging((), tuple(notes))
    chapters, fmt, read = (
        (meta.chapters, "ffmetadata", ()) if meta else _media_chapters(runner, given.source)
    )
    notes.extend(read)  # told with the job's others (F6)
    if not chapters:
        return Tagging((), tuple(notes))
    chapters = _unimplied(chapters, given.media.duration)
    converted = convert(Metadata(chapters=chapters), fmt, "vorbis")
    pairs, written = vorbis.comments(converted.meta)  # raw: -metadata takes a value as it is
    comments = [arg for name, value in pairs for arg in ("-metadata", f"{name}={value}")]
    # encoder= first: ffmpeg's dictionary moves its last entry into the slot of one replaced
    # (dict.c), and the muxer replaces encoder -- else the last title would precede its time
    args = ("-map_chapters", "-1", "-metadata", "encoder=", *comments)
    return Tagging(args, (*notes, *converted.notes, *written))


def _media_chapters(
    runner: Runner, source: str
) -> tuple[tuple[Chapter, ...], Format, tuple[str, ...]]:
    """The media's chapters, and the format they are in -- only here is reading them worth a run.

    A FLAC's from its own comment block, byte-exact (``media.flac``): ffmpeg reads a FLAC with
    a CUESHEET block with the block's tracks overwriting the comments' chapters of the same id
    (flacdec.c, avpriv_new_chapter: measured), and a text export cannot tell a value's line
    break from two comments. Malformed comments are read as ffmpeg reads them, noted.
    """
    if ext_of(source) == "flac":
        held = [
            (name, value) for name, value in flac.comments(source) or () if _CHAPTER.fullmatch(name)
        ]
        if held:
            try:
                return vorbis.read(vorbis.text(held), source).chapters, "vorbis", ()
            except ffmeta.Error as malformed:  # ffmpeg skips what it cannot read: so do we, said
                why = f"the source's chapter comments: {malformed}: read as ffmpeg reads them"
                return read_input(source, runner)[0].chapters, "ffmetadata", (why,)
    return read_input(source, runner)[0].chapters, "ffmetadata", ()


def _dropped(runner: Runner, given: list[str], held: list[str], ext: str) -> tuple[str, ...]:
    """Each given tag a .``ext`` holds not, by the trial read back; none if unreadable."""
    asked = [name for name in given if name.lower() not in _MUXERS]
    if not asked:
        return ()
    kept = output.trial(runner, held, ext, read_tags=True).tags
    missing = [name for name in asked if kept is not None and name.lower() not in kept]
    return (f"the tags {', '.join(missing)}: a .{ext} holds them not: left out",) if missing else ()


def _unimplied(chapters: tuple[Chapter, ...], duration: Fraction | None) -> tuple[Chapter, ...]:
    """The ends a comment's start implies, gone, so only an end that says more is noted lost.

    A chapter's implied end is the next one's start, exactly; the last one's, the media's end
    within a millisecond -- the comments' own precision, and ffmpeg's: it ends a comment's last
    chapter at the duration rounded to its 1/1000 time base (measured, 3.007 for 3.0065).
    """
    ordered = sorted(chapters, key=lambda chapter: chapter.start)
    nexts = [chapter.start for chapter in ordered[1:]]
    kept: list[Chapter] = []
    for chapter, after in zip(ordered, [*nexts, None], strict=True):
        if after is not None:  # the next one's start: exactly
            implied = chapter.end in (None, after)
        else:  # the last: the media's end, within a millisecond
            implied = chapter.end is None or (
                duration is not None and abs(chapter.end - duration) < _MILLISECOND
            )
        kept.append(replace(chapter, end=None) if implied else chapter)
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class Applied:
    """A metadata file as ffmetadata for ffmpeg to apply, and a note for each step to it.

    The notes are told with the job's others, after its refusals (F6).
    """

    path: Path | None = None
    notes: tuple[str, ...] = ()


def metadata_file(o: ConvertOptions, runner: Runner, media: Media, out_ext: str) -> Applied:
    """--metadata's file as ffmetadata, else an attached one's where attachments are not held.

    A flow calls it after its own refusals and before any pass (F6), so a malformed file
    never precedes an output that exists, a container refused, a transcript unreadable.
    """
    if o.metadata is not None:  # the user's word wins
        return Applied(*applied(o.metadata, runner, media.duration))
    if family(out_ext) == family("mkv"):  # attachments carried as they are (3.14)
        return Applied()
    return _attached(runner, o.input, media)


def _attached(runner: Runner, source: str, media: Media) -> Applied:
    """The first attached metadata file that applies, as --metadata would (3.14).

    Tried in order: one refused is noted with its reason, never a refusal of the job (an
    attachment, not the user's word); those after the one applied, noted left out.
    """
    notes: list[str] = []
    applied_name: str | None = None
    result: Path | None = None
    for index, attachment in enumerate(media.attachments):
        name = attachment.filename
        if name is None or not is_metadata(ext_of(name)):
            continue
        if applied_name is not None:
            notes.append(f"the attached {name}: {applied_name} applied already: left out")
            continue
        dumped = runner.workdir / f"attached{index}.{ext_of(name)}"  # only now: none made for none
        # ffmpeg dumps it, then exits non-zero (no output file given): the file is the answer
        dump = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            f"-dump_attachment:t:{index}",
            str(dumped),
        ]
        _ = runner.capture([*dump, "-i", source])
        try:
            if not dumped.is_file():
                refuse("ffmpeg extracted none")  # as the cover's (3.15)
            result, told = applied(str(dumped), runner, media.duration)
        except (FfmanError, ffmeta.Error) as why:  # ours (none extracted), ffmeta's (malformed)
            notes.append(f"the attached {name}: {why}: left out")
            continue
        applied_name = name
        notes.append(f"the attached {name}: its tags and chapters applied, in place of the media's")
        notes.extend(told)  # its conversion's own, after what it is
    return Applied(result, tuple(notes))
