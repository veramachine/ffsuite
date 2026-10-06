"""The folders ffman carries: its presets in the package, and any folder copied out of a zip."""

import json
import zipfile
from importlib import resources
from pathlib import Path
from typing import cast

import pytest

from ffman.jobs.convert.carried import own_folder
from ffman.media.run import Runner


def _preset(name: str) -> dict[str, object]:
    # an XDG_CONFIG_HOME, as ffmpeg-normalize reads one: ffmpeg-normalize/presets/NAME.json
    found = resources.files("ffman") / "normalize" / "ffmpeg-normalize" / "presets" / f"{name}.json"
    return cast("dict[str, object]", json.loads(found.read_text(encoding="utf-8")))


def test_the_presets_youtube_picks_are_carried() -> None:
    # plan.youtube_sound's two: FDK's, and the native twin for an ffmpeg without it
    fdk, native = _preset("youtube-aac"), _preset("youtube-aac-native")
    assert fdk["audio-codec"] == "libfdk_aac"
    assert native == {**fdk, "audio-codec": "aac"}  # the one difference


def test_unzipped_the_folder_is_itself() -> None:
    with Runner(dry_run=True) as runner:
        assert own_folder(runner, "normalize") == str(resources.files("ffman") / "normalize")


def test_a_folder_held_in_a_zip_is_copied_whole(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    held = tmp_path / "ffman.zip"
    with zipfile.ZipFile(held, "w") as archive:
        archive.writestr("ffman/normalize/ffmpeg-normalize/presets/p.json", "{}\n")
        archive.writestr("ffman/normalize/top.txt", "t")

    def files(_package: str) -> zipfile.Path:
        return zipfile.Path(held, "ffman/")

    monkeypatch.setattr(resources, "files", files)  # the module carried asks: the same object
    with Runner(dry_run=False) as runner:
        folder = Path(own_folder(runner, "normalize"))
        assert folder == runner.workdir / "normalize"
        copied = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
        assert copied == [
            "ffmpeg-normalize",
            "ffmpeg-normalize/presets",
            "ffmpeg-normalize/presets/p.json",
            "top.txt",
        ]
        assert (folder / "ffmpeg-normalize/presets/p.json").read_text() == "{}\n"
