"""The command line: the top level, and dispatch to a command."""

import contextlib
import os
import signal
import sys
from collections.abc import Callable, Sequence
from typing import Final

from ffman import __summary__, __version__
from ffman.effects import format_catalogue
from ffman.errors import PROG, REFUSALS, refuse
from ffman.jobs.convert.dispatch import convert
from ffman.jobs.convert.options import validate
from ffman.jobs.meta.options import validate as validate_meta
from ffman.jobs.meta.run import run as meta
from ffman.media.run import SIGNALS, Interrupted, Runner, install_signal_handlers
from ffman.options import CONVERT, META, format_help, parse

TOP_USAGE: Final = f"{PROG} COMMAND [options]"
TOP_HELP: Final = f"""Usage: {TOP_USAGE}

{__summary__}

Commands:
  convert   transform one media file: resize, effects, subtitles, encoding
  effects   the video effects, their values and what auto means
  meta      write or edit a metadata file: ffmetadata, Vorbis comments, a cue sheet

Options:
  -h, --help   show this help
  --version    show the version

See {PROG} COMMAND --help.
"""

# The bash commands, refused with their equivalent (D4; docs/ffman-spec.md section 7).
OLD_COMMANDS: Final = {
    "resize": f"resize is now: {PROG} convert ... (the same options)",
    "overlay": f"overlay is now: {PROG} convert -i F --burn-subs S ...",
    "attach": f"attach is now: {PROG} convert -i F --add-subs S [--language L] (-o O | --in-place)",
}


def run_convert(argv: list[str]) -> int:
    """``ffman convert``: parse and check its options."""
    parsed = parse("convert", CONVERT, argv)
    if parsed.help:
        print(
            format_help(
                f"{PROG} convert -i INPUT [options]",
                "Transform one media file: resize, effects, subtitles, encoding.",
                CONVERT,
            ),
            end="",
        )
        return 0
    options = validate(parsed)
    with Runner(dry_run=options.dry_run) as runner:
        convert(options, runner)
    return 0


def run_meta(argv: list[str]) -> int:
    """``ffman meta``: a metadata file written or edited (spec 8)."""
    parsed = parse("meta", META, argv)
    if parsed.help:
        usage = f"{PROG} meta [-i INPUT] (-o OUTPUT | -o - | --in-place) [--set K=V ...] [options]"
        print(
            format_help(
                usage,
                "Write or edit a metadata file: ffmetadata, Vorbis comments, a cue sheet.",
                META,
            ),
            end="",
        )
        return 0
    options = validate_meta(parsed)
    with Runner(dry_run=options.dry_run) as runner:
        meta(options, runner)
    return 0


EFFECTS_HELP: Final = f"""Usage: {PROG} effects [video] [NAME]

The effects --vfx takes, in the order they run, with what each value means
when left out. NAME shows one.
"""


def run_effects(argv: list[str]) -> int:
    """``ffman effects [video] [NAME]``: the catalogue."""
    if any(arg in ("-h", "--help") for arg in argv):
        print(EFFECTS_HELP, end="")
        return 0
    words = argv[1:] if argv[:1] == ["video"] else argv
    if len(words) > 1 or (words and words[0].startswith("-")):
        refuse(f"effects: unexpected: {' '.join(words)} (see {PROG} effects --help)")
    print(format_catalogue(words[0] if words else None), end="")
    return 0


COMMANDS: Final[dict[str, Callable[[list[str]], int]]] = {
    "convert": run_convert,
    "effects": run_effects,
    "meta": run_meta,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run ffman with ``argv`` (default: the process arguments); return the exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    previous = {sig: signal.getsignal(sig) for sig in SIGNALS}
    install_signal_handlers()
    try:
        status = _dispatch(args)
        # A pipe is block-buffered: flush here, where a reader gone is handled,
        # not at exit, where Python reports it and exits 120 (the docs' recipe).
        _ = sys.stdout.flush()
    except Interrupted as stop:  # cleaned up on the way out; silent, as bash was
        return stop.status
    except REFUSALS as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # the reader left (ffman ... | head): quiet, as bash died of SIGPIPE
        _stdout_to_devnull()
        return 128 + signal.SIGPIPE
    except OSError as error:  # the environment: a folder not writable, a disk full
        print(f"{PROG}: error: {_describe(error)}", file=sys.stderr)
        return 1
    else:
        return status
    finally:  # an in-process caller keeps its own handlers
        for sig, handler in previous.items():
            if handler is not None:
                _ = signal.signal(sig, handler)


def _stdout_to_devnull() -> None:
    """Point stdout at /dev/null, so the exit's own flush cannot fail again.

    The Python documentation's recipe (signal module, "Note on SIGPIPE"); not
    SIG_DFL, which would let a signal end ffman mid-job, its ffmpeg orphaned.
    """
    # Best effort: a caller's stdout may have no descriptor (io.UnsupportedOperation).
    with contextlib.suppress(OSError, ValueError):
        devnull = os.open(os.devnull, os.O_WRONLY)
        _ = os.dup2(devnull, sys.stdout.fileno())


def _describe(error: OSError) -> str:
    """``strerror: filename``: typeshed's ``filename`` is Any, narrowed to what it holds."""
    filename: object = error.filename  # pyright: ignore[reportAny] -- typeshed: Any
    what = error.strerror or str(error)
    if isinstance(filename, str | bytes):
        return f"{what}: {os.fsdecode(filename)}"
    return what


def _dispatch(args: list[str]) -> int:
    if not args:
        print(f"Usage: {TOP_USAGE}", file=sys.stderr)
        return 1
    word, rest = args[0], args[1:]
    if word in ("-h", "--help"):
        print(TOP_HELP, end="")
        return 0
    if word == "--version":
        print(f"{PROG} {__version__}")
        return 0
    if word in OLD_COMMANDS:
        refuse(OLD_COMMANDS[word])
    command = COMMANDS.get(word)
    if command is None:
        refuse(f"unknown command: {word} (see {PROG} --help)")
    return command(rest)
