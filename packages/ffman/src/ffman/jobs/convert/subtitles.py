"""A video's subtitle streams (spec 3.12): each copied, converted, or left out -- noted.

What the output holds is asked of ffmpeg (``output.holds``), a trial a candidate: the
stream as it is first, then each text encoder. An image subtitle passes the copy alone:
no conversion makes text of a picture.
"""

from typing import Final

from ffman.jobs.convert import output
from ffman.media.probe import Media, Subtitle
from ffman.media.run import Runner
from ffman.plan.encode import container_flags

_TEXT: Final = ("mov_text", "webvtt", "srt", "ass")  # MP4's, WebM's, then Matroska's own


def kept(runner: Runner, media: Media, source: str, ext: str) -> output.Kept:
    """Each of ``media``'s subtitle streams as a .``ext`` holds it, if it does.

    ``source`` is the input as ffmpeg opens it.
    """
    args: list[str] = []
    notes: list[str] = []
    written = 0  # the output's subtitle streams so far: each kept one's index there
    answers: dict[str, str | None] = {}  # one per codec: the trial sees nothing else
    for index, track in enumerate(media.subtitles):
        if track.codec is not None and track.codec in answers:
            codec = answers[track.codec]
        else:
            tried = (c for c in ("copy", *_TEXT) if _holds(runner, source, index, c, ext))
            codec = next(tried, None)  # the first held: as it is, else as text
            if track.codec is not None:
                answers[track.codec] = codec
        if codec is None:
            why = f"a .{ext} holds it neither as it is nor as text"
            notes.append(f"{_named(index, track)} -- {why}: left out")
            continue
        args += ["-map", f"0:s:{index}", f"-c:s:{written}", codec]
        written += 1
        if codec != "copy":
            notes.append(f"{_named(index, track)} converted to {codec}")
    return output.Kept(tuple(args), tuple(notes))


def _holds(runner: Runner, source: str, index: int, codec: str, ext: str) -> bool:
    trial = ["-i", source, "-map", f"0:s:{index}", "-c:s", codec, *container_flags(ext)]
    return output.holds(runner, trial, ext) is None


def _named(index: int, track: Subtitle) -> str:
    """``subtitle track N (LANGUAGE, TITLE): CODEC`` -- what a reader knows it by."""
    known = ", ".join(part for part in (track.language, track.title) if part)
    return f"subtitle track {index + 1}{f' ({known})' if known else ''}: {track.codec or 'unknown'}"
