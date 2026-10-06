import pytest

from ffman.graph.light import DECODE, ENCODE, transfer
from ffman.media.probe import Rational, Video
from ffman.plan.encode import (
    audio_args,
    container_flags,
    enc_time_base,
    ffv1_slices,
    gif_args,
    image_args,
    lossless_args,
    optimizer,
    youtube_args,
)


@pytest.mark.parametrize(
    ("time_base", "expected"),
    [
        ("1/12800", "1/12800"),
        ("1001/30000", "1001/30000"),
        ("0/1", "demux"),
        ("01/25", "demux"),
        (None, "demux"),
        ("N/A", "demux"),
    ],
)
def test_enc_time_base(time_base: str | None, expected: str) -> None:
    """ffprobe's text through the boundary: bash's answers, row for row."""
    assert enc_time_base(Rational.parse(time_base)) == expected


@pytest.mark.parametrize(
    ("cores", "size", "slices"),
    [
        (4, (1920, 1080), None),  # ffv1's own 2x2 is four already
        (5, (1920, 1080), 6),  # 2x3
        (8, (1920, 1080), 8),  # 2x4
        (16, (1920, 1080), 16),  # 4x4 (3 rows take at most 6 across: 18)
        (8, (40, 40), None),  # no slice fits 32 px twice
    ],
)
def test_ffv1_slices(cores: int, size: tuple[int, int], slices: int | None) -> None:
    assert ffv1_slices(cores, *size) == slices


def test_lossless_args() -> None:
    assert lossless_args("h264", time_base=Rational(1, 25)) == [
        "-c:v",
        "libx264",
        "-preset",
        "veryslow",
        "-qp",
        "0",
        "-enc_time_base:v",
        "1/25",
    ]
    assert lossless_args("ffv1", time_base=None, slices=8)[-4:] == [
        "-slices",
        "8",
        "-enc_time_base:v",
        "demux",
    ]
    assert "-slices" not in lossless_args("h264", time_base=None, slices=8)  # only ffv1 slices
    assert lossless_args("vp9", time_base=None)[:6] == [
        "-c:v",
        "libvpx-vp9",
        "-lossless",
        "1",
        "-deadline",
        "good",
    ]


@pytest.mark.parametrize(
    ("codec", "encoder", "channels", "expected"),
    [
        ("copy", None, 2, ["-c:a", "copy"]),
        ("none", None, 2, ["-an"]),
        (
            "aac",
            "libfdk_aac",
            2,
            ["-c:a", "libfdk_aac", "-profile:a", "aac_low", "-b:a", "384k", "-cutoff", "20000"],
        ),
        ("aac", "aac", 6, ["-c:a", "aac", "-b:a", "1152k"]),
        (
            "opus",
            "libopus",
            2,
            [
                "-c:a",
                "libopus",
                "-b:a",
                "510k",
                "-vbr",
                "on",
                "-compression_level",
                "10",
                "-application",
                "audio",
                "-ar",
                "48000",
            ],
        ),
        (
            "opus",
            "libopus",
            6,
            [
                "-c:a",
                "libopus",
                "-b:a",
                "1536k",
                "-vbr",
                "on",
                "-compression_level",
                "10",
                "-application",
                "audio",
                "-ar",
                "48000",
            ],
        ),
        ("flac", "flac", 2, ["-c:a", "flac", "-compression_level", "10"]),
        ("pcm", "pcm_s24le", 2, ["-c:a", "pcm_s24le"]),
    ],
)
def test_audio_args(codec: str, encoder: str | None, channels: int, expected: list[str]) -> None:
    assert audio_args(codec, encoder, channels) == expected


def test_the_rest() -> None:
    assert image_args("mjpeg") == ["-c:v", "mjpeg", "-q:v", "1", "-pix_fmt", "yuvj444p"]
    assert (gif_args("once"), gif_args("reverse")) == (
        ["-c:v", "gif", "-loop", "-1", "-an"],
        ["-c:v", "gif", "-loop", "0", "-an"],
    )
    assert (container_flags("m4a"), container_flags("mkv")) == (["-movflags", "+faststart"], [])
    youtube = youtube_args(12, 8000, time_base=Rational(1, 12800))
    assert youtube[10:14] == ["-g:v:0", "12", "-flags:v:0", "+cgop"]
    assert all(
        option.endswith(":v:0") for option in youtube[::2]
    )  # the picture's alone: a cover copied
    assert optimizer("jpeg", "p.jpeg") == ["jpegoptim", "-q", "--auto-mode", "--", "p.jpeg"]
    assert optimizer("png", "p.png") == ["oxipng", "-q", "-o", "max", "--", "p.png"]
    assert optimizer("gif", "p.gif") == ["gifsicle", "-b", "-O3", "--", "p.gif"]
    assert optimizer("webp", "p.webp") is None


@pytest.mark.parametrize(
    ("codec", "tag", "curve"),
    [
        ("h264", None, "bt1886"),
        ("h264", "iec61966-2-1", "srgb"),  # tagged: sRGB, whatever the codec
        ("png", None, "srgb"),
        ("png", "unknown", "srgb"),
        ("png", "bt709", "bt1886"),  # an image tagged otherwise keeps its tag
        ("mjpeg", None, "srgb"),
    ],
)
def test_transfer(codec: str, tag: str | None, curve: str) -> None:
    video = Video(
        codec, 16, 16, None, None, None, None, None, None, None, None, None, tag, None, None
    )
    assert transfer(video) == curve


def test_the_curves_are_raw() -> None:
    # ffman.graph escapes: nothing here may be pre-escaped as bash's \, was
    for expression in (*DECODE.values(), *ENCODE.values()):
        assert "\\" not in expression
        assert expression.count("(") == expression.count(")")
