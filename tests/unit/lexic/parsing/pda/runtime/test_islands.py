"""Tests for lexic.parsing.pda.runtime.islands — the island sub-parse + splice.

Shed from :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` as free functions
(Task 2b): a windowed Earley sub-parse over a small real grammar, driven
through the module's three public entry points directly. The functions are
already covered end-to-end by the ``parse_pda`` parity/fallback suites, so
this file targets the function-level contracts (return shapes, the two
``PdaFail`` messages) rather than exhaustive behavior.

``island_derivation``'s ``PdaFail`` ("no derivation") path needs a completion
that decodes to an empty derivation stream — an internal engine-decode edge
case with no clean direct fixture; it stays uncovered here and relies on the
``parse_pda`` integration suites, per the plan's guidance not to force a
brittle fixture.
"""

from __future__ import annotations

import pytest

from lexic.ir.nodes import IrAst
from lexic.parsing.earley.forest import ParseTree
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.tables import compile_tables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.islands import (
    island_derivation,
    island_parse,
    island_run,
)

# ── island_run ────────────────────────────────────────────────────────


def test_island_run_returns_kernel_item_and_end_on_match(digit_grammar: IrAst):
    """A matching window returns (kernel, accepting_item, end)."""
    tables = compile_tables(digit_grammar)
    result = island_run(tables, "5")
    assert result is not None
    kern, item, end = result
    assert isinstance(kern, Kernel)
    assert isinstance(item, int)
    assert end == 1


def test_island_run_returns_none_when_the_start_rule_never_completes(
    digit_grammar: IrAst,
):
    """A window the start rule can't match at all returns None."""
    tables = compile_tables(digit_grammar)
    assert island_run(tables, "x") is None


def test_island_run_finds_the_longest_origin_zero_completion(sss_grammar: IrAst):
    """``s = s s / 'a'`` over 'aaa' completes at end=3, not a shorter prefix."""
    tables = compile_tables(sss_grammar)
    result = island_run(tables, "aaa")
    assert result is not None
    _, _, end = result
    assert end == 3


# ── island_parse ──────────────────────────────────────────────────────


def test_island_parse_happy_path_returns_tree_and_end(digit_grammar: IrAst):
    """The common case: a matching window decodes to (tree, consumed_len)."""
    tables = compile_tables(digit_grammar)
    tree, end = island_parse(tables, "5", 0, "digit")
    assert isinstance(tree, ParseTree)
    assert tree.symbol == "digit"
    assert end == 1


def test_island_parse_starts_from_the_given_position(digit_grammar: IrAst):
    """The window opens at pos, not at the start of text."""
    tables = compile_tables(digit_grammar)
    tree, end = island_parse(tables, "x5", 1, "digit")
    assert isinstance(tree, ParseTree)
    assert end == 1


def test_island_parse_raises_pda_fail_with_position_on_no_match(digit_grammar: IrAst):
    """No completion anywhere in the window raises PdaFail naming the position."""
    tables = compile_tables(digit_grammar)
    with pytest.raises(PdaFail, match=r"island 'digit': no match at 0"):
        island_parse(tables, "x", 0, "digit")


def test_island_parse_resolves_an_ambiguous_completion_via_island_derivation(
    sss_grammar: IrAst,
):
    """'aaa' under ``s = s s / 'a'`` is genuinely ambiguous (Catalan C_2) —
    the FastTree fast path misses, so island_parse falls through to
    island_derivation for the first derivation. Exercises both functions.
    """
    tables = compile_tables(sss_grammar)
    tree, end = island_parse(tables, "aaa", 0, "s")
    assert isinstance(tree, ParseTree)
    assert end == 3


# ── island_derivation ─────────────────────────────────────────────────


def test_island_derivation_returns_the_first_derivation(sss_grammar: IrAst):
    """Given an ambiguous completion's kernel/item/end, decodes one tree."""
    tables = compile_tables(sss_grammar)
    result = island_run(tables, "aaa")
    assert result is not None
    kern, item, end = result
    tree = island_derivation(kern, item, end, "s")
    assert isinstance(tree, ParseTree)
    assert tree.symbol == "s"
