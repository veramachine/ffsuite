"""A remux (spec 3.11): another container, a codec, a metadata file -- what the output holds
asked of ffmpeg before any work."""

from pathlib import Path

import pytest

from ffman.cli import main
from ffman.errors import FfmanError
from ffman.jobs.convert import output
from ffman.jobs.convert.options import validate
from ffman.media.probe import read
from ffman.media.run import Runner
from ffman.options import CONVERT, parse
from ffman.plan.flows import Flow, select_flow
from tests.support.media import tool


@pytest.mark.parametrize(
    ("argv", "flow"),
    [
        (["-o", "a.mp4"], Flow.REMUX),  # another container
        (["-o", "a.mov"], Flow.REMUX),  # the same family, another muxer
        (["--audio-codec", "flac"], Flow.REMUX),  # a codec
        (["--video-codec", "ffv1"], Flow.REMUX),
        (["--lossless"], Flow.REMUX),
        (["--metadata", "m.ffmeta"], Flow.REMUX),
        (["-o", "a.mp4", "-w", "32"], Flow.PICTURE),  # a size: the picture's
    ],
)
def test_what_a_remux_is(argv: list[str], flow: Flow) -> None:
    assert select_flow(validate(parse("convert", CONVERT, ["-i", "a.webm", *argv]))) is flow


@pytest.fixture(scope="module")
def sources(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A second of H.264 and AAC in MP4, and of VP9 and Opus in WebM."""
    folder = tmp_path_factory.mktemp("remux")
    lavfi = ["-f", "lavfi", "-i", "testsrc=d=1:s=64x48", "-f", "lavfi", "-i", "sine=d=1"]
    made = {"mp4": ("libx264", "aac"), "webm": ("libvpx-vp9", "libopus")}
    for ext, (video, audio) in made.items():
        _ = tool(
            ffmpeg, "-v", "error", *lavfi, "-c:v", video, "-c:a", audio, str(folder / f"s.{ext}")
        )
    return {ext: folder / f"s.{ext}" for ext in made}


def codecs(ffprobe: str, path: Path) -> list[str]:
    return tool(
        ffprobe, "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)
    ).split()


def convert(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    status = main(["convert", *argv])
    return status, capsys.readouterr().err


def test_another_container_copies(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.mp4"
    assert convert(capsys, "-i", str(sources["webm"]), "-o", str(out))[0] == 0
    assert codecs(ffprobe, out) == ["vp9", "opus"]  # nothing encoded again


def test_a_codec_alone_encodes_that_kind(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.mp4"
    assert (
        convert(capsys, "-i", str(sources["mp4"]), "-o", str(out), "--audio-codec", "flac")[0] == 0
    )
    assert codecs(ffprobe, out) == ["h264", "flac"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ((), "a .webm holds no h264 video, the source's: --video-codec to give one it holds"),
        (
            ("--video-codec", "vp9"),
            "a .webm holds no aac audio, the source's: --audio-codec to give one it holds",
        ),
        (
            ("--video-codec", "h264", "--audio-codec", "opus"),
            "--video-codec h264: a .webm holds no h264",
        ),
        (
            ("-w", "32"),
            "a .webm holds no h264 video, the source's: --video-codec to give one it holds",
        ),  # the picture's too
        (
            ("--lossless",),  # no codec given: the source's, not --video-codec's
            "a .webm holds no h264 video, the source's: --video-codec to give one it holds",
        ),
    ],
)
def test_what_a_webm_cannot_hold_is_refused_before_any_work(
    capsys: pytest.CaptureFixture[str],
    sources: dict[str, Path],
    tmp_path: Path,
    argv: tuple[str, ...],
    message: str,
) -> None:
    out = tmp_path / "o.webm"
    assert convert(capsys, "-i", str(sources["mp4"]), "-o", str(out), *argv) == (
        1,
        f"ffman: error: {message}\n",
    )
    assert not out.exists()


def test_what_it_holds_once_asked(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.webm"
    assert (
        convert(
            capsys,
            "-i",
            str(sources["mp4"]),
            "-o",
            str(out),
            "--video-codec",
            "vp9",
            "--audio-codec",
            "opus",
        )[0]
        == 0
    )
    assert codecs(ffprobe, out) == ["vp9", "opus"]


def test_the_same_container_nothing_asked_is_nothing_to_do(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], tmp_path: Path
) -> None:
    status, err = convert(capsys, "-i", str(sources["mp4"]), "-o", str(tmp_path / "g.mp4"))
    assert (status, err.startswith("ffman: error: convert: nothing to do: give ")) == (
        1,
        True,
    )  # M066


def test_a_picture_made_anew_is_not_a_remux(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], tmp_path: Path
) -> None:
    status, err = convert(capsys, "-i", str(sources["mp4"]), "-o", str(tmp_path / "o.gif"))
    assert (status, err) == (
        1,
        "ffman: error: convert: a .gif is a picture made anew: give a size (-w, -H, -a) or an effect\n",
    )


def test_held_together_or_not_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    def holds(_runner: Runner, args: list[str], _ext: str) -> str | None:
        return "both at once" if "-c:v" in args and "-c:a" in args else None  # each alone: held

    monkeypatch.setattr(output, "holds", holds)
    kinds = (
        output.Held("video", ["-c:v", "copy"], "h264", asked=False),
        output.Held("audio", ["-c:a", "copy"], "aac", asked=False),
    )
    with (
        Runner(dry_run=True, cores=1) as runner,
        pytest.raises(FfmanError, match=r"^a \.x holds not these streams together: both at once$"),
    ):
        output.check_held(runner, "x", ["-i", "in"], kinds, [])


def test_no_picture_no_slices(ffmpeg: str, tmp_path: Path) -> None:
    flac = tmp_path / "a.flac"
    _ = tool(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=0.2", str(flac))
    with Runner(dry_run=False, cores=4) as runner:
        assert output.source_slices(runner, read(str(flac), runner)) is None


def test_into_its_own_container_copied_whole(
    capsys: pytest.CaptureFixture[str],
    sources: dict[str, Path],
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
) -> None:
    cover = tmp_path / "cover.png"
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=red:s=16x16",
        "-frames:v",
        "1",
        str(cover),
    )
    covered = tmp_path / "covered.mp4"
    maps = ["-map", "0", "-map", "1", "-c", "copy", "-disposition:v:1", "attached_pic"]
    _ = tool(
        ffmpeg, "-v", "error", "-i", str(sources["mp4"]), "-i", str(cover), *maps, str(covered)
    )
    tags = tmp_path / "m.ffmeta"
    _ = tags.write_text(";FFMETADATA1\ntitle=T\n")
    out = tmp_path / "o.mp4"
    assert convert(capsys, "-i", str(covered), "-o", str(out), "--metadata", str(tags))[0] == 0
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name:stream_disposition=attached_pic",
        "-of",
        "csv=p=0",
        str(out),
    )
    assert shown.split() == ["h264,0", "aac,0", "png,1"]  # the cover kept, as a plain copy keeps it


@pytest.fixture
def attached(sources: dict[str, Path], ffmpeg: str, tmp_path: Path) -> Path:
    """The MP4 source in Matroska, a font attached."""
    font = tmp_path / "font.ttf"
    _ = font.write_bytes(b"\x00\x01\x00\x00not a real font, an attachment's bytes")
    path = tmp_path / "attached.mkv"
    mime = ["-metadata:s:t:0", "mimetype=font/ttf"]
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(sources["mp4"]),
        "-attach",
        str(font),
        *mime,
        "-map",
        "0",
        "-c",
        "copy",
        str(path),
    )
    return path


def test_attachments_carried_within_one_family_noted_across(
    capsys: pytest.CaptureFixture[str], attached: Path, ffprobe: str, tmp_path: Path
) -> None:
    kept = tmp_path / "kept.mkv"
    assert convert(capsys, "-i", str(attached), "-o", str(kept), "--audio-codec", "flac")[0] == 0
    kinds = tool(
        ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(kept)
    ).split()
    assert kinds == ["video", "audio", "attachment"]  # within its family: carried
    status, err = convert(capsys, "-i", str(attached), "-o", str(tmp_path / "o.mp4"))
    assert (
        status,
        "ffman: attachments are not carried into .mp4 (another container family)\n" in err,
    ) == (0, True)


def test_add_subs_notes_attachments_too(
    capsys: pytest.CaptureFixture[str], attached: Path, tmp_path: Path
) -> None:
    srt = tmp_path / "s.srt"
    _ = srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nHi\n")
    status, err = convert(
        capsys, "-i", str(attached), "-o", str(tmp_path / "o.mp4"), "--add-subs", str(srt)
    )
    assert (
        status,
        "ffman: attachments are not carried into .mp4 (another container family)\n" in err,
    ) == (0, True)


def test_into_flac_the_picture_noted(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], ffprobe: str, tmp_path: Path
) -> None:
    out = tmp_path / "o.flac"
    status, err = convert(
        capsys, "-i", str(sources["mp4"]), "-o", str(out), "--audio-codec", "flac"
    )
    assert status == 0
    assert (
        "ffman: the picture (h264): a .flac holds covers alone: left out\n" in err
    )  # flacenc.c ignores it, silent
    assert tool(
        ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)
    ).split() == ["audio"]


def test_into_flac_a_picture_asked_is_refused(
    capsys: pytest.CaptureFixture[str], sources: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "o.flac"
    status, err = convert(
        capsys,
        "-i",
        str(sources["mp4"]),
        "-o",
        str(out),
        "--audio-codec",
        "flac",
        "--video-codec",
        "ffv1",
    )
    assert (status, out.exists()) == (1, False)  # asked for, not dropped: refused before any work
    assert "ffman: error: --video-codec ffv1: a .flac holds pictures as covers alone\n" in err
