"""Tests for lexic.parsing.earley.kernel.forest.support.readout — the decode seam.

What a finished kernel says about the parse it built: the accepting items, the
forest root, the decoded chart (including the deferred Leo chains ``to_chart``
expands first), and the readable form of a packed item.

Ported from ``test_kernel.py`` when ``readout.py`` was split out — assertions
unchanged.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import derivations
from lexic.parsing.earley.kernel.forest.chart import Chart
from lexic.parsing.earley.kernel.forest.forest import ParseTree, SppfNode
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_item,
    accept_items,
    accept_node,
    decode_item,
    root_ambiguous,
    start_completion_ends,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ORIGIN_MASK
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import (
    norm,
    star,
)
from tests.unit.lexic.parsing.ir_fixtures import word_grammar as _word_grammar

# ── to_chart / accept_node decode shapes ──────────────────────────────


def test_accept_node_returns_sppf_node_on_success():
    """accept_node() returns an SppfNode when accept >= 0."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "5", record_links=True).run()
    node = accept_node(kernel)
    assert isinstance(node, SppfNode)


def test_accept_node_returns_ir_none_on_failure():
    """accept_node() returns IrNone (IrNoneType) when accept == -1."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "z", record_links=True).run()
    assert accept_item(kernel) == -1
    node = accept_node(kernel)
    assert isinstance(node, IrNoneType)


def test_to_chart_returns_chart_with_links():
    """to_chart() returns a Chart whose links table has entries."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi", record_links=True).run()
    chart = to_chart(kernel)
    assert isinstance(chart, Chart)
    assert len(chart.links) > 0


# ── expand_leo chain rebuild ────────────────────────────────────────────


def test_expand_leo_via_to_chart_reconstructs_unambiguous_derivation():
    """to_chart() (which expands all leo_links) lets derivations() reconstruct
    the single unambiguous derivation for a long right-recursive input."""
    g = star("a")
    text = "a" * 60
    trees = derivations(g, text)
    assert len(trees) == 1
    assert isinstance(trees[0], ParseTree)


def test_to_chart_idempotent_across_repeat_calls():
    """Calling to_chart() twice on the same finished kernel agrees / no exception."""
    g = star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a" * 60, record_links=True).run()
    chart1 = to_chart(kernel)
    chart2 = to_chart(kernel)
    assert len(chart1.links) == len(chart2.links)


def embedded_ambiguous() -> IrAst:
    """w = p ; p = u u* ; u = [ab]+ — p's split ambiguity embedded under w."""
    ab = IrCharClass(IrRange(IrChr(97), IrChr(98)))
    return norm(
        IrRule("w", IrAlternation(IrSequence(IrItem(IrRuleRef("p"))))),
        IrRule(
            "p",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("u")),
                    IrItem(IrRuleRef("u"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule("u", IrAlternation(IrSequence(IrItem(ab, IrQuantifier(1, IrNone))))),
        start="w",
    )


def test_to_chart_expands_leo_links_under_mixed_provenance():
    """A Leo top that also gained normal-completer families keeps its chains.

    Over "aab" the embedded grammar records p's whole-input completion both
    through the normal completer (two families in ``links``) and through a
    deferred Leo chain (one more in ``leo_links``) — mixed provenance.
    ``to_chart()`` must materialise the deferred family too (L4: the old
    ``key not in links`` guard silently dropped it).
    """
    tables = compile_tables(embedded_ambiguous())
    kernel = Kernel(tables, "aab", record_links=True).run()
    mixed = [k for k in kernel.st.leo_links if k in kernel.st.links]
    assert mixed  # the L4 precondition: mixed provenance actually occurs here
    to_chart(kernel)
    for key in mixed:
        for entry in kernel.st.leo_links[key]:
            assert entry in kernel.st.links[key]


# ── decode_item ──────────────────────────────────────────────────────────


def test_decode_item_returns_earley_item_shape():
    """decode_item(item) returns the (IrRuleRef, IrSequence, dot, origin) tuple."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "5", record_links=True).run()
    decoded = decode_item(kernel.tables, accept_item(kernel))
    assert isinstance(decoded, tuple)
    assert len(decoded) == 4
    rule_ref, seq, dot, origin = decoded
    assert isinstance(rule_ref, IrRuleRef)
    assert rule_ref == IrRuleRef("digit")
    assert dot == len(seq)
    assert origin == 0


# ── accept_items / root_ambiguous (L2 root arm-choice) ────────────────


def twin_arm_grammar() -> IrAst:
    """v ::= a | b, a/b both "x" — the start completes the whole input two ways."""
    return norm(
        IrRule("v", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
        IrRule("a", IrLiteral("x")),
        IrRule("b", IrLiteral("x")),
        start="v",
    )


def test_accept_items_lists_every_accepting_production():
    """A twin-arm start yields two accepting items (one per production)."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "x", record_links=True).run()
    items = accept_items(kernel)
    assert len(items) == 2
    # Both are origin-0 completions of the start rule over the whole input.
    for it in items:
        assert it & ORIGIN_MASK == 0
        assert decode_item(kernel.tables, it)[0] == IrRuleRef("v")


def test_accept_items_empty_on_no_parse():
    """accept_items() is empty when the input does not derive."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "z", record_links=True).run()
    assert accept_items(kernel) == []


def test_root_ambiguous_true_for_twin_arms():
    """root_ambiguous is True when the start completes via ≥2 productions."""
    kernel = Kernel(compile_tables(twin_arm_grammar()), "x", record_links=True).run()
    assert root_ambiguous(kernel) is True


def test_root_ambiguous_false_for_single_production():
    """root_ambiguous is False for an unambiguous single-production accept."""
    kernel = Kernel(compile_tables(_digit_grammar()), "5", record_links=True).run()
    assert root_ambiguous(kernel) is False


# ── start_completion_ends — the island seam's cross-span evidence ─────


def test_start_completion_ends_lists_every_origin_zero_end(sss_grammar):
    """``s = s s / 'a'`` over 'aaa' completes from origin 0 at 1, 2 and 3."""
    kern = Kernel(compile_tables(sss_grammar), "aaa")
    kern.longest_start_completion()
    assert start_completion_ends(kern) == (1, 2, 3)


def test_start_completion_ends_single_on_unambiguous(sss_grammar):
    """A one-char window has the single end its one completion spans."""
    kern = Kernel(compile_tables(sss_grammar), "a")
    kern.longest_start_completion()
    assert start_completion_ends(kern) == (1,)


def test_start_completion_ends_empty_on_no_parse(sss_grammar):
    """No origin-0 completion anywhere → no ends."""
    kern = Kernel(compile_tables(sss_grammar), "x")
    kern.longest_start_completion()
    assert not start_completion_ends(kern)
