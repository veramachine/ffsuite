"""Parse a filtergraph's text as ffmpeg 8.1.2 does, into ffman.graph's data.

A transcription of libavutil's av_get_token and get_key/av_opt_get_key_value
and libavfilter's graph segment parser (n8.1.2), so two texts can be compared
by what ffmpeg reads from them (stage A's bash comparison, G1) and a rendered graph
by what it gives back (the round trip). Proven against ffmpeg itself: tests/
test_graph.py prints, through the metadata filter, the value ffmpeg read.
"""

from typing import Final

from ffman.graph import Arg, Chain, Filter, Graph

WHITESPACE: Final = " \n\t\r"


class ParseError(ValueError):
    """What ffmpeg would refuse to parse."""


def get_token(text: str, i: int, terms: str) -> tuple[str, int]:
    """av_get_token: the token from ``i`` to a character of ``terms``, and where it stopped."""
    while i < len(text) and text[i] in WHITESPACE:
        i += 1
    out: list[str] = []
    end = 0  # out's length up to which trailing whitespace is kept
    while i < len(text) and text[i] not in terms:
        c = text[i]
        i += 1
        if c == "\\" and i < len(text):
            out.append(text[i])
            i += 1
            end = len(out)
        elif c == "'":
            while i < len(text) and text[i] != "'":
                out.append(text[i])
                i += 1
            if i < len(text):
                i += 1
                end = len(out)
        else:
            out.append(c)
    while len(out) > end and out[-1] in WHITESPACE:
        _ = out.pop()
    return "".join(out), i


def _is_key_char(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c in "-_/.")


def _key(text: str, i: int) -> tuple[str, int] | None:
    """get_key: key characters, then (whitespace and) ``=``; None when there is no key."""
    j = i
    while j < len(text) and text[j] in WHITESPACE:
        j += 1
    start = j
    while j < len(text) and _is_key_char(text[j]):
        j += 1
    key = text[start:j]
    while j < len(text) and text[j] in WHITESPACE:
        j += 1
    if j >= len(text) or text[j] != "=":
        return None
    return key, j + 1


def parse_options(text: str) -> tuple[Arg, ...]:
    """ff_filter_opt_parse's split: positional values, then key=value pairs, ':'-separated."""
    args: list[Arg] = []
    keyed = False
    i = 0
    while i < len(text):
        found = _key(text, i)
        if found is not None:
            key, i = found
            value, i = get_token(text, i, ":")
            args.append((key, value))
            keyed = True
        elif keyed:  # after a key, ffmpeg rejects all remaining shorthand
            msg = f"No option name near '{text[i:]}'"
            raise ParseError(msg)
        else:
            value, i = get_token(text, i, ":")
            args.append(value)
        if i < len(text):
            i += 1  # the ':'
    return tuple(args)


def _labels(text: str, i: int) -> tuple[tuple[str, ...], int]:
    labels: list[str] = []
    while True:
        while i < len(text) and text[i] in WHITESPACE:
            i += 1
        if i >= len(text) or text[i] != "[":
            return tuple(labels), i
        name, i = get_token(text, i + 1, "]")
        if not name or i >= len(text):
            msg = "Bad (empty?) label, or mismatched '['"
            raise ParseError(msg)
        labels.append(name)
        i += 1


def _filter(text: str, i: int) -> tuple[Filter, tuple[str, ...], tuple[str, ...], int]:
    """parse_filter: input labels, the name, ``=options``, output labels."""
    ins, i = _labels(text, i)
    name, i = get_token(text, i, "=,;[")
    args: tuple[Arg, ...] = ()
    if i < len(text) and text[i] == "=":
        options, i = get_token(text, i + 1, "[],;")
        args = parse_options(options)
    outs, i = _labels(text, i)
    while i < len(text) and text[i] in WHITESPACE:
        i += 1
    return Filter(name, args), ins, outs, i


def _chain(text: str, i: int) -> tuple[Chain, int]:
    """chain_parse: filters ``,``-separated; labels only at the chain's ends."""
    filters: list[Filter] = []
    inputs: tuple[str, ...] = ()
    while True:
        f, ins, outs, i = _filter(text, i)
        if filters and ins:
            msg = "input labels in the middle of a chain"
            raise ParseError(msg)
        inputs = inputs if filters else ins
        filters.append(f)
        if i < len(text) and text[i] == ",":
            if outs:
                msg = "output labels in the middle of a chain"
                raise ParseError(msg)
            i += 1
            continue
        return Chain(tuple(filters), inputs, outs), i


def parse(text: str) -> Graph:
    """The graph ffmpeg reads from ``text`` (no ``sws_flags=`` prefix: ffman writes none)."""
    chains: list[Chain] = []
    i = 0
    while True:
        while i < len(text) and text[i] in WHITESPACE:
            i += 1
        if i >= len(text):
            break
        chain, i = _chain(text, i)
        chains.append(chain)
        if i < len(text) and text[i] == ";":
            i += 1
        elif i < len(text):
            msg = f"unexpected {text[i]!r}"
            raise ParseError(msg)
    if not chains:
        msg = "No filters specified in the graph description"
        raise ParseError(msg)
    return Graph(tuple(chains))
