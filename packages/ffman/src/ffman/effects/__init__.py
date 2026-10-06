"""The effects registry: what each effect takes, the ``--vfx`` grammar, the catalogue.

A spec is ``NAME[:ARG[,ARG...]]``; an ARG is the main parameter's value (first
only) or ``KEY=VALUE``. Only the first ``:`` ends the name, only ``,`` separates
arguments, only the first ``=`` ends a key -- so ``time=23:59:58`` parses. No
value means auto. The order they run in is their stage's, not the listing's
(docs/ffman-python.md section 3.3). Ranges and messages are the bash ffman's
(``fx_validate``), the flag replaced by the spec.
"""

from types import MappingProxyType
from typing import Final

from ffman.effects import (
    blur,
    camcorder,
    chromatic_aberration,
    crt,
    datamosh,
    dither,
    halation,
    invert,
    pixelate,
    vhs,
)
from ffman.effects.spec import Effect, Param, Request
from ffman.errors import refuse

# The registry, in the order the bash ffman listed and ran them
VIDEO: Final = (
    blur.EFFECT,
    pixelate.EFFECT,
    invert.EFFECT,
    chromatic_aberration.EFFECT,
    halation.EFFECT,
    datamosh.EFFECT,
    camcorder.EFFECT,
    vhs.EFFECT,
    dither.EFFECT,
    crt.EFFECT,
)
_BY_NAME: Final = {effect.name: effect for effect in VIDEO}


def parse_spec(spec: str) -> Request:
    """Parse one ``--vfx`` spec."""
    name, colon, args = spec.partition(":")
    effect = _BY_NAME.get(name)
    if effect is None:
        refuse(f"--vfx: unknown effect: {name} (see ffman effects)")
    values: dict[str, str] = {}
    if colon:
        for position, arg in enumerate(args.split(",")):
            key, equals, value = arg.partition("=")
            if not equals:
                key, value = _main_param(effect, spec, position), arg
            _set(effect, values, key, value)
    return Request(effect, MappingProxyType(values))  # read-only: validated once


def parse_specs(specs: list[str]) -> tuple[Request, ...]:
    """Parse every ``--vfx``; an effect twice is refused."""
    requests = tuple(parse_spec(spec) for spec in specs)
    seen: set[str] = set()
    for request in requests:
        if request.effect.name in seen:
            refuse(f"--vfx {request.effect.name} given twice")
        seen.add(request.effect.name)
    return requests


def _main_param(effect: Effect, spec: str, position: int) -> str:
    if not effect.params:
        refuse(f"--vfx {effect.name} takes no value: {spec}")
    if not effect.positional:
        keys = ", ".join(f"{p.name}=" for p in effect.params)
        refuse(f"--vfx {effect.name} takes named values ({keys}): {spec}")
    if position > 0:
        refuse(f"--vfx {effect.name}: only the first value may go without a name: {spec}")
    return effect.params[0].name


def _set(effect: Effect, values: dict[str, str], key: str, value: str) -> None:
    param = next((p for p in effect.params if p.name == key), None)
    if param is None:
        known = ", ".join(p.name for p in effect.params) or "none"
        refuse(f"--vfx {effect.name}: unknown parameter: {key} ({known})")
    if key in values:
        refuse(f"--vfx {effect.name}: {key} given twice")
    if not ((param.auto and value == "auto") or param.check(value)):
        refuse(f"--vfx {effect.name}: {param.must}: {value}")
    values[key] = value


def format_catalogue(name: str | None = None) -> str:
    """The catalogue: every video effect in stage order, or the one named."""
    effects = sorted(VIDEO, key=lambda e: e.stage) if name is None else [_named(name)]
    lines = (
        []
        if name is not None
        else ["Video effects, in the order they run (--vfx NAME[:VALUE]):", ""]
    )
    for effect in effects:
        lines.append(f"  {effect.name:<22}{effect.about}")
        lines += [f"  {'':<22}  {_describe(param)}" for param in effect.params]
    return "\n".join(lines) + "\n"


def _describe(param: Param) -> str:
    """``name: range (auto: meaning)``, the range read from the refusal's own text."""
    allowed = param.must.removeprefix(f"{param.name} ").removeprefix("must be ")
    unset = "auto" if param.auto else "left out"
    return f"{param.name}: {allowed} ({unset}: {param.unset})"


def _named(name: str) -> Effect:
    effect = _BY_NAME.get(name)
    if effect is None:
        refuse(f"unknown effect: {name} (see ffman effects)")
    return effect
