"""ffman's own font (6.7.3): FFMAN_FONTS_DIR, else the package's copy, else one written safe."""

import hashlib
from fractions import Fraction
from importlib import resources
from pathlib import Path
from typing import Final

import pytest

from ffman.cli import main
from ffman.effects.camcorder import STAMP_FILE, STAMP_FONT, script
from ffman.errors import FfmanError
from ffman.jobs.convert import fonts
from ffman.media.run import Runner
from ffman.subs.ass import FONT, FONT_FILES
from tests.support.media import tool

OWN = Path(str(resources.files("ffman") / "fonts"))


def test_the_variable_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in FONT_FILES.values():
        _ = (tmp_path / name).write_bytes(b"x")
    monkeypatch.setenv("FFMAN_FONTS_DIR", str(tmp_path))
    with Runner(dry_run=True) as runner:
        assert fonts.fonts_dir(runner, FONT) == str(tmp_path)


def test_a_variable_the_filters_split_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FFMAN_FONTS_DIR", "/fonts:here")
    with (
        Runner(dry_run=True) as runner,
        pytest.raises(FfmanError, match=r"^FFMAN_FONTS_DIR has characters"),
    ):
        _ = fonts.fonts_dir(runner, FONT)


def test_unset_ffmans_own(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FFMAN_FONTS_DIR", raising=False)
    with Runner(dry_run=True) as runner:
        assert fonts.fonts_dir(runner, FONT) == str(OWN)
    assert capsys.readouterr().err == ""  # both fonts there: nothing to say
    assert sorted(p.name for p in OWN.glob("*.otf")) == sorted([*FONT_FILES.values(), STAMP_FILE])


def test_a_copy_the_filters_split_is_written_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = (
        tmp_path / "My Projects" / "ffman"
    )  # installed under a spaced folder: the filters split it
    (package / "fonts").mkdir(parents=True)
    for name in (*FONT_FILES.values(), STAMP_FILE):
        _ = (package / "fonts" / name).write_bytes((OWN / name).read_bytes())
    monkeypatch.delenv("FFMAN_FONTS_DIR", raising=False)

    def files(_package: str) -> Path:
        return package

    monkeypatch.setattr(resources, "files", files)  # the module fonts asks: the same object
    with Runner(dry_run=False) as runner:
        folder = Path(fonts.fonts_dir(runner, FONT))
        assert folder.parent == runner.workdir  # the work directory's path: safe
        for name in (*FONT_FILES.values(), STAMP_FILE):
            assert (folder / name).read_bytes() == (OWN / name).read_bytes()


def test_a_folder_without_the_font_noted_once_a_job(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FFMAN_FONTS_DIR", str(tmp_path))  # empty
    said = f"ffman: IBM Plex Sans not in {tmp_path}: the system's font in its place, line widths estimated\n"
    with Runner(dry_run=True) as runner:
        assert (
            fonts.fonts_dir(runner, FONT) == fonts.fonts_dir(runner, FONT) == str(tmp_path)
        )  # a burn and the camcorder
    assert capsys.readouterr().err == said  # once
    with Runner(dry_run=True) as runner:
        _ = fonts.fonts_dir(runner, FONT)
    assert capsys.readouterr().err == said  # a new job: told again


def test_the_camcorder_refuses_a_split_folder_as_a_burn_does(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, ffmpeg: str, tmp_path: Path
) -> None:
    source = tmp_path / "v.mp4"
    lavfi = [
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=1:s=64x48:r=25",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ]
    _ = tool(ffmpeg, "-v", "error", *lavfi, str(source))
    monkeypatch.setenv("FFMAN_FONTS_DIR", "/fonts:here")  # its stamp once read this unchecked
    out = tmp_path / "o.mp4"
    assert (
        main(["convert", "-i", str(source), "--vfx", "camcorder", "-o", str(out), "--dry-run"]) == 1
    )
    said = "ffman: error: FFMAN_FONTS_DIR has characters ffmpeg's filter syntax would split on: /fonts:here\n"
    assert capsys.readouterr().err == said


def test_a_copy_missing_a_weight_is_noted_not_fatal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "My Projects" / "ffman"
    (package / "fonts").mkdir(parents=True)
    regular = FONT_FILES[False]
    _ = (package / "fonts" / regular).write_bytes((OWN / regular).read_bytes())  # the bold lost

    def files(_package: str) -> Path:
        return package

    monkeypatch.delenv("FFMAN_FONTS_DIR", raising=False)
    monkeypatch.setattr(resources, "files", files)
    with Runner(dry_run=False) as runner:
        folder = Path(fonts.fonts_dir(runner, FONT))
        assert sorted(p.name for p in folder.iterdir()) == [regular]  # what there was, copied
    said = f"ffman: IBM Plex Sans not in {folder}: the system's font in its place, line widths estimated\n"
    assert capsys.readouterr().err == said


RELEASE: Final = {  # IBM Plex 1.1.0's, as nixpkgs' ibm-plex fetches it (its fetchzip hash reproduced)
    "IBMPlexSans-Regular.otf": "6b17a35a31ded2e81b3ed19e5eb532d22b9a0b5a76833b0d757a5c71ab5e0f6c",
    "IBMPlexSans-Bold.otf": "19de5aec74215119b3f8f7d1b1f0e0eba867bee2d2c65c5761b287d67581c316",
    "IBMPlexMono-Bold.otf": "44f6da8e1146b28809182fe2a7a91a987a792ac294836ae1eeece09eaf35a6c7",  # the stamp's
    "OFL.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",  # its LICENSE.txt
}


def test_the_bundled_files_are_the_releases_unmodified() -> None:
    # the OFL's Reserved Font Name forbids a modified copy, and the rendering rests on these bytes
    held = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in OWN.iterdir()}
    assert held == RELEASE


@pytest.mark.parametrize("family", ["DejaVu Sans", "Liberation Serif"])  # --font's: fontconfig's
def test_another_family_missing_plex_is_not_told(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, family: str
) -> None:
    monkeypatch.setenv("FFMAN_FONTS_DIR", str(tmp_path))  # empty: no Plex Sans
    with Runner(dry_run=True) as runner:
        assert fonts.fonts_dir(runner, family) == str(tmp_path)
        assert (
            capsys.readouterr().err == ""
        )  # fontconfig's either way: nothing missing it draws with
        _ = fonts.fonts_dir(runner, "ibm plex sans")  # the burn's, in libass's case-blind compare
    assert capsys.readouterr().err.startswith("ffman: IBM Plex Sans not in ")


def test_the_stamp_font_is_the_scripts() -> None:
    assert f"Style: Cam,{STAMP_FONT}," in script(1577934245, Fraction(1), 64)  # its Style names it


def test_the_camcorder_tells_of_plex_mono_alone(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, ffmpeg: str, tmp_path: Path
) -> None:
    source = tmp_path / "v.mp4"
    lavfi = [
        "-f",
        "lavfi",
        "-i",
        "testsrc=d=1:s=64x48:r=25",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ]
    _ = tool(ffmpeg, "-v", "error", *lavfi, str(source))
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("FFMAN_FONTS_DIR", str(empty))
    assert (
        main(
            [
                "convert",
                "-i",
                str(source),
                "--vfx",
                "camcorder",
                "-o",
                str(tmp_path / "o.mp4"),
                "--dry-run",
            ]
        )
        == 0
    )
    said = f"ffman: IBM Plex Mono not in {empty}: the system's font in its place\n"
    assert capsys.readouterr().err == said  # its stamp's family, once; never Plex Sans
