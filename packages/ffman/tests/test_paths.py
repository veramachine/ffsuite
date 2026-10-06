import os
import stat
import subprocess
from pathlib import Path

import pytest

from ffman.errors import FfmanError
from ffman.media.paths import ext_of, file_url, partial_output, resolve_output, same_file


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith(".ffman."))


@pytest.mark.parametrize(
    ("name", "ext"),
    [
        ("in.mp4", "mp4"),
        ("IN.MP4", "mp4"),
        ("a.b.MKV", "mkv"),
        (".hidden", "hidden"),
        ("file.", ""),
        ("noext", ""),
        ("dir.d/noext", ""),
    ],
)
def test_ext_of_is_bashs(name: str, ext: str) -> None:
    assert ext_of(name) == ext


@pytest.mark.parametrize(
    ("given", "default_ext", "expected"),
    [
        ("dir/in.MP4", None, "dir/in.ffman.mp4"),
        ("in.mp4", None, "in.ffman.mp4"),
        ("a.b.mkv", None, "a.b.ffman.mkv"),
        ("x.mov", "mp4", "x.ffman.mp4"),
        ("/abs.mp4", None, "/abs.ffman.mp4"),
    ],
)
def test_default_name(given: str, default_ext: str | None, expected: str) -> None:
    assert resolve_output(
        given, None, in_place=False, overwrite=False, default_ext=default_ext
    ) == Path(expected)


@pytest.mark.parametrize(("given", "output"), [("in.mp4", "out"), ("noext", None)])
def test_output_needs_an_extension(given: str, output: str | None) -> None:
    shown = output or "noext.ffman."
    with pytest.raises(
        FfmanError, match=rf"^output needs an extension \(it selects the container\): {shown}$"
    ):
        _ = resolve_output(given, output, in_place=False, overwrite=False)


def test_existing_output_needs_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    _ = out.write_bytes(b"x")
    with pytest.raises(FfmanError) as error:
        _ = resolve_output("in.mp4", str(out), in_place=False, overwrite=False)
    assert str(error.value) == f"output exists: {out} (use --overwrite to replace it)"
    assert resolve_output("in.mp4", str(out), in_place=False, overwrite=True) == out


def test_the_input_only_with_in_place(tmp_path: Path) -> None:
    real = tmp_path / "a.mp4"
    _ = real.write_bytes(b"x")
    link = tmp_path / "link.mp4"
    link.symlink_to(real)
    assert same_file(str(link), str(real))
    with pytest.raises(FfmanError) as error:
        _ = resolve_output(str(link), str(real), in_place=False, overwrite=True)
    assert str(error.value) == f"the output is the input: use --in-place to replace it: {real}"
    # in place, through the link: the target is replaced, not the link
    assert resolve_output(str(link), None, in_place=True, overwrite=False) == real


def test_partial_becomes_the_new_output_with_the_umask(tmp_path: Path) -> None:
    target = tmp_path / "new" / "deep" / "out.mp4"
    with partial_output(target) as partial:
        assert partial.parent == target.parent
        assert partial.name.startswith(".ffman.")
        assert partial.name.endswith(".mp4")
        _ = partial.write_bytes(b"data")
    mask = os.umask(0)
    _ = os.umask(mask)
    assert target.read_bytes() == b"data"
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~mask
    assert leftovers(target.parent) == []


def test_partial_takes_the_replaced_files_permissions(tmp_path: Path) -> None:
    target = tmp_path / "out.mkv"
    _ = target.write_bytes(b"old")
    target.chmod(0o640)
    with partial_output(target) as partial:
        _ = partial.write_bytes(b"new")
    assert target.read_bytes() == b"new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_an_empty_partial_is_refused_and_leaves_nothing(tmp_path: Path) -> None:
    target = tmp_path / "out.mp4"
    _ = target.write_bytes(b"old")
    with pytest.raises(FfmanError, match=r"^ffmpeg produced no output$"), partial_output(target):
        pass
    assert target.read_bytes() == b"old"
    assert leftovers(tmp_path) == []


class MidwayError(Exception):
    pass


def write_half_then_fail(target: Path) -> None:
    with partial_output(target) as partial:
        _ = partial.write_bytes(b"half")
        raise MidwayError


def test_a_failure_removes_the_partial_and_keeps_the_target(tmp_path: Path) -> None:
    target = tmp_path / "out.mp4"
    _ = target.write_bytes(b"old")
    with pytest.raises(MidwayError):
        write_half_then_fail(target)
    assert target.read_bytes() == b"old"
    assert leftovers(tmp_path) == []


def test_in_place_needs_an_extension_too(tmp_path: Path) -> None:
    source = tmp_path / "noext"
    _ = source.write_bytes(b"x")
    with pytest.raises(FfmanError) as error:
        _ = resolve_output(str(source), None, in_place=True, overwrite=False)
    assert str(error.value) == f"output needs an extension (it selects the container): {source}"


def test_a_file_url_is_the_path_behind_file() -> None:
    assert file_url("a:b.mp4") == "file:a:b.mp4"
    assert file_url(Path("/w/ffman.x/mosh.mkv")) == "file:/w/ffman.x/mosh.mkv"


@pytest.mark.ffmpeg
def test_ffmpeg_reads_a_colon_name_as_a_protocol_but_for_file(
    ffmpeg: str, ffprobe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why file_url: ``a:b.mp4`` is protocol ``a`` to ffmpeg 8.1; ``file:`` opens it."""
    monkeypatch.chdir(tmp_path)
    make = [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=d=0.1", "-frames:v", "1"]
    _ = subprocess.run([*make, "file:a:b.png"], check=True)  # noqa: S603 -- ffmpeg
    probe = [ffprobe, "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0"]
    bare = subprocess.run([*probe, "a:b.png"], capture_output=True, text=True, check=False)  # noqa: S603 -- ffprobe
    opened = [*probe, file_url("a:b.png")]
    prefixed = subprocess.run(opened, capture_output=True, text=True, check=True)  # noqa: S603 -- ffprobe
    assert bare.returncode != 0
    assert "Protocol not found" in bare.stderr
    assert prefixed.stdout.strip() == "png"
