"""Tests for lexic.parsing.parallel.stitch.plan — the region-plan derivation.

The plan is derived once per grammar and product and then spent on every
document, so what these pin is the DERIVATION: which recurrences are
recognised, which are declined, and that a declined one is a clean ``None``
rather than a fallback that indexes past the end of a malformed arm.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.stitch.plan import (
    bracket_rule,
    derive_plan,
    field_slot,
    model_type,
)
from tests.split_helpers import PAREN_SUM


def test_direct_candidate_short_tail_arm_declines_without_index_error() -> None:
    """A malformed direct tail is a safe decline, not an indexing fallback."""
    compiled = compile_text(
        'root ::= group\ngroup ::= "(" node more* ")"\nnode ::= [a-z]+\nmore ::= ","\n'
    )

    assert derive_plan(compiled.codegen_grammar, compiled.product, "group") is None
    assert compiled.parse("(alpha)").to_text() == "(alpha)"


def test_a_configured_recurrence_binds_to_real_classes_and_slots() -> None:
    """The ordinary items/tail shape derives a plan naming both model classes."""
    compiled = compile_text(
        "root ::= group\n"
        'group ::= "(" items ")"\n'
        "items ::= node more*\n"
        'more ::= "," node\n'
        "node ::= [a-z]+\n",
        cache_key="configured-plan",
    )
    plan = derive_plan(compiled.codegen_grammar, compiled.product, "group")

    assert plan is not None
    assert plan.head_rule == "node"
    assert plan.separators == frozenset({","})
    assert plan.outer_items >= 0


def test_a_rule_with_no_recurrence_derives_no_plan() -> None:
    """A bracket rule that repeats nothing is a decline, not an empty plan."""
    compiled = compile_text('root ::= group\ngroup ::= "(" node ")"\nnode ::= [a-z]+\n')

    assert derive_plan(compiled.codegen_grammar, compiled.product, "group") is None


def test_the_derived_plan_is_memoised_per_grammar_and_product() -> None:
    """Deriving twice returns the same object — the plan is spent, not rebuilt."""
    compiled = compile_text(
        "root ::= group\n"
        'group ::= "(" items ")"\n'
        "items ::= node more*\n"
        'more ::= "," node\n'
        "node ::= [a-z]+\n",
        cache_key="memoised-plan",
    )
    grammar, product = compiled.codegen_grammar, compiled.product

    first = derive_plan(grammar, product, "group")
    assert first is derive_plan(grammar, product, "group")


def test_model_type_and_field_slot_refuse_rather_than_assume() -> None:
    """Both readers answer ``None`` for a routine that names no generated class.

    The defect this catches: returning a default slot or the base class would
    make an unbindable rule look bindable, and the split would then write a
    model field that does not exist.
    """
    compiled = compile_text('root ::= "a"\n')
    routine = next(iter(compiled.product.routines.values()))

    assert model_type(None) is None
    assert field_slot(routine, 99) is None


def test_a_run_led_by_a_set_carries_the_set() -> None:
    """``(addop term)*`` with ``addop ::= "+" | "-"`` separates by either: the
    plan names both, and never the terms' own ``*/``."""
    compiled = compile_text(PAREN_SUM, cache_key="lead-set-plan")
    grammar = compiled.codegen_grammar
    plan = derive_plan(grammar, compiled.product, bracket_rule(grammar, "factor", "("))

    assert plan is not None
    assert plan.head_rule == "term"
    assert plan.separators == frozenset("+-")


def test_around_holds_what_the_bracket_arm_emits_beside_its_run() -> None:
    """The delimiters, and a wrapper's characters where the arm has one."""
    compiled = compile_text(
        PAREN_SUM.replace('"(" expr ")"', '"(" pad expr ")"') + 'pad ::= " "*\n',
        cache_key="lead-set-around",
    )
    grammar = compiled.codegen_grammar
    plan = derive_plan(grammar, compiled.product, bracket_rule(grammar, "factor", "("))

    assert plan is not None
    assert all(plan.around.has(char) for char in "( )")
    assert not any(plan.around.has(char) for char in plan.separators)
