"""The package's layers (docs/ffman-phase6.md §3), read from the source's syntax trees.

Imports point down, never in a cycle; only the media layer starts processes;
planners and graphs touch no file; ffman takes its libraries' public API alone
(each library's own test_imports.py holds the other way). Every ``import`` and
``from ... import`` counts, wherever it stands, a name that is a submodule as
that module (the package imports absolutely: a relative import fails, until the
reader reads it). A rule's exceptions are listed exactly, each with the box
that closes it: one closed and not struck fails too.
"""

import ast
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final, cast

import pytest

SRC: Final = Path(__file__).resolve().parent.parent / "src"

# 5 the entry; 4 the jobs and the grammar they read; 3 the planners (pure decisions,
# effects, subtitles, metadata files); 2 filtergraphs as data; 1 media (ffprobe, processes, paths);
# 0 what everything may use (errors, values, the version, stage A's number text)
LAYERS: Final[dict[str, int]] = {
    "ffman.__main__": 5,
    "ffman.cli": 5,
    "ffman.jobs": 4,
    "ffman.jobs.convert": 4,
    "ffman.jobs.convert.attach": 4,
    "ffman.jobs.convert.burn": 4,
    "ffman.jobs.convert.carried": 4,
    "ffman.jobs.convert.covers": 4,
    "ffman.jobs.convert.cuesheet": 4,
    "ffman.jobs.convert.dispatch": 4,
    "ffman.jobs.convert.fonts": 4,
    "ffman.jobs.convert.metadata": 4,
    "ffman.jobs.convert.options": 4,
    "ffman.jobs.convert.output": 4,
    "ffman.jobs.convert.passes": 4,
    "ffman.jobs.convert.remux": 4,
    "ffman.jobs.convert.render": 4,
    "ffman.jobs.convert.resize": 4,
    "ffman.jobs.convert.subtitles": 4,
    "ffman.jobs.convert.tagging": 4,
    "ffman.jobs.convert.youtube": 4,
    "ffman.jobs.meta": 4,
    "ffman.jobs.meta.io": 4,
    "ffman.jobs.meta.options": 4,
    "ffman.jobs.meta.run": 4,
    "ffman.options": 4,
    "ffman.plan": 3,
    "ffman.plan.encode": 3,
    "ffman.plan.flows": 3,
    "ffman.plan.geometry": 3,
    "ffman.plan.outputs": 3,
    "ffman.plan.request": 3,
    "ffman.plan.streams": 3,
    "ffman.plan.youtube": 3,
    "ffman.effects": 3,
    "ffman.effects.spec": 3,
    "ffman.effects.frame": 3,
    "ffman.effects.stages": 3,
    "ffman.effects.blur": 3,
    "ffman.effects.pixelate": 3,
    "ffman.effects.invert": 3,
    "ffman.effects.chromatic_aberration": 3,
    "ffman.effects.halation": 3,
    "ffman.effects.datamosh": 3,
    "ffman.effects.camcorder": 3,
    "ffman.effects.vhs": 3,
    "ffman.effects.dither": 3,
    "ffman.effects.crt": 3,
    "ffman.subs": 3,
    "ffman.subs.ass": 3,
    "ffman.subs.ingest": 3,
    "ffman.subs.normalize": 3,
    "ffman.subs.layout": 3,
    "ffman.subs.breaks": 3,
    "ffman.subs.colorize": 3,
    "ffman.subs.markup": 3,
    "ffman.subs.metrics": 3,
    "ffman.subs.paint": 3,
    "ffman.subs.srt": 3,
    "ffman.graph": 2,
    "ffman.graph.gif": 2,
    "ffman.graph.light": 2,
    "ffman.graph.resize": 2,
    "ffman.graph.sizes": 2,
    "ffman.media": 1,
    "ffman.media.flac": 1,
    "ffman.media.paths": 1,
    "ffman.media.probe": 1,
    "ffman.media.run": 1,
    "ffman": 0,
    "ffman.errors": 0,
    "ffman.fmt": 0,
    "ffman.values": 0,
}
MEDIA: Final = 1

# importer -> imported, against the layers: none since 6.1's moves; one added must
# say which box closes it
EXCEPTIONS: Final[frozenset[tuple[str, str]]] = frozenset()

# planners and graphs touch no file and no OS (§3: "pure"): a module that does,
# and the box that moves its I/O to the job
PURE: Final = frozenset({2, 3})
# not io: its StringIO is text in memory (io.open is an "open", caught below)
IO_MODULES: Final = frozenset({"os", "shutil", "tempfile", "subprocess"})
IO_CALLS: Final = frozenset(
    {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "unlink",
        "mkdir",
        "touch",
        "rename",
        "is_file",
        "is_dir",
        "exists",
        "stat",
        "iterdir",
        "glob",
    }
)
IMPURE: Final[frozenset[str]] = frozenset()  # none since 6.3: the job reads the transcript


def _modules() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted((SRC / "ffman").rglob("*.py")):
        parts = list(path.relative_to(SRC).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        found[".".join(parts)] = path
    return found


def _imports(module: str, path: Path, modules: dict[str, Path]) -> tuple[set[str], set[str]]:
    """``module``'s ffman imports (as modules) and the other top-level names it imports."""
    ours: set[str] = set()
    others: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                (ours if alias.name.split(".")[0] == "ffman" else others).add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            assert not node.level, f"{module}: a relative import -- teach this reader first"
            base = node.module or ""
            if base.split(".")[0] != "ffman":
                others.add(base.split(".")[0])
                continue
            for alias in node.names:
                sub = f"{base}.{alias.name}"
                ours.add(sub if sub in modules else base)
    return ours - {module}, {name.split(".")[0] for name in others}


def _graph() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    modules = _modules()
    pairs = {m: _imports(m, p, modules) for m, p in modules.items()}
    return {m: ours for m, (ours, _) in pairs.items()}, {
        m: others for m, (_, others) in pairs.items()
    }


def test_every_module_has_a_layer() -> None:
    assert set(_graph()[0]) == set(LAYERS)


def test_imports_point_down_but_for_the_listed_exceptions() -> None:
    up = {(m, i) for m, imported in _graph()[0].items() for i in imported if LAYERS[i] > LAYERS[m]}
    assert up == EXCEPTIONS


def test_no_import_cycle() -> None:
    graph = _graph()[0]
    state: dict[str, int] = {}  # 1 on the path, 2 done

    def visit(module: str, path: list[str]) -> None:
        state[module] = 1
        for imported in sorted(graph[module]):
            if state.get(imported) == 1:
                cycle = [*path[path.index(imported) :], imported]
                pytest.fail(f"an import cycle: {' -> '.join(cycle)}")
            if imported not in state:
                visit(imported, [*path, imported])
        state[module] = 2

    for module in sorted(graph):
        if module not in state:
            visit(module, [module])


def test_the_planners_and_graphs_touch_no_file() -> None:
    impure = set[str]()
    others = _graph()[1]
    for module, path in _modules().items():
        if LAYERS[module] not in PURE:
            continue
        tree = ast.parse(path.read_text())
        calls = {
            n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        if calls & IO_CALLS or others[module] & IO_MODULES:
            impure.add(module)
    assert impure == IMPURE


def test_only_media_starts_processes() -> None:
    starters = {m for m, others in _graph()[1].items() if "subprocess" in others}
    assert starters
    assert all(LAYERS[m] == MEDIA for m in starters), starters


# ffman's libraries (6.7.5): it may import them -- they never import it (their own
# test_imports.py) -- but only their public API, which their versions promise to keep
LIBRARIES: Final = ("ffmeta", "subverter")


def _library_names() -> list[tuple[str, str]]:
    """Each dotted name ffman reaches in a library, with where: imported, or an attribute's chain.

    An import binds a local name to what it names (``import ffmeta.cue``: ``ffmeta``; ``from
    ffmeta import vorbis``: ``ffmeta.vorbis``); a chain of attributes on one extends it. Scope is
    not read: a name bound anywhere counts in its whole module -- a collision fails, never passes.
    """
    found: list[tuple[str, str]] = []
    for module, path in _modules().items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in LIBRARIES:
                        found.append((f"{module}:{node.lineno}", alias.name))
                        local = alias.asname or alias.name.split(".")[0]
                        bound[local] = alias.name if alias.asname else local
            elif (
                isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in LIBRARIES
            ):
                for alias in node.names:
                    name = f"{node.module}.{alias.name}"
                    found.append((f"{module}:{node.lineno}", name))
                    bound[alias.asname or alias.name] = name
        inner = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        found += [
            (f"{module}:{node.lineno}", chain)
            for node in ast.walk(tree)  # a chain's outermost attribute: _public reads every part
            if isinstance(node, ast.Attribute)
            and id(node) not in inner
            and (chain := _chain(node, bound))
        ]
    return found


def _chain(node: ast.Attribute, bound: dict[str, str]) -> str:
    """An attribute chain's dotted name, if it starts at a bound name; else ""."""
    parts: list[str] = []
    value: ast.expr = node
    while isinstance(value, ast.Attribute):
        parts.insert(0, value.attr)
        value = value.value
    return (
        ".".join([bound[value.id], *parts])
        if isinstance(value, ast.Name) and value.id in bound
        else ""
    )


def _dunder(name: str) -> bool:
    """``__name__`` and its kind: every module's and object's protocol, not a library's API."""
    return name.startswith("__") and name.endswith("__")


def _public(dotted: str) -> bool:
    """Whether a library's dotted name is public: in each module, in its ``__all__`` or a submodule.

    Past the modules -- a public object's attribute, or a dunder, every module's protocol -- the
    rest is the object's own, but a private part is private wherever it stands.
    """
    root, *parts = dotted.split(".")
    if any(part.startswith("_") and not _dunder(part) for part in parts):
        return False
    reached: object = importlib.import_module(root)
    for part in parts:
        if not isinstance(reached, ModuleType) or _dunder(part):
            return True
        submodule = f"{reached.__name__}.{part}"
        if hasattr(reached, "__path__") and importlib.util.find_spec(submodule):
            reached = importlib.import_module(submodule)
        elif part in cast("tuple[str, ...] | list[str]", getattr(reached, "__all__", ())):
            reached = cast("object", getattr(reached, part))
        else:
            return False
    return True


def test_ffman_uses_its_libraries_public_api_alone() -> None:
    names = _library_names()
    assert names  # a reader that finds nothing proves nothing
    private = [f"{where}: {dotted}" for where, dotted in names if not _public(dotted)]
    assert private == []
