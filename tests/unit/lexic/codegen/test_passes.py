"""Tests for codegen/passes.py — hoist groups, hoist arms, relax noise."""

from __future__ import annotations

import pytest

from lexic.codegen.passes import (
    build_codegen_grammar,
    hoist_arms,
    hoist_groups,
    relax_non_semantic,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)

_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _rules_by_name(ast: IrAst) -> dict[str, IrRule]:
    return {str(rule.name): rule for rule in ast.rules}


# ── hoist_groups ──────────────────────────────────────────────────────


def test_hoist_groups_extracts_quantified_ref_group():
    """A starred ref-bearing group becomes a <rule>-item helper rule."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral(",")), IrItem(IrRuleRef("x"))))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrSequence(IrItem(IrRuleRef("x")), IrItem(group, _STAR))),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    result = _rules_by_name(hoist_groups(ast))
    assert "r-item" in result
    body_item = result["r"].body[0][1]
    assert body_item == IrItem(IrRuleRef("r-item"), _STAR)


def test_hoist_groups_leaves_literal_only_groups_inline():
    """A quantified pure-literal group stays a pattern, not a rule."""
    group = IrAlternation(IrLiteral("+"), IrLiteral("-"))
    ast = IrAst(IrSeq(IrRule("r", IrItem(group, _PLUS))), "r")
    hoisted = hoist_groups(ast)
    assert [str(rule.name) for rule in hoisted.rules] == ["r"]


def test_hoist_groups_appends_helpers_after_the_original_rules():
    """Helper rules land at the end, originals keep their order."""
    group = IrAlternation(IrRuleRef("x"))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group, _STAR)),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    assert [str(rule.name) for rule in hoist_groups(ast).rules] == ["r", "x", "r-item"]


# ── hoist_arms ────────────────────────────────────────────────────────


def _alt_ast() -> IrAst:
    """alt → x | "y" ws — one unit-ref arm, one multi-item arm."""
    return IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(IrItem(IrLiteral("y")), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )


def test_hoist_arms_extracts_the_multi_item_arm():
    """The non-ref arm becomes alt-arm2, indexed over non-empty arms."""
    result = _rules_by_name(hoist_arms(_alt_ast()))
    assert "alt-arm2" in result
    assert result["alt-arm2"].body == IrAlternation(
        IrSequence(IrItem(IrLiteral("y")), IrItem(IrRuleRef("ws")))
    )


def test_hoist_arms_leaves_every_arm_a_unit_ref():
    """Post-pass, the alternation's non-empty arms are single unit refs."""
    result = _rules_by_name(hoist_arms(_alt_ast()))
    assert result["alt"].body == IrAlternation(
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    )


def test_hoist_arms_inserts_arm_rules_right_after_their_alternation():
    """Arm rules follow the alternation, before later rules."""
    order = [str(rule.name) for rule in hoist_arms(_alt_ast()).rules]
    assert order == ["alt", "alt-arm2", "x", "ws"]


def test_hoist_arms_keeps_an_empty_arm_in_place():
    """The zero-kid empty arm survives (new-pipeline behavior, spike probe g)."""
    ast = IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(IrItem(IrRuleRef("ws")), IrItem(IrRuleRef("x"))),
                    IrSequence(),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )
    result = _rules_by_name(hoist_arms(ast))
    assert IrSequence() in tuple(result["alt"].body)
    assert "alt-arm2" in result


def test_hoist_arms_skips_non_alternation_rules():
    """Sequence and value_str rules pass through untouched."""
    ast = IrAst(
        IrSeq(
            IrRule("seq", IrSequence(IrItem(IrRuleRef("x")), IrItem(IrLiteral("!")))),
            IrRule(
                "x",
                IrAlternation(
                    IrLiteral("a"),
                    IrSequence(IrItem(IrLiteral("b")), IrItem(IrLiteral("c"))),
                ),
            ),
        ),
        "seq",
    )
    assert hoist_arms(ast) == ast


def test_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms():
    """Arm numbering counts every non-empty arm, not just the hoisted ones.

    Two unit-ref arms (never hoisted) precede the multi-item arm, so the
    hoisted rule is ``alt-arm3`` — the arm's position among non-empty arms,
    not the count of arms actually hoisted.
    """
    ast = IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(IrItem(IrRuleRef("y"))),
                    IrSequence(IrItem(IrLiteral("z")), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("y", IrLiteral("y")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )
    result = _rules_by_name(hoist_arms(ast))
    assert "alt-arm3" in result
    assert "alt-arm2" not in result


def test_hoist_arms_empty_arm_does_not_advance_the_counter():
    """An empty arm between a unit-ref arm and a multi-item arm is skipped
    when numbering — the multi-item arm is still ``-arm2``, not ``-arm3``."""
    ast = IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(),
                    IrSequence(IrItem(IrLiteral("z")), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )
    result = _rules_by_name(hoist_arms(ast))
    assert "alt-arm2" in result
    assert list(result["alt"].body) == [
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    ]


def test_hoist_arms_raises_on_a_name_collision():
    """A user rule already named <rule>-arm<N> is refused, not shadowed."""
    ast = _alt_ast()
    ast = IrAst(IrSeq(*ast.rules, IrRule("alt-arm2", IrLiteral("!"))), ast.start)
    with pytest.raises(UnsupportedConstructError, match="collides"):
        hoist_arms(ast)


# ── relax_non_semantic ────────────────────────────────────────────────


def test_relax_sets_min_zero_on_noise_refs():
    """A required ref to a semantic=False rule becomes optional."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), _PLUS)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = _rules_by_name(relax_non_semantic(ast))
    assert relaxed["r"].body[0][0].quantifier == IrQuantifier(0, IrNone)


def test_relax_keeps_refs_to_semantic_rules():
    """Only flagged rules relax; everything else is untouched."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("x"), _PLUS)),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    assert relax_non_semantic(ast) == ast


def test_relax_does_not_descend_into_groups():
    """Arm-level items only — a noise ref inside an inline group keeps min."""
    group = IrAlternation(IrSequence(IrItem(IrRuleRef("ws"), _PLUS)))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = _rules_by_name(relax_non_semantic(ast))
    inner = relaxed["r"].body[0][0].atom
    assert isinstance(inner, IrAlternation)
    assert inner[0][0].quantifier == _PLUS


def test_relax_is_a_noop_when_the_ref_is_already_optional():
    """A noise ref already at min=0 is untouched (idempotent, no double-relax)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), _STAR)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    assert relax_non_semantic(ast) == ast


def test_relax_preserves_the_semantic_flags():
    """The noise flag itself survives the rewrite (ast.non_semantic stable)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"))),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    assert relax_non_semantic(ast).non_semantic == frozenset({"ws"})


# ── composition ───────────────────────────────────────────────────────


def test_build_codegen_grammar_composes_all_three_passes():
    """Groups hoist, arms hoist, noise refs relax — in that order."""
    group = IrAlternation(IrRuleRef("x"))
    ast = IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(IrItem(group, _STAR), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "alt",
    )
    result = _rules_by_name(build_codegen_grammar(ast))
    assert "alt-item" in result  # group hoisted to a helper
    assert "alt-arm2" in result  # multi-item arm hoisted
    arm_items = result["alt-arm2"].body[0]
    assert arm_items[0] == IrItem(IrRuleRef("alt-item"), _STAR)
    assert arm_items[1].quantifier == IrQuantifier(0, 1)  # ws ref relaxed
