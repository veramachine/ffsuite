"""Running tools: children, signals, the work directory, thread arguments, --dry-run.

Stage A keeps the bash ffman's behaviour. Each tool runs in its own process
group with stdin from /dev/null, so a signal reaches ffman at once and ffman
stops the whole tree (ffmpeg-normalize runs its own ffmpeg): TERM, up to 3 s
of polling every 0.3 s, then KILL. SIGINT, SIGTERM and SIGHUP exit 130, 143,
129 after cleanup; the first one resets the handlers, so a second one acts at
once (bash's ``trap -``). Measured in bash: without this, SIGTERM to ffman left
ffmpeg encoding with nothing to clean up after it. The poll counts zombies:
an orphan of the tree waits for PID 1 to reap it (at once under systemd; 1.5 s
measured in a sandbox), bounded by the 3 s -- as bash's ``kill -0`` did.
"""

import contextlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from types import FrameType, TracebackType
from typing import Final, Self

from ffman.errors import PROG, refuse
from ffman.values import is_safe_path

SIGNALS: Final = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
_POLLS: Final = 10  # x 0.3 s: bash's wait for a stopped tool's group
_POLL_SECONDS: Final = 0.3
_NATIVE_ENCODER: Final = re.compile(r" -c:v (ffv1|mpeg4|png|mjpeg) ")
_AUTO_THREADS_CAP: Final = 16  # libavcodec's and libavutil's MAX_AUTO_THREADS
_TMP: Final = "/tmp"  # noqa: S108 -- the POSIX default, as mktemp's


def note(message: str) -> None:
    """Tell the user something on stderr, as bash's ``note``: ``ffman: MESSAGE``."""
    _ = sys.stderr.write(f"{PROG}: {message}\n")


class Interrupted(BaseException):
    """A signal arrived; ffman exits ``128 + signum`` once everything is cleaned up.

    A BaseException, not an Exception: nothing may swallow it on its way out.
    """

    def __init__(self, signum: int) -> None:
        """Remember the signal."""
        super().__init__(signum)
        self.status: int = 128 + signum


def install_signal_handlers() -> None:
    """Turn SIGINT, SIGTERM and SIGHUP into ``Interrupted``."""
    for sig in SIGNALS:
        _ = signal.signal(sig, _on_signal)


def _on_signal(signum: int, _frame: FrameType | None) -> None:
    for sig in SIGNALS:
        _ = signal.signal(sig, signal.SIG_DFL)
    raise Interrupted(signum)


def cores() -> int:
    """The processors to use, as ``nproc`` counts them; else as Python does, noted.

    Below 16 ffmpeg threads itself (``ffmpeg_args``): the count sets FFV1's slices past four, and
    ffmpeg's threads past its cap of 16.

    coreutils' own answer, not a copy: it honours OMP_NUM_THREADS (a minimum) and
    OMP_THREAD_LIMIT (a maximum), from coreutils 9.8 cgroup v2 CPU quotas, besides affinity.
    Without it (macOS ships none), ``os.process_cpu_count``: affinity alone, or
    PYTHON_CPU_COUNT; 1 if even that is unknown.
    """
    try:
        result = subprocess.run(["nproc"], capture_output=True, text=True, check=True)  # noqa: S607 -- PATH is the package's own
        return int(result.stdout)
    except FileNotFoundError:
        why = missing("nproc")
    except (OSError, subprocess.CalledProcessError, ValueError):
        why = "nproc gave no count"
    count = os.process_cpu_count() or 1
    note(f"{why}: {count} {'processor' if count == 1 else 'processors'}, as Python counts them")
    return count


def ffmpeg_args(args: Sequence[str], cores: int) -> list[str]:
    """``args`` with explicit thread counts where ffmpeg's own would cap (bash ``ffargs``).

    ffmpeg's auto counts stop at 16 (FFMIN(cpus + 1, MAX_AUTO_THREADS)); with 16 or
    more cores, cpus + 1 goes before each input, to the filter graphs, and to a native
    encoder (not libx264, whose own auto is 1.5x cores).
    """
    n = cores + 1
    if n <= _AUTO_THREADS_CAP:
        return list(args)
    out: list[str] = []
    for arg in args:
        if arg == "-i":
            out += ["-threads", str(n)]
        out.append(arg)
    if _NATIVE_ENCODER.search(f" {' '.join(args)} "):
        out[-1:-1] = ["-threads", str(n)]
    return ["-filter_threads", str(n), "-filter_complex_threads", str(n), *out]


class Runner:
    """Runs a job's tools; owns its work directory. Use as a context manager."""

    def __init__(self, *, dry_run: bool, cores: int | None = None) -> None:
        """A runner; ``dry_run`` prints the producing commands instead of running them."""
        self.dry_run: Final = dry_run
        self._cores: int | None = (
            cores  # None: counted on first use, so a job running no ffmpeg never asks
        )
        self._workdir: Path | None = None

    def __enter__(self) -> Self:
        """Start."""
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Remove the work directory, however the job ended."""
        if self._workdir is not None:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    @property
    def cores(self) -> int:
        """The processors ffmpeg is given: ``cores()``, counted on first use (its note then)."""
        if self._cores is None:
            self._cores = cores()
        return self._cores

    @property
    def workdir(self) -> Path:
        """The job's private directory, made on first use: ``$TMPDIR/ffman.*``, else /tmp.

        TMPDIR is used only if its path is filter-safe: files here go into ffmpeg
        filter arguments.
        """
        if self._workdir is None:
            base = os.environ.get("TMPDIR") or _TMP
            safe = base if is_safe_path(base) else _TMP
            self._workdir = Path(tempfile.mkdtemp(prefix="ffman.", dir=safe))
        return self._workdir

    def ffmpeg(self, args: Sequence[str]) -> None:
        """Run an ffmpeg that writes (skipped, and printed, under --dry-run)."""
        argv = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-stats", "-y"]
        if self.run([*argv, *ffmpeg_args(args, self.cores)]) != 0:
            refuse("ffmpeg failed (its message is above)")

    def run(self, argv: Sequence[str]) -> int:
        """Run a tool that writes; its output goes to the terminal. Returns its status."""
        if self.dry_run:
            _ = sys.stdout.write(f"{shlex.join(argv)}\n")
            return 0
        return _child(argv, capture=False).returncode

    def capture(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run a tool that only reads (it runs under --dry-run too): its output, captured."""
        return _child(argv, capture=True)


_FFMPEG: Final = "ffmpeg (https://ffmpeg.org)"  # the package of both
_PROVIDERS: Final = {"ffmpeg": _FFMPEG, "ffprobe": _FFMPEG}


def missing(tool: str) -> str:
    """A tool not found, in words: what to install, where that is known (spec 1)."""
    provider = _PROVIDERS.get(tool)
    return f"{tool} not found" + (f": install {provider}" if provider else "")


def require(*tools: str) -> None:
    """Refused, before any work, unless each of ``tools`` is on ``PATH``."""
    for tool in tools:
        if shutil.which(tool) is None:
            refuse(missing(tool))


def _child(argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in its own process group; on any exception, stop the whole tree first."""
    pipe = subprocess.PIPE if capture else None
    try:
        process = subprocess.Popen(  # noqa: S603 -- argv, never a shell
            argv,
            stdin=subprocess.DEVNULL,
            stdout=pipe,
            stderr=pipe,
            encoding="utf-8",
            errors="replace",  # as jq read it: a stray byte is U+FFFD, not a crash
            process_group=0,
        )
    except FileNotFoundError:
        if shutil.which(argv[0]) is not None:  # another file than the tool: the environment's
            raise
        refuse(missing(argv[0]))
    try:
        out, err = process.communicate()
    except BaseException:
        _stop(process)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, out, err)


def _stop(process: subprocess.Popen[str]) -> None:
    """TERM the group, poll up to 3 s (reaping the leader, or it lingers as a zombie), KILL."""
    group = process.pid
    _signal_group(group, signal.SIGTERM)
    for _ in range(_POLLS):
        _ = process.poll()
        if not _group_alive(group):
            break
        time.sleep(_POLL_SECONDS)
    _signal_group(group, signal.SIGKILL)
    _ = process.wait()


# killpg: ESRCH, the group is gone; EPERM, on macOS, members left that are all zombies (Linux
# signals a zombie; macOS refuses it, as Mozilla's bug 1329528 found). Uncaught, that EPERM ended
# a stopped job with "Operation not permitted", exit 1, not 128 + signum (macOS CI, 2026-10).
def _signal_group(group: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, sig)


def _group_alive(group: int) -> bool:
    """Whether the group has members, zombies counted (on macOS, the EPERM they give)."""
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
