"""Tests for lexic.parsing.pda.runtime.islands — the island sub-parse + splice.

Shed from :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` as free functions
(Task 2b): a windowed Earley sub-parse over a small real grammar, driven
through the module's three public entry points directly. The functions are
already covered end-to-end by the ``pda_model`` parity/fallback suites, so
this file targets the function-level contracts (return shapes, the two
``PdaFail`` messages) rather than exhaustive behavior.

``island_derivation``'s ``PdaFail`` ("no derivation") path needs a completion
that decodes to an empty derivation stream — an internal engine-decode edge
case with no clean direct fixture; it stays uncovered here and relies on the
``pda_model`` integration suites, per the plan's guidance not to force a
brittle fixture.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.ir import IrAst
from lexic.parsing.earley.kernel.forest import ParseTree
from lexic.parsing.earley.kernel.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.islands import (
    IslandPolicy,
    island_derivation,
    island_parse,
    island_run,
    island_value,
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

    Under ``ambiguous=True``, because taking a derivation from several is the
    behaviour being exercised and the default now refuses it.
    """
    tables = compile_tables(sss_grammar)
    tree, end = island_parse(tables, "aaa", 0, "s", IslandPolicy(ambiguous=True))
    assert isinstance(tree, ParseTree)
    assert end == 3


def test_island_parse_refuses_derivations_that_mean_different_things(sss_compiled):
    """A silently chosen derivation is a wrong answer where an error is available.

    An island is the ONE site where the model path chooses — everywhere else it
    is predictive and produces one derivation by construction — and the choice
    is invisible to the round-trip invariant, because ``to_text()`` reproduces
    the input for whichever derivation was taken.
    """
    tables = compile_tables(sss_compiled.codegen_grammar)
    with pytest.raises(UnsupportedConstructError, match="mean different things"):
        island_parse(tables, "aaa", 0, "s", IslandPolicy(fold=sss_compiled.fold))


def test_island_parse_allows_derivations_that_mean_the_same_thing() -> None:
    """An inline group like ``([0-9] | [1-9] [0-9]*)`` carves a single digit two
    ways and folds to one model both times — the arms never materialise a class.

    Refusing that refuses ``{"a":1}`` for a difference nothing downstream can
    observe, which is why the check is on values and not on derivation count.
    """
    compiled = compile_text(
        'root ::= number\nnumber ::= ("-"? ([0-9] | [1-9] [0-9]{0,15}))',
        cache_key="inline-ambiguous",
    )
    ready = normalize(lift_optional_nullables(compiled.codegen_grammar))
    tables = compile_tables(ready)
    tree, end = island_parse(tables, "5", 0, "number", IslandPolicy(fold=compiled.fold))
    assert isinstance(tree, ParseTree)
    assert end == 1


def test_the_fast_path_declining_is_not_by_itself_ambiguity(sss_grammar: IrAst):
    """The refusal asks the derivation STREAM, not ``isinstance``.

    ``FastTree`` also declines when a key packs several families or the root has
    many productions, so reading its miss as "ambiguous" refused ordinary input
    — 46 tests, including ``{"a":1}``. An unambiguous island whose fast path
    misses must still parse under the default.
    """
    tables = compile_tables(sss_grammar)
    tree, end = island_parse(tables, "a", 0, "s")
    assert isinstance(tree, ParseTree)
    assert end == 1


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


# ── island_value — the splice fail-soft guard ─────────────────────────


def test_island_value_passes_the_computed_value_through():
    """A clean fold/reduce step returns its value untouched."""
    assert island_value(lambda: "model", "r", 7) == "model"


def test_island_value_reroutes_a_lexic_error_to_pdafail():
    """A library error from the fold (a window-truncated valid-prefix
    mis-parse — e.g. an unknown symbol) becomes PdaFail, cause preserved,
    so the Earley completion takes over as the authority."""

    def _refuse() -> str:
        raise UnsupportedConstructError("notation: unknown symbol 'IrQuan'")

    with pytest.raises(PdaFail) as err:
        island_value(_refuse, "arglist", 12)
    assert "arglist" in str(err.value) and "12" in str(err.value)
    assert isinstance(err.value.__cause__, UnsupportedConstructError)


def test_island_value_reroutes_field_validation_errors_too():
    """The whole LexicError vocabulary reroutes, not just the parse error."""

    def _refuse() -> str:
        raise FieldValidationError("field 'x': out of class")

    with pytest.raises(PdaFail):
        island_value(_refuse, "r", 0)


def test_island_value_lets_non_library_exceptions_surface():
    """An authored-constructor bug (non-LexicError) is NOT muted."""

    def _boom() -> str:
        raise RuntimeError("authored ctor bug")

    with pytest.raises(RuntimeError):
        island_value(_boom, "r", 0)
