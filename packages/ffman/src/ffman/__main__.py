"""ffman's entry: the ``ffman`` command (pyproject's scripts) and ``python -m ffman``.

ffman runs its tools as POSIX does -- process groups, SIGHUP (``media/run.py``) -- so on
Windows its command line cannot even be imported: the platform is checked first, the command
line imported after.
"""

import sys
from typing import Final

from ffman.errors import PROG

WINDOWS: Final = f"{PROG}: error: ffman runs on Linux and macOS; on Windows, run it in WSL\n"


def main() -> int:
    """The exit status: refused on Windows, else the command line's."""
    if sys.platform == "win32":
        _ = sys.stderr.write(WINDOWS)
        return 1
    from ffman.cli import main as command_line  # noqa: PLC0415 -- after the check, as above

    return command_line()


if __name__ == "__main__":
    sys.exit(main())
