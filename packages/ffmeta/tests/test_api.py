"""ffmeta's root exports every type its API takes or returns, directly or as a field of one.

A type reached and not exported fails here: a user would have to dig into a submodule for it.
"""

import dataclasses
import typing
from typing import cast

import ffmeta


def _types_in(hint: object) -> list[type]:
    """The package's own classes a type hint names: through aliases, unions, generics."""
    if isinstance(hint, typing.TypeAliasType):
        return _types_in(cast("object", hint.__value__))
    if isinstance(hint, type):
        return [hint] if hint.__module__.split(".")[0] == "ffmeta" else []
    arguments = cast("tuple[object, ...]", typing.get_args(hint))
    return [found for argument in arguments for found in _types_in(argument)]


def _reached() -> set[type]:
    """Every class of the package the root's names reach: their signatures, their fields."""
    reached: set[type] = set()
    todo: list[object] = [getattr(ffmeta, name) for name in ffmeta.__all__]
    while todo:
        thing = todo.pop()
        if isinstance(thing, type):
            if thing in reached:
                continue
            reached.add(thing)
            fields = dataclasses.is_dataclass(thing)
            hints = cast("dict[str, object]", typing.get_type_hints(thing)) if fields else {}
        elif callable(thing):
            hints = cast("dict[str, object]", typing.get_type_hints(thing))
        else:  # a type alias, the classes it names; a constant, none
            todo.extend(_types_in(thing))
            continue
        todo.extend(found for value in hints.values() for found in _types_in(value))
    return reached


def test_the_root_exports_every_type_its_api_reaches() -> None:
    assert {kind.__name__ for kind in _reached()} - set(ffmeta.__all__) == set()
