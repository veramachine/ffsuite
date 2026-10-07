import shutil
from pathlib import Path
from typing import Final

import pytest
from hypothesis import settings

from tests.support.media import CD_SECONDS, tool

# Reproducible everywhere, the Nix sandbox included: the same examples each run,
# and no example database. Hypothesis still caches the constants it reads from the
# source in .hypothesis/ (derived, deterministic; ignored by git).
settings.register_profile("ffman", derandomize=True, database=None)
settings.load_profile("ffman")

# The pinned tools' fixtures: a test taking one (ffprobe's takes ffmpeg's) is marked ``ffmpeg``
# however it asks, so ``-m "not ffmpeg"`` leaves no test needing a pin -- CI's checks.yml, where
# a runner's own ffmpeg would fail the pin's check rather than skip.
_PINNED: Final = frozenset({"ffmpeg", "metaflac"})


@pytest.hookimpl(tryfirst=True)  # before -m deselects
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark ``ffmpeg`` each test taking a pinned tool's fixture, directly or through another."""
    for item in items:
        if isinstance(item, pytest.Function) and _PINNED.intersection(item.fixturenames):
            item.add_marker(pytest.mark.ffmpeg)


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    """The ffmpeg on PATH, which must be the pin: these tests make claims about ffmpeg 8.1."""
    found = shutil.which("ffmpeg")
    if found is None:
        pytest.skip("no ffmpeg")
    version = tool(found, "-version")  # the ffmpeg on PATH, checked below
    assert version.startswith("ffmpeg version 8.1."), "the pin is ffmpeg 8.1.2"
    return found


@pytest.fixture(scope="session")
def ffprobe(ffmpeg: str) -> str:
    """The ffprobe beside the pinned ffmpeg."""
    return str(Path(ffmpeg).with_name("ffprobe"))


@pytest.fixture(scope="session")
def metaflac() -> str:
    """The metaflac on PATH, which must be the pin: these tests make claims about FLAC 1.5."""
    found = shutil.which("metaflac")
    if found is None:
        pytest.skip("no metaflac")
    version = tool(found, "--version")  # the metaflac on PATH, checked below
    assert version.startswith("metaflac 1.5."), "the pin is FLAC 1.5.0"
    return found


@pytest.fixture(scope="session")
def cd_flac(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A CD-DA FLAC (stereo, 16-bit, 44.1 kHz) of CD_SECONDS, silent: to carry comments and cue sheets.

    metaflac's CD rules apply to it; silence is some 100 kB, where a tone is 7 MB.
    """
    path = tmp_path_factory.mktemp("cd") / "cd.flac"
    silence = ("-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(CD_SECONDS))
    _ = tool(ffmpeg, "-v", "error", *silence, "-sample_fmt", "s16", "-c:a", "flac", str(path))
    return path
