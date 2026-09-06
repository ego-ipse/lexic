"""Tests for lexic.parsing.pda.runtime.islands — the island sub-parse + splice.

Shed from :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` as free functions
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

import random

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.generate import generate
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
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.islands import (
    ISLAND_WINDOW,
    IslandPolicy,
    island_derivation,
    island_parse,
    island_run,
    island_value,
)
from lexic.parsing.product.tree import EMPTY_RESULT, Completed, ProductExecutor
from lexic.parsing.products import _model_product
from tests.paths import GROUND_TRUTH

# ── island_run ────────────────────────────────────────────────────────


def test_island_run_returns_kernel_item_and_end_on_match(digit_grammar: IrAst):
    """A matching window returns the kernel and (accepting_item, end)."""
    tables = compile_tables(digit_grammar)
    kern, best = island_run(tables, "5")
    assert isinstance(kern, Kernel)
    assert best is not None
    item, end = best
    assert isinstance(item, int)
    assert end == 1


def test_island_run_returns_none_when_the_start_rule_never_completes(
    digit_grammar: IrAst,
):
    """A window the start rule can't match returns the kernel and no completion."""
    tables = compile_tables(digit_grammar)
    kern, best = island_run(tables, "x")
    assert isinstance(kern, Kernel)
    assert best is None


def test_island_run_finds_the_longest_origin_zero_completion(sss_grammar: IrAst):
    """``s = s s / 'a'`` over 'aaa' completes at end=3, not a shorter prefix."""
    tables = compile_tables(sss_grammar)
    _, best = island_run(tables, "aaa")
    assert best is not None
    _, end = best
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


def _cross_span_tables():
    """``x ::= "a" | "ab"`` — an arm choice whose arms span different ends."""
    x = IrRule(
        "x",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("ab"))),
        ),
    )
    return compile_tables(IrAst(rules=IrSeq(x), start="x"))


def test_island_parse_bails_when_a_shorter_end_could_compose():
    """A second completion end whose next char the continuation accepts is a
    cross-span arm choice the seam cannot settle — PdaFail names both ends."""
    policy = IslandPolicy(follow=CharSet(frozenset("b")))
    with pytest.raises(PdaFail, match=r"arm choice spans two ends \(1, 2\)"):
        island_parse(_cross_span_tables(), "abc", 0, "x", policy)


def test_island_parse_commits_longest_when_the_shorter_cannot_compose():
    """A shorter end whose next char the continuation refuses is no
    alternative — longest-match stays the defined answer."""
    policy = IslandPolicy(follow=CharSet(frozenset("z")))
    tree, end = island_parse(_cross_span_tables(), "abc", 0, "x", policy)
    assert isinstance(tree, ParseTree)
    assert end == 2


def test_island_parse_without_follow_keeps_plain_longest_match():
    """No continuation evidence (the direct-call seam) — legacy longest-match."""
    tree, end = island_parse(_cross_span_tables(), "abc", 0, "x")
    assert isinstance(tree, ParseTree)
    assert end == 2


def test_island_parse_grows_past_a_window_cut_multi_char_literal():
    """A multi-char literal cut by the window files NO item at all, and it can
    jump the shorter arm's completion column without ever filing one there —
    the truncation is invisible anywhere but the edge zone. The growth
    predicate must read liveness over the zone, or the island splices a
    truncated longest match (the short arm's end, not the long arm's)."""
    pre = IrRule(
        "pre",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("pre"))),
            IrSequence(IrItem(IrLiteral("a"))),
        ),
    )
    x = IrRule(
        "x",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("pre")), IrItem(IrLiteral("b"))),
            IrSequence(IrItem(IrRuleRef("pre")), IrItem(IrLiteral("bcd"))),
        ),
    )
    tables = compile_tables(IrAst(rules=IrSeq(x, pre), start="x"))
    text = "a" * (ISLAND_WINDOW - 2) + "bcd"
    tree, end = island_parse(tables, text, 0, "x")
    assert isinstance(tree, ParseTree)
    assert end == len(text)


def test_island_parse_resolves_an_ambiguous_completion_via_island_derivation(
    sss_grammar: IrAst,
):
    """'aaa' under ``s = s s / 'a'`` is genuinely ambiguous (Catalan C_2) —
    the FastTree fast path misses, so island_parse falls through to
    island_derivation for the first derivation. Exercises both functions.

    Under a take-the-first resolver, because taking a derivation from several
    is the behaviour being exercised and the default now refuses it.
    """
    tables = compile_tables(sss_grammar)
    tree, end = island_parse(
        tables, "aaa", 0, "s", IslandPolicy(resolve=lambda first, other: first)
    )
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
        island_parse(
            tables, "aaa", 0, "s", IslandPolicy(executor=sss_compiled.executor)
        )


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
    tree, end = island_parse(
        tables, "5", 0, "number", IslandPolicy(executor=compiled.executor)
    )
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
    kern, best = island_run(tables, "aaa")
    assert best is not None
    item, end = best
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


# ── ambiguity is a property of the FOREST, not of the first two derivations ──


def _vyx_span(seed: int):
    """A vyx parse whose forest holds >2 derivations, and its kernel."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    rules = {r.name: r for r in compiled.grammar.rules}
    text = generate(
        compiled.grammar.start, rules, rng=random.Random(seed), max_depth=12
    )
    kern = Kernel(product.tables, text)
    best = kern.longest_start_completion()
    assert best is not None
    return compiled, kern, best


@pytest.mark.parametrize("seed", [79, 108])
def test_a_decided_split_past_the_second_derivation_is_accepted(seed):
    """PORTED, opposite expectation: these two are SPLIT class, and splits decide.

    They were the witnesses that ambiguity past the second derivation is still
    ambiguity — derivations [0] and [1] agree and a later one does not, which
    the two-derivation sample could not see. That machinery is unchanged and
    still exercised by the arm-class case below.

    What changed is the classification: both seeds carry ONLY split-class points
    (0 arm-class, verified), and a split now has a defined answer — the first
    slot owns the text. Refusing it would refuse a question the engine can
    answer, and RFC 8259's own shape is ambiguous, so that refusal is not
    available. The engines agree on these inputs; nothing is left to refuse.
    """
    compiled, kern, best = _vyx_span(seed)
    item, end = best
    assert isinstance(
        island_derivation(
            kern, item, end, "vyx", policy=IslandPolicy(executor=compiled.executor)
        ),
        ParseTree,
    )


def test_generated_quantifier_arms_past_the_second_derivation_are_splits():
    """Raw helper-arm ids are not authored choices, even on later derivations.

    This test formerly called these points arm-class because normalisation gave
    the two states of one ``__rep_*`` helper different arm ids. That applies an
    implementation identity where the invariant requires authored structure.
    Both states belong to one quantified item, so the leftmost split policy
    decides them and the model path must not refuse.
    """
    compiled, kern, best = _vyx_span(146)
    item, end = best
    assert isinstance(
        island_derivation(
            kern, item, end, "vyx", policy=IslandPolicy(executor=compiled.executor)
        ),
        ParseTree,
    )


class _CountingExecutor(ProductExecutor):
    """A real ProductExecutor whose splice/splice_replay return fixed
    results in order, instead of completing through a routine table.

    ``different_meaning`` calls ``replay`` for both the baseline (via
    ``remembered``) and each alternate sibling, so a two-derivation span
    drives exactly two calls — the fixture controls both answers directly
    rather than depending on what a real grammar happens to build.
    """

    __slots__ = ("_at", "_results")

    def __init__(self, results):
        super().__init__({})
        self._results = list(results)
        self._at = 0

    def _next(self):
        value = self._results[min(self._at, len(self._results) - 1)]
        self._at += 1
        return value

    def splice(self, root):
        del root
        return self._next()

    def splice_replay(self, root, results):
        del root, results
        return self._next()


def test_an_empty_derivation_against_a_real_none_value_refuses_as_ambiguous(
    sss_grammar: IrAst,
):
    """EmptyResult and Completed(None) are DIFFERENT types under same_value's
    first check, so a two-derivation span where one means "produced nothing"
    and the other means "produced a real None" refuses — the one behaviour
    change a round-trip corpus cannot observe, because to_text() reproduces
    the input for either derivation."""
    tables = compile_tables(sss_grammar)
    kern, best = island_run(tables, "aaa")
    assert best is not None
    item, end = best
    executor = _CountingExecutor([EMPTY_RESULT, Completed(None)])
    with pytest.raises(UnsupportedConstructError, match="mean different things"):
        island_derivation(kern, item, end, "s", policy=IslandPolicy(executor=executor))


def test_two_derivations_both_meaning_none_settle_as_one_meaning(sss_grammar: IrAst):
    """The twin case: a real None built twice is still ONE value, not two —
    a present Python None is not an absence, and same_value must not refuse
    two derivations that agree on it."""
    tables = compile_tables(sss_grammar)
    kern, best = island_run(tables, "aaa")
    assert best is not None
    item, end = best
    executor = _CountingExecutor([Completed(None), Completed(None)])
    tree = island_derivation(
        kern, item, end, "s", policy=IslandPolicy(executor=executor)
    )
    assert isinstance(tree, ParseTree)


def test_authored_arm_past_the_second_derivation_still_refuses():
    """Seed 266 reaches two authored ``body-line`` arms, not helper states."""
    compiled, kern, best = _vyx_span(266)
    item, end = best
    with pytest.raises(UnsupportedConstructError):
        island_derivation(
            kern, item, end, "vyx", policy=IslandPolicy(executor=compiled.executor)
        )
