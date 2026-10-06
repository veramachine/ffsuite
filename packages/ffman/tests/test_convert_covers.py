"""Cover art (spec 3.15): kept where held, attached into Matroska, noted elsewhere."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ffman.cli import main
from ffman.jobs.convert import covers, output
from ffman.media.probe import Cover, Media
from ffman.media.run import Runner
from tests.support.media import tool


@pytest.fixture(scope="module")
def covered(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A second of AAC in M4A, a PNG cover attached_pic; and the PNG itself."""
    folder = tmp_path_factory.mktemp("cover")
    png = folder / "cover.png"
    _ = tool(
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=red:s=32x32", "-frames:v", "1", str(png)
    )
    path = folder / "src.m4a"
    lavfi = ["-f", "lavfi", "-i", "sine=d=1", "-i", str(png), "-map", "0", "-map", "1"]
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        *lavfi,
        "-c:a",
        "aac",
        "-c:v",
        "copy",
        "-disposition:v:0",
        "attached_pic",
        str(path),
    )
    return path, png


def streams(ffprobe: str, path: Path) -> list[str]:
    shown = tool(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name:stream_disposition=attached_pic:stream_tags=filename",
        "-of",
        "csv=p=0",
        str(path),
    )
    return shown.split()


@pytest.mark.parametrize(
    ("ext", "codec", "kept", "note"),
    [
        ("flac", "flac", ["flac,0", "png,1"], None),
        ("mp3", "mp3", ["mp3,0", "png,1"], None),
        ("mp4", "copy", ["aac,0", "png,1"], None),
        ("mka", "copy", ["aac,0", "png,1,cover.png"], None),  # attached, as Matroska's cover art
        (
            "mov",
            "copy",
            ["aac,0"],
            "ffman: the cover (png): a .mov drops it, its muxer silent: left out",
        ),
        ("ogg", "vorbis", ["vorbis,0"], "ffman: the cover (png): a .ogg holds none: left out"),
    ],
)
def test_a_cover_as_each_output_keeps_one(
    capsys: pytest.CaptureFixture[str],
    covered: tuple[Path, Path],
    ffprobe: str,
    tmp_path: Path,
    ext: str,
    codec: str,
    kept: list[str],
    note: str | None,
) -> None:
    out = tmp_path / f"o.{ext}"
    assert main(["convert", "-i", str(covered[0]), "-o", str(out), "--audio-codec", codec]) == 0
    notes = [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("ffman: the cover")
    ]
    assert (notes, streams(ffprobe, out)) == ([note] if note else [], kept)


def test_matroskas_cover_byte_exact_and_back(
    capsys: pytest.CaptureFixture[str],
    covered: tuple[Path, Path],
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
) -> None:
    mka, back, png = tmp_path / "o.mka", tmp_path / "back.m4a", tmp_path / "got.png"
    assert main(["convert", "-i", str(covered[0]), "-o", str(mka)]) == 0
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(mka),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-frames:v",
        "1",
        "-f",
        "image2",
        str(png),
    )
    assert png.read_bytes() == covered[1].read_bytes()  # extracted and attached byte-exact
    assert (
        main(["convert", "-i", str(mka), "-o", str(back)]) == 0
    )  # ffmpeg reads cover.png as a cover
    _ = capsys.readouterr()
    assert streams(ffprobe, back) == ["aac,0", "png,1"]


def test_what_a_cover_cannot_be_is_noted(monkeypatch: pytest.MonkeyPatch) -> None:
    two = Media(None, None, (), (), None, None, covers=(Cover(0, "bmp"), Cover(1, "png")))
    with Runner(dry_run=False, cores=1) as runner:
        done = covers.kept(runner, two, "mkv", covers.Job("in.mka", ()))
    assert done == output.Kept(
        (),
        (
            "the cover: one kept, not two: left out",
            "the cover (bmp): Matroska's covers are JPEG or PNG: left out",
        ),
    )

    def silent(_self: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(argv), 0, "", "")  # as ffmpeg, but no file

    monkeypatch.setattr(Runner, "capture", silent)
    one = Media(None, None, (), (), None, None, covers=(Cover(0, "png"),))
    with Runner(dry_run=False, cores=1) as runner:
        done = covers.kept(runner, one, "mkv", covers.Job("in.mka", ()))
    assert done.notes == ("the cover (png): ffmpeg extracted none: left out",)


@pytest.mark.parametrize(
    ("size", "picture", "name"),
    [
        ("64x32", "png", "cover_land.png"),
        ("32x64", "png", "cover.png"),
        ("32x32", "png", "cover.png"),
        ("96x48", "jpg", "cover_land.jpg"),  # JPEG: Matroska's other cover format, image/jpeg
    ],
)
def test_matroskas_cover_named_by_its_orientation(
    capsys: pytest.CaptureFixture[str],
    ffmpeg: str,
    ffprobe: str,
    tmp_path: Path,
    size: str,
    picture: str,
    name: str,
) -> None:
    image, source, out, back = (
        tmp_path / f"c.{picture}",
        tmp_path / "s.m4a",
        tmp_path / "o.mka",
        tmp_path / "back.m4a",
    )
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=blue:s={size}",
        "-frames:v",
        "1",
        str(image),
    )
    lavfi = ["-f", "lavfi", "-i", "sine=d=1", "-i", str(image), "-map", "0", "-map", "1"]
    _ = tool(
        ffmpeg,
        "-v",
        "error",
        *lavfi,
        "-c:a",
        "aac",
        "-c:v",
        "copy",
        "-disposition:v:0",
        "attached_pic",
        str(source),
    )
    assert main(["convert", "-i", str(source), "-o", str(out)]) == 0
    assert (
        main(["convert", "-i", str(out), "-o", str(back)]) == 0
    )  # read back as a cover, whatever its name
    _ = capsys.readouterr()
    codec = {"png": "png", "jpg": "mjpeg"}[picture]
    assert (
        streams(ffprobe, out)[-1] == f"{codec},1,{name}"
    )  # Matroska's names: _land wider than tall
    assert streams(ffprobe, back) == ["aac,0", f"{codec},1"]


def test_add_subs_places_the_cover_as_every_flow(
    capsys: pytest.CaptureFixture[str], covered: tuple[Path, Path], ffprobe: str, tmp_path: Path
) -> None:
    srt, out = tmp_path / "s.srt", tmp_path / "o.mka"
    _ = srt.write_text("1\n00:00:00,100 --> 00:00:00,900\nhi\n")
    assert main(["convert", "-i", str(covered[0]), "-o", str(out), "--add-subs", str(srt)]) == 0
    _ = capsys.readouterr()
    assert streams(ffprobe, out) == [
        "aac,0",
        "subrip,0",
        "png,1,cover.png",
    ]  # attached (3.15), not a track
