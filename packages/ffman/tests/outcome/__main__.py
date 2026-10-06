"""``python -m tests.outcome``: report a commit's outcomes, compare two, or both at once."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

from tests.outcome.diff import Comparison, compare, summary
from tests.outcome.report import load, make, save

SRC = Path(__file__).resolve().parents[2] / "src"


def _has(root: str, commit: str, path: str) -> bool:
    """Whether the revision has ``path`` (git archive refuses one it lacks)."""
    probe = ["git", "-C", root, "cat-file", "-e", f"{commit}:{path}"]
    return subprocess.run(probe, capture_output=True, check=False).returncode == 0  # noqa: S603 -- git


def _export(rev: str, into: Path) -> Path:
    """``rev``'s ffman ``src``, exported from git (no worktree, no index).

    Its ``pyproject.toml`` comes too: an uninstalled ffman reads its version beside ``src``; and
    its libraries, where the revision has them. ffman a member (``packages/ffman``): all of
    ``packages/``. Before, ffman the repository's root: ``src``, ``pyproject.toml`` and
    ``packages/`` if there (6.7.5-6.7.7).
    """
    top = ["git", "rev-parse", "--show-toplevel"]
    root = subprocess.run(top, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603 -- git
    # resolved first: a revision is never read as an option (git archive --output=...)
    verify = ["git", "-C", root, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"]
    commit = subprocess.run(verify, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603 -- git
    if _has(root, commit, "packages/ffman"):
        paths, src = ["packages"], into / "packages" / "ffman" / "src"
    else:
        paths = ["src", "pyproject.toml", *(["packages"] if _has(root, commit, "packages") else [])]
        src = into / "src"
    archive = ["git", "-C", root, "archive", commit, *paths]
    data = subprocess.run(archive, capture_output=True, check=True).stdout  # noqa: S603 -- git
    _ = subprocess.run(["tar", "-x", "-C", str(into)], input=data, check=True)  # noqa: S603, S607 -- tar
    return src


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tests.outcome", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="run the corpus against a src directory")
    _ = report.add_argument("src", type=Path)
    _ = report.add_argument("out", type=Path)
    diff = commands.add_parser("diff", help="compare two reports")
    _ = diff.add_argument("old", type=Path)
    _ = diff.add_argument("new", type=Path)
    both = commands.add_parser(
        "compare", help="report a git revision and this tree's src, then compare"
    )
    _ = both.add_argument("rev", help="the base revision, e.g. HEAD")
    _ = both.add_argument("--keep", type=Path, help="a directory to keep both reports in")
    return parser


def _compare_rev(rev: str, keep: Path | None) -> Comparison:
    with tempfile.TemporaryDirectory(prefix="ffman-compare.") as top:
        into = keep or Path(top)
        into.mkdir(parents=True, exist_ok=True)
        save(make(_export(rev, Path(top))), into / "old.json")
        save(make(SRC), into / "new.json")
        return compare(load(into / "old.json"), load(into / "new.json"))


def main(argv: list[str] | None = None) -> int:
    """The three commands; ``diff`` and ``compare`` exit 1 when anything changed."""
    args = _parser().parse_args(argv)
    command = cast("str", args.command)
    if command == "report":
        save(make(cast("Path", args.src).resolve()), cast("Path", args.out))
        return 0
    if command == "diff":
        result = compare(load(cast("Path", args.old)), load(cast("Path", args.new)))
    else:
        result = _compare_rev(cast("str", args.rev), cast("Path | None", args.keep))
    _ = sys.stdout.write(summary(result) + "\n")
    return 1 if result.changed else 0


if __name__ == "__main__":
    sys.exit(main())
