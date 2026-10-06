from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ffman.errors import FfmanError
from ffman.jobs.convert.options import validate
from ffman.media.probe import Attachment, Audio, Media, Rational, Subtitle, Video
from ffman.options import CONVERT, parse
from ffman.plan.encode import audio_args
from ffman.plan.flows import Flow, select_flow
from ffman.plan.outputs import (
    ImageFrame,
    Output,
    check_burn_source,
    check_moving,
    image_frame,
    output_kind,
)
from ffman.plan.request import ConvertOptions
from ffman.plan.streams import (
    Attachments,
    Lossless,
    Sound,
    attach_streams,
    attachments,
    lossless,
    sound,
    subtitle_codec,
)
from ffman.plan.youtube import (
    Copied,
    Normalised,
    Silent,
    YouTubeSound,
    YouTubeVideo,
    check_youtube_output,
    check_youtube_source,
    fps_of,
    youtube_sound,
    youtube_video,
)

ALL = frozenset({"libx264", "libx265", "libvpx-vp9", "libaom-av1", "ffv1", "libfdk_aac"})


def o(*argv: str) -> ConvertOptions:
    return validate(parse("convert", CONVERT, ["-i", "in.mp4", *argv]))


def media(
    codec: str | None = "h264", channels: int | None = 2, subs: int = 0, attachments: int = 0
) -> Media:
    square = Rational(1, 1)
    video = Video(
        codec, 640, 360, None, square, None, None, None, None, None, None, None, None, None, None
    )
    tracks = (Subtitle("subrip", None, None),) * subs
    attached = (Attachment("font.ttf"),) * attachments
    return Media(video, Audio("aac", "LC", channels, 48000), tracks, attached, Fraction(1), None)


@pytest.mark.parametrize(
    ("argv", "flow"),
    [
        (["-p", "yt"], Flow.YOUTUBE),
        (["-p", "yt", "--normalize"], Flow.YOUTUBE),
        (["--add-subs", "s.srt"], Flow.TRACKS),
        (["-w", "320"], Flow.PICTURE),
        (["--vfx", "crt"], Flow.PICTURE),
        (["--burn-subs", "s.srt"], Flow.PICTURE),
        (["--burn-subs", "s.srt", "-w", "320", "-b"], Flow.PICTURE),
    ],
)
def test_the_flows(argv: list[str], flow: Flow) -> None:
    assert select_flow(o(*argv)) is flow


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["-p", "yt", "--loop"],
            "--preset youtube is a job of its own: --loop cannot be added, for now",
        ),
        (
            ["--add-subs", "s.srt", "--loop-reverse"],
            "--add-subs copies the picture and the sound: --loop-reverse cannot be added, for now",
        ),
        (
            ["--loop"],
            "convert: nothing to do: give a size (-w, -H, -a), an effect (--vfx), subtitles (--burn-subs, --add-subs), another container, a codec or --preset",
        ),  # bash's resize: "give --width ..."
        (
            ["-p", "yt", "-w", "320"],
            "--preset youtube is a job of its own: -w cannot be added, for now",
        ),
        (
            ["-p", "yt", "--vfx", "crt"],
            "--preset youtube is a job of its own: --vfx cannot be added, for now",
        ),
        (
            ["-p", "yt", "--add-subs", "s.srt"],
            "--preset youtube is a job of its own: --add-subs cannot be added, for now",
        ),
        (
            ["--add-subs", "s.srt", "--burn-subs", "b.srt"],
            "--add-subs copies the picture and the sound: --burn-subs cannot be added, for now",
        ),
        (
            ["--add-subs", "s.srt", "--audio-codec", "flac"],
            "--add-subs copies the picture and the sound: --audio-codec cannot be added, for now",
        ),
        (
            ["--add-subs", "s.srt", "--lossless"],
            "--add-subs copies the picture and the sound: --lossless cannot be added, for now",
        ),
        (
            ["--burn-subs", "s.srt", "-b"],
            "--bblur and --resize-mode need a size or a ratio to resize to (-w, -H or -a)",
        ),
        (
            ["--burn-subs", "s.srt", "-r", "stretch"],
            "--bblur and --resize-mode need a size or a ratio to resize to (-w, -H or -a)",
        ),
        (
            [],
            "convert: nothing to do: give a size (-w, -H, -a), an effect (--vfx), subtitles (--burn-subs, --add-subs), another container, a codec or --preset",
        ),
    ],
)
def test_what_no_bash_command_did_is_refused(argv: list[str], message: str) -> None:
    with pytest.raises(FfmanError) as error:
        _ = select_flow(o(*argv))
    assert str(error.value) == message


# bash's inline checks (cmd_resize, cmd_overlay): their messages, read from the code.
@pytest.mark.parametrize(
    ("argv", "burn", "moving", "ext", "expected"),
    [
        ([], False, True, "mkv", Output.VIDEO),
        ([], False, True, "gif", Output.GIF),
        ([], False, False, "png", Output.IMAGE),
        ([], False, False, "gif", Output.GIF),
        ([], False, True, "png", "a video cannot be resized into an image (.png)"),
        ([], False, False, "mp4", "an image cannot be resized into a video (.mp4)"),
        ([], True, True, "jpg", "overlay output must be a video"),
        (["--loop"], False, True, "mp4", "--loop and --loop-reverse need a .gif output"),
        (
            ["--loop-reverse"],
            False,
            False,
            "gif",
            "--loop and --loop-reverse need a moving source: an image makes a one-frame GIF",
        ),
        (["--loop"], True, True, "gif", Output.GIF),
    ],
)
def test_output_kind(
    argv: list[str], burn: bool, moving: bool, ext: str, expected: Output | str
) -> None:
    if isinstance(expected, Output):
        assert output_kind(o(*argv), burn=burn, moving=moving, out_ext=ext) is expected
    else:
        with pytest.raises(FfmanError) as error:
            _ = output_kind(o(*argv), burn=burn, moving=moving, out_ext=ext)
        assert str(error.value) == expected


def test_burning_and_moshing_need_a_video() -> None:
    with pytest.raises(FfmanError, match=r"^overlay needs a video, not an image: a\.png$"):
        check_burn_source("png", "a.png")
    check_burn_source("mp4", "a.mp4")
    with pytest.raises(
        FfmanError, match=r"^--datamosh melts scene cuts: it needs a moving source$"
    ):
        check_moving(o("--vfx", "datamosh"), moving=False)
    check_moving(o("--vfx", "datamosh"), moving=True)
    check_moving(o("--vfx", "crt"), moving=False)


def test_lossless_and_image_frame() -> None:
    assert image_frame("jpeg") == ImageFrame("jpeg", "mjpeg")
    kept = lossless(o(), media("hevc"), ALL)
    assert kept == Lossless("hevc", "libx265", "re-rendered: the source's codec (hevc), losslessly")
    asked = lossless(o("--video-codec", "AOM"), media(), ALL)
    assert (asked.codec, asked.why) == ("av1", "re-rendered: --video-codec, losslessly")


@pytest.mark.parametrize(
    ("argv", "source", "encoders", "message"),
    [
        (
            ["--video-codec", "copy"],
            "h264",
            ALL,
            "--video-codec copy is impossible here: the picture is re-rendered",
        ),
        (
            [],
            "mpeg2video",
            ALL,
            "no lossless encoder for video codec 'mpeg2video'; choose --video-codec h264, hevc, vp9, av1 or ffv1",
        ),
        (
            [],
            None,
            ALL,
            "no lossless encoder for video codec ''; choose --video-codec h264, hevc, vp9, av1 or ffv1",
        ),
        ([], "vp9", frozenset({"libx264"}), "this ffmpeg has no libvpx-vp9 encoder"),
    ],
)
def test_lossless_refusals(
    argv: list[str], source: str | None, encoders: frozenset[str], message: str
) -> None:
    with pytest.raises(FfmanError) as error:
        _ = lossless(o(*argv), media(source), encoders)
    assert str(error.value) == message


def test_an_image_format_nothing_writes() -> None:
    with pytest.raises(FfmanError) as error:
        _ = image_frame("bmp")
    assert str(error.value) == "unsupported image output '.bmp' (png, jpg, webp, avif, tiff)"


@pytest.mark.parametrize(
    ("argv", "channels", "encoders", "expected"),
    [
        ([], 2, ALL, Sound("copy")),
        (["--audio-codec", "none"], 2, ALL, Sound("none")),
        (["--audio-codec", "aac"], 6, ALL, Sound("aac", "libfdk_aac", 6)),
        (
            ["--audio-codec", "aac"],
            2,
            frozenset[str](),
            Sound("aac", "aac", 2),
        ),  # no FDK: native
        (
            ["--audio-codec", "opus"],
            None,
            ALL,
            Sound("opus", "libopus", 2),
        ),  # bash: ${1:-2}
        (
            ["--audio-codec", "flac"],
            0,
            ALL,
            Sound("flac", "flac", 2),
        ),  # bash: ch > 0 || 2
    ],
)
def test_sound(
    argv: list[str], channels: int | None, encoders: frozenset[str], expected: Sound
) -> None:
    assert sound(o(*argv), media(channels=channels), encoders) == expected


def test_attachments_carried_within_one_family() -> None:
    assert attachments(media(), "mkv", "mp4") == Attachments(carry=False)  # none to carry: no note
    assert attachments(media(subs=1), "mkv", "mp4") == Attachments(carry=False)  # subtitles: 3.12's
    assert attachments(media(attachments=1), "mkv", "mka") == Attachments(carry=True)
    dropped = attachments(media(attachments=2), "mkv", "webm")
    assert (dropped.carry, dropped.note) == (
        False,
        "attachments are not carried into .webm (another container family)",
    )


ACROSS = ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?"]


@pytest.mark.parametrize(
    ("in_ext", "out_ext", "fmt", "codec", "streams"),
    [  # bash's attach: its maps and scopy
        (
            "mkv",
            "mkv",
            "ass",
            "ass",
            (
                ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?", "-map", "0:d?"],
                ["-c:s:1", "ass"],
            ),
        ),
        (
            "mkv",
            "mkv",
            "srt",
            "srt",
            (
                ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?", "-map", "0:d?"],
                ["-c:s:1", "srt"],
            ),
        ),
        ("mp4", "mkv", "vtt", "srt", ([*ACROSS, "-map", "0:t?"], ["-c:s", "srt", "-c:s:1", "srt"])),
        ("mkv", "mp4", "ass", "mov_text", (ACROSS, ["-c:s", "mov_text"])),
        ("mkv", "webm", "srt", "webvtt", (ACROSS, ["-c:s", "webvtt"])),
    ],
)
def test_attach_streams(
    in_ext: str, out_ext: str, fmt: str, codec: str, streams: tuple[list[str], list[str]]
) -> None:
    assert subtitle_codec(out_ext, fmt) == codec
    assert attach_streams(in_ext, out_ext, codec, 1) == streams


def test_a_container_without_subtitles() -> None:
    with pytest.raises(FfmanError) as error:
        _ = subtitle_codec("avi", "srt")
    assert (
        str(error.value)
        == "a .avi file cannot carry a subtitle track; give --output with .mka or .m4a (audio), .mkv or .mp4 (video)"
    )


def yt(
    matrix: str | None = "bt709",
    pix: str = "yuv420p",
    primaries: str | None = "bt709",
    rng: str | None = "tv",
    field: str | None = "progressive",
    rate: str = "25/1",
    size: tuple[int, int] = (1920, 1080),
    transfer: str | None = None,
    audio: Audio | None = None,
) -> Media:
    video = Video(
        "h264",
        size[0],
        size[1],
        None,
        Rational(1, 1),
        Rational(1, 12800),
        None,
        Rational.parse(rate),
        Rational.parse(rate),
        pix,
        field,
        primaries,
        transfer,
        rng,
        matrix,
    )
    return Media(video, audio, (), (), None, None)


def test_youtube_refusals() -> None:
    with pytest.raises(FfmanError, match=r"^convert needs a video, not an image: a\.png$"):
        check_youtube_source(yt(), "png", "a.png")
    with pytest.raises(FfmanError, match=r"^no video stream in: a\.m4a$"):
        check_youtube_source(Media(None, None, (), (), None, None), "m4a", "a.m4a")
    for transfer in ("smpte2084", "arib-std-b67"):
        with pytest.raises(
            FfmanError,
            match=rf"^HDR input \({transfer}\) is not supported by --preset youtube \(SDR only\)$",
        ):
            check_youtube_source(yt(transfer=transfer), "mkv", "a.mkv")
    check_youtube_source(yt(), "mkv", "a.mkv")
    with pytest.raises(
        FfmanError, match=r"^YouTube's container is MP4: --output must end in \.mp4$"
    ):
        check_youtube_output("mkv")
    check_youtube_output("mp4")
    with pytest.raises(FfmanError, match=r"^cannot determine the frame rate of: a\.mp4$"):
        _ = youtube_video(yt(rate="0/0"), "a.mp4")
    with pytest.raises(
        FfmanError,
        match=r"^unsupported colour matrix 'bt2020nc' for --preset youtube \(bt709 or bt601 SDR\)$",
    ):
        _ = youtube_video(yt(matrix="bt2020nc"), "a.mp4")
    with pytest.raises(FfmanError, match=r"^no video stream in: a\.m4a$"):
        _ = youtube_video(Media(None, None, (), (), None, None), "a.m4a")


@pytest.mark.parametrize(
    ("rate", "fps"),
    [
        ("25/1", Fraction(25)),
        ("30000/1001", Fraction("29.970030")),
        ("0/0", None),
        ("25", None),
        ("x/y", None),
        (None, None),
        ("50/-1", None),
    ],
)
def test_fps_of_as_bash(rate: str | None, fps: Fraction | None) -> None:
    """ffprobe's text through the boundary: bash's answers, row for row."""
    assert fps_of(Rational.parse(rate)) == fps


@given(st.integers(-(10**9), 10**9), st.integers(1, 10**7))
def test_fps_of_is_the_value_bash_printed(num: int, den: int) -> None:
    """%.6f of the exact value, read back: round half to even at the seventh decimal."""
    assert fps_of(Rational(num, den)) == Fraction(f"{Fraction(num, den):.6f}")


@pytest.mark.parametrize("k", [-3, -1, 0, 1, 2, 7])
def test_fps_of_rounds_a_tie_to_even(k: int) -> None:
    tie = Fraction(2 * k + 1, 2 * 10**6)  # exactly half a millionth past a value
    assert fps_of(Rational(tie.numerator, tie.denominator)) == Fraction(f"{tie:.6f}")


def names(video: YouTubeVideo) -> list[str]:
    return [f.render() for f in video.filters]


def test_youtube_filters() -> None:
    assert names(youtube_video(yt(), "a")) == [
        "format=yuv420p",
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
    ]
    assert (
        names(youtube_video(yt(field="tt"), "a"))[0]
        == "bwdif=mode=send_frame:parity=auto:deint=all"
    )
    rgb = "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int"
    assert names(youtube_video(yt(pix="rgb24"), "a"))[0] == rgb
    assert names(youtube_video(yt(matrix="gbr", pix="gbrp"), "a"))[0] == rgb
    assert (
        names(youtube_video(yt(matrix=None, rng="pc"), "a"))[0]
        == "scale=out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int"
    )
    assert names(youtube_video(yt(matrix="unknown", rng="tv"), "a"))[0] == "format=yuv420p"
    assert names(youtube_video(yt(matrix="bt470bg", primaries="smpte170m", rng="pc"), "a"))[0] == (
        "zscale=matrixin=470bg:primariesin=170m:transferin=601:rangein=full:matrix=709:primaries=709:transfer=709:range=limited"
    )
    assert names(youtube_video(yt(matrix="smpte170m", primaries="bt470bg", rng=None), "a"))[0] == (
        "zscale=matrixin=170m:primariesin=470bg:transferin=601:rangein=limited:matrix=709:primaries=709:transfer=709:range=limited"
    )


@pytest.mark.parametrize(
    ("rate", "size", "gop", "kbps"),
    [
        ("25/1", (1920, 1080), 12, 8000),  # 12.5: bash rounds up only above a half
        ("30000/1001", (1920, 1080), 15, 8000),
        ("60/1", (3840, 2160), 30, 68000),
        ("61/2", (1280, 720), 15, 5000),  # 30.5 is not above 30.5: the lower rate
        ("31/1", (7680, 4320), 15, 240000),  # 15.5: a tie, down
        ("1/1", (300, 200), 1, 1000),  # at least 1
        ("50/1", (300, 200), 25, 1500),
        ("24/1", (854, 480), 12, 2500),
        ("24/1", (1080, 1920), 12, 8000),  # the long side counts
    ],
)
def test_youtube_gop_and_bitrate(rate: str, size: tuple[int, int], gop: int, kbps: int) -> None:
    video = youtube_video(yt(rate=rate, size=size), "a")
    assert (video.gop, video.kbps) == (gop, kbps)


def test_youtube_note() -> None:
    video = youtube_video(yt(rate="30000/1001"), "a")
    assert video.note == "H.264 High 1920x1080 @ 29.970030 fps, GOP 15, 8000 kbps two-pass"


@pytest.mark.parametrize(
    ("audio", "normalize", "encoders", "expected"),
    [
        (
            None,
            False,
            ALL,
            Silent("no audio stream: the upload will be silent"),
        ),
        (Audio("aac", "LC", 2, 48000), False, ALL, Copied()),
        (
            Audio("aac", "LC", 2, 48000),
            True,
            ALL,
            Normalised(
                "youtube-aac", "normalising audio (aac 48000 Hz 2 ch) with preset youtube-aac"
            ),
        ),
        (
            Audio("aac", "LC", 2, 44100),
            False,
            frozenset[str](),
            Normalised(
                "youtube-aac-native",
                "normalising audio (aac 44100 Hz 2 ch) with preset youtube-aac-native",
            ),
        ),
        (
            Audio("opus", None, None, None),
            False,
            ALL,
            Normalised("youtube-aac", "normalising audio (opus ? Hz ? ch) with preset youtube-aac"),
        ),
        (
            Audio(None, None, 2, 48000),
            False,
            ALL,
            Silent("no audio stream: the upload will be silent"),
        ),
    ],
)
def test_youtube_sound(
    audio: Audio | None, normalize: bool, encoders: frozenset[str], expected: YouTubeSound
) -> None:
    media = Media(None, audio, (), (), None, None)
    assert youtube_sound(media, normalize=normalize, encoders=encoders) == expected


@pytest.mark.parametrize(
    "codec", ["copy", "none", "flac", "aac", "opus", "mp3", "vorbis", "alac", "pcm"]
)
def test_a_sound_is_what_audio_args_takes(codec: str) -> None:
    # the seam the job uses: a decision straight into its arguments, for every codec
    s = sound(o("--audio-codec", codec), media(), ALL)
    assert audio_args(s.codec, s.encoder, s.channels or 2)[:2] in (
        ["-c:a", s.encoder],
        ["-c:a", "copy"],
        ["-an"],
    )
