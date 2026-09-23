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

import math

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.windows import END, MORE
from lexic.parsing.pda.compiler.continuation import (
    WINDOW,
    IslandContinuations,
    site_positions,
)
from lexic.parsing.pda.compiler.specs import arm_items
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


# ── windows: the occurrence continuation a few characters deep ─────────────


def test_the_windows_carry_each_sites_continuation_two_deep() -> None:
    """``+`` then a term at one site; a newline, then the end, at the other."""
    got = continuations(_TWO_SITES).windows("expr")
    plus = [w for w in got if len(w[0]) == 2 and w[0][0].has("+")]
    assert plus and all(w[0][1].has("a") and w[1] == MORE for w in plus)
    assert any(len(w[0]) == 1 and w[0][0].has("\n") and w[1] == END for w in got)


def test_a_full_width_window_is_never_taken_as_complete() -> None:
    """``"+" term nl`` goes on past two characters: MORE, not END."""
    got = continuations(_TWO_SITES).windows("expr")
    assert all(state != END for chars, state in got if len(chars) == WINDOW)
    assert any(state == END for chars, state in got if len(chars) < WINDOW)


# ── per-site: only the sites that can stand where this one does ────────────

_TWO_PLACES = (
    'doc ::= x? "a" rest x? "#a"\nrest ::= [b-z]*\nx ::= x "#" | x "~" | "~"\n'
)
"""``x`` opens the document at one site and follows ``a`` at the other: the
first can only be at position 0, the second never is."""


def sites_of_x(
    source: str, delegated: bool = False
) -> tuple[IslandContinuations, list]:
    """The continuations of ``source``, and ``doc``'s references to ``x``."""
    compiled = compile_text(source, cache_key=f"sites-{hash(source)}-{delegated}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    analysis = GrammarAnalysis(IrAst(grammar.rules, grammar.start), delegated=delegated)
    items = arm_items(analysis.rules["doc"].body[0])
    refs = [item for item in items if str(item.atom) == "x"]
    return IslandContinuations(analysis, analysis.islands), refs


def test_a_site_at_the_start_is_placed_at_zero_and_a_later_one_is_not() -> None:
    """The start rule begins at 0; a site after ``"a"`` never does."""
    conts, (first, later) = sites_of_x(_TWO_PLACES)
    places = site_positions(conts.analysis.rules, conts.analysis.start)
    assert places[id(first)] == (0.0, 0.0)
    assert places[id(later)][0] >= 1.0


def test_a_site_is_followed_only_by_what_can_follow_it_where_it_stands() -> None:
    """``#a`` follows the later site, which never shares the first's place."""
    conts, (first, later) = sites_of_x(_TWO_PLACES)
    assert conts.follow("x").has("#")
    assert not conts.follow("x", first).has("#")
    assert conts.follow("x", later).has("#")


def test_a_delegates_analysis_never_narrows() -> None:
    """A delegate's window rebases positions: every site stays in the union."""
    conts, (first, _later) = sites_of_x(_TWO_PLACES, delegated=True)
    assert conts.follow("x", first) == conts.follow("x")


def test_a_nullable_prefix_pulls_a_site_to_the_start() -> None:
    """``y? x``: ``x`` may open the document when ``y`` is absent."""
    source = 'doc ::= y? x "a"\ny ::= "b"\nx ::= x "#" | x "~" | "~"\n'
    conts, (only,) = sites_of_x(source)
    places = site_positions(conts.analysis.rules, conts.analysis.start)
    assert places[id(only)] == (0.0, 1.0)


def test_what_follows_the_next_occurrence_is_the_rest_of_the_arm() -> None:
    """In ``x+ "z"``, a one-character ``x`` may be the last, so ``z`` can be
    the second character after the current one ends — not only what follows
    the rule."""
    source = 'doc ::= sec+\nsec ::= x+ "z"\nx ::= x "#" | x "~" | "~"\n'
    compiled = compile_text(source, cache_key="windows-next-occurrence")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    conts = IslandContinuations(analysis, analysis.islands)
    got = conts.windows("x")
    assert any(
        len(chars) == 2 and chars[0].has("~") and chars[1].has("z") for chars, _ in got
    )


def test_a_cycle_of_references_places_every_site_anywhere_past_its_start() -> None:
    """``a → b → c → a``, each after an ``x``: every reference can begin
    arbitrarily deep, however the rounds happen to order them."""
    source = 'doc ::= a\na ::= "x" b | "y"\nb ::= "x" c | "y"\nc ::= "x" a | "y"\n'
    compiled = compile_text(source, cache_key="positions-cycle")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    places = site_positions(analysis.rules, analysis.start)
    refs = [
        item
        for name, rule in analysis.rules.items()
        if name != "doc"
        for arm in rule.body
        for item in arm_items(arm)
        if id(item) in places
    ]
    assert len(refs) >= 6, "the cycle's references, arms included, were not found"
    assert all(places[id(item)][1] == math.inf for item in refs)


def test_a_reference_inside_an_inline_group_is_a_site() -> None:
    """``x`` is reached only through ``("q" | x) ";"``, a group the lift keeps.
    What follows the group, ``;``, follows ``x`` there; skipping the group
    left ``x`` with no site at all, which reads as no evidence and lets
    longest-match stand unchecked."""
    source = (
        'doc ::= item+\nitem ::= ("q" | x) ";"\nx ::= x "a" | x ";" "c" | "b" | "c"\n'
    )
    compiled = compile_text(source, cache_key="site-in-group")
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    conts = IslandContinuations(analysis, analysis.islands)
    assert conts.follow("x").has(";")
    assert any(chars[0].has(";") for chars, _ in conts.windows("x"))
