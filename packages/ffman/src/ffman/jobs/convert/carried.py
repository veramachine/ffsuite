"""The folders ffman carries in its package -- its fonts, its presets -- as paths a tool reads.

Installed, each is a folder of the package; held in a zip, or at a path the tool cannot take,
it is copied whole into the job's work directory.
"""

from collections.abc import Callable
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from ffman.media.run import Runner


def own_folder(runner: Runner, name: str, usable: Callable[[str], bool] = lambda _: True) -> str:
    """The package's folder ``name``: itself, if a real path ``usable`` takes; else a copy."""
    own = resources.files("ffman") / name
    if isinstance(own, Path) and usable(str(own)):
        return str(own)
    copied = runner.workdir / name
    _copy(own, copied)
    return str(copied)


def _copy(tree: Traversable, into: Path) -> None:
    into.mkdir(exist_ok=True)
    for entry in tree.iterdir():
        if entry.is_dir():
            _copy(entry, into / entry.name)
        else:
            _ = (into / entry.name).write_bytes(entry.read_bytes())
