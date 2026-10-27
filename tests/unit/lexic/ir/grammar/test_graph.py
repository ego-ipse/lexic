"""Tests for ir/grammar/graph.py — the rule-reference graph: references, the
first-occurrence name list, reachability both ways, and cycle membership
as reaching oneself."""

from __future__ import annotations

from lexic.ir.grammar.graph import (
    has_reference,
    reach,
    reachable,
    reaching,
    references,
    refs_in_order,
)
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spine.spine import IrNone


def rule(name: str, *refs: str) -> IrRule:
    """A rule whose body references ``refs``, in the given order, plus a literal tail."""
    items = [IrItem(IrRuleRef(ref)) for ref in refs]
    items.append(IrItem(IrLiteral("x")))
    return IrRule(name, IrSequence(*items))


def table(*rules: IrRule) -> dict[str, IrRule]:
    """The rule table the graph questions are asked of."""
    return {str(r.name): r for r in rules}


# ── references and has_reference ──────────────────────────────────────────


def test_references_yields_every_occurrence_in_pre_order_groups_included():
    """A group's references come where the group stands, and a repeat is
    yielded again: counting a name's references is counting these."""
    group = IrItem(IrAlternation(IrSequence(IrItem(IrRuleRef("g"))), IrSequence()))
    body = IrSequence(
        IrItem(IrRuleRef("a")), group, IrItem(IrRuleRef("a"), IrQuantifier(0, IrNone))
    )
    assert [str(r) for r in references(body)] == ["a", "g", "a"]


def test_has_reference_is_false_only_for_a_ref_free_body():
    """A literal-only body names nothing; one reference anywhere is enough."""
    assert not has_reference(rule("root").body)
    assert has_reference(rule("root", "a").body)


# ── refs_in_order — public direct entry (compile's prelude closure calls it) ──


def test_refs_in_order_collects_names_in_pre_order():
    """refs_in_order walks a subtree and appends each IrRuleRef name, in the
    order it is first encountered."""
    out: list[str] = []
    refs_in_order(rule("root", "b", "a").body, out)
    assert out == ["b", "a"]


def test_refs_in_order_dedupes_a_repeated_ref():
    """A ref seen more than once appears only at its first occurrence."""
    out: list[str] = []
    refs_in_order(rule("root", "b", "a", "b").body, out)
    assert out == ["b", "a"]


def test_refs_in_order_appends_onto_an_existing_accumulator():
    """The accumulator is not reset — callers may seed it or call repeatedly."""
    out: list[str] = ["seed"]
    refs_in_order(rule("root", "a").body, out)
    assert out == ["seed", "a"]


def test_refs_in_order_on_a_ref_free_body_leaves_the_accumulator_untouched():
    """A body with no IrRuleRef contributes nothing."""
    out: list[str] = []
    refs_in_order(rule("root").body, out)
    assert not out


# ── reach, reachable, reaching, cyclic ───────────────────────────────────

_CHAIN = table(rule("root", "a"), rule("a", "b"), rule("b", "a", "ghost"), rule("c"))
"""``a`` and ``b`` form a cycle; ``b`` names an undefined ``ghost``; ``c`` is
unreached."""


def test_reach_is_the_full_closure_inside_a_cycle_too():
    """``b`` reaches itself and everything ``a`` reaches — a closure built
    rule by rule, not one cut short where a walk met a rule on its stack."""
    got = reach(_CHAIN)
    assert got["root"] == {"a", "b", "ghost"}
    assert got["a"] == got["b"] == {"a", "b", "ghost"}
    assert got["c"] == frozenset()


def test_reachable_keeps_only_defined_rules_roots_included():
    """``ghost`` is named and undefined, and an undefined root is dropped."""
    assert reachable(_CHAIN, ["root"]) == {"root", "a", "b"}
    assert reachable(_CHAIN, ["nowhere", "c"]) == {"c"}


def test_reaching_is_the_reverse_closure_entry_included():
    """Every rule with a path to ``b``, and ``b`` itself."""
    assert reaching(_CHAIN, "b") == {"root", "a", "b"}
    assert reaching(_CHAIN, "c") == {"c"}


def test_cycle_membership_is_reaching_oneself_not_reaching_a_cycle():
    """A rule on a cycle reaches itself; ``root`` reaches the ``a``/``b``
    cycle without being on it."""
    assert {name for name, seen in reach(_CHAIN).items() if name in seen} == {"a", "b"}


def test_a_right_recursive_rule_is_on_a_cycle():
    """``r ::= "a" r | "b"`` is recursive — on a cycle — though not
    left-recursive, which is the PDA analysis' own question."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("r"))),
        IrSequence(IrItem(IrLiteral("b"))),
    )
    assert "r" in reach(table(IrRule("r", body)))["r"]
