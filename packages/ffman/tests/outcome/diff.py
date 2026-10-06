"""Two reports compared, case by case: identical, the same graph in other text, or changed.

"Same graph": the commands differ only in filtergraph arguments that
``tests/support/filtergraph.py`` -- ffmpeg 8.1.2's own parser, transcribed --
reads as the same graph. ffmpeg would do the same, so a form-only change may
produce one; it is listed, not failed. Anything else that differs is a change,
and so is a case in one report only.
"""

import difflib
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from tests.outcome.report import Outcome, Report
from tests.support.filtergraph import parse

GRAPH_OPTIONS: Final = frozenset(
    {"-filter_complex", "-lavfi", "-vf", "-af", "-filter:v", "-filter:a"}
)


class Verdict(Enum):
    """How one case compares."""

    IDENTICAL = "identical"
    SAME_GRAPH = "same graph"
    CHANGED = "changed"


@dataclass(slots=True)
class Comparison:
    """Every case's verdict, the changes' diffs, and what differs in the reports' making."""

    verdicts: dict[str, Verdict] = field(default_factory=dict)
    diffs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> list[str]:
        """The cases that changed."""
        return [c for c, v in self.verdicts.items() if v is Verdict.CHANGED]


def _same_graphs(a: str, b: str) -> bool:
    """Two command lines equal but for filtergraphs that parse the same."""
    try:
        x, y = shlex.split(a), shlex.split(b)
    except ValueError:
        return False
    if len(x) != len(y):
        return False
    for i, (p, q) in enumerate(zip(x, y, strict=True)):
        if p == q:
            continue
        if i == 0 or x[i - 1] != y[i - 1] or x[i - 1] not in GRAPH_OPTIONS:
            return False
        try:
            if parse(p) != parse(q):
                return False
        except ValueError:  # ParseError, or a graph ffman.graph's own data refuses
            return False
    return True


def _render(o: Outcome) -> list[str]:
    lines = [f"args: {shlex.join(o['args'])}", f"status: {o['status']}"]
    lines += [f"stdout: {s}" for s in o["stdout"].splitlines()]
    lines += [f"stderr: {s}" for s in o["stderr"].splitlines()]
    for name, text in sorted(o["files"].items()):
        lines += [f"{name}: {s}" for s in text.splitlines()] or [f"{name}: (empty)"]
    return [*lines, f"workdir: {o['workdir']}"]


def _verdict(a: Outcome, b: Outcome) -> Verdict:
    if a == b:
        return Verdict.IDENTICAL
    rest_equal = all(a[k] == b[k] for k in ("args", "status", "stderr", "files", "workdir"))
    old, new = a["stdout"].splitlines(), b["stdout"].splitlines()
    if (
        rest_equal
        and len(old) == len(new)
        and all(p == q or _same_graphs(p, q) for p, q in zip(old, new, strict=True))
    ):
        return Verdict.SAME_GRAPH
    return Verdict.CHANGED


def compare(old: Report, new: Report) -> Comparison:
    """``new`` against ``old``."""
    result = Comparison()
    for key in ("ffmpeg", "python"):
        if old["header"][key] != new["header"][key]:
            result.warnings.append(f"{key}: {old['header'][key]} -> {new['header'][key]}")
    if old["header"]["sources"] != new["header"]["sources"]:
        result.warnings.append(
            "the corpus' sources differ (byte for byte): a difference may be theirs"
        )
    for case_id in sorted(old["cases"].keys() | new["cases"].keys()):
        a, b = old["cases"].get(case_id), new["cases"].get(case_id)
        if a is None or b is None:
            result.verdicts[case_id] = Verdict.CHANGED
            result.diffs[case_id] = f"only in the {'new' if a is None else 'old'} report"
            continue
        verdict = _verdict(a, b)
        result.verdicts[case_id] = verdict
        if verdict is Verdict.CHANGED:
            lines = difflib.unified_diff(_render(a), _render(b), "old", "new", lineterm="", n=1)
            result.diffs[case_id] = "\n".join(lines)
    return result


def summary(result: Comparison) -> str:
    """The comparison, for a reader: warnings, counts, then each change's diff."""
    counts = {v: sum(1 for x in result.verdicts.values() if x is v) for v in Verdict}
    head = [f"warning: {w}" for w in result.warnings]
    head.append(", ".join(f"{n} {v.value}" for v, n in counts.items()))
    same = [c for c, v in result.verdicts.items() if v is Verdict.SAME_GRAPH]
    head += [f"same graph: {c}" for c in same]
    return "\n".join([*head, *(f"\n== {c}\n{result.diffs[c]}" for c in result.changed)])
