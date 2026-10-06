"""Encoders: which one each codec asks for, and the settings it runs at.

The bash ffman's, argument for argument: a codec by any of its names, the
encoder that writes it (losslessly where it can), and its settings (bash's
video_encoder, audio_encoder, image_encoder, gif_encoder, container_flags,
optimize_output and YouTube's x264). Each encoder is named once, in the tables
at the top; the settings tables hold what follows ``-c:v NAME``.
"""

import re
from typing import Final

from ffman.media.probe import Rational

# --video-codec's names (bash's video_encoder), each to its codec
VIDEO_ALIASES: Final = {
    **dict.fromkeys(("h264", "avc", "x264", "libx264"), "h264"),
    **dict.fromkeys(("hevc", "h265", "x265", "libx265"), "hevc"),
    **dict.fromkeys(("vp9", "libvpx-vp9"), "vp9"),
    **dict.fromkeys(("av1", "aom", "libaom-av1"), "av1"),
    "ffv1": "ffv1",
}
VIDEO_ENCODERS: Final = {
    "h264": "libx264",
    "hevc": "libx265",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
    "ffv1": "ffv1",
}

AUDIO_CODECS: Final = ("copy", "none", "flac", "aac", "opus", "mp3", "vorbis", "alac", "pcm")
AUDIO_ENCODERS: Final = {
    "flac": "flac",
    "aac": "aac",  # native; libfdk_aac when this ffmpeg has it (plan.streams, plan.youtube)
    "opus": "libopus",
    "mp3": "libmp3lame",
    "vorbis": "libvorbis",
    "alac": "alac",
    "pcm": "pcm_s24le",
}
FDK_AAC: Final = "libfdk_aac"

# bash's is_image_ext: what reads as a still picture (bmp too, which nothing writes)
IMAGE_INPUTS: Final = frozenset({"png", "jpg", "jpeg", "webp", "avif", "tif", "tiff", "bmp"})
# what a picture can be written as, and by which encoder
IMAGE_ENCODERS: Final = {
    "png": "png",
    "jpg": "mjpeg",
    "jpeg": "mjpeg",
    "webp": "libwebp",
    "avif": "libaom-av1",
    "tif": "tiff",
    "tiff": "tiff",
}


# Containers that take each other's subtitle and attachment streams as they are
# (bash's family, which its container_flags repeated)
FAMILIES: Final = {
    **dict.fromkeys(("mkv", "mka"), "matroska"),
    **dict.fromkeys(("mp4", "m4v", "mov", "m4a", "m4b"), "mp4"),
}


def family(ext: str) -> str:
    """Containers that take each other's subtitle and attachment streams as they are."""
    return FAMILIES.get(ext, ext)


# The settings each encoder runs at: the bash ffman's, argument for argument.
# what follows -c:v NAME: bash's settings, one option (and its value) a line
_LOSSLESS: Final[dict[str, tuple[str, ...]]] = {
    "h264": (
        "-preset", "veryslow",
        "-qp", "0",
    ),
    "hevc": (
        "-preset", "veryslow",
        "-x265-params", "lossless=1:log-level=error",
    ),
    # good, not best: in one pass libvpx threads rows only for good (vp9_set_row_mt)
    "vp9": (
        "-lossless", "1",
        "-deadline", "good",
        "-cpu-used", "0",
        "-row-mt", "1",
    ),
    "av1": (
        "-crf", "0",
        "-b:v", "0",
        "-cpu-used", "0",
        "-row-mt", "1",
    ),
    "ffv1": (
        "-level", "3",
        "-g", "1",
        "-slicecrc", "1",
    ),
}  # fmt: skip
_IMAGE: Final[dict[str, tuple[str, ...]]] = {
    "png": (),
    "mjpeg": (
        "-q:v", "1",
        "-pix_fmt", "yuvj444p",
    ),
    "libwebp": (
        "-lossless", "1",
        "-compression_level", "6",
        "-quality", "100",
    ),
    "libaom-av1": (
        "-crf", "0",
        "-b:v", "0",
        "-cpu-used", "0",
        "-pix_fmt", "yuv444p10le",
        "-still-picture", "1",
    ),
    "tiff": (
        "-compression_algo", "deflate",
    ),
}  # fmt: skip
_SLICE_MIN: Final = 32  # px: the least a slice may be, either way


def enc_time_base(time_base: Rational | None) -> str:
    """The source stream's time base for -enc_time_base:v, else ``demux`` (bash's src_tb)."""
    if time_base is None or time_base.num <= 0 or time_base.den <= 0:
        return "demux"
    return time_base.text()


def ffv1_slices(cores: int, width: int, height: int) -> int | None:
    """FFV1's slices: the smallest v x h layout ffv1enc accepts (h from v to 2v) with one per core.

    ffv1 threads across its slices and by default takes 2x2 -- four threads on any
    machine; each slice at least 32 px. None where four suffice or nothing fits.
    """
    if cores <= 4:  # noqa: PLR2004 -- the default layout's four
        return None
    fits = [
        v * k
        for v in range(2, 33)
        for k in range(v, 2 * v + 1)
        if k * _SLICE_MIN <= width and v * _SLICE_MIN <= height and v * k >= cores
    ]
    return min(fits, default=None)


def lossless_args(
    codec: str, *, time_base: Rational | None, slices: int | None = None
) -> list[str]:
    """The lossless encoder's arguments (bash's video_encoder)."""
    args = ["-c:v", VIDEO_ENCODERS[codec], *_LOSSLESS[codec]]
    if codec == "ffv1" and slices is not None:
        args += ["-slices", str(slices)]
    return [*args, "-enc_time_base:v", enc_time_base(time_base)]


_AUDIO_FIXED: Final = {
    "copy": ("-c:a", "copy"),
    "none": ("-an",),
    "flac": ("-c:a", AUDIO_ENCODERS["flac"], "-compression_level", "10"),
    "mp3": ("-c:a", AUDIO_ENCODERS["mp3"], "-b:a", "320k", "-compression_level", "0"),
    "vorbis": ("-c:a", AUDIO_ENCODERS["vorbis"], "-q:a", "10"),
    "alac": ("-c:a", AUDIO_ENCODERS["alac"]),
    "pcm": ("-c:a", AUDIO_ENCODERS["pcm"]),
}


def audio_args(codec: str, encoder: str | None, channels: int) -> list[str]:
    """Each audio codec at its best (bash's audio_encoder); ``copy`` and ``none`` too."""
    if codec == "aac":
        rate = ["-b:a", f"{192 * channels}k"]
        if encoder == FDK_AAC:  # CBR 192 kbps a channel, full band: FDK's CBR low-passes at 17 kHz
            return ["-c:a", FDK_AAC, "-profile:a", "aac_low", *rate, "-cutoff", "20000"]
        return ["-c:a", AUDIO_ENCODERS["aac"], *rate]
    if codec == "opus":
        kbps = 256 * channels
        if channels <= 2:  # noqa: PLR2004 -- stereo: opus's 510 kbps ceiling
            kbps = min(kbps, 510)
        compression = ["-compression_level", "10", "-application", "audio", "-ar", "48000"]
        return ["-c:a", AUDIO_ENCODERS["opus"], "-b:a", f"{kbps}k", "-vbr", "on", *compression]
    return list(_AUDIO_FIXED[codec])


def image_args(encoder: str) -> list[str]:
    """One frame at its format's best lossless (or highest) setting (bash's image_encoder)."""
    return ["-c:v", encoder, *_IMAGE[encoder]]


def gif_args(loop: str) -> list[str]:
    """GIF: once, or forever (the muxer's loop=0); no audio (bash's gif_encoder)."""
    return ["-c:v", "gif", "-loop", "-1" if loop == "once" else "0", "-an"]


def container_flags(ext: str) -> list[str]:
    """MP4's index first, so it plays while it downloads (bash's container_flags)."""
    return ["-movflags", "+faststart"] if family(ext) == "mp4" else []


def youtube_args(gop: int, kbps: int, *, time_base: Rational | None) -> list[str]:
    """x264 as YouTube asks: High, 2 B-frames, a closed GOP of half a second (bash's convert).

    Each the picture's alone (output v:0): an option for every video stream reaches a copied
    cover too, and a PNG's encoder cannot parse x264's profile (measured).
    """
    return [
        "-c:v:0", VIDEO_ENCODERS["h264"],
        "-preset:v:0", "veryslow",
        "-profile:v:0", "high",
        "-pix_fmt:v:0", "yuv420p",
        "-bf:v:0", "2",
        "-g:v:0", str(gop),
        "-flags:v:0", "+cgop",
        "-coder:v:0", "1",
        "-b:v:0", f"{kbps}k",
        "-enc_time_base:v:0", enc_time_base(time_base),
    ]  # fmt: skip


# an entry: six flags and a name; the legend above them (" V..... = Video") names none
_ENCODER_LINE: Final = re.compile(r" [A-Z.]{6} (?!= )(\S+) ")


def parse_encoders(listing: str) -> frozenset[str]:
    """The encoders in ``ffmpeg -hide_banner -encoders``' listing (bash's have_encoder)."""
    return frozenset(m[1] for line in listing.splitlines() if (m := _ENCODER_LINE.match(line)))


def attachment_args(*, carry: bool) -> list[str]:
    """The attachment streams, copied as they are, or none (subtitles: each its own, 3.12)."""
    return ["-map", "0:t?", "-c:t", "copy"] if carry else []


def optimizer(ext: str, path: str) -> list[str] | None:
    """An image's or a GIF's lossless optimiser, at its strongest (bash's optimize_output)."""
    match ext:
        case "png":
            return ["oxipng", "-q", "-o", "max", "--", path]
        case "jpg" | "jpeg":
            return ["jpegoptim", "-q", "--auto-mode", "--", path]
        case "gif":
            return ["gifsicle", "-b", "-O3", "--", path]
        case _:
            return None
