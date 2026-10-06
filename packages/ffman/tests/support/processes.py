"""Live processes by their command lines, as ``ps`` lists them: one reading on Linux and macOS.

``ps -A -ww -o pid= -o args=`` -- procps' and macOS's alike (nixpkgs' ``unixtools.ps``): every
process, its arguments joined by spaces, unabridged. A zombie keeps no arguments (procps:
``[sleep] <defunct>``; macOS: ``<defunct>``), so no marker matches it.
"""

import subprocess
from typing import Final

_PS: Final = ("ps", "-A", "-ww", "-o", "pid=", "-o", "args=")


def command_lines() -> dict[int, str]:
    """Each process's command line, by its pid."""
    listed = subprocess.run(_PS, capture_output=True, text=True, check=True).stdout  # noqa: S603 -- ps from PATH
    found: dict[int, str] = {}
    for line in listed.splitlines():
        pid, _, args = line.strip().partition(" ")
        found[int(pid)] = args.strip()
    return found


def marked(marker: str, *, program: str = "") -> list[int]:
    """The processes whose command line carries ``marker`` (and starts with ``program``)."""
    return sorted(
        pid for pid, args in command_lines().items() if marker in args and args.startswith(program)
    )
