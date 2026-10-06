"""One outcome case: ``ffman ARGS`` as ``python -m ffman`` runs it, its work files kept.

Run as ``python driver.py CAPTURE -- ARGS`` with a commit's ``src`` on
PYTHONPATH and TMPDIR set by the report. It imports nothing of ffman's or of
the tests': its one hook is Python's audit event ``shutil.rmtree``, which fires
however ffman removes its work directory -- so one driver runs any commit. A
work directory (``ffman.*`` in TMPDIR) is copied to CAPTURE as it goes. A copy
that fails is kept from ffman (it would read as ffman's own error) and ends the
driver with FAILED, after ffman: the report refuses the case.
"""

import os
import runpy
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

FAILED: Final = 125  # the driver's own failure: ffman exits 0, 1, 120 or 128+N
MARK: Final = "outcome driver: capture failed:"


def _keeper(
    tmpdir: Path, capture: Path, failures: list[str]
) -> Callable[[str, tuple[object, ...]], None]:
    def hook(event: str, args: tuple[object, ...]) -> None:
        if (
            event != "shutil.rmtree"
            or not args
            or not isinstance(args[0], str | bytes | os.PathLike)
        ):
            return
        path = Path(os.fsdecode(args[0]))
        if path.parent == tmpdir and path.name.startswith("ffman.") and path.is_dir():
            try:
                _ = shutil.copytree(path, capture / path.name, symlinks=True)
            except OSError as error:  # shutil.Error is one
                failures.append(f"{path}: {error}")

    return hook


def main() -> None:
    """Install the hook, then hand the process to ffman."""
    if len(sys.argv) < 3 or sys.argv[2] != "--":
        sys.exit("usage: driver.py CAPTURE -- ARGS")
    capture, args = sys.argv[1], sys.argv[3:]
    if not os.environ.get("TMPDIR"):
        sys.exit("driver: TMPDIR must name the report's work directory")
    tmpdir = Path(os.environ["TMPDIR"])
    failures: list[str] = []
    sys.addaudithook(_keeper(tmpdir, Path(capture), failures))
    sys.argv = ["ffman", *args]
    try:
        _ = runpy.run_module("ffman", run_name="__main__", alter_sys=True)
    finally:
        if failures:  # written unbuffered: os._exit flushes nothing
            _ = os.write(2, f"{MARK} {'; '.join(failures)}\n".encode())
            os._exit(FAILED)  # past ffman's own SystemExit


if __name__ == "__main__":
    main()
