"""The YouTube flow: bash's convert --preset youtube (H.264 High, two-pass; AAC).

The source's refusals, its filters to BT.709 SDR, the frame rate, GOP and
bitrate, and the sound: copied when it complies, else normalised.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from ffman.errors import refuse
from ffman.graph import Filter
from ffman.graph.resize import SCALER
from ffman.media.probe import Media, Rational, Video
from ffman.plan.encode import FDK_AAC
from ffman.plan.outputs import is_image

_HDR: Final = frozenset({"smpte2084", "arib-std-b67"})
_INTERLACED: Final = frozenset({"tt", "bb", "tb", "bt"})
_RGB_FORMATS: Final = (
    "rgb",
    "bgr",
    "gbr",
    "argb",
    "abgr",
    "0rgb",
    "0bgr",
    "x2rgb",
    "x2bgr",
    "pal8",
)
# yt_bitrate: the first class the long or the short side reaches, kbps at <= 30.5 fps and above
_BITRATES: Final = (
    (7680, 4320, 160000, 240000),
    (3840, 2160, 45000, 68000),
    (2560, 1440, 16000, 24000),
    (1920, 1080, 8000, 12000),
    (1280, 720, 5000, 7500),
    (854, 480, 2500, 4000),
)


@dataclass(frozen=True, slots=True)
class YouTubeVideo:
    """The picture's filters and x264's settings (bash's convert)."""

    filters: tuple[Filter, ...]
    fps: Fraction  # to 6 decimals, as bash printed it (fps_of), in the note too
    gop: int
    kbps: int
    width: int
    height: int

    @property
    def note(self) -> str:
        """The note bash printed before encoding."""
        size = f"{self.width}x{self.height} @ {self.fps:.6f} fps"
        return f"H.264 High {size}, GOP {self.gop}, {self.kbps} kbps two-pass"


@dataclass(frozen=True, slots=True)
class Silent:
    """No audio stream: the upload is silent (and said so)."""

    note: str


@dataclass(frozen=True, slots=True)
class Copied:
    """Already what YouTube asks for -- AAC LC, 48 kHz, stereo: copied."""


@dataclass(frozen=True, slots=True)
class Normalised:
    """Any other sound: ffmpeg-normalize's preset makes it (and it is said)."""

    preset: str
    note: str


type YouTubeSound = Silent | Copied | Normalised  # bash's three: no stream, copy, normalise


def _moving_picture(media: Media, path: str) -> tuple[Video, int, int]:
    """The video stream and its size, which bash required (``[[ -n $w && -n $h ]]``)."""
    video = media.video
    if video is None or video.width is None or video.height is None:
        refuse(f"no video stream in: {path}")
    return video, video.width, video.height


def check_youtube_source(media: Media, in_ext: str, path: str) -> None:
    """The first refusals of bash's convert: a picture that moves, and SDR."""
    if is_image(in_ext):
        refuse(f"convert needs a video, not an image: {path}")
    video, _, _ = _moving_picture(media, path)
    if video.color_transfer in _HDR:
        refuse(
            f"HDR input ({video.color_transfer}) is not supported by --preset youtube (SDR only)"
        )


def check_youtube_output(out_ext: str) -> None:
    """YouTube's container (after the output is resolved, as bash checked it)."""
    if out_ext != "mp4":
        refuse("YouTube's container is MP4: --output must end in .mp4")


def fps_of(rate: Rational | None) -> Fraction | None:
    """``N/D`` to 6 decimals, as bash's fps_of printed it (%.6f); None if none or D <= 0.

    Exact where bash printed a double: they differ only on a tie at the seventh
    decimal, which needs a denominator with 5**7 in it -- no frame rate has one.
    """
    if rate is None or rate.den <= 0:
        return None
    return round(Fraction(rate.num, rate.den), 6)  # half to even, as %.6f of the exact value


def youtube_video(media: Media, path: str) -> YouTubeVideo:
    """The filters, the frame rate, the GOP and the bitrate (bash's convert, in its order)."""
    video, width, height = _moving_picture(media, path)
    rate = video.frame_rate()
    filters: list[Filter] = []
    if video.field_order in _INTERLACED:
        filters.append(
            Filter("bwdif", (("mode", "send_frame"), ("parity", "auto"), ("deint", "all")))
        )
    filters += _to_bt709(video.color_space, video.pix_fmt, video.color_primaries, video.color_range)
    filters += [
        Filter("format", ("yuv420p",)),
        Filter(
            "setparams",
            (
                ("color_primaries", "bt709"),
                ("color_trc", "bt709"),
                ("colorspace", "bt709"),
                ("range", "tv"),
            ),
        ),
    ]
    fps = fps_of(rate)
    if fps is None or fps <= 0:
        refuse(f"cannot determine the frame rate of: {path}")
    return YouTubeVideo(
        tuple(filters),
        fps,
        _gop(fps),
        youtube_kbps(width, height, fps),
        width,
        height,
    )


def _to_bt709(
    matrix: str | None, pix_fmt: str | None, primaries: str | None, rng: str | None
) -> list[Filter]:
    """To BT.709, limited range, from what the source is tagged (bash's colour step)."""
    if matrix == "gbr" or (pix_fmt or "").startswith(_RGB_FORMATS):
        matrix = "rgb"
    if matrix == "rgb":
        return [
            Filter("scale", (("out_color_matrix", "bt709"), ("out_range", "tv"), ("flags", SCALER)))
        ]
    if matrix in (None, "unknown", "bt709"):
        return [Filter("scale", (("out_range", "tv"), ("flags", SCALER)))] if rng == "pc" else []
    if matrix not in ("smpte170m", "bt470bg"):
        refuse(f"unsupported colour matrix '{matrix}' for --preset youtube (bt709 or bt601 SDR)")
    given = (
        ("matrixin", "470bg" if matrix == "bt470bg" else "170m"),
        ("primariesin", "470bg" if primaries == "bt470bg" else "170m"),
        ("transferin", "601"),
        ("rangein", "full" if rng == "pc" else "limited"),
    )
    wanted = (("matrix", "709"), ("primaries", "709"), ("transfer", "709"), ("range", "limited"))
    return [Filter("zscale", (*given, *wanted))]


def _gop(fps: Fraction) -> int:
    """Half a second of frames: bash rounds up only above a half (25 fps: 12), at least 1."""
    n = fps / 2
    g = int(n)
    if n - g > Fraction(1, 2):
        g += 1
    return max(g, 1)


def youtube_kbps(width: int, height: int, fps: Fraction) -> int:
    """YouTube's bitrate for a size and rate, kbps (bash's yt_bitrate); over 30.5 fps: higher."""
    long, short = max(width, height), min(width, height)
    high = fps > Fraction(61, 2)
    for class_long, class_short, low_rate, high_rate in _BITRATES:
        if long >= class_long or short >= class_short:
            return high_rate if high else low_rate
    return 1500 if high else 1000


def youtube_sound(media: Media, *, normalize: bool, encoders: frozenset[str]) -> YouTubeSound:
    """Copied when it already is AAC LC, 48 kHz, stereo (unless --normalize), else normalised."""
    audio = media.audio
    if audio is None or audio.codec is None:
        return Silent("no audio stream: the upload will be silent")
    compliant = (audio.codec, audio.profile, audio.sample_rate, audio.channels) == (
        "aac",
        "LC",
        48000,
        2,
    )
    if compliant and not normalize:
        return Copied()
    preset = "youtube-aac" if FDK_AAC in encoders else "youtube-aac-native"
    channels = "?" if audio.channels is None else audio.channels  # bash's ${ach:-?}: 0 prints 0
    hz = "?" if audio.sample_rate is None else audio.sample_rate  # bash's ${asr:-?}: 0 prints 0
    what = f"{audio.codec} {hz} Hz {channels} ch"
    return Normalised(preset, f"normalising audio ({what}) with preset {preset}")
