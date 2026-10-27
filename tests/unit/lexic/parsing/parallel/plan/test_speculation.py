"""Tests for ``lexic.parsing.parallel.plan.speculation`` — the propose licence.

A speculative cut is verified by parsing, and a parse proves only that the
document HAS a reading. What makes the reading unique is a grammar property,
so these cases aim at each clause of it — and at the one grammar that passes
every determinism check and is still ambiguous.
"""

from __future__ import annotations

from itertools import product

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.parallel.plan.speculation import (
    opens_with,
    speculative_openings,
)
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import rule_extensions
from lexic.parsing.pda.core.charsets import CharSet
from tests.unit.lexic.parsing.parallel.speculation_fixtures import (
    ANNOUNCED,
)


def _rules(source: str, key: str) -> dict:
    grammar = compile_text(source, cache_key=key).codegen_grammar
    return {str(rule.name): rule for rule in grammar.rules}


def _extend(source: str, key: str, unit: str) -> CharSet:
    """The unit's EXTEND as the clause reads it: over the lifted analysis."""
    grammar = compile_text(source, cache_key=key).codegen_grammar
    analysis = GrammarAnalysis(lift_optional_nullables(grammar))
    return rule_extensions(analysis).found[unit]


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


# ── EXTEND, the exclusive-opening clause's reading ──────────────────────


def test_a_repeated_item_extends_with_its_own_opening() -> None:
    """``unit ::= [a-z]+`` is ONE item, and a complete unit lengthens by
    another letter — exactly what collides with its own FIRST."""
    found = _extend("root ::= unit+\nunit ::= [a-z]+\n", "spec-munch", "unit")
    assert found.has("a") and found.has("z")
    rules = _rules("root ::= unit+\nunit ::= [a-z]+\n", "spec-munch")
    assert opens_with(rules, "unit").overlaps(found)


def test_a_nested_vanishable_tail_contributes_its_extensions() -> None:
    """``section``'s own tail vanishes inside ``line*``, so a complete section
    lengthens by what a line begins with — and never by ``#``."""
    found = _extend(ANNOUNCED, "spec-announced", "section")
    assert found.has("a") and found.has(" ")
    assert not found.has("#")


_WITNESS = 'root ::= r3+\nr3 ::= [ab]* "ab"\n'
"""The walk the clause used to read answered NOTHING for ``r3`` — yet ``ab``
lengthens to ``abab`` and to ``abbab``. A missed extension is false
disjointness, which is false uniqueness."""


def test_extend_holds_what_the_old_walk_missed() -> None:
    """``r3``'s EXTEND holds both letters."""
    found = _extend(_WITNESS, "spec-r3", "r3")
    assert found.has("a") and found.has("b")


def test_extend_holds_every_brute_force_extension() -> None:
    """Every ``(u, uw)`` pair the grammar accepts over ``{a, b}`` up to length
    six puts ``w[0]`` in EXTEND: the fixpoint is never short of the truth."""
    compiled = compile_text(_WITNESS.replace("r3+", "r3"), cache_key="spec-r3-one")
    accepted = set()
    for size in range(1, 7):
        for letters in product("ab", repeat=size):
            text = "".join(letters)
            try:
                compiled.parse(text, cores=1)
            except LexicError:
                continue
            accepted.add(text)
    truth = {
        w[len(u)]
        for u in accepted
        for w in accepted
        if len(w) > len(u) and w.startswith(u)
    }
    assert truth == {"a", "b"}
    found = _extend(_WITNESS.replace("r3+", "r3"), "spec-r3-one", "r3")
    assert all(found.has(c) for c in truth)
