import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ffman.errors import FfmanError
from ffman.media import run as run_module
from ffman.media.run import (
    SIGNALS,
    Interrupted,
    Runner,
    cores,
    ffmpeg_args,
    install_signal_handlers,
)
from tests.support.processes import marked


def test_ffmpeg_args_below_the_cap_unchanged() -> None:
    args = ["-i", "a.mkv", "-c:v", "ffv1", "o.mkv"]
    assert ffmpeg_args(args, 15) == args


def test_ffmpeg_args_past_the_cap() -> None:
    # bash's ffargs, cross-checked on 35 cases (1, 8, 15, 16, 31 cores)
    assert ffmpeg_args(["-i", "a.mkv", "-c:v", "ffv1", "o.mkv"], 32) == [
        "-filter_threads", "33", "-filter_complex_threads", "33",
        "-threads", "33", "-i", "a.mkv", "-c:v", "ffv1", "-threads", "33", "o.mkv",
    ]  # fmt: skip
    assert ffmpeg_args(["-i", "a", "-c:v", "libx264", "o.mp4"], 16) == [
        "-filter_threads", "17", "-filter_complex_threads", "17",
        "-threads", "17", "-i", "a", "-c:v", "libx264", "o.mp4",
    ]  # fmt: skip


def test_cores_is_nprocs_with_openmp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "7")
    assert cores() == 7
    monkeypatch.setenv("OMP_THREAD_LIMIT", "3")
    assert cores() == 3


def test_cores_without_nproc_counts_as_python_does(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(
        os, "process_cpu_count", lambda: 4
    )  # PYTHON_CPU_COUNT is read at startup alone
    assert cores() == 4
    assert (
        capsys.readouterr().err == "ffman: nproc not found: 4 processors, as Python counts them\n"
    )


def test_cores_without_any_count_is_one(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(os, "process_cpu_count", lambda: None)
    assert cores() == 1
    assert capsys.readouterr().err == "ffman: nproc not found: 1 processor, as Python counts them\n"


def test_cores_when_nproc_fails(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = (tmp_path / "nproc").write_text("#!/bin/sh\nexit 1\n")
    (tmp_path / "nproc").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(os, "process_cpu_count", lambda: 2)
    assert cores() == 2
    assert (
        capsys.readouterr().err
        == "ffman: nproc gave no count: 2 processors, as Python counts them\n"
    )


def test_a_runner_counts_on_first_use_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[int] = []

    def counted() -> int:
        asked.append(1)
        return 6

    monkeypatch.setattr(run_module, "cores", counted)
    with Runner(dry_run=True) as runner:
        assert asked == []  # a job running no ffmpeg never asks, never notes
        assert (runner.cores, runner.cores, asked) == (6, 6, [1])  # once


def test_workdir_is_made_once_and_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    with Runner(dry_run=False, cores=1) as runner:
        workdir = runner.workdir
        assert workdir.parent == tmp_path
        assert workdir.name.startswith("ffman.")
        assert runner.workdir == workdir
        _ = (workdir / "x").write_text("x")
    assert not workdir.exists()


def test_an_unsafe_tmpdir_falls_back_to_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe = tmp_path / "with space"
    unsafe.mkdir()
    monkeypatch.setenv("TMPDIR", str(unsafe))
    with Runner(dry_run=False, cores=1) as runner:
        assert runner.workdir.parent == Path("/tmp")  # noqa: S108 -- the fallback under test


def test_dry_run_prints_what_writes_and_runs_what_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = tmp_path / "made"
    with Runner(dry_run=True, cores=1) as runner:
        assert runner.run(["touch", str(made)]) == 0
        assert runner.capture(["echo", "read"]).stdout == "read\n"
    assert not made.exists()
    assert capsys.readouterr().out == f"touch {made}\n"


def test_ffmpeg_command_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with Runner(dry_run=True, cores=1) as runner:
        runner.ffmpeg(["-i", "in put.mkv", "o.mkv"])
    assert capsys.readouterr().out == (
        "ffmpeg -hide_banner -nostdin -loglevel error -stats -y -i 'in put.mkv' o.mkv\n"
    )
    fake = tmp_path / "ffmpeg"
    _ = fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    with (
        Runner(dry_run=False, cores=1) as runner,
        pytest.raises(FfmanError, match=r"^ffmpeg failed \(its message is above\)$"),
    ):
        runner.ffmpeg(["-i", "x"])


def test_interrupted_status() -> None:
    assert Interrupted(signal.SIGINT).status == 130
    assert Interrupted(signal.SIGTERM).status == 143
    assert Interrupted(signal.SIGHUP).status == 129


# Real processes, real signals: a job holding a work directory and a partial,
# running a process tree (a leader and a background grandchild in its group).
JOB = """
import pathlib, sys
try:  # measured here too; coverage's .pth would do it, but Nix puts it on PYTHONPATH, not a site dir
    import coverage
except ImportError:
    pass
else:
    coverage.process_startup()
from ffman.media.paths import partial_output
from ffman.media.run import Interrupted, Runner, install_signal_handlers
install_signal_handlers()
try:
    with Runner(dry_run=False, cores=1) as runner, partial_output(pathlib.Path(sys.argv[1])) as partial:
        print(runner.workdir, partial, flush=True)
        runner.run(["sh", "-c", sys.argv[2]])
except Interrupted as stop:
    sys.exit(stop.status)
"""


def gone_within(marker: str, seconds: float) -> bool:
    """Whether the tree's live processes (a zombie keeps no arguments) end within ``seconds``."""
    deadline = time.monotonic() + seconds
    while marked(marker, program="sleep ") and time.monotonic() < deadline:
        time.sleep(0.05)
    return not marked(marker, program="sleep ")


@pytest.mark.parametrize(
    ("sig", "status", "tree", "honours_term"),
    [
        (signal.SIGTERM, 143, "sleep {m} & exec sleep {m}", True),
        (signal.SIGINT, 130, "sleep {m} & exec sleep {m}", True),
        (signal.SIGHUP, 129, "sleep {m} & exec sleep {m}", True),
        (signal.SIGTERM, 143, "trap '' TERM; sleep {m} & sleep {m}; wait", False),
    ],
)
def test_a_signal_stops_the_tree_and_cleans_up(
    tmp_path: Path, sig: int, status: int, tree: str, honours_term: bool
) -> None:
    marker = f"{600 + os.getpid() % 100}.{sig}{len(tree)}"
    with subprocess.Popen(  # noqa: S603 -- the test's own interpreter and script
        [sys.executable, "-c", JOB, str(tmp_path / "out.mkv"), tree.format(m=marker)],
        stdout=subprocess.PIPE,
        text=True,
    ) as job:  # closes its pipe and waits: unclosed, a ResourceWarning
        try:
            assert job.stdout is not None
            workdir, partial = map(Path, job.stdout.readline().split())
            deadline = time.monotonic() + 5
            while len(marked(marker, program="sleep ")) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(marked(marker, program="sleep ")) == 2, "the tree did not start"
            start = time.monotonic()
            job.send_signal(sig)
            # TERM reaches the whole group at once; a tree ignoring it lives until the KILL,
            # after bash's 10 polls of 0.3 s. (ffman's exit also waits, within those 3 s, for
            # PID 1 to reap the orphans' zombies: measured, not assumed; so did bash's kill -0.)
            assert gone_within(marker, 1.0) is honours_term
            assert job.wait(timeout=10) == status
            elapsed = time.monotonic() - start
            # 3 s of polls, and room for a loaded builder (macOS CI's took 4.009 s)
            assert elapsed <= 6.0, elapsed
            if not honours_term:
                assert elapsed >= 2.8, elapsed
            assert marked(marker) == []  # the job is gone: anything left is a leak
            assert not workdir.exists()
            assert not partial.exists()
            assert not (tmp_path / "out.mkv").exists()
        finally:  # a failed check fails here, not after the tree's 600 s: nothing outlives it
            for pid in marked(marker):
                with contextlib.suppress(ProcessLookupError):  # gone since the listing
                    os.kill(pid, signal.SIGKILL)
            job.kill()


def test_a_stop_survives_macos_refusing_a_group_of_zombies(monkeypatch: pytest.MonkeyPatch) -> None:
    # macOS's killpg gives EPERM where Linux signals a zombie; here every call does. The tool
    # signals ffman (this process) once it is surely waited on, then exits: the stop that
    # follows polls a group that killpg refuses, and still ends in Interrupted
    def refused(_group: int, _sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", refused)
    monkeypatch.setattr(run_module, "_POLL_SECONDS", 0.01)
    previous = {sig: signal.getsignal(sig) for sig in SIGNALS}
    try:
        install_signal_handlers()
        with Runner(dry_run=False, cores=1) as runner, pytest.raises(Interrupted) as stop:
            _ = runner.run(["sh", "-c", "sleep 0.2; kill -TERM $PPID"])
        assert stop.value.status == 143
    finally:
        for sig, handler in previous.items():
            if handler is not None:
                _ = signal.signal(sig, handler)


def test_the_first_signal_resets_the_handlers() -> None:
    previous = {sig: signal.getsignal(sig) for sig in SIGNALS}
    try:
        install_signal_handlers()
        with pytest.raises(Interrupted) as stop:
            _ = signal.raise_signal(signal.SIGHUP)
        assert stop.value.status == 129
        # a second signal now acts at once, as after bash's `trap -`
        assert all(signal.getsignal(sig) == signal.SIG_DFL for sig in SIGNALS)
    finally:
        for sig, handler in previous.items():
            if handler is not None:
                _ = signal.signal(sig, handler)


def test_capture_survives_bytes_that_are_not_utf8() -> None:
    with Runner(dry_run=False, cores=1) as runner:
        assert runner.capture(["printf", r"a\377b"]).stdout == "a\ufffdb"  # as jq: U+FFFD
