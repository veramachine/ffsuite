"""What a job writes with: this ffmpeg's encoders, and the output through a partial file."""

import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ffman.errors import refuse
from ffman.media.paths import ext_of, partial_output
from ffman.media.probe import Audio, Media, Video, tag_names
from ffman.media.run import Runner, missing, note
from ffman.plan.encode import (
    FDK_AAC,
    container_flags,
    ffv1_slices,
    lossless_args,
    optimizer,
    parse_encoders,
)


def encoders(runner: Runner) -> frozenset[str]:
    """The encoders this ffmpeg has (bash's have_encoder: FFMAN_NO_FDK=1 hides FDK)."""
    listing = runner.capture(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    found = parse_encoders(listing)
    return found - {FDK_AAC} if os.environ.get("FFMAN_NO_FDK") == "1" else found


def write(
    runner: Runner, target: Path, args: list[str], finish: Callable[[str], None] | None = None
) -> None:
    """Write through a partial file beside ``target``: optimised, finished, renamed, printed.

    ``finish`` works on the partial before the rename (a FLAC's CUESHEET block), so the
    target never is without it. Under --dry-run nothing is written: the commands are printed
    with the partial's pattern in its place.
    """
    ext = ext_of(str(target))
    if runner.dry_run:
        _produce(runner, args, str(target.parent / f".ffman.XXXXXX.{ext}"), ext, finish)
        return
    with partial_output(target) as partial:
        _produce(runner, args, str(partial), ext, finish)
    _ = sys.stdout.write(f"{target}\n")


def _produce(
    runner: Runner, args: list[str], partial: str, ext: str, finish: Callable[[str], None] | None
) -> None:
    """The output made in ``partial``, losslessly optimised if its format has one, finished."""
    runner.ffmpeg([*args, partial])
    optimise = optimizer(ext, partial)
    if optimise is not None:
        if shutil.which(optimise[0]) is None:  # optional: the output kept
            note(f"{missing(optimise[0])}: the .{ext} written unoptimised")
        elif runner.run(optimise) != 0:
            refuse(f"{optimise[0]} failed (its message is above)")
    if finish is not None:
        finish(partial)


@dataclass(frozen=True, slots=True)
class Trial:
    """A header-only trial's answer: ffmpeg's first error line, or the tags it wrote."""

    error: str | None
    tags: frozenset[str] | None = None  # lower-cased; None unread (or unreadable)


def trial(runner: Runner, args: list[str], ext: str, *, read_tags: bool = False) -> Trial:
    """The planned command with ``-t 0`` into a .``ext``, and if asked, its tags read back.

    Each encoder opened, the header written, no frame (spec 3.11); the tags as ffprobe reads
    them (3.13). Under --dry-run too, as a probe: in a directory of its own, gone after.
    """
    with tempfile.TemporaryDirectory(prefix="ffman-trial.") as folder:  # not a job's ffman.*
        written = Path(folder) / f"trial.{ext}"
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            *args,
            "-t",
            "0",
            "-y",
            str(written),
        ]
        done = runner.capture(argv)
        if done.returncode != 0:
            lines = (line.strip() for line in done.stderr.splitlines())
            return Trial(next((line for line in lines if line), "ffmpeg failed"))
        return Trial(None, _tags_of(runner, written) if read_tags else None)


def _tags_of(runner: Runner, path: Path) -> frozenset[str] | None:
    """A file's tags as ffprobe reads them, lower-cased; None when it reads none of it."""
    shown = ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)]
    done = runner.capture(shown)
    if done.returncode != 0:
        return None
    return tag_names(done.stdout or "{}")


def holds(runner: Runner, args: list[str], ext: str) -> str | None:
    """None if a .``ext`` takes ``args``' streams; else ffmpeg's first error line."""
    return trial(runner, args, ext).error


@dataclass(frozen=True, slots=True)
class Held:
    """One kind of stream as planned: its arguments, the codec a refusal names, asked or not."""

    kind: str  # video, audio: its flag is --KIND-codec
    args: list[str]
    codec: str
    asked: bool


def check_held(
    runner: Runner, ext: str, inputs: list[str], kinds: tuple[Held, ...], rest: list[str]
) -> None:
    """Refused before any work unless a .``ext`` holds each kind's streams (spec 3.11).

    The whole asked of ffmpeg first; on a failure, each kind alone tells which.
    """
    whole = [*inputs, *(arg for held in kinds for arg in held.args), *rest]
    error = holds(runner, whole, ext)
    if error is None:
        return
    for held in kinds:
        if holds(runner, [*inputs, *held.args, *container_flags(ext)], ext) is None:
            continue
        flag = f"--{held.kind}-codec"
        if held.asked:
            refuse(f"{flag} {held.codec}: a .{ext} holds no {held.codec}")
        refuse(
            f"a .{ext} holds no {held.codec} {held.kind}, the source's: {flag} to give one it holds"
        )
    refuse(f"a .{ext} holds not these streams together: {error}")


def named(asked: str | None, stream: Video | Audio | None) -> str:
    """The codec a refusal names: the one asked, else the source's."""
    if asked is not None and asked != "copy":
        return asked
    return (stream.codec if stream else None) or "unknown"


def source_slices(runner: Runner, media: Media) -> int | None:
    """FFV1's slices for the source's picture, as its encode would take them; None unknown."""
    video = media.video
    if video is None or video.width is None or video.height is None:
        return None
    return ffv1_slices(runner.cores, video.width, video.height)


def lossless_picture(runner: Runner, media: Media, codec: str) -> list[str]:
    """The source's picture (an attached one left: ``0:V``), encoded losslessly in ``codec``."""
    time_base = media.video.time_base if media.video else None
    slices = source_slices(runner, media)
    return ["-map", "0:V?", *lossless_args(codec, time_base=time_base, slices=slices)]


@dataclass(frozen=True, slots=True)
class Kept:
    """Streams an output keeps beside the picture and the sound: their arguments, every note."""

    args: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
