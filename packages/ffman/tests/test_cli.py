import os
import runpy
import signal
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import NoReturn

import pytest

import ffman
from ffman import __version__
from ffman.cli import COMMANDS, OLD_COMMANDS, main
from ffman.media.run import SIGNALS, Interrupted

NOTHING_ASKED = "a size (-w, -H, -a), an effect (--vfx), subtitles (--burn-subs, --add-subs)"


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == f"ffman {__version__}\n"


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help(flag: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([flag]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Usage: ffman COMMAND [options]")
    assert "convert" in out


def test_no_arguments_prints_usage_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 1
    assert capsys.readouterr().err == "Usage: ffman COMMAND [options]\n"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        pytest.param(
            ["frobnicate"], "unknown command: frobnicate (see ffman --help)", id="unknown-command"
        ),
        pytest.param(["--bogus"], "unknown command: --bogus (see ffman --help)", id="unknown-flag"),
        pytest.param(["--"], "unknown command: -- (see ffman --help)", id="dashes"),
        *[
            pytest.param([old, "-i", "x"], text, id=f"{old}-is-convert")
            for old, text in OLD_COMMANDS.items()
        ],
        # bash's help of its other commands: each now names what replaces it
        *[
            pytest.param([old, "--help"], text, id=f"{old}-help")
            for old, text in OLD_COMMANDS.items()
        ],
        pytest.param(
            ["convert", "--bogus"],
            "convert: unknown option: --bogus (see ffman convert --help)",
            id="unknown-option",
        ),
        pytest.param(["convert"], "convert: --input is required", id="no-input"),
        pytest.param(
            ["convert", "-i", "x.mp4"],
            f"convert: nothing to do: give {NOTHING_ASKED}, another container, a codec or --preset",
            id="nothing-asked",
        ),
    ],
)
def test_refusals_exit_one_with_ffmans_prefix(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 1
    assert capsys.readouterr().err == f"ffman: error: {message}\n"


def test_convert_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--help"]) == 0
    assert capsys.readouterr().out.startswith("Usage: ffman convert -i INPUT [options]")


def test_python_dash_m(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ffman", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        _ = runpy.run_module("ffman", run_name="__main__", alter_sys=True)
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"ffman {__version__}\n"


WINDOWS = "ffman: error: ffman runs on Linux and macOS; on Windows, run it in WSL\n"


def test_windows_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(SystemExit) as exit_info:
        _ = runpy.run_module("ffman", run_name="__main__", alter_sys=True)
    assert exit_info.value.code == 1
    assert capsys.readouterr().err == WINDOWS


# Windows as Python shows it to ffman: none of the POSIX names ffman's tool handling uses
# (the signal module's documentation: SIGHUP, SIGKILL, SIGPIPE Unix's; os.killpg Unix's)
_AS_WINDOWS = """
import os, signal, sys
for name in ("SIGHUP", "SIGKILL", "SIGPIPE"):
    delattr(signal, name)
del os.killpg
from ffman.__main__ import main
sys.platform = "win32"  # after the imports: the standard library's own choose by it
sys.exit(main())
"""


def test_windows_is_refused_before_anything_posix_is_imported() -> None:
    # the command as installed (pyproject's scripts: ffman.__main__:main), in a fresh Python
    argv = [sys.executable, "-c", _AS_WINDOWS]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603 -- this Python
    assert (done.returncode, done.stdout, done.stderr) == (1, "", WINDOWS)


def test_an_environment_error_is_a_message_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def denied(_argv: list[str]) -> int:
        raise PermissionError(13, "Permission denied", "/no/such/place")

    monkeypatch.setitem(COMMANDS, "convert", denied)
    assert main(["convert"]) == 1
    assert capsys.readouterr().err == "ffman: error: Permission denied: /no/such/place\n"


def test_an_environment_error_without_a_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def full(_argv: list[str]) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setitem(COMMANDS, "convert", full)
    assert main(["convert"]) == 1
    assert capsys.readouterr().err == "ffman: error: No space left on device\n"


@pytest.mark.parametrize(
    ("argv", "start"),
    [
        (["effects"], "Video effects"),
        (["effects", "video"], "Video effects"),
        (["effects", "crt"], "  crt"),
        (["effects", "video", "vhs"], "  vhs"),
        (["effects", "-h"], "Usage: ffman effects"),
    ],
)
def test_effects_command(argv: list[str], start: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(argv) == 0
    assert capsys.readouterr().out.startswith(start)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["effects", "blur", "crt"], "effects: unexpected: blur crt (see ffman effects --help)"),
        (["effects", "--all"], "effects: unexpected: --all (see ffman effects --help)"),
        (["effects", "glow"], "unknown effect: glow (see ffman effects)"),
    ],
)
def test_effects_refusals(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 1
    assert capsys.readouterr().err == f"ffman: error: {message}\n"


def test_a_signal_is_its_status_silently_and_the_handlers_come_back(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {sig: signal.getsignal(sig) for sig in SIGNALS}

    def stopped(_argv: list[str]) -> int:
        raise Interrupted(signal.SIGTERM)

    monkeypatch.setitem(COMMANDS, "convert", stopped)
    assert main(["convert"]) == 143
    assert capsys.readouterr() == ("", "")
    assert {sig: signal.getsignal(sig) for sig in SIGNALS} == before


def test_a_handler_python_did_not_install_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    # typeshed: getsignal may return None (a handler set outside Python); it cannot be reinstalled
    real = signal.getsignal

    def getsignal(sig: int) -> object:
        return None if sig == signal.SIGHUP else real(sig)

    monkeypatch.setattr(signal, "getsignal", getsignal)
    assert main(["--version"]) == 0


# A real broken pipe: stdout is a pipe whose reader is already gone, so the
# first write fails (EPIPE), as when ``ffman effects | head`` stops reading.
CHILD = """
import sys
try:  # measured here too (Nix does not process coverage's .pth)
    import coverage
except ImportError:
    pass
else:
    coverage.process_startup()
from ffman.cli import main
sys.exit(main(["effects"]))
"""


@pytest.mark.parametrize("unbuffered", [False, True])  # the installed ffman runs buffered
def test_a_reader_gone_is_quiet_and_141_as_bash(unbuffered: bool) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    if unbuffered:
        env["PYTHONUNBUFFERED"] = "1"
    read, write = os.pipe()
    os.close(read)
    try:
        child = subprocess.run(  # noqa: S603 -- the test's own interpreter
            [sys.executable, "-c", CHILD],
            stdout=write,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
    finally:
        os.close(write)
    assert child.returncode == 141  # 128 + SIGPIPE, bash's
    assert child.stderr == b""


def test_a_reader_gone_with_a_stdout_without_a_descriptor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gone(_argv: list[str]) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setitem(COMMANDS, "convert", gone)
    assert main(["convert"]) == 141  # capsys's stdout has no descriptor: still no crash
    assert capsys.readouterr().err == ""


def test_a_source_tree_has_its_version_from_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # run as is (PYTHONPATH=src: the equivalence harness), ffman has no installed metadata
    _ = (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "ffman"\nversion = "9.9"\ndescription = "d"\n'
    )

    def missing(name: str) -> NoReturn:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(ffman, "metadata", missing)
    assert ffman.about(tmp_path) == ("9.9", "d")
    monkeypatch.undo()
    assert ffman.about(tmp_path) == (__version__, ffman.__summary__)  # installed: the metadata
