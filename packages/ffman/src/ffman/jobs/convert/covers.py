"""A cover (spec 3.15): into Matroska attached, into MOV noted, elsewhere copied if held.

Measured: MP4, M4A, FLAC, MP3 keep a cover copied with attached_pic; MOV's muxer drops it
without a word; Matroska's writes it as a video track; WebM, Ogg and Opus fail on one. A
header trial cannot read a cover back (it is a packet, and -t 0 writes none): its exit
says only whether the output takes one.
"""

from dataclasses import dataclass
from typing import Final

from ffman.jobs.convert import output
from ffman.media.probe import Cover, Media
from ffman.media.run import Runner
from ffman.plan.encode import family

_IMAGES: Final = {"png": ("png", "image/png"), "mjpeg": ("jpg", "image/jpeg")}  # Matroska's


@dataclass(frozen=True, slots=True)
class Job:
    """What a cover joins: the input, the job's own trial, the output's streams before it.

    The trial's streams are known held (3.11); ``pictures`` and ``attachments`` are the
    cover's index among each kind in the output.
    """

    source: str
    held: tuple[str, ...]
    pictures: int = 0
    attachments: int = 0


def kept(runner: Runner, media: Media, ext: str, job: Job) -> output.Kept:
    """The first cover as a .``ext`` keeps one, and a note for each left out."""
    if not media.covers:
        return output.Kept()
    cover = media.covers[0]
    notes = ["the cover: one kept, not two: left out" for _ in media.covers[1:]]
    if family(ext) == family("mkv"):
        args, why = _attached(runner, cover, job.source, job.attachments)
    elif ext == "mov":
        args, why = (), "a .mov drops it, its muxer silent"
    else:
        args, why = _copied(runner, cover, ext, job)
    if why is not None:
        notes.append(f"the cover ({cover.codec or 'unknown'}): {why}: left out")
    return output.Kept(args, tuple(notes))


def _attached(
    runner: Runner, cover: Cover, source: str, at: int
) -> tuple[tuple[str, ...], str | None]:
    """Into Matroska: extracted byte-exact, attached under its cover art name (``_named``)."""
    image = _IMAGES.get(cover.codec or "")
    if image is None:
        return (), "Matroska's covers are JPEG or PNG"
    suffix, mimetype = image
    name = f"{_named(cover)}.{suffix}"
    path = runner.workdir / name
    picture = [
        "-map",
        f"0:v:{cover.index}",
        "-c",
        "copy",
        "-frames:v",
        "1",
        "-f",
        "image2",
        str(path),
    ]
    _ = runner.capture(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", source, *picture])
    if not path.is_file():
        return (), "ffmpeg extracted none"
    named = (
        f"-metadata:s:t:{at}",
        f"mimetype={mimetype}",
        f"-metadata:s:t:{at}",
        f"filename={name}",
    )
    return ("-attach", str(path), *named), None


def _named(cover: Cover) -> str:
    """Matroska's cover art name: ``cover_land`` wider than tall, else ``cover``.

    Square, portrait, or a size unknown: ``cover``. Its filenames are case-sensitive.
    """
    landscape = cover.width is not None and cover.height is not None and cover.width > cover.height
    return "cover_land" if landscape else "cover"


def _copied(runner: Runner, cover: Cover, ext: str, job: Job) -> tuple[tuple[str, ...], str | None]:
    """Elsewhere: copied with attached_pic after the pictures, if the job's trial holds it too.

    The job's whole trial, not the cover alone: an audio muxer (FLAC, MP3) refuses an output
    holding no sound, whatever its cover (measured).
    """
    at = job.pictures
    copied = (
        "-map",
        f"0:v:{cover.index}",
        f"-c:v:{at}",
        "copy",
        f"-disposition:v:{at}",
        "attached_pic",
    )
    if output.holds(runner, [*job.held, *copied], ext) is not None:
        return (), f"a .{ext} holds none"
    return copied, None
