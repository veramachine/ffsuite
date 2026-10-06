"""subverter imports nothing but itself and the standard library: its dependencies are none.

uv cannot ensure it -- a workspace member can import what another declares (its docs) -- so this
does, read from the source's syntax trees: every ``import`` and ``from ... import``, wherever it
stands, against the running Python's standard library (the pin's is the floor's, 3.13: a later
one may add names). A relative import, ``importlib`` whole, or ``__import__`` is refused too:
this reader would not see where it leads.
"""

import ast
import sys
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[1] / "src" / "subverter"
_DYNAMIC: Final = frozenset({"importlib", "__import__"})


def _imports() -> list[tuple[str, str]]:
    """Each import's module (its top-level name), with where it stands."""
    found: list[tuple[str, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        where = path.relative_to(SRC.parent).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found += [
                    (alias.name.split(".")[0], f"{where}:{node.lineno}") for alias in node.names
                ]
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                found.append((module.split(".")[0] or module, f"{where}:{node.lineno}"))
            elif (isinstance(node, ast.Name) and node.id == "__import__") or (
                isinstance(node, ast.Attribute) and node.attr == "__import__"  # builtins.__import__
            ):
                found.append(("__import__", f"{where}:{node.lineno}"))
    return found


def test_it_imports_itself_and_the_standard_library_alone() -> None:
    imports = _imports()
    assert imports  # a reader that finds nothing proves nothing
    outside = [
        f"{where}: {module}"
        for module, where in imports
        if module in _DYNAMIC or (module != "subverter" and module not in sys.stdlib_module_names)
    ]
    assert outside == []
