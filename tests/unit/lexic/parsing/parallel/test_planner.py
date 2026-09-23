"""Tests for ``lexic.parsing.parallel.planner`` — which plans a grammar admits.

Derivation and certification are per grammar: the plans are memoised by
grammar identity, and a plan survives only the proof its shape owes.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.planner import _certified, split_plan, split_plans
from tests.split_helpers import LEAD_RULE
from tests.unit.lexic.parsing.parallel.envelope_fixtures import (
    CONTINUATION_SOURCE,
    TWO_MARK_SOURCE,
)


def test_plan_is_memoised_per_grammar():
    """The shape analysis runs once per grammar identity."""
    compiled = compile_text(LEAD_RULE)
    grammar = compiled.codegen_grammar
    assert split_plan(grammar) is split_plan(grammar)


def test_split_plans_are_memoised_per_grammar_while_cuts_stay_per_document() -> None:
    """The plan tuple is one object per grammar identity — computed once,
    reused — but the cut OFFSETS it produces are a function of the document,
    never cached across two different ones."""
    compiled = compile_text(TWO_MARK_SOURCE, cache_key="two-mark-memo")
    grammar = compiled.codegen_grammar

    assert split_plans(grammar) is split_plans(grammar)

    plan = split_plans(grammar)[1].envelope
    assert plan is not None and plan.mark == "\n"

    short_entries = [f"k{chr(97 + i)} = v" for i in range(26)]
    long_entries = short_entries * 4
    short_text = "\n".join(short_entries)
    long_text = "\n".join(long_entries)

    assert plan.cuts(short_text) != plan.cuts(long_text)


# ── the terminated-plan boundary route: SplitPlan.bound ──────────────────

_TWO_ARM_TERMINATOR = (
    "root ::= item+\n"
    "item ::= a nl | b nl\n"
    'a ::= "a" mid\n'
    'b ::= "b" mid\n'
    'mid ::= "\\n" "x"\n'
    'nl ::= "\\n"\n'
)
"""A unit with two arms sharing a final ``nl``: a raw terminated plan
exists, but the unit has no single-arm shape to announce itself, so
``unit_prefix`` returns ``None`` and there is no boundary route either."""


def test_a_terminated_plan_with_an_announcing_prefix_is_certified_with_a_bound() -> (
    None
):
    """``terminates_once`` fails on this unit, but it announces itself, so
    certification takes the boundary route and the certified plan carries
    the proven prefix — the raw (uncertified) plan carries none."""
    compiled = compile_text(CONTINUATION_SOURCE)
    grammar = compiled.codegen_grammar
    plan = split_plan(grammar)

    assert plan is not None and plan.bound is None

    certified = _certified(plan, compiled.split_analysis or compiled.grammar)

    assert certified is not None
    assert certified.bound is not None
    assert certified.bound.literal == " "


def test_a_terminated_plan_without_an_announcing_prefix_is_dropped() -> None:
    """A raw terminated plan exists, but the unit's two arms give
    ``unit_prefix`` no single shape to announce — neither route certifies,
    and the plan is dropped rather than certified with an empty bound."""
    compiled = compile_text(_TWO_ARM_TERMINATOR)
    grammar = compiled.codegen_grammar
    plan = split_plan(grammar)

    assert plan is not None and plan.bound is None
    assert _certified(plan, compiled.split_analysis or compiled.grammar) is None
