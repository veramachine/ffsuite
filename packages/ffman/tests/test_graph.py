import re
import subprocess
from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ffman.graph import Chain, Filter, Graph, Labels, escape_description, escape_value
from tests.support.filtergraph import ParseError, get_token, parse


def test_rendering() -> None:
    graph = Graph(
        (
            Chain((Filter("split", ("2",)),), ("0:v:0",), ("a", "b")),
            Chain(
                (Filter("scale", ("64", "36", ("flags", "lanczos+accurate_rnd"))), Filter("null")),
                ("a",),
                ("c",),
            ),
            Chain((Filter("overlay", (("x", "(W-w)/2"),)),), ("b", "c")),
        )
    )
    assert (
        graph.render()
        == "[0:v:0]split=2[a][b];[a]scale=64:36:flags=lanczos+accurate_rnd,null[c];[b][c]overlay=x=(W-w)/2"
    )


@pytest.mark.parametrize(
    ("value", "level1", "level2"),
    [
        ("pow(val/65535,2.4)", "pow(val/65535,2.4)", r"pow(val/65535\,2.4)"),
        ("dir/a:b,c.ass", r"dir/a\:b,c.ass", r"dir/a\\:b\,c.ass"),
        ("it's", r"it\'s", r"it\\\'s"),
        ("a=b", r"a\=b", r"a\\=b"),
        (" x ", r"\ x\ ", r"\\ x\\\ "),  # level 2: only the last space is at an edge
        ("", "", ""),
    ],
)
def test_the_two_levels(value: str, level1: str, level2: str) -> None:
    assert escape_value(value) == level1
    assert escape_description(level1) == level2


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Filter("Scale"), "not a valid filter name: 'Scale'"),
        (
            lambda: Filter("scale", (("w", "1"), "2")),
            "scale: a positional value after a keyed one: '2'",
        ),
        (lambda: Filter("scale", (("w h", "1"),)), "not a valid option key: 'w h'"),
        (lambda: Filter("scale", (("w=h", "1"),)), "not a valid option key: 'w=h'"),
        (lambda: Filter("scale", ("",)), "scale: an empty positional value"),
        (lambda: Chain((), ("a",)), "a chain needs a filter"),
        (lambda: Chain((Filter("null"),), ("a]b",)), "not a valid label: 'a]b'"),
        (lambda: Graph(()), "a graph needs a chain"),
    ],
)
def test_what_ffmpeg_would_refuse_is_refused_here(
    build: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        _ = build()


def test_labels_are_fresh() -> None:
    labels = Labels()
    assert [labels.new("v"), labels.new("v"), labels.new("v"), labels.new("bg")] == [
        "v",
        "v2",
        "v3",
        "bg",
    ]


# Values: any text at all, half their characters the ones escaping is about -- drawn
# uniformly from all of unicode, those are almost never drawn (mutants survived).
SPECIAL = st.sampled_from(list("\\':=,;[] \t"))
VALUES = st.text(
    alphabet=st.one_of(SPECIAL, st.characters(codec="utf-8", exclude_categories=("Cs",))),
    max_size=24,
)
KEYS = st.from_regex(r"[A-Za-z0-9_./-]{1,7}", fullmatch=True)  # ffmpeg's key alphabet, not a guess
NAMES = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)
LABELS = st.from_regex(r"[A-Za-z0-9_.:]{1,8}", fullmatch=True)


@st.composite
def filters(draw: st.DrawFn) -> Filter:
    positional = draw(st.lists(VALUES.filter(bool), max_size=2))
    keyed = draw(st.lists(st.tuples(KEYS, VALUES), max_size=3))
    return Filter(draw(NAMES), (*positional, *keyed))


@st.composite
def chains(draw: st.DrawFn) -> Chain:
    body = draw(st.lists(filters(), min_size=1, max_size=3))
    return Chain(
        tuple(body),
        tuple(draw(st.lists(LABELS, max_size=2))),
        tuple(draw(st.lists(LABELS, max_size=2))),
    )


@st.composite
def graphs(draw: st.DrawFn) -> Graph:
    return Graph(tuple(draw(st.lists(chains(), min_size=1, max_size=3))))


@given(graphs())
def test_what_is_rendered_parses_back(graph: Graph) -> None:
    assert parse(graph.render()) == graph


def test_the_tokenizer_as_ffmpeg() -> None:
    # av_get_token's own edges (libavutil/avstring.c, n8.1.2)
    assert get_token("  a b  ", 0, ":") == ("a b", 7)
    assert get_token(r"a\ ", 0, ":") == ("a ", 3)  # an escaped space stays
    assert get_token("'a '  ", 0, ":") == ("a ", 6)  # so does a quoted one
    assert get_token("'a  ", 0, ":") == ("a", 4)  # an unclosed quote: trimmed
    assert get_token("a\\", 0, ":") == ("a\\", 2)  # a last backslash: kept
    with pytest.raises(ParseError, match="No option name"):
        _ = parse("f=k=v:positional")


# Against ffmpeg itself (8.1.2, the pin; conftest's fixture): what it read, printed by the metadata filter.
def read_back(ffmpeg: str, graph_text: str) -> str | None:
    """The value ffmpeg's metadata filter stored and printed; None if ffmpeg refused the graph."""
    run = subprocess.run(  # noqa: S603 -- ffmpeg, checked by the fixture
        [ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-f", "lavfi", "-i", "color=s=16x16:d=0.04",
         "-filter_complex", graph_text, "-frames:v", "1", "-f", "null", "-"],
        capture_output=True,
        check=False,
    )  # fmt: skip
    if run.returncode != 0:
        return None
    for line in run.stderr.decode("utf-8", "replace").split("\n"):
        if "Parsed_metadata" in line and "] k=" in line:
            return line.split("] k=", 1)[1]
    return None


PRINTABLE = st.text(  # printed one per line: no control characters
    alphabet=st.one_of(
        SPECIAL.filter(lambda c: c != "\t"),
        st.characters(codec="utf-8", exclude_categories=("Cs", "Cc")),
    ),
    max_size=24,
)


@pytest.mark.ffmpeg
@settings(max_examples=60, deadline=None)  # each example runs ffmpeg: its time is the machine's
@given(PRINTABLE)
def test_any_value_reaches_ffmpeg_unchanged(ffmpeg: str, value: str) -> None:
    add = Filter("metadata", (("mode", "add"), ("key", "k"), ("value", value)))
    graph = Graph((Chain((add, Filter("metadata", (("mode", "print"),))), ("0:v",)),))
    assert read_back(ffmpeg, graph.render()) == value


RAW = st.text(alphabet=" abc:=,;[]'\\", max_size=16)


@pytest.mark.ffmpeg
@settings(max_examples=80, deadline=None)  # each example runs ffmpeg: its time is the machine's
@given(RAW)
def test_the_parser_reads_what_ffmpeg_reads(ffmpeg: str, raw: str) -> None:
    text = f"[0:v]metadata=mode=add:key=k:value={raw},metadata=mode=print"
    theirs = read_back(ffmpeg, text)
    if theirs is None:  # ffmpeg refused it: nothing to compare
        return
    ours = parse(text).chains[0].filters[0].args[2]
    assert ours == ("value", theirs)


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "raw", [r"'pow(val/65535\,2.4)*65535'", r"a\\\:b", r"'t\'", r"\ x\ ", r"'x':'y'"]
)
def test_the_parser_reads_bashs_quoted_forms(ffmpeg: str, raw: str) -> None:
    text = f"[0:v]metadata=mode=add:key=k:value={raw},metadata=mode=print"
    theirs = read_back(ffmpeg, text)
    if theirs is None:  # refused by ffmpeg for its syntax: refused here too
        with pytest.raises(ParseError):
            _ = parse(text)
    else:
        assert parse(text).chains[0].filters[0].args[2] == ("value", theirs)


SAFE = ["null", "hflip", "vflip", "format=yuv420p", "scale=16:16"]


@pytest.mark.ffmpeg
@settings(max_examples=40, deadline=None)  # each example runs ffmpeg: its time is the machine's
@given(
    st.lists(st.sampled_from(SAFE), min_size=1, max_size=4),
    st.lists(PRINTABLE, max_size=2),
    st.booleans(),
)
def test_every_graph_built_runs(
    ffmpeg: str, names: list[str], values: list[str], branch: bool
) -> None:
    labels = Labels()
    body = [
        Filter(n.split("=")[0], tuple(n.split("=")[1].split(":")) if "=" in n else ())
        for n in names
    ]
    body += [
        Filter("metadata", (("mode", "add"), ("key", f"k{i}"), ("value", v)))
        for i, v in enumerate(values)
    ]
    out = labels.new("out")
    if branch:
        a, b, c = labels.new("a"), labels.new("b"), labels.new("c")
        chains = (
            Chain((Filter("split", ("2",)),), ("0:v",), (a, b)),
            Chain(tuple(body), (a,), (c,)),
            Chain((Filter("overlay"),), (b, c), (out,)),
        )
    else:
        chains = (Chain(tuple(body), ("0:v",), (out,)),)
    run = subprocess.run(  # noqa: S603 -- ffmpeg, checked by the fixture
        [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=s=16x16:d=0.04",
         "-filter_complex", Graph(chains).render(), "-map", f"[{out}]", "-frames:v", "1", "-f", "null", "-"],
        capture_output=True,
        check=False,
    )  # fmt: skip
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
