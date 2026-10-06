"""The streams a job writes: the picture's lossless encoder, the sound, the attachments carried.

Encoder availability and a subtitle file's format come in as data: nothing here
runs anything. The attach flow's streams last.
"""

from dataclasses import dataclass
from pathlib import Path

from ffman.errors import refuse
from ffman.media.probe import Media
from ffman.plan.encode import AUDIO_ENCODERS, FDK_AAC, VIDEO_ALIASES, VIDEO_ENCODERS, family
from ffman.plan.request import ConvertOptions


@dataclass(frozen=True, slots=True)
class Lossless:
    """The picture re-encoded losslessly."""

    codec: str
    encoder: str
    why: str


@dataclass(frozen=True, slots=True)
class Sound:
    """The audio streams: copied, dropped, or encoded (all of them, as bash's 0:a?).

    ``codec`` is --audio-codec's value -- ``copy`` (copied), ``none`` (dropped),
    or a codec (encoded, by ``encoder``): what encode.audio_args takes.
    """

    codec: str
    encoder: str | None = None
    channels: int | None = None


@dataclass(frozen=True, slots=True)
class Attachments:
    """Attachment streams: carried, or dropped with a note."""

    carry: bool
    note: str | None = None


def lossless(o: ConvertOptions, media: Media, encoders: frozenset[str]) -> Lossless:
    """A video's picture re-rendered: lossless, its codec or --video-codec's (video_encoder)."""
    source = (media.video.codec if media.video else None) or ""
    asked = (o.video_codec or source).lower()
    if asked == "copy":
        refuse("--video-codec copy is impossible here: the picture is re-rendered")
    codec = VIDEO_ALIASES.get(asked)
    if codec is None:
        choose = "choose --video-codec h264, hevc, vp9, av1 or ffv1"
        refuse(f"no lossless encoder for video codec '{asked}'; {choose}")
    encoder = VIDEO_ENCODERS[codec]
    if encoder not in encoders:
        refuse(f"this ffmpeg has no {encoder} encoder")
    why = "--video-codec" if o.video_codec else f"the source's codec ({source})"
    return Lossless(codec, encoder, f"re-rendered: {why}, losslessly")


def sound(o: ConvertOptions, media: Media, encoders: frozenset[str]) -> Sound:
    """The audio of a video output: bash's audio_encoder (copied unless asked)."""
    if o.audio_codec == "copy":
        return Sound("copy")
    if o.audio_codec == "none":
        return Sound("none")
    channels = media.audio.channels if media.audio and media.audio.channels else 2
    encoder = AUDIO_ENCODERS[o.audio_codec]
    if o.audio_codec == "aac" and FDK_AAC in encoders:
        encoder = FDK_AAC
    return Sound(o.audio_codec, encoder, channels)


def attachments(media: Media, in_ext: str, out_ext: str) -> Attachments:
    """A video's attachment streams: carried within one container family, else noted."""
    if not media.attachments:
        return Attachments(carry=False)
    if family(in_ext) == family(out_ext):
        return Attachments(carry=True)
    return Attachments(
        carry=False, note=f"attachments are not carried into .{out_ext} (another container family)"
    )


# The attach flow: the track added, every other stream copied.
def subtitle_codec(out_ext: str, subtitle_format: str) -> str:
    """The codec a container takes a subtitle track in (bash's sub_codec_for)."""
    kind = family(out_ext)
    if kind == "matroska":
        return "ass" if subtitle_format in ("ass", "ssa") else "srt"
    codec = {"mp4": "mov_text", "webm": "webvtt"}.get(kind)
    if codec is None:
        where = "give --output with .mka or .m4a (audio), .mkv or .mp4 (video)"
        refuse(f"a .{out_ext} file cannot carry a subtitle track; {where}")
    return codec


def attach_streams(
    in_ext: str, out_ext: str, codec: str, index: int
) -> tuple[list[str], list[str]]:
    """An attach job's maps and subtitle codecs (bash's attach: its maps and scopy).

    Within a family everything is copied, the new track (subtitle stream ``index``)
    in ``codec``. Across, only what the target holds (measured in bash: an ASS
    track or a font attachment failed into .mp4) -- the picture, the sound and the
    subtitles; into Matroska the attachments too, the subtitles there as SRT and
    the new track in ``codec``; elsewhere every subtitle in ``codec``.
    """
    if family(in_ext) == family(out_ext):  # all but covers (``0:V``): covers.kept's (3.15)
        whole = ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?", "-map", "0:d?"]
        return whole, [f"-c:s:{index}", codec]
    maps = ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?"]
    if family(out_ext) == "matroska":
        return [*maps, "-map", "0:t?"], ["-c:s", "srt", f"-c:s:{index}", codec]
    return maps, ["-c:s", codec]


def kept_metadata(inputs: list[str], applied: Path | None) -> tuple[list[str], list[str]]:
    """One more input, and the one mapping of the global tags and chapters (spec 3.10).

    The media's (input 0); or, with a metadata file ``applied``, the file's -- its index the
    inputs' count. Each stream's own tags are copied either way (ffmpeg's copy_meta): a
    global map alone leaves them to it. Never both: two ``-map_metadata`` would merge.
    """
    if applied is None:
        return [], ["-map_metadata", "0", "-map_chapters", "0"]
    index = str(inputs.count("-i"))
    return ["-f", "ffmetadata", "-i", str(applied)], [
        "-map_metadata",
        index,
        "-map_chapters",
        index,
    ]
