"""Run every case against a commit's ``src``; record what ffman did, canonicalised.

A case's record: its exit status, stdout (the plan and the commands, under
--dry-run), stderr (notes, refusals), and every file its work directory held
(the ASS and SRT it wrote, links) -- copied whole by the driver as it is
removed, so complete by construction; a case that prints ``$WORK`` with no
work directory captured fails the report, never records a silent miss. Paths that differ
per run or per machine become names: ``$WORK`` (the work directory), ``$CORPUS`` (which holds
fonts and presets for ffman too) and ``$SRC`` (the commit's: ffman's own presets, the variable
unset). Nothing else is rewritten.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Final, TypedDict, cast

from tests.outcome import corpus, driver

FORMAT: Final = 1
DRIVER: Final = Path(__file__).resolve().with_name("driver.py")
TIMEOUT: Final = 300  # s, a case
_SUFFIX: Final = r"(?:\\*[a-z0-9_]){8}"  # tempfile.mkdtemp's 8 of [a-z0-9_], after "ffman."
_PLAIN: Final = re.compile(r"[A-Za-z0-9._/-]+")


class Outcome(TypedDict):
    """One case's record."""

    args: list[str]
    status: int
    stdout: str
    stderr: str
    files: dict[str, str]
    workdir: bool  # a work directory was made, and captured


class Header(TypedDict):
    """What the report was made with."""

    ffmpeg: str
    python: str
    sources: dict[str, str]


class Report(TypedDict):
    """A whole report."""

    format: int
    header: Header
    cases: dict[str, Outcome]


def _tolerant(path: str) -> str:
    """A pattern for ``path`` however a commit escapes it: any backslashes before any character.

    Safe because the report's paths hold only ``[A-Za-z0-9._/-]``, none of which
    ffmpeg's syntax treats as special at any level: escaped or not, they read the same.
    """
    if not _PLAIN.fullmatch(path):
        msg = f"a path the report cannot name safely: {path}"
        raise ValueError(msg)
    return "".join(r"\\*" + re.escape(c) for c in path)


def _names(tmpdir: Path, corpus_dir: Path, src: Path) -> list[tuple[re.Pattern[str], str]]:
    pairs = [
        (_tolerant(f"{tmpdir}/ffman.") + _SUFFIX, "$WORK"),
        (_tolerant(str(corpus_dir)), "$CORPUS"),
        (_tolerant(str(src)), "$SRC"),
    ]
    return [(re.compile(p), n) for p, n in pairs]


def canonical(text: str, names: list[tuple[re.Pattern[str], str]]) -> str:
    """``text`` with each run's and machine's paths as their names."""
    for pattern, name in names:
        text = pattern.sub(name, text)
    return text


def _files(workdir: Path, names: list[tuple[re.Pattern[str], str]]) -> dict[str, str]:
    """Every captured file, keyed ``$WORK/RELATIVE``: text, a link's target, or a binary's digest."""
    out: dict[str, str] = {}
    for path in sorted(workdir.rglob("*")):
        key = "$WORK/" + path.relative_to(workdir).as_posix()
        if path.is_symlink():
            out[key] = "-> " + canonical(str(path.readlink()), names)
        elif path.is_file():
            data = path.read_bytes()
            try:
                out[key] = canonical(data.decode(), names)
            except UnicodeDecodeError:
                out[key] = "binary sha256:" + hashlib.sha256(data).hexdigest()
    return out


def pythonpath(src: Path) -> str:
    """ffman's import path: its ``src``, and each other workspace package's.

    Before (6.7.5-6.7.7), ffman the workspace's root: the others under it, in ``packages/``.
    ffman a member, ``packages/ffman``, none under it: the others its siblings.
    """
    tree = src.parent
    member = tree.parent.name == "packages" and not (tree / "packages").is_dir()
    packages = tree.parent if member else tree / "packages"
    others = sorted(str(own) for own in packages.glob("*/src") if own != src)
    return os.pathsep.join([str(src), *others])


def run_case(src: Path, corpus_dir: Path, scratch: Path, case: corpus.Case) -> Outcome:
    """One case, in its own TMPDIR and capture directory."""
    base = scratch / case.id.replace("/", "_")
    tmpdir, capture = base / "tmp", base / "capture"
    tmpdir.mkdir(parents=True)
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": pythonpath(src),
        "TMPDIR": str(tmpdir),
        "HOME": str(base),
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "OMP_NUM_THREADS": "4",  # nproc's answer: over 1 (FFV1's slices), under 16 (no -threads)
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FFMAN_FONTS_DIR": str(corpus_dir / corpus.FONTS),
        "FFMAN_NORMALIZE_HOME": str(corpus_dir / corpus.NORMALIZE),
        **{k: v.replace("{corpus}", str(corpus_dir)) for k, v in case.env},
    }
    # -S: no site-packages -- the commit's sources alone, ffman's and its libraries' (packages/
    # beside src): an installed one's, or its metadata, must not answer for the commit's
    argv = [sys.executable, "-S", str(DRIVER), str(capture), "--", *case.args]
    done = subprocess.run(  # noqa: S603 -- our driver
        argv, cwd=corpus_dir, env=env, capture_output=True, text=True, timeout=TIMEOUT, check=False
    )
    if done.returncode == driver.FAILED and driver.MARK in done.stderr:
        msg = f"{case.id}: {done.stderr.strip().splitlines()[-1]}"
        raise RuntimeError(msg)
    names = _names(tmpdir, corpus_dir, src)
    stdout, stderr = canonical(done.stdout, names), canonical(done.stderr, names)
    workdirs = sorted(capture.iterdir()) if capture.is_dir() else []
    if len(workdirs) > 1 or ("$WORK" in stdout + stderr and not workdirs):
        msg = f"{case.id}: work directories captured: {[w.name for w in workdirs]}, printed: {'$WORK' in stdout + stderr}"
        raise RuntimeError(msg)
    files = _files(workdirs[0], names) if workdirs else {}
    return Outcome(
        args=list(case.args),
        status=done.returncode,
        stdout=stdout,
        stderr=stderr,
        files=files,
        workdir=bool(workdirs),
    )


def _first_line(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout.splitlines()[0]  # noqa: S603 -- the pinned tools


def make(src: Path, workers: int | None = None) -> Report:
    """Build the corpus, run every case against ``src``, and gather the report.

    ``src`` must be a tree's: ``src/ffman`` and the ``pyproject.toml`` beside it, which
    an uninstalled ffman reads (each case runs under -S) -- else every case would
    record the same crash, as if it were ffman's answer.
    """
    for needed in (src / "ffman" / "__init__.py", src.parent / "pyproject.toml"):
        if not needed.is_file():
            msg = f"not an ffman source tree: {needed} is missing"
            raise RuntimeError(msg)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        msg = "no ffmpeg on PATH"
        raise RuntimeError(msg)
    with tempfile.TemporaryDirectory(prefix="ffman-outcome.") as top:
        corpus_dir, scratch = Path(top) / "corpus", Path(top) / "scratch"
        corpus.build(corpus_dir, ffmpeg)
        sources = {
            n: hashlib.sha256((corpus_dir / n).read_bytes()).hexdigest()
            for n in sorted(corpus.SOURCES)
        }
        every = corpus.cases()
        with ThreadPoolExecutor(max_workers=workers or min(8, os.cpu_count() or 1)) as pool:
            outcomes = list(pool.map(partial(run_case, src, corpus_dir, scratch), every))
    header = Header(
        ffmpeg=_first_line([ffmpeg, "-version"]), python=sys.version.split()[0], sources=sources
    )
    return Report(
        format=FORMAT, header=header, cases={c.id: o for c, o in zip(every, outcomes, strict=True)}
    )


def save(report: Report, path: Path) -> None:
    """Write ``report`` as sorted, indented JSON (diffable by eye too)."""
    _ = path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _dict(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) for k in cast("dict[object, object]", value)
    ):
        msg = f"report: {what} is not an object"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _str(value: object, what: str) -> str:
    if not isinstance(value, str):
        msg = f"report: {what} is not text"
        raise TypeError(msg)
    return value


def _strs(value: object, what: str) -> list[str]:
    if not isinstance(value, list):
        msg = f"report: {what} is not a list"
        raise TypeError(msg)
    return [_str(v, what) for v in cast("list[object]", value)]


def _bool(value: object, what: str) -> bool:
    if not isinstance(value, bool):
        msg = f"report: {what} is not a boolean"
        raise TypeError(msg)
    return value


def _texts(value: object, what: str) -> dict[str, str]:
    return {k: _str(v, f"{what}[{k}]") for k, v in _dict(value, what).items()}


def load(path: Path) -> Report:
    """A report read back, every field checked: a malformed one is an error, never empty."""
    root = _dict(cast("object", json.loads(path.read_text())), str(path))
    if root.get("format") != FORMAT:
        msg = f"report: {path} has format {root.get('format')!r}, not {FORMAT}"
        raise TypeError(msg)
    head = _dict(root.get("header"), "header")
    header = Header(
        ffmpeg=_str(head.get("ffmpeg"), "ffmpeg"),
        python=_str(head.get("python"), "python"),
        sources=_texts(head.get("sources"), "sources"),
    )
    cases: dict[str, Outcome] = {}
    for case_id, raw in _dict(root.get("cases"), "cases").items():
        o = _dict(raw, case_id)
        status = o.get("status")
        if not isinstance(status, int) or isinstance(status, bool):
            msg = f"report: {case_id}'s status is not an integer"
            raise TypeError(msg)
        cases[case_id] = Outcome(
            args=_strs(o.get("args"), f"{case_id}.args"),
            status=status,
            stdout=_str(o.get("stdout"), f"{case_id}.stdout"),
            stderr=_str(o.get("stderr"), f"{case_id}.stderr"),
            files=_texts(o.get("files"), f"{case_id}.files"),
            workdir=_bool(o.get("workdir"), f"{case_id}.workdir"),
        )
    return Report(format=FORMAT, header=header, cases=cases)
