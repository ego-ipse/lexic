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
from lexic.parsing import ParseConfig
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.gates.windows import END, MORE, UNK, Pref
from lexic.parsing.pda.analysis.predicates import rule_alphabets
from lexic.parsing.pda.compiler.clones import compile_clones
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime import islands
from lexic.parsing.pda.runtime.islands import (
    ISLAND_WINDOW,
    IslandPolicy,
    bounded_window,
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
    tree, end, _value = island_parse(tables, "5", 0, "digit")
    assert isinstance(tree, ParseTree)
    assert tree.symbol == "digit"
    assert end == 1


def test_island_parse_starts_from_the_given_position(digit_grammar: IrAst):
    """The window opens at pos, not at the start of text."""
    tables = compile_tables(digit_grammar)
    tree, end, _value = island_parse(tables, "x5", 1, "digit")
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
    cross-span arm choice the seam cannot settle. It is UNDECIDABLE, not a
    miss (``ProbeFork``), so no enclosing attempt reads it as the island
    failing; the message names both ends."""
    policy = IslandPolicy(follow=CharSet(frozenset("b")))
    with pytest.raises(ProbeFork, match=r"arm choice spans two ends \(1, 2\)"):
        island_parse(_cross_span_tables(), "abc", 0, "x", policy)


def test_island_parse_commits_longest_when_the_shorter_cannot_compose():
    """A shorter end whose next char the continuation refuses is no
    alternative — longest-match stays the defined answer."""
    policy = IslandPolicy(follow=CharSet(frozenset("z")))
    tree, end, _value = island_parse(_cross_span_tables(), "abc", 0, "x", policy)
    assert isinstance(tree, ParseTree)
    assert end == 2


def test_island_parse_without_follow_keeps_plain_longest_match():
    """No continuation evidence (the direct-call seam) — legacy longest-match."""
    tree, end, _value = island_parse(_cross_span_tables(), "abc", 0, "x")
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
    tree, end, _value = island_parse(tables, text, 0, "x")
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
    tree, end, _value = island_parse(
        tables,
        "aaa",
        0,
        "s",
        IslandPolicy(config=ParseConfig(resolve=lambda first, other: first)),
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
    tree, end, _value = island_parse(
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
    tree, end, _value = island_parse(tables, "a", 0, "s")
    assert isinstance(tree, ParseTree)
    assert end == 1


# ── island_derivation ─────────────────────────────────────────────────


def test_island_derivation_returns_the_first_derivation(sss_grammar: IrAst):
    """Given an ambiguous completion's kernel/item/end, decodes one tree."""
    tables = compile_tables(sss_grammar)
    kern, best = island_run(tables, "aaa")
    assert best is not None
    item, end = best
    tree, _value = island_derivation(kern, item, end, "s")
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
    tree, value = island_derivation(
        kern, item, end, "vyx", policy=IslandPolicy(executor=compiled.executor)
    )

    assert isinstance(tree, ParseTree)
    assert value is not None, "the settle step built a value and must hand it back"


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
    tree, value = island_derivation(
        kern, item, end, "vyx", policy=IslandPolicy(executor=compiled.executor)
    )

    assert isinstance(tree, ParseTree)
    assert value is not None, "the settle step built a value and must hand it back"


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
    tree, _value = island_derivation(
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


# ── the window climb stops at the first window that refuses ─────────────

_CLIMB_HOST = (
    "root ::= head inner tail\n"
    'head ::= "<"\n'
    'tail ::= ">"\n'
    "inner ::= expr\n"
    "expr ::= step op term | term\n"
    "step ::= expr\n"
    "term ::= [a-z]\n"
    'op ::= "+"\n'
)
"""A left-recursive island inside a delimited host — the shape whose climb
doubles. `expr`'s own FOLLOW holds the operator, so every completion but the
first has a shorter one the continuation accepts.

The recursion goes through `step` rather than directly, because DIRECT left
recursion no longer islands — the fold rewrites it into a loop and builds the
model back (:mod:`lexic.parsing.pda.compiler.leftrec.rewrite`). The fold does
not take indirect recursion, so this still reaches the island seam, which is
what these tests are about."""


def _windows(source: str, text: str, key: str) -> list[int]:
    """Every island window width the production seam opens for one parse."""
    compiled = compile_text(source, cache_key=key)
    widths: list[int] = []
    real = islands.island_run

    def watched(tables, window_text, delegates):
        """Record the width, then run the window."""
        widths.append(len(window_text))
        return real(tables, window_text, delegates)

    islands.island_run = watched
    try:
        compiled.parse(text, cores=1)
    finally:
        islands.island_run = real
    return widths


def test_an_island_that_cannot_settle_answers_at_the_first_window():
    """The answer the climb used to reach last is reached first — once.

    Completion ends only accumulate, so the answer at any width is the answer
    at every wider one, and the climb was re-deriving it four more times over
    a document that never had a different one to give.

    That first window is now the EXACT one rather than the 256-character
    floor: ``expr`` derives ``[a-z+]`` and its reference is followed by
    ``>``, which it cannot hold, so its extent is bounded by the first ``>``
    and one sub-parse at that width settles it. The trade is stated rather
    than hidden — an island that ends up REFUSING now parses to its bound
    instead of stopping at 256, which is more work than the floor was. It is
    bounded work, and it precedes a whole-document Earley fallback that
    dwarfs it; a climbing window would have reached the same width anyway,
    five parses later.
    """
    terms = 3 * ISLAND_WINDOW  # two characters each, so the input doubles twice
    text = (
        "<" + "+".join("abcdefghijklmnopqrstuvwxyz"[n % 26] for n in range(terms)) + ">"
    )
    assert len(text) > 4 * ISLAND_WINDOW, "the input must be wide enough to double"

    widths = _windows(_CLIMB_HOST, text, "climb-refuses")

    assert len(widths) == 1, f"the climb doubled past its answer: {widths}"
    assert widths[0] == text.index(">") - 1, "not the exact bound"


def test_an_island_that_settles_still_settles():
    """One completion, no shorter alternative, no refusal — and a parse."""
    compiled = compile_text(_CLIMB_HOST, cache_key="climb-settles")

    model = compiled.parse("<a>", cores=1)

    assert model.to_text() == "<a>"


def test_the_climb_still_grows_when_nothing_refuses():
    """The doubling is not removed — only the re-derivation of a refusal.

    A window narrower than the island, with a continuation no shorter end
    composes with, must still widen until the island fits.
    """
    tables = compile_tables(
        IrAst(
            rules=IrSeq(
                IrRule(
                    "x",
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("x")), IrItem(IrLiteral("a"))),
                        IrSequence(IrItem(IrLiteral("a"))),
                    ),
                )
            ),
            start="x",
        )
    )
    text = "a" * (ISLAND_WINDOW * 2)
    widths: list[int] = []
    real = islands.island_run

    def watched(inner_tables, window_text, delegates):
        """Record the width, then run the window."""
        widths.append(len(window_text))
        return real(inner_tables, window_text, delegates)

    islands.island_run = watched
    try:
        _tree, end, _value = island_parse(tables, text, 0, "x", IslandPolicy())
    finally:
        islands.island_run = real

    assert end == len(text)
    assert widths == [ISLAND_WINDOW, ISLAND_WINDOW * 2], widths


# ── the exact window: one sub-parse where the continuation bounds the island ──


def test_bounded_window_reaches_the_first_continuation_character():
    """The scan's whole contract: the distance to the first one, from ``pos``."""
    assert bounded_window("abc\ndef\n", 0, CharSet.from_chars("\n")) == 3
    assert bounded_window("abc\ndef\n", 4, CharSet.from_chars("\n")) == 3


def test_bounded_window_takes_the_nearest_of_several_continuation_characters():
    """Several continuation characters, and the nearest is the bound."""
    assert bounded_window("ab;cd,ef", 0, CharSet.from_chars(",", ";")) == 2
    assert bounded_window("ab;cd,ef", 3, CharSet.from_chars(",", ";")) == 2


def test_bounded_window_is_the_rest_of_the_input_when_none_occurs():
    """No continuation character left means the island may reach the end.

    This is the single-island document — the window is the whole remainder and
    one sub-parse settles it, where the climb paid 256+512+1024+… to cover the
    same characters.
    """
    assert bounded_window("abcdef", 0, CharSet.from_chars("\n")) == 6
    assert bounded_window("abcdef", 4, CharSet.from_chars("\n")) == 2


def test_an_island_whose_alphabet_misses_its_continuation_parses_once():
    """``line ::= expr nl`` over a left-recursive ``expr`` — one window, exact.

    ``expr`` derives ``[a-z+]`` and its reference is followed by ``\\n``, which
    it cannot hold, so no completion reaches past the first newline. The
    window is that distance and the climb never runs.
    """
    text = "a+b+c\nd+e\n"
    compiled = compile_text(
        "root ::= line+\nline ::= expr nl\nexpr ::= step op term | term\n"
        'step ::= expr\nterm ::= [a-z]\nop ::= "+"\nnl ::= "\\n"\n',
        cache_key="exact-window",
    )
    widths: list[int] = []
    real = islands.island_run

    def spy(tables, window_text, delegates):
        widths.append(len(window_text))
        return real(tables, window_text, delegates)

    islands.island_run = spy
    try:
        model = compiled.parse(text, cores=1)
    finally:
        islands.island_run = real

    assert model.to_text() == text
    # two lines, one sub-parse each, each exactly as wide as its own line's
    # expression — never the 256-character floor, never a doubling
    assert widths == [5, 3], widths


def test_an_island_whose_alphabet_meets_its_continuation_keeps_the_climb():
    """A string literal that can hold its own terminator must still climb.

    Here the island's alphabet includes the continuation character, so the
    first occurrence of it says nothing about where the island ends — the
    bound would be wrong and the compiler must decline to take it.
    """
    compiled = compile_text(
        'root ::= expr "+" term nl | expr nl\n'
        'expr ::= expr "+" term | term\nterm ::= [a-z]\nnl ::= "\\n"\n',
        cache_key="overlap-climb",
    )
    lifted = lift_optional_nullables(compiled.codegen_grammar)
    specs, _ = compile_clones(lifted, compiled.product)
    cont = specs.continuations.follow("expr")

    assert cont.has("+"), "the caller can put + after the island"
    held = rule_alphabets(specs.analysis.rules)["expr"]
    assert held.has("+"), "and the island holds + too"
    assert not specs.continuations.bounds("expr", cont)


def test_the_exact_window_does_not_weaken_the_two_ends_refusal():
    """The bound removes ends that could not exist, not ends that could.

    Same grammar as above: ``a+b\\n`` genuinely derives two ways and means two
    different things, so both engines must refuse it rather than answer.
    """
    compiled = compile_text(
        'root ::= expr "+" term nl | expr nl\n'
        'expr ::= expr "+" term | term\nterm ::= [a-z]\nnl ::= "\\n"\n',
        cache_key="overlap-climb",
    )
    with pytest.raises((PdaFail, UnsupportedConstructError)):
        compiled.parse("a+b\n", cores=1)


def test_bounded_window_skips_the_end_of_input_sentinel():
    """A continuation of "end of input" bounds the island at the end, not at 0.

    The sentinel is spelled ``""`` and ``text.find("", pos)`` is ``pos``,
    because every string contains the empty one everywhere. Scanning for it
    would bound every island that may run to the end of the document to a
    width of zero — which is the whole document's worth of parse, silently
    not done.
    """
    assert bounded_window("abcdef", 0, CharSet.from_chars("")) == 6
    assert bounded_window("abcdef", 2, CharSet.from_chars("")) == 4
    # and beside a real character, the real one still bounds it
    assert bounded_window("ab\ncd", 0, CharSet.from_chars("", "\n")) == 2


# ── the value the settle step built is the value the seam splices ──────────


def test_the_settled_value_is_what_a_fresh_splice_would_build() -> None:
    """The handed-back value equals re-splicing the same tree, model for model.

    `different_meaning` builds the baseline to answer the ambiguity question
    and retains it — its own docstring says a resolver "does not construct its
    chosen result again". The seam used to discard it and splice the same tree
    a second time, which was 610 µs per island on a 48-character island and a
    third of that row's parse.

    Identical BY CONSTRUCTION — same builder, same tree — so this compares the
    two answers directly rather than trusting the argument, and it asks through
    the public entry rather than reaching into the settle step.
    """
    compiled = compile_text(
        'root ::= number\nnumber ::= ("-"? ([0-9] | [1-9] [0-9]{0,15}))',
        cache_key="settled-value",
    )
    tables = compile_tables(
        normalize(lift_optional_nullables(compiled.codegen_grammar))
    )

    _tree, _end, value = island_parse(
        tables, "5", 0, "number", IslandPolicy(executor=compiled.executor)
    )
    fresh = compiled.executor.splice(_tree)

    assert value is not None, "the settle step built a value and must hand it back"
    assert isinstance(value, Completed) and isinstance(fresh, Completed)
    assert value.value.dump() == fresh.value.dump()
    assert value.value.to_text() == fresh.value.to_text()


def test_an_executor_less_island_hands_back_no_value(digit_grammar: IrAst) -> None:
    """No product, nothing built — the seam completes the tree itself.

    The ``None`` is the honest answer rather than a failure: it is what tells
    the caller to splice, and a value invented here would be a value built
    without a product to build it with.
    """
    tables = compile_tables(digit_grammar)

    tree, end, value = island_parse(tables, "5", 0, "digit")

    assert isinstance(tree, ParseTree)
    assert end == 1
    assert value is None


# ── continues: the continuation a few characters deep ──────────────────────


def _window(chars: str, state: str) -> Pref:
    """One window over single-character sets, spelled as a string."""
    return (tuple(CharSet.from_chars(c) for c in chars), state)


def test_no_windows_is_no_evidence_and_admits():
    """Without windows the one-character test decides alone."""
    assert islands.continues((), "ab", 0)


def test_a_window_must_match_every_character_it_names():
    """Two characters named, two characters checked."""
    windows = (_window("+a", MORE),)
    assert islands.continues(windows, "x+a", 1)
    assert not islands.continues(windows, "x+b", 1)


def test_a_window_past_the_end_of_the_text_cannot_match():
    """Text too short for the window is not a continuation of it."""
    assert not islands.continues((_window("+a", MORE),), "x+", 1)


def test_a_complete_window_matches_only_where_the_input_ends():
    """END is the whole continuation, so anything after it disagrees."""
    windows = (_window(";", END),)
    assert islands.continues(windows, "x;", 1)
    assert not islands.continues(windows, "x;y", 1)


def test_unknown_past_its_characters_matches_on_them_alone():
    """UNK says nothing beyond what it spells."""
    assert islands.continues((_window(" ", UNK),), "x y", 1)
