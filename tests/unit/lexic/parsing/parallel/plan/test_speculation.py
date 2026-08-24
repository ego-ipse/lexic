"""Tests for ``lexic.parsing.parallel.plan.speculation`` — the propose licence.

A speculative cut is verified by parsing, and a parse proves only that the
document HAS a reading. What makes the reading unique is a grammar property,
so these cases aim at each clause of it — and at the one grammar that passes
every determinism check and is still ambiguous.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.plan.speculation import (
    continues,
    opens_with,
    speculative_openings,
)
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.parallel.speculation_fixtures import (
    ANNOUNCED,
)


def _rules(source: str, key: str) -> dict:
    grammar = compile_text(source, cache_key=key).codegen_grammar
    return {str(rule.name): rule for rule in grammar.rules}


def _grammar(source: str, key: str):
    return compile_text(source, cache_key=key).codegen_grammar


# ── the licence ───────────────────────────────────────────────────────────


def test_a_section_grammar_licenses_its_opening_character() -> None:
    """Nothing a section continues with is ``#``, so a cut may be proposed
    wherever one stands and the piece parse settles whether it was right."""
    grammar = _grammar(ANNOUNCED, "spec-announced")
    assert speculative_openings(grammar, "section") == frozenset({"#"})


# ── the clause each witness aims at ───────────────────────────────────────


def test_a_maximal_munch_unit_refuses_though_nothing_is_conflicted() -> None:
    """The counterexample the whole precondition exists for. ``unit ::= [a-z]+``
    has no island, no conflicted rule and no nullable unit, and ``"abc"``
    divides three ways — so a determinism check alone would license it.

    Sequential does not even REFUSE here: it answers with the maximal munch,
    silently, which is what makes a wrong cut silently wrong. That answer is
    pinned, because a test asserting only "declines" would pass on a tree
    where the exclusive-opening clause had been deleted."""
    source = "root ::= unit+\nunit ::= [a-z]+\n"
    compiled = compile_text(source, cache_key="spec-munch")
    assert repr(compiled.parse("abc", cores=1)) == "Root((Unit('abc'),))"
    assert speculative_openings(compiled.codegen_grammar, "unit") == frozenset()


def test_overlapping_arms_refuse_on_the_determinism_clause() -> None:
    """``"a" | "aa"`` settles its second success at RUNTIME, which is a check
    and not a proof, so the rule is conflicted and the licence is withheld."""
    grammar = _grammar('root ::= unit+\nunit ::= "a" | "aa"\n', "spec-arms")
    assert speculative_openings(grammar, "unit") == frozenset()


def test_a_vanishing_unit_refuses() -> None:
    """A unit that may spell nothing makes ``unit+`` infinitely segmentable."""
    grammar = _grammar("root ::= unit+\nunit ::= [a-z]*\n", "spec-nullable")
    assert speculative_openings(grammar, "unit") == frozenset()


def test_an_assembling_paragraph_refuses() -> None:
    """I17's permanent counterexample keeps its job: an empty line may belong
    to either side of a boundary, so the segmentation is not forced."""
    source = (
        "doc ::= para (bl para)*\n"
        'bl ::= "\\n\\n"\n'
        "para ::= line+\n"
        'line ::= [a-z]* "\\n"\n'
    )
    grammar = _grammar(source, "spec-assembling")
    assert speculative_openings(grammar, "para") == frozenset()


def test_an_unknown_unit_refuses() -> None:
    """A name the grammar does not define licenses nothing."""
    grammar = _grammar(ANNOUNCED, "spec-announced")
    assert speculative_openings(grammar, "nosuchrule") == frozenset()


# ── the continuation walk itself ──────────────────────────────────────────


def test_a_repeated_item_continues_with_its_own_opening() -> None:
    """The term a top-level reading misses. ``unit ::= [a-z]+`` is ONE item, so
    an arm-remainder walk finds nothing after it and reads CONT as empty; the
    unit continues with another copy of the item, and that is what collides
    with its own FIRST."""
    rules = _rules("root ::= unit+\nunit ::= [a-z]+\n", "spec-munch")
    found = continues(rules, "unit")
    assert found.has("a") and found.has("z")
    assert opens_with(rules, "unit").overlaps(found)


def test_a_nested_vanishable_tail_contributes_its_continuations() -> None:
    """A could-end point can sit BELOW the arm's top level, so the walk follows
    references: ``section``'s own tail vanishes inside ``line*``."""
    rules = _rules(ANNOUNCED, "spec-announced")
    found = continues(rules, "section")
    assert found.has("a") and found.has(" ")
    assert not found.has("#")


def test_an_unresolvable_name_inflates_rather_than_shrinks() -> None:
    """Overapproximating is the only safe direction — a missed continuation is
    false disjointness, which is false uniqueness — so what the walk cannot
    resolve answers ANY."""
    assert continues({}, "missing") == CharSet.ANY
