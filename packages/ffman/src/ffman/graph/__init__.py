r"""Filtergraphs as data, rendered for ``-filter_complex`` with ffmpeg's escaping.

A value is held raw and escaped once, here, at the two levels ffmpeg parses
(doc/filters.texi, "Notes on filtergraph escaping", n8.1.2): in an option's
value, ``\ ' : =`` (``=`` too: a positional ``a=b`` would read as a key); in the
filter's whole description, ``\ ' [ ] , ;``. At both, leading and trailing
whitespace, which ``av_get_token`` trims unless escaped. No shell level: argv
reaches ffmpeg as is. Positional values come before keyed ones, which is all
ffmpeg accepts (``ff_filter_opt_parse``). The bash ffman quoted some values
and escaped others by hand; the texts differ, what ffmpeg parses does not
(stage A's bash comparison compared graphs as ffmpeg parses them).
"""

import re
from dataclasses import dataclass, field, replace
from typing import Final

_NAME: Final = re.compile(r"[a-z0-9_]+")  # a filter's name (all are lowercase)
# an option's key: is_key_char's alphabet (libavutil/opt.c) -- gblur's sigmaV
_KEY: Final = re.compile(r"[A-Za-z0-9_./-]+")
_LABEL: Final = re.compile(r"[A-Za-z0-9_.:]+")  # a link's label, or a stream (0:v:0)
_WHITESPACE: Final = " \n\t\r"  # av_get_token's (libavutil/avstring.c)
_IN_VALUE: Final = "\\':="
_IN_DESCRIPTION: Final = "\\'[],;"

type Arg = str | tuple[str, str]  # a positional value, or (key, value)


def _escape(text: str, special: str) -> str:
    """Backslash every special character, and whitespace at either end."""
    last = len(text) - 1
    return "".join(
        f"\\{c}" if c in special or (c in _WHITESPACE and i in (0, last)) else c
        for i, c in enumerate(text)
    )


def escape_value(value: str) -> str:
    """An option's value, escaped for the option list (level 1)."""
    return _escape(value, _IN_VALUE)


def escape_description(description: str) -> str:
    """A filter's option list, escaped for the graph (level 2)."""
    return _escape(description, _IN_DESCRIPTION)


def _check(pattern: re.Pattern[str], text: str, what: str) -> str:
    if pattern.fullmatch(text) is None:
        msg = f"not a valid {what}: {text!r}"
        raise ValueError(msg)
    return text


@dataclass(frozen=True, slots=True)
class Filter:
    """One filter: its name, then positional values, then keyed ones (raw, unescaped)."""

    name: str
    args: tuple[Arg, ...] = ()

    def __post_init__(self) -> None:
        """Refuse what ffmpeg would: a bad name or key, a positional value after a key."""
        _ = _check(_NAME, self.name, "filter name")
        keyed = False
        for arg in self.args:
            if isinstance(arg, tuple):
                _ = _check(_KEY, arg[0], "option key")
                keyed = True
            elif keyed:
                msg = f"{self.name}: a positional value after a keyed one: {arg!r}"
                raise ValueError(msg)
            elif not arg:  # "f=" is no option at all; "f=x:" drops the last: unreadable
                msg = f"{self.name}: an empty positional value"
                raise ValueError(msg)

    def render(self) -> str:
        """``name`` or ``name=escaped options``."""
        if not self.args:
            return self.name
        parts = (
            f"{a[0]}={escape_value(a[1])}" if isinstance(a, tuple) else escape_value(a)
            for a in self.args
        )
        return f"{self.name}={escape_description(':'.join(parts))}"


@dataclass(frozen=True, slots=True)
class Chain:
    """Filters in sequence, from input labels to output labels."""

    filters: tuple[Filter, ...]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """A chain has a filter; every label is a valid one."""
        if not self.filters:
            msg = "a chain needs a filter"
            raise ValueError(msg)
        for label in (*self.inputs, *self.outputs):
            _ = _check(_LABEL, label, "label")

    def render(self) -> str:
        """``[in]f1,f2[out]``."""
        labels_in = "".join(f"[{label}]" for label in self.inputs)
        labels_out = "".join(f"[{label}]" for label in self.outputs)
        return labels_in + ",".join(f.render() for f in self.filters) + labels_out


@dataclass(frozen=True, slots=True)
class Graph:
    """Chains, rendered ``;``-separated: the text of ``-filter_complex``."""

    chains: tuple[Chain, ...]

    def __post_init__(self) -> None:
        """A graph has a chain."""
        if not self.chains:
            msg = "a graph needs a chain"
            raise ValueError(msg)

    def render(self) -> str:
        """The graph's text."""
        return ";".join(chain.render() for chain in self.chains)


NULL: Final = Filter("null")  # what an empty chain holds


@dataclass(frozen=True, slots=True)
class Open:
    """A graph being built: the chains finished, and the one still open.

    The open chain is where the next filters go -- the bash ffman appended them
    to its filter text with ``,`` -- until it is closed into labels.
    """

    inputs: tuple[str, ...]
    filters: tuple[Filter, ...] = ()
    chains: tuple[Chain, ...] = ()

    def then(self, *filters: Filter) -> "Open":
        """The open chain, extended."""
        return replace(self, filters=(*self.filters, *filters))

    def end(self, outputs: tuple[str, ...]) -> tuple[Chain, ...]:
        """Every chain, the open one closed into ``outputs`` (``null`` when it holds none)."""
        return (*self.chains, Chain(self.filters or (NULL,), self.inputs, outputs))

    def close(self, *outputs: str) -> Graph:
        """The graph, the open chain closed into ``outputs``."""
        return Graph(self.end(outputs))


@dataclass(slots=True)
class Labels:
    """Fresh link labels for one graph: ``stem``, then ``stem2``, ``stem3``..."""

    _used: set[str] = field(default_factory=set[str])

    def new(self, stem: str) -> str:
        """A label not handed out before in this graph."""
        _ = _check(_NAME, stem, "label stem")
        label, n = stem, 1
        while label in self._used:
            n += 1
            label = f"{stem}{n}"
        self._used.add(label)
        return label
