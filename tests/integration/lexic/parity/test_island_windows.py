"""An island's grown window is the chart a fresh window of its final width builds.

`island_parse` climbs by growing one chart (:class:`~lexic.parsing.earley.resume
.WindowKernel`) instead of re-parsing each width. That is sound only if growing
changes nothing a reader can see, so every climb the suites drive is read here
against a window opened at its final width directly: the same columns in the same
order, the same families in the same order, the same delegated completions.
One witness climbs with an interior delegate whose word crosses the first
window's edge, so a completion filed past the stop and set aside is part of
what is compared.

And the construction fact the growth leans on: island tables are never
run-collapsed, because `PdaTables` compiles them plain.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lexic.compile import compile_text
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.resume import WindowKernel
from lexic.parsing.pda.runtime import islands
from lexic.parsing.pda.runtime.islands import ISLAND_WINDOW, IslandPolicy, island_parse
from tests.unit.lexic.parsing.pda.runtime.test_islands import cut_literal_tables
from tools.benchmark.cases.grammars import BENCHES


def _opened(parse: Callable[[], object]) -> list[tuple[WindowKernel, tuple]]:
    """Every window an island opened while ``parse`` ran, with how it opened."""
    seen: list[tuple[WindowKernel, tuple]] = []
    real = islands.island_run

    def opened(tables, text, pos, width, delegates=None):
        kern = real(tables, text, pos, width, delegates)
        seen.append((kern, (tables, text, pos, delegates)))
        return kern

    islands.island_run = opened
    try:
        parse()
    finally:
        islands.island_run = real
    return seen


def _chart(kern: WindowKernel) -> tuple:
    """Everything a reader of the window can see, order included."""
    st = kern.st
    return (
        kern.text,
        kern.cols,
        st.seen,
        st.waiting,
        st.scannable,
        st.predicted,
        st.leo,
        {key: [_family(link) for link in links] for key, links in st.links.items()},
        st.leo_links,
        st.groups,
        {key: (leaf.text, repr(leaf.payload)) for key, leaf in kern.delegated.items()},
    )


def _family(link: tuple) -> tuple:
    """A family, its delegated child read by value: two charts' payload leaves
    are two objects."""
    child = link[2]
    if isinstance(child, PayloadLeaf):
        child = (child.text, repr(child.payload))
    return (link[0], link[1], child)


def _climbed(parse: Callable[[], object]) -> list[tuple[WindowKernel, WindowKernel]]:
    """Each window that grew, regrown width by width as the island grew it,
    beside a fresh one opened at its final width — both read before anything
    decodes them (a decode expands Leo chains into the families)."""
    pairs = []
    for kern, (tables, text, pos, delegates) in _opened(parse):
        width = min(ISLAND_WINDOW, len(text) - pos)
        if kern.stop == width:
            continue  # it never grew
        grown = WindowKernel(tables, text, pos, width, delegates).run()
        while grown.stop < kern.stop:
            width *= 2
            grown.grow(min(width, len(text) - pos))
        fresh = WindowKernel(tables, text, pos, kern.stop, delegates).run()
        pairs.append((grown, fresh))
    return pairs


def _x_tables():
    """``x ::= x "a" | "a"`` — the climb with nothing to refuse."""
    rule = IrRule(
        "x",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("x")), IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("a"))),
        ),
    )
    return compile_tables(IrAst(rules=IrSeq(rule), start="x"))


def _bench_parse(name: str, sample: str) -> Callable[[], object]:
    bench = next(b for b in BENCHES if b.name == name)
    return lambda: bench.compiled.parse(getattr(bench, sample), cores=1)


DELEGATED_CLIMB = (
    'root ::= item tail\nitem ::= more "a" | more "b" | word\nmore ::= item\n'
    'word ::= "z" [c-y]+\ntail ::= "zz\\n"\n'
)
"""relay-climb's island with a delegated base: ``word`` is conflict-free and
loops, so the sub-parse completes it through a delegate. Left-recursive through
the relay ``more``, so the fold leaves ``item`` an island."""

DELEGATED_TEXT = "z" + "c" * 300 + "a" * 300 + "zz\n"
"""A word longer than the first window, so its delegate lands past the stop."""


def _delegated_parse() -> object:
    compiled = compile_text(DELEGATED_CLIMB, cache_key="island-windows-delegated")
    return compiled.parse(DELEGATED_TEXT, cores=1)


CLIMBS = {
    "relay-climb corpus": _bench_parse("relay-climb", "corpus"),
    "relay-climb full": _bench_parse("relay-climb", "full"),
    "a delegate past the first edge": _delegated_parse,
    "x over two windows": lambda: island_parse(
        _x_tables(), "a" * (2 * ISLAND_WINDOW), 0, "x", IslandPolicy()
    ),
    "a literal across the edge": lambda: island_parse(
        cut_literal_tables(), "a" * (ISLAND_WINDOW - 2) + "bcd", 0, "x"
    ),
}
"""The climbs the suites drive: the bench row that climbs, the noise family whose
climb whose delegate lands past the first window, and the unit climbs."""


@pytest.mark.parametrize("label", CLIMBS)
def test_a_grown_window_is_the_chart_of_its_final_width(label: str) -> None:
    """Growing the window leaves exactly the chart a fresh window builds."""
    pairs = _climbed(CLIMBS[label])
    assert pairs, f"{label} no longer climbs"
    for grown, fresh in pairs:
        assert _chart(grown) == _chart(fresh)


def test_the_delegating_climb_delegates_past_its_first_edge() -> None:
    """The delegated word ends past the first window, so the comparison above
    covers a completion the anchored delegate filed beyond the stop."""
    pairs = _climbed(_delegated_parse)
    assert len(pairs) == 1, pairs
    grown = pairs[0][0]
    ends = [key & grown.tables.packing.mask for key in grown.delegated]
    assert ends == [DELEGATED_TEXT.index("a")], ends
    assert ends[0] > ISLAND_WINDOW


ISLAND_HOSTS = {
    **{bench.name: bench.compiled for bench in BENCHES},
    "delegated climb": compile_text(DELEGATED_CLIMB, cache_key="island-windows-hosts"),
}
"""Every roster grammar, and the delegated climb, whose ``word ::= "z" [c-y]+``
is the loop a run terminal would collapse anywhere but an island."""


@pytest.mark.parametrize("label", ISLAND_HOSTS)
def test_no_island_table_is_run_collapsed(label: str) -> None:
    """Every island's tables are plain, so no window ever holds a run terminal,
    whose maximal run would depend on input past its stop."""
    pda = ISLAND_HOSTS[label].pda_tables()
    for name in pda.islands:
        lens = pda.island_tables(name).terms.lens
        assert all(length != 0 for length in lens), f"{label}: {name}"
