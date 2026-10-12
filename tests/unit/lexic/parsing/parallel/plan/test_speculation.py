"""Tests for ``lexic.parsing.parallel.plan.speculation`` — the propose licence.

A speculative cut is verified by parsing, and a parse proves only that the
document HAS a reading. What makes the reading unique is a grammar property,
so these cases aim at each clause of it — and at the one grammar that passes
every determinism check and is still ambiguous.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing import parse_model
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.discovery.anchors import anchors
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.plan import speculation
from lexic.parsing.parallel.plan.speculation import opens_with, speculative_openings
from lexic.parsing.parallel.planner import safe_plans, split_plans
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import rule_extensions
from tests.unit.lexic.parsing.parallel.speculation_fixtures import (
    ANNOUNCED,
    announced_doc,
)

RECURSIVE = (
    "root ::= section+\n"
    'section ::= "#" body\n'
    'body ::= [a-z ] body | "\\n" rest\n'
    "rest ::= ([a-z ] body)?\n"
)
"""ANNOUNCED's language, its lines spelled by right recursion instead of a loop."""

TAIL = 'root ::= unit+\nunit ::= "#" "a" tail?\ntail ::= "#" "b"\n'
"""A complete ``#a`` goes on as ``#a#b``: ``#`` both lengthens a unit and opens one."""


def _clauses(grammar: IrAst, unit: str) -> tuple[bool, bool, bool]:
    """Whether each of determinism, visibility and EXTEND would refuse alone."""
    rules = {str(rule.name): rule for rule in grammar.rules}
    analysis = GrammarAnalysis(lift_optional_nullables(grammar))
    opening = opens_with(rules, unit)
    return (
        bool(analysis.taxonomy.conflicts),
        not opening.chars <= anchors(grammar),
        opening.overlaps(rule_extensions(analysis).found[unit]),
    )


class _Unconflicted(GrammarAnalysis):
    """The real analysis with only its conflicts set aside, so the clauses after
    determinism decide — EXTEND is still the real analysis' own."""

    def __init__(self, grammar: IrAst) -> None:
        super().__init__(grammar)
        self.taxonomy.conflicts.clear()


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


# ── each clause alone ─────────────────────────────────────────────────────


def test_a_conflicted_unit_refuses_on_determinism_alone() -> None:
    """``y y`` over ``"a" | "aa"`` carves two ways; ``;`` closes the unit."""
    source = 'root ::= unit+\nunit ::= "#" x ";"\nx ::= y y\ny ::= "a" | "aa"\n'
    grammar = _grammar(source, "spec-conflicted")
    assert _clauses(grammar, "unit") == (True, False, False)
    assert speculative_openings(grammar, "unit") == frozenset()


def test_an_opening_inside_a_run_refuses_on_visibility_alone() -> None:
    """A run's characters are no anchors, so no window scan finds the unit."""
    grammar = _grammar('root ::= unit+\nunit ::= [a-z]+ ";"\n', "spec-run")
    assert _clauses(grammar, "unit") == (False, True, False)
    assert speculative_openings(grammar, "unit") == frozenset()


def test_extend_refuses_a_unit_its_own_opening_lengthens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every grammar measured whose EXTEND holds its own visible opening is
    conflicted too, so determinism refuses it first — as here. Set aside by
    hand, EXTEND refuses on its own, while ANNOUNCED, which it does not
    lengthen, is still licensed."""
    tail = _grammar(TAIL, "spec-tail")
    assert GrammarAnalysis(lift_optional_nullables(tail)).taxonomy.conflicts
    assert speculative_openings(tail, "unit") == frozenset()
    monkeypatch.setattr(speculation, "GrammarAnalysis", _Unconflicted)
    tail = _grammar(TAIL, "spec-tail-unconflicted")
    assert _clauses(tail, "unit")[1:] == (False, True)
    assert speculative_openings(tail, "unit") == frozenset()
    announced = _grammar(ANNOUNCED, "spec-announced-unconflicted")
    assert speculative_openings(announced, "section") == frozenset({"#"})


# ── a recursive unit ──────────────────────────────────────────────────────


def test_a_recursive_body_licenses_its_opening() -> None:
    """A complete section goes on only with ``[a-z ]``: the cycle through
    ``body`` is read to its fixpoint rather than given up as ANY."""
    grammar = _grammar(RECURSIVE, "spec-recursive")
    assert _clauses(grammar, "section") == (False, False, False)
    assert speculative_openings(grammar, "section") == frozenset({"#"})


def test_a_recursive_body_splits_to_the_sequential_model() -> None:
    """The licence certifies, and the pieces stitch to the one sequential model."""
    compiled = compile_text(RECURSIVE, cache_key="spec-recursive")
    grammar, binding = compiled.codegen_grammar, compiled.product
    view = compiled.split_analysis or compiled.grammar
    assert any(plan.opening for plan in safe_plans(split_plans(grammar), view))
    text = announced_doc(300)
    split = split_model(parse_model, grammar, Request(text, binding), 4)
    assert split is not None
    assert split == parse_model(grammar, text, binding)
