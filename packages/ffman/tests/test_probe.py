import json
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Literal, final

import pytest

from ffman.errors import FfmanError
from ffman.media.probe import Audio, Media, Rational, Subtitle, Video, parse, read, tag_names

FIXTURES = Path(__file__).parent / "fixtures" / "probe"


def media(name: str) -> Media:
    return parse((FIXTURES / f"{name}.json").read_text())


def video(name: str) -> Video:
    found = media(name).video
    assert found is not None
    return found


def audio(name: str) -> Audio:
    found = media(name).audio
    assert found is not None
    return found


# What each file was made with (record.sh), not what the parser returns.
def test_plain_file() -> None:
    v, a = video("h264_aac.mp4"), audio("h264_aac.mp4")
    assert (v.codec, v.width, v.height, v.rotation, v.sar, v.pix_fmt) == (
        "h264",
        640,
        360,
        None,
        Rational(1, 1),
        "yuv420p",
    )
    rate = Rational(25, 1)
    assert (v.avg_frame_rate, v.r_frame_rate, v.field_order) == (rate, rate, "progressive")
    assert (a.codec, a.profile, a.channels, a.sample_rate) == ("aac", "LC", 2, 48000)
    assert media("h264_aac.mp4").creation_time == "2019-06-01T12:34:56.000000Z"
    # the format's "1.000000": bash's pq .format.duration
    assert media("h264_aac.mp4").duration == 1
    assert media("image.png").duration is None


def test_rotation_is_the_display_matrix_as_text() -> None:
    v = video("rotated.mp4")
    assert (v.width, v.height, v.rotation) == (640, 360, "90")  # stored size; geometry turns it


def test_anamorphic_sar_and_ntsc_rate() -> None:
    v = video("anamorphic.mkv")
    assert (v.width, v.height, v.sar, v.r_frame_rate) == (
        720,
        480,
        Rational(32, 27),
        Rational(30000, 1001),
    )


def test_cover_art_is_no_picture() -> None:
    m = media("cover_art.m4a")
    assert m.video is None
    assert m.audio is not None


def test_subtitle_tracks_are_read_attachments_counted() -> None:
    m = media("subs_attach.mkv")
    assert len(m.attachments) == 1  # recorded
    assert m.subtitles == (Subtitle("subrip", "por", None),)
    assert (media("h264_aac.mp4").subtitles, media("h264_aac.mp4").attachments) == ((), ())


def test_hdr_tags() -> None:
    v = video("hdr10.mkv")
    assert (v.pix_fmt, v.color_primaries, v.color_transfer, v.color_space, v.color_range) == (
        "yuv420p10le",
        "bt2020",
        "smpte2084",
        "bt2020nc",
        "tv",
    )


def test_interlaced_and_images() -> None:
    assert video("interlaced.mp4").field_order == "tt"
    assert (video("image.png").codec, video("anim.gif").codec) == ("png", "gif")
    assert media("image.png").audio is None


def stream(**fields: object) -> dict[str, object]:
    return {"codec_type": "video", "width": 4, "height": 2, **fields}


def probed(*streams: dict[str, object], fmt: object = None) -> Media:
    root: dict[str, object] = {"streams": list(streams)}
    if fmt is not None:
        root["format"] = fmt
    return parse(json.dumps(root))


# The edges no recorded file has, each as bash's jq read it.
@pytest.mark.parametrize(
    ("fields", "rotation"),
    [
        ({"side_data_list": [{"rotation": -90}]}, "-90"),
        (
            {"side_data_list": [{"rotation": 0}]},
            "0",
        ),  # 0 is a value (jq's // takes only null, false)
        ({"side_data_list": [{"x": 1}, {"rotation": 270}]}, "270"),  # the first number
        (
            {"side_data_list": [{"rotation": "90"}], "tags": {"rotate": "180"}},
            "180",
        ),  # not a number: the tag
        (
            {"side_data_list": [{"rotation": 90}], "tags": {"rotate": "180"}},
            "90",
        ),  # the matrix first
        ({"tags": {"rotate": "90"}}, "90"),
        ({"side_data_list": [{"rotation": True}]}, None),  # jq's numbers: no booleans
        ({}, None),
    ],
)
def test_rotation_as_bash(fields: dict[str, object], rotation: str | None) -> None:
    v = probed(stream(**fields)).video
    assert v is not None
    assert v.rotation == rotation


@pytest.mark.parametrize(
    ("disposition", "picture"),
    [
        (None, True),
        ({"attached_pic": 0}, True),
        ({"attached_pic": False}, True),
        ({"attached_pic": 1}, False),
        ({"attached_pic": True}, False),
    ],
)
def test_attached_pictures_are_skipped(disposition: object, picture: bool) -> None:
    first = stream(width=1) if disposition is None else stream(width=1, disposition=disposition)
    v = probed(first, stream(width=2)).video
    assert v is not None
    assert (v.width == 1) is picture


def test_absent_null_empty_and_mistyped_fields_are_none() -> None:
    v = probed(stream(width=None, height="360", pix_fmt="", codec_name=5, channels=True)).video
    assert v is not None
    assert (v.width, v.height, v.pix_fmt, v.codec) == (None, None, None, None)


def test_a_file_without_streams() -> None:
    m = probed(fmt={"tags": {"creation_time": ""}})
    assert (m.video, m.audio, m.subtitles, m.attachments) == (None, None, (), ())
    assert (m.duration, m.creation_time) == (None, None)
    assert parse("[]") == Media(None, None, (), (), None, None)


@final
class FakeRunner:
    """probe.Capturing: what the command would print, and its status."""

    def __init__(self, stdout: str, status: int = 0) -> None:
        self.stdout = stdout
        self.status = status
        self.argv: list[str] = []

    def capture(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.argv = list(argv)
        return subprocess.CompletedProcess(argv, self.status, self.stdout, "")


def test_read_runs_bashs_ffprobe_command(tmp_path: Path) -> None:
    source = tmp_path / "a:b.mp4"
    _ = source.write_bytes(b"x")
    runner = FakeRunner((FIXTURES / "h264_aac.mp4.json").read_text())
    assert read(str(source), runner).video is not None
    assert runner.argv == [
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", "--", f"file:{source}",
    ]  # fmt: skip


def test_read_refuses_as_bash(tmp_path: Path) -> None:
    with pytest.raises(FfmanError, match=r"^no such file: /nonexistent\.mp4$"):
        _ = read("/nonexistent.mp4", FakeRunner(""))
    source = tmp_path / "junk.mp4"
    _ = source.write_bytes(b"x")
    for runner in (FakeRunner("", status=1), FakeRunner("not json")):
        with pytest.raises(FfmanError) as error:
            _ = read(str(source), runner)
        assert str(error.value) == f"ffprobe cannot read: {source}"


@pytest.mark.parametrize(
    ("text", "sep", "parsed"),
    [
        ("30000/1001", "/", Rational(30000, 1001)),
        ("32:27", ":", Rational(32, 27)),
        ("0/0", "/", Rational(0, 0)),  # unknown: kept, not None
        ("50/-1", "/", Rational(50, -1)),  # %d prints a sign
        ("01/25", "/", None),  # %d prints no leading zero
        ("-0/1", "/", None),  # nor -0
        ("1:1", "/", None),  # the other separator
        ("25", "/", None),
        ("N/A", "/", None),
        ("", "/", None),
        (None, "/", None),
    ],
)
def test_a_ratio_is_ffprobes_text_exactly(
    text: str | None, sep: Literal["/", ":"], parsed: Rational | None
) -> None:
    """%d{sep}%d (avtext_print_rational, n8.1.2): its language, and nothing else."""
    assert Rational.parse(text, sep) == parsed


def test_a_ratios_text_is_as_printed() -> None:
    assert (Rational(2, 50).text(), Rational(0, 0).text()) == ("2/50", "0/0")  # not reduced


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ("1.000000", Fraction(1)),  # ffprobe's %f
        ("0.040000", Fraction(1, 25)),
        ("-0.500000", Fraction(-1, 2)),
        ("16", Fraction(16)),  # any decimal, as awk read it
        ("1e3", None),
        ("N/A", None),
        (".5", None),
    ],
)
def test_a_duration_is_any_decimal_exactly(duration: str, seconds: Fraction | None) -> None:
    assert parse(json.dumps({"format": {"duration": duration}})).duration == seconds


@pytest.mark.parametrize(
    ("rate", "hz"), [("48000", 48000), ("0", 0), ("048000", None), ("-1", None), ("4.8e4", None)]
)
def test_a_sample_rate_is_ffprobes_unsigned_integer(rate: str, hz: int | None) -> None:
    stream = {"codec_type": "audio", "sample_rate": rate}
    audio = parse(json.dumps({"streams": [stream]})).audio
    assert audio is not None
    assert audio.sample_rate == hz


def test_a_frame_time_from_the_rate_its_frames_come_at() -> None:
    """The average rate; ffprobe's 0/0 for it, the base rate; neither known, none."""
    v = video("h264_aac.mp4")
    ntsc = replace(v, avg_frame_rate=Rational(30000, 1001))
    assert ntsc.frame_time() == Fraction(1001, 30000)  # exactly: 33.3667 ms
    unset = replace(v, avg_frame_rate=Rational(0, 0), r_frame_rate=Rational(25, 1))
    assert (unset.frame_rate(), unset.frame_time()) == (Rational(25, 1), Fraction(1, 25))
    assert replace(v, avg_frame_rate=None, r_frame_rate=None).frame_time() is None
    assert (
        replace(v, avg_frame_rate=Rational(0, 0), r_frame_rate=Rational(0, 0)).frame_time() is None
    )


def test_covers_are_read_apart_from_the_pictures() -> None:
    m = media("cover_art.m4a")
    assert (len(m.covers), m.pictures) == (1, 0)  # recorded: a cover, no other picture


def test_format_tag_names_are_lower_cased_none_where_not_ffprobes_shape() -> None:
    assert tag_names('{"format": {"tags": {"TITLE": "x", "Artist": "y"}}}') == {"title", "artist"}
    assert tag_names('{"format": {}}') == frozenset()  # tagless
    assert tag_names("{}") == frozenset()
    assert tag_names("[]") is None
    assert tag_names('{"format": null}') is None
    assert tag_names('{"format": {"tags": ["title"]}}') is None
