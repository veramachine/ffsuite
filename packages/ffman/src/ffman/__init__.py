"""ffman: opinionated media conversion on ffmpeg."""

import tomllib
from importlib.metadata import PackageNotFoundError, metadata
from pathlib import Path
from typing import Final, cast

_ROOT: Final = Path(__file__).parents[2]  # in a source tree: the project, pyproject.toml beside src


def about(root: Path = _ROOT) -> tuple[str, str]:
    """The version and summary: the installed package's metadata, else pyproject.toml's.

    Both come from pyproject.toml; installing writes them into the metadata. A
    source tree run as is (the equivalence harness: PYTHONPATH=src) has no
    metadata, and its pyproject.toml is ``root``, beside src.
    """
    try:
        found = metadata("ffman")
    except PackageNotFoundError:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text())
        project = cast("dict[str, str]", pyproject["project"])
        return project["version"], project["description"]
    return found["Version"], found["Summary"]


__version__, __summary__ = about()
