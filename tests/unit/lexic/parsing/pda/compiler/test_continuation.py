"""Tests for lexic.parsing.pda.compiler.continuation — an island's occurrence.

Two derivations, each with one way to be wrong that no other test catches.

``follow`` reads what the island's REFERENCES are followed by. Reading the
island rule's own FOLLOW instead is not a subtle error — it made every
left-recursive island with an infix operator refuse on its first completion,
every time, and the whole document fall back to Earley. The tests below pin
both halves of why: the island's own arms must not contribute, and every
external site must.

``bounds`` decides whether that set also fixes the island's extent, which is
what replaces a doubling window with one sub-parse at an exact width. It must
say no whenever the island can spell a continuation character, because there
the first occurrence of one says nothing about where the island ends.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.continuation import IslandContinuations
from lexic.parsing.pda.core.charsets import CharSet

_LEFT_RECURSIVE = 'root ::= item "e"\nitem ::= item "d" | "a"\n'
"""``item`` islands by left recursion; ``root`` puts ``e`` after it, and
``item``'s own arm puts ``d`` after it. The two must not be confused."""

_TWO_SITES = (
    'root ::= expr "+" term nl | expr nl\n'
    'expr ::= expr "+" term | term\nterm ::= [a-z]\nnl ::= "\\n"\n'
)
"""Two arms reach the island, and ``a+b\\n`` derives both ways."""


def continuations(source: str) -> IslandContinuations:
    """The derivation under test, built the way the clone compiler builds it."""
    compiled = compile_text(source, cache_key=f"cont-{hash(source)}")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    islands = analysis.islands - frozenset(analysis.taxonomy.attempts)
    return IslandContinuations(analysis, islands)


def test_the_islands_own_recursion_is_not_its_callers_continuation() -> None:
    """``d`` follows ``item`` inside ``item``; only ``e`` follows the reference.

    This is the defect the module exists for. ``item ::= item "d"`` puts ``d``
    into FOLLOW(``item``) purely because the rule places the reference before
    the literal — but a shorter end followed by ``d`` is the island continuing
    ITSELF, which longest-match absorbs under the same arm.
    """
    got = continuations(_LEFT_RECURSIVE).follow("item")

    assert got.has("e"), "the caller's continuation is the evidence"
    assert not got.has("d"), "the island's own recursion is not the caller"


def test_every_external_site_contributes() -> None:
    """Both of the caller's arms are in the union, not just the entered one.

    The PDA commits to an arm before entering the island, so a per-site answer
    would let a cross-arm ambiguity through silently: with only ``{'\\n'}`` in
    hand the seam settles ``a+b\\n``, which means two different things.
    """
    got = continuations(_TWO_SITES).follow("expr")

    assert got.has("+") and got.has("\n")


def test_the_answer_is_memoised_per_island() -> None:
    """Asked twice, derived once — and the same set both times."""
    derivation = continuations(_LEFT_RECURSIVE)

    first = derivation.follow("item")
    assert derivation.follow("item") == first


def test_an_island_referenced_from_nowhere_carries_no_evidence() -> None:
    """A rule nothing refers to has an empty continuation, not a wrong one.

    Empty is the honest answer and the seam reads it as "no evidence", taking
    plain longest-match rather than refusing on a set that was never derived.
    """
    got = continuations(_LEFT_RECURSIVE).follow("nonexistent-rule")

    assert got.is_empty()


def test_a_disjoint_continuation_bounds_the_island() -> None:
    """``item`` derives ``[ad]`` and is followed by ``e`` — the scan is sound.

    It cannot consume an ``e``, so no completion of it reaches past the first
    one, and one sub-parse at that width settles the island.
    """
    derivation = continuations(_LEFT_RECURSIVE)

    assert derivation.bounds("item", derivation.follow("item"))


def test_an_overlapping_continuation_does_not_bound_it() -> None:
    """``expr`` can spell ``+`` and may be followed by ``+`` — no bound.

    The first ``+`` after the cursor could be inside the island or after it,
    so it fixes nothing and the doubling climb has to stay.
    """
    derivation = continuations(_TWO_SITES)

    assert not derivation.bounds("expr", derivation.follow("expr"))


def test_an_empty_continuation_bounds_nothing() -> None:
    """There is no character to scan for, so there is no bound to take."""
    derivation = continuations(_LEFT_RECURSIVE)

    assert not derivation.bounds("item", CharSet.EMPTY)


def test_a_negated_continuation_bounds_nothing() -> None:
    """A co-finite set is not something a linear scan enumerates.

    The refusal is about the SCAN, not about soundness: the bound might well
    hold, and the derivation declines it rather than enumerating a complement.
    """
    derivation = continuations(_LEFT_RECURSIVE)

    assert not derivation.bounds("item", CharSet.ANY)


# ── a repeating reference is followed by its next occurrence ────────────────

_SEC = 'sec ::= sec "~" | sec "^" | "a" "b"*\n'
"""An island by left recursion (two recursive arms, so nothing folds it) that
begins with ``a``."""


def follow_of_sec(doc: str) -> CharSet:
    """What follows island ``sec`` where ``doc`` references it."""
    return continuations(f"doc ::= {doc}\n{_SEC}").follow("sec")


def test_a_repeating_reference_counts_its_next_occurrence() -> None:
    """After one ``sec`` of ``sec+`` comes ``.`` or another ``sec``: a shorter
    end that another occurrence continues is a second carving of the caller."""
    got = follow_of_sec('sec+ "."')
    assert got.has(".") and got.has("a")


def test_a_bounded_repeat_is_followed_by_its_next_occurrence_too() -> None:
    """``{2,3}`` can take another occurrence; at its ceiling the extra FIRST
    only over-approximates, which can refuse more but never admit less."""
    assert follow_of_sec('sec{2,3} "."').has("a")


def test_a_reference_that_cannot_repeat_gains_nothing() -> None:
    """``sec?`` occurs at most once, so only ``.`` follows it."""
    got = follow_of_sec('sec? "."')
    assert got.has(".") and not got.has("a")


def test_a_reference_in_a_repeated_group_is_unchanged() -> None:
    """In ``(sec ";")+`` the next occurrence comes after ``;``, which is what
    follows ``sec``, so ``a`` does not."""
    got = follow_of_sec('(sec ";")+')
    assert got.has(";") and not got.has("a")


def test_the_next_occurrence_unbounds_the_window() -> None:
    """``sec`` spells ``a``, so once ``a`` can follow it, the first ``a``
    no longer marks its end and the window must climb."""
    alone = continuations(f'doc ::= sec "."\n{_SEC}')
    repeated = continuations(f'doc ::= sec+ "."\n{_SEC}')
    assert alone.bounds("sec", alone.follow("sec"))
    assert not repeated.bounds("sec", repeated.follow("sec"))
