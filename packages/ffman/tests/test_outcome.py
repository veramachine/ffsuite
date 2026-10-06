"""The outcome report's own tests: naming, verdicts, loading, the corpus, one real case."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Final, cast

import pytest

from tests.outcome import corpus
from tests.outcome.diff import Verdict, compare, summary
from tests.outcome.report import (
    FORMAT,
    Header,
    Outcome,
    Report,
    canonical,
    load,
    make,
    pythonpath,
    run_case,
    save,
)
from tests.outcome.report import _names as names  # pyright: ignore[reportPrivateUsage]

SRC = Path(__file__).resolve().parent.parent / "src"
TMP = Path("/t/ffman-outcome.ab_c9/scratch/case/tmp")
CORPUS = Path("/t/ffman-outcome.ab_c9/corpus")
EXPORTED = Path("/t/ffman-compare.x_y1z2ab/packages/ffman/src")


def _outcome(**changes: object) -> Outcome:
    base = Outcome(
        args=["convert", "--dry-run", "-i", "v.mp4", "-w", "160"],
        status=0,
        stdout="ffmpeg -i file:v.mp4 -filter_complex '[0:v:0]scale=160:90,setsar=1[v]' x.mp4\n",
        stderr="",
        files={},
        workdir=False,
    )
    return Outcome(**{**base, **changes})  # pyright: ignore[reportArgumentType]


def _report(cases: dict[str, Outcome]) -> Report:
    header = Header(ffmpeg="ffmpeg version 8.1.2", python="3.13", sources={"v.mp4": "0"})
    return Report(format=FORMAT, header=header, cases=cases)


@pytest.mark.parametrize(
    ("text", "named"),
    [
        (f"{TMP}/ffman.h2oe_ze6/subs.ass", "$WORK/subs.ass"),
        (r"/t/ffman-outcom\e.ab_c9/scratch/case/tmp/ffman.h2o\e_z\e6/subs.ass", "$WORK/subs.ass"),
        (f"fontsdir={CORPUS}/fonts", "fontsdir=$CORPUS/fonts"),
        (r"/t/ffman-outcom\\e.ab_c9/corpus/fonts", "$CORPUS/fonts"),
        (f"XDG_CONFIG_HOME={EXPORTED}/ffman/normalize", "XDG_CONFIG_HOME=$SRC/ffman/normalize"),
        (f"{TMP}/ffman.short/x", f"{TMP}/ffman.short/x"),  # not mkdtemp's 8: left alone
    ],
)
def test_paths_are_named_however_escaped(text: str, named: str) -> None:
    assert canonical(text, names(TMP, CORPUS, EXPORTED)) == named


def test_a_path_with_syntax_characters_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot name safely"):
        _ = names(Path("/t/a:b"), CORPUS, EXPORTED)


def test_identical_and_changed() -> None:
    old = _report({"a": _outcome(), "b": _outcome(), "c": _outcome(), "d": _outcome()})
    new = _report(
        {
            "a": _outcome(),
            "b": _outcome(stderr="ffman: a note\n"),
            "c": _outcome(files={"$WORK/subs.ass": "x"}, workdir=True),
            "e": _outcome(),
        }
    )
    result = compare(old, new)
    assert result.verdicts == {
        "a": Verdict.IDENTICAL,
        "b": Verdict.CHANGED,
        "c": Verdict.CHANGED,
        "d": Verdict.CHANGED,
        "e": Verdict.CHANGED,
    }
    assert result.diffs["d"] == "only in the old report"
    assert result.diffs["e"] == "only in the new report"
    assert "+stderr: ffman: a note" in result.diffs["b"]
    assert "1 identical, 0 same graph, 4 changed" in summary(result)


def test_a_graph_ffmpeg_reads_the_same_is_not_a_change() -> None:
    escaped = "ffmpeg -i file:v.mp4 -filter_complex '[0:v:0]scale=1\\\\60:90,setsar=1[v]' x.mp4\n"
    unreadable = (
        "ffmpeg -i file:v.mp4 -filter_complex '[0:v:0]scal\\\\e=160:90,setsar=1[v]' x.mp4\n"
    )
    reordered = "ffmpeg -i file:v.mp4 -filter_complex '[0:v:0]scale=90:160,setsar=1[v]' x.mp4\n"
    outside = "ffmpeg -i file:w.mp4 -filter_complex '[0:v:0]scale=160:90,setsar=1[v]' x.mp4\n"
    old = _report({k: _outcome() for k in ("same", "other", "arg", "bad")})
    new = _report(
        {
            "same": _outcome(stdout=escaped),
            "other": _outcome(stdout=reordered),
            "arg": _outcome(stdout=outside),
            "bad": _outcome(stdout=unreadable),
        }
    )
    result = compare(old, new)
    assert result.verdicts["same"] is Verdict.SAME_GRAPH
    assert result.verdicts["other"] is Verdict.CHANGED
    assert result.verdicts["arg"] is Verdict.CHANGED  # not a filtergraph argument
    assert result.verdicts["bad"] is Verdict.CHANGED  # a graph ffman.graph refuses: no crash
    assert "same graph: same" in summary(result)


def test_the_headers_differences_are_warned() -> None:
    old = _report({})
    new = _report({})
    new["header"]["ffmpeg"] = "ffmpeg version 8.2"
    new["header"]["sources"] = {"v.mp4": "1"}
    warnings = compare(old, new).warnings
    assert warnings[0] == "ffmpeg: ffmpeg version 8.1.2 -> ffmpeg version 8.2"
    assert "sources differ" in warnings[1]


def test_a_report_round_trips(tmp_path: Path) -> None:
    report = _report({"a": _outcome(files={"$WORK/x": "é"}, workdir=True)})
    save(report, tmp_path / "r.json")
    assert load(tmp_path / "r.json") == report


_GONE: Final = object()  # a key removed, not replaced


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("format",), 0, "format"),
        (("cases", "a", "status"), "0", "status is not an integer"),
        (("cases", "a", "status"), True, "status is not an integer"),
        (("cases", "a", "workdir"), 1, "is not a boolean"),
        (("cases", "a", "files"), [], "is not an object"),
        (("cases", "a", "args"), "convert", "is not a list"),
        (("cases", "a", "stdout"), _GONE, "is not text"),
        (("header",), _GONE, "header is not an object"),
    ],
)
def test_a_malformed_report_is_an_error_never_empty(
    tmp_path: Path, path: tuple[str, ...], value: object, message: str
) -> None:
    raw = cast("dict[str, object]", json.loads(json.dumps(_report({"a": _outcome()}))))
    node = raw
    for key in path[:-1]:
        node = cast("dict[str, object]", node[key])
    if value is _GONE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    _ = (tmp_path / "r.json").write_text(json.dumps(raw))
    with pytest.raises(TypeError, match=message):
        _ = load(tmp_path / "r.json")


def test_the_corpus_ids_are_unique_and_its_inputs_are_built() -> None:
    cases = corpus.cases()
    assert len({c.id for c in cases}) == len(cases)
    made = {
        *corpus.SOURCES,
        "t.ass",
        "bad.mp4",
        "exists.mp4",
        "noext",
        "badtoken.json",
        corpus.EVERYTHING,
    }
    made |= {p.name for p in corpus.FIXTURES.iterdir()}
    made |= set(corpus.METADATA)  # spec 3.9's files
    missing = {"nothing.mp4"}  # the one input that must not exist
    for case in cases:
        for i, arg in enumerate(case.args[:-1]):
            if arg == "-i":
                assert case.args[i + 1] in made | missing, case.id


@pytest.mark.ffmpeg
def test_a_case_runs_its_work_directory_kept(tmp_path: Path, ffmpeg: str) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    lavfi = ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=0.2", "-c:v", "libx264"]
    _ = subprocess.run([ffmpeg, "-v", "error", *lavfi, str(root / "v.mp4")], check=True)  # noqa: S603 -- ffmpeg
    _ = shutil.copy(corpus.FIXTURES / "regular.srt", root / "regular.srt")
    (root / corpus.FONTS).mkdir()
    case = corpus.Case(
        "burn", ("convert", "--dry-run", "-i", "v.mp4", "--burn-subs", "regular.srt")
    )
    outcome = run_case(SRC, root, tmp_path / "scratch", case)
    assert outcome["status"] == 0, outcome["stderr"]
    assert outcome["workdir"]
    assert list(outcome["files"]) == ["$WORK/subs.ass"]
    assert outcome["files"]["$WORK/subs.ass"].startswith("[Script Info]")
    assert "ass=filename=$WORK/subs.ass:fontsdir=$CORPUS/fonts" in outcome["stdout"]
    assert not re.search(str(tmp_path), json.dumps(outcome))


def test_a_report_needs_a_source_tree(tmp_path: Path) -> None:
    (tmp_path / "src" / "ffman").mkdir(parents=True)
    _ = (tmp_path / "src" / "ffman" / "__init__.py").write_text("")
    with pytest.raises(RuntimeError, match=r"pyproject\.toml is missing"):
        _ = make(tmp_path / "src")


@pytest.mark.ffmpeg
def test_a_capture_that_fails_is_refused_not_recorded(tmp_path: Path, ffmpeg: str) -> None:
    """Kept from ffman, whose error it would read as; the report refuses the case."""
    root = tmp_path / "corpus"
    root.mkdir()
    lavfi = ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=0.2", "-c:v", "libx264"]
    _ = subprocess.run([ffmpeg, "-v", "error", *lavfi, str(root / "v.mp4")], check=True)  # noqa: S603 -- ffmpeg
    _ = shutil.copy(corpus.FIXTURES / "regular.srt", root / "regular.srt")
    (root / corpus.FONTS).mkdir()
    blocked = tmp_path / "scratch" / "burn"
    blocked.mkdir(parents=True)
    _ = (blocked / "capture").write_text("a file where the capture goes")
    case = corpus.Case(
        "burn", ("convert", "--dry-run", "-i", "v.mp4", "--burn-subs", "regular.srt")
    )
    with pytest.raises(RuntimeError, match="burn: outcome driver: capture failed:"):
        _ = run_case(SRC, root, tmp_path / "scratch", case)


@pytest.mark.parametrize(
    ("tree", "libraries"),
    [
        ("packages/ffman", "packages"),  # ffman a member, its libraries its siblings
        (".", "packages"),  # before (6.7.5-6.7.7): the workspace's root, its libraries under it
        ("packages/old", "packages/old/packages"),  # the same, kept in a folder named packages
    ],
)
def test_the_import_path_is_ffmans_src_and_the_other_packages(
    tmp_path: Path, tree: str, libraries: str
) -> None:
    others = [tmp_path / libraries / name / "src" for name in ("ffmeta", "subverter")]
    src = tmp_path / tree / "src"
    for folder in (src, *others):
        folder.mkdir(parents=True)
    assert pythonpath(src).split(os.pathsep) == [str(src), *map(str, others)]


def test_ffman_alone_imports_its_src_alone(tmp_path: Path) -> None:
    # before 6.7.5, no workspace: a folder beside it is not its library
    src, stray = tmp_path / "ffman" / "src", tmp_path / "other" / "src"
    for folder in (src, stray):
        folder.mkdir(parents=True)
    assert pythonpath(src) == str(src)
