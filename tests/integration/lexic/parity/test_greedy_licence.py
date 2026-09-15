"""The split-greedy licence, end to end: same answers, bounded work, no islands.

A nullable-bodied item inside a repetition carves every document many ways, all
of them the same production over the same span — a SPLIT, whose answer is the
leftmost chain. The licence lets the predictive path take that shape instead of
handing it to the gated engine, so the tests here ask the two questions a
licence has to answer: does it change any answer, and does it withhold itself
where it was not certified.
"""

from __future__ import annotations

from typing import SupportsIndex

import pytest

from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.program.flatten import gate_take
from lexic.parsing.pda.compiler.program.opcodes import GATE_GREEDY
from lexic.parsing.products import earley_model, parse_model, pda_model
from tests.parity_helpers import answers, built

PARA = (
    "doc ::= para+\n"
    "para ::= line+ blank\n"
    "line ::= [a-z ]* nl\n"
    "blank ::= nl\n"
    'nl ::= "\\n"\n'
)
"""The shape the bullet is about: a blank line is a tail OR one more empty line."""

TWO_TAIL = (
    "doc ::= para+\n"
    "para ::= line+ blank\n"
    "line ::= [a-z]* nl\n"
    "blank ::= nl nl\n"
    'nl ::= "\\n"\n'
)
"""``m = 2`` — the tail is two terminators, so the gate reads three characters."""

ASTRA = 'doc ::= u+ c\nu ::= i+ tl\ni ::= [a]* t\ntl ::= t\nt ::= ";"\nc ::= "a"\n'
"""The continuation begins with a BODY character: matched in full, not peeked."""

WRAPPED = (
    "doc ::= open body close\n"
    'open ::= "<"\n'
    'close ::= ">"\n'
    "body ::= para+\n"
    "para ::= line+ blank\n"
    "line ::= [a-z]* nl\n"
    "blank ::= nl\n"
    'nl ::= "\\n"\n'
)
"""The same class wrapped: a fixed prefix, a closer, and the loop in its own rule."""

VARIABLE_PREFIX = (
    "doc ::= open body close\n"
    "open ::= [<]+\n"
    'close ::= ">"\n'
    "body ::= para+\n"
    "para ::= line+ blank\n"
    "line ::= [a-z]* nl\n"
    "blank ::= nl\n"
    'nl ::= "\\n"\n'
)
"""A prefix whose extent is a split of its own — outside condition (h)."""


DOCUMENTS = [
    "\n\n",  # one empty line, then the tail
    "a\n\n",
    "a\nb\n\n",
    "\n\n\n",  # a run of terminators: every carving is the same model
    "\n\n\n\n",
    "a\n\n\nb\n\n",
    "a\n" * 6 + "\n",
]


@pytest.mark.parametrize("text", DOCUMENTS)
def test_both_engines_answer_the_same_way(text: str) -> None:
    """The one thing the licence may not do is change an answer.

    Hand-picked rather than fuzzed: every document here sits on a boundary the
    licence reasons about — nothing but the tail, a single empty item, a run of
    them, and a tail in the middle that must NOT end the unit.
    """
    predictive, gated = answers(PARA, "licence-para", text)

    assert predictive == gated
    assert predictive != "declined", "the licence should have taken this shape"


@pytest.mark.parametrize("text", ["\n\n\n", "a\n\n\n", "a\nb\n\n\nc\n\n\n"])
def test_a_two_terminator_tail_answers_the_same_way(text: str) -> None:
    """``m = 2``: the gate reads three characters and must still agree."""
    predictive, gated = answers(TWO_TAIL, "licence-two-tail", text)

    assert predictive == gated
    assert predictive != "declined"


@pytest.mark.parametrize("text", ["a;;a", "a;;a;;a", ";;a", "a;;;;a"])
def test_the_charged_continuation_answers_the_same_way(text: str) -> None:
    """astra's shape end to end.

    ``"a;;a"`` and ``"a;;a;;a"`` agree on their next two characters at the
    first boundary and differ in the answer, so a two-character window would
    get one of them wrong. Both are here.
    """
    predictive, gated = answers(ASTRA, "licence-astra", text)

    assert predictive == gated
    assert predictive != "declined"


def test_the_document_that_is_only_a_tail_is_refused_by_both() -> None:
    """Not in the language — a unit needs an item, and neither engine invents one."""
    predictive, gated = answers(PARA, "licence-para", "\n")

    assert gated == "refused"
    assert predictive in {"refused", "declined"}


@pytest.mark.parametrize(
    "text", ["<a\n\n>", "<\n\n>", "<a\nb\n\nc\n\n>", "<a\n\n\n\n>", "<\n\n\n>"]
)
def test_the_wrapped_shape_answers_the_same_way(text: str) -> None:
    """Condition (h): a fixed prefix, a closer, and the loop in a rule of its own.

    The wrapper is consumed once, outside every boundary the exchange moves, so
    the licence extends to it — and the continuation the gate charges is what
    follows ``body`` in ``doc``'s arm, not what follows the loop in ``body``'s.
    """
    predictive, gated = answers(WRAPPED, "licence-wrapped", text)

    assert predictive == gated
    assert predictive != "declined", "the wrapper condition should have taken this"


# ── the withhold ───────────────────────────────────────────────────────


def test_a_variable_extent_prefix_is_issued_no_licence() -> None:
    """Condition (h): the prefix must have a fixed extent.

    ``open ::= [<]+`` can end at more than one position, so where it ends is a
    split of its own — and the first slot takes as much as it can, which makes
    the prefix's maximisation outrank the loop's. The licence proves nothing
    about that interaction, so it withholds rather than assume.
    """
    compiled, _product = built(VARIABLE_PREFIX, "licence-variable-prefix")
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())

    assert analysis.taxonomy.ready_loop_gates == {}


@pytest.mark.parametrize(
    "text", ["<a\n\n>", "<\n\n>", "<a\nb\n\nc\n\n>", "<a\n\n\n\n>"]
)
def test_the_variable_prefix_grammar_still_answers_through_the_composed_entry(
    text: str,
) -> None:
    """Withholding a licence may not cost an answer — only the fast path."""
    compiled, product = built(VARIABLE_PREFIX, "licence-variable-prefix")
    composed = parse_model(compiled.codegen_grammar, text, compiled.product)
    gated = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )

    assert repr(composed) == repr(gated)
    assert composed.to_text() == text


def test_a_delegated_analysis_issues_no_licence() -> None:
    """The withhold at its own seam, not through a grammar that happens to fail.

    An island interior is analysed with the island as its start rule; the flag
    says so, and the certifier is never reached. Asserted directly because the
    grammar above declines for a different reason — condition (f) — and a guard
    that is never exercised is a guard nobody has tested.
    """
    compiled, _product = built(PARA, "licence-para")
    delegated = GrammarAnalysis(compiled.codegen_grammar, delegated=True)
    delegated.eval(delegated, compiled.codegen_grammar, ())
    ordinary = GrammarAnalysis(compiled.codegen_grammar)
    ordinary.eval(ordinary, compiled.codegen_grammar, ())

    assert ordinary.taxonomy.ready_loop_gates != {}, "the control must be licensed"
    assert delegated.taxonomy.ready_loop_gates == {}


# ── bounded work ───────────────────────────────────────────────────────


def test_the_gate_reads_a_bounded_window_however_long_the_run() -> None:
    """Characters COUNTED, not seconds measured — the claim is boundedness.

    The predicate compared ``text[after:] == close``, which copies the whole
    remaining suffix every time the tail matches: on a run of terminators that
    is O(n) boundaries × O(n) copy, quadratic character work from a gate whose
    entire claim is a bounded window. A timing test would have called it slow;
    this one names what it reads.

    Counted by giving the gate a string that reports every slice and
    ``startswith`` it is asked for. The bound is per CALL — the gate reads the
    tail, the continuation and nothing else — so it does not grow with the
    document.
    """
    reads: list[int] = []

    class Counted(str):
        """A document that records how many characters each read touches."""

        __slots__ = ()

        def startswith(
            self,
            prefix: str | tuple[str, ...],
            start: SupportsIndex | None = 0,
            end: SupportsIndex | None = None,
            /,
        ) -> bool:
            reads.append(len(prefix) if isinstance(prefix, str) else 0)
            return str.startswith(self, prefix, start, end)

        def __getitem__(self, item):
            if isinstance(item, slice):
                reads.append(len(self) - (item.start or 0))
            return str.__getitem__(self, item)

    gate = (";", "", None)
    for size in (64, 4096):
        reads.clear()
        text = Counted(";" * size)
        for pos in range(size):
            gate_take(text, pos, GATE_GREEDY, gate)
        assert max(reads) <= 4, (
            f"a read of {max(reads)} characters at {size}: the gate is not "
            f"reading a bounded window"
        )


def test_a_document_the_gated_engine_cannot_finish_parses_on_the_predictive_path() -> (
    None
):
    """16 KB of the class, on the route the licence opens — and no Earley run.

    This shape's gated cost is superlinear: the effort's own reports have it at
    1,955 ms for 11,738 characters and 202 s with 1.3 GB at 28 KB, so a
    document this size is not something to hand it inside a test suite. What is
    asserted here is that the predictive path TAKES the shape and the model
    round-trips — the timing itself is cited, never re-measured.
    """
    compiled, product = built(PARA, "licence-para")
    text = "abc def\nghi\n\n" * 1260

    model = pda_model(product.pda, text, compiled.product.executor)

    assert model.to_text() == text
    assert len(text) > 16000


def test_the_shape_no_longer_islands() -> None:
    """The licence's point, stated as the fact it changes.

    Before it, ``para`` was an island and every document went to the gated
    engine. An island here would make the row above pass by falling back.
    """
    compiled, _product = built(PARA, "licence-para")
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())

    assert analysis.islands == frozenset()
    assert len(analysis.taxonomy.ready_loop_gates) == 1
