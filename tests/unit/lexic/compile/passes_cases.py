"""Shared test bodies for the ``lexic.compile.passes`` module.

The test bodies live here as module-level functions taking the module under
test as their sole parameter; ``tests/unit/lexic/compile/test_passes.py``
imports its target module and calls :func:`make_passes_tests` to populate its
globals. The parameterization is a vestige of a strangler window when a
byte-identical twin module existed; only the compile module remains.
"""

from __future__ import annotations

from functools import partial
from types import ModuleType
from typing import Callable

import pytest

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

STAR = IrQuantifier(0, IrNone)
PLUS = IrQuantifier(1, IrNone)


def rules_by_name(ast: IrAst) -> dict[str, IrRule]:
    """The AST's rules keyed by name."""
    return {str(rule.name): rule for rule in ast.rules}


def alt_ast() -> IrAst:
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
            IrRule("ws", IrItem(IrLiteral(" "), STAR)),
        ),
        "alt",
    )


# ── hoist_groups ──────────────────────────────────────────────────────


def case_hoist_groups_extracts_quantified_ref_group(passes: ModuleType) -> None:
    """A starred ref-bearing group becomes a <rule>-item helper rule."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral(",")), IrItem(IrRuleRef("x"))))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrSequence(IrItem(IrRuleRef("x")), IrItem(group, STAR))),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    result = rules_by_name(passes.hoist_groups(ast))
    assert "r-item" in result
    body_item = result["r"].body[0][1]
    assert body_item == IrItem(IrRuleRef("r-item"), STAR)


def case_hoist_groups_leaves_literal_only_groups_inline(passes: ModuleType) -> None:
    """A quantified pure-literal group stays a pattern, not a rule."""
    group = IrAlternation(IrLiteral("+"), IrLiteral("-"))
    ast = IrAst(IrSeq(IrRule("r", IrItem(group, PLUS))), "r")
    hoisted = passes.hoist_groups(ast)
    assert [str(rule.name) for rule in hoisted.rules] == ["r"]


def case_hoist_groups_appends_helpers_after_the_original_rules(
    passes: ModuleType,
) -> None:
    """Helper rules land at the end, originals keep their order."""
    group = IrAlternation(IrRuleRef("x"))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group, STAR)),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    assert [str(rule.name) for rule in passes.hoist_groups(ast).rules] == [
        "r",
        "x",
        "r-item",
    ]


# ── hoist_arms ────────────────────────────────────────────────────────


def case_hoist_arms_extracts_the_multi_item_arm(passes: ModuleType) -> None:
    """The non-ref arm becomes alt-arm2, indexed over non-empty arms."""
    result = rules_by_name(passes.hoist_arms(alt_ast()))
    assert "alt-arm2" in result
    assert result["alt-arm2"].body == IrAlternation(
        IrSequence(IrItem(IrLiteral("y")), IrItem(IrRuleRef("ws")))
    )


def case_hoist_arms_leaves_every_arm_a_unit_ref(passes: ModuleType) -> None:
    """Post-pass, the alternation's non-empty arms are single unit refs."""
    result = rules_by_name(passes.hoist_arms(alt_ast()))
    assert result["alt"].body == IrAlternation(
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    )


def case_hoist_arms_inserts_arm_rules_right_after_their_alternation(
    passes: ModuleType,
) -> None:
    """Arm rules follow the alternation, before later rules."""
    order = [str(rule.name) for rule in passes.hoist_arms(alt_ast()).rules]
    assert order == ["alt", "alt-arm2", "x", "ws"]


def case_hoist_arms_keeps_an_empty_arm_in_place(passes: ModuleType) -> None:
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
            IrRule("ws", IrItem(IrLiteral(" "), STAR)),
        ),
        "alt",
    )
    result = rules_by_name(passes.hoist_arms(ast))
    assert IrSequence() in tuple(result["alt"].body)
    assert "alt-arm2" in result


def case_hoist_arms_skips_non_alternation_rules(passes: ModuleType) -> None:
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
    assert passes.hoist_arms(ast) == ast


def case_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms(
    passes: ModuleType,
) -> None:
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
            IrRule("ws", IrItem(IrLiteral(" "), STAR)),
        ),
        "alt",
    )
    result = rules_by_name(passes.hoist_arms(ast))
    assert "alt-arm3" in result
    assert "alt-arm2" not in result


def case_hoist_arms_empty_arm_does_not_advance_the_counter(
    passes: ModuleType,
) -> None:
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
            IrRule("ws", IrItem(IrLiteral(" "), STAR)),
        ),
        "alt",
    )
    result = rules_by_name(passes.hoist_arms(ast))
    assert "alt-arm2" in result
    assert list(result["alt"].body) == [
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    ]


def case_hoist_arms_raises_on_a_name_collision(passes: ModuleType) -> None:
    """A user rule already named <rule>-arm<N> is refused, not shadowed."""
    ast = alt_ast()
    ast = IrAst(IrSeq(*ast.rules, IrRule("alt-arm2", IrLiteral("!"))), ast.start)
    with pytest.raises(UnsupportedConstructError, match="collides"):
        passes.hoist_arms(ast)


# ── relax_non_semantic ────────────────────────────────────────────────


def case_relax_sets_min_zero_on_noise_refs(passes: ModuleType) -> None:
    """A required ref to a semantic=False rule becomes optional."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), PLUS)),
            IrRule("ws", IrItem(IrLiteral(" "), PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = rules_by_name(passes.relax_non_semantic(ast))
    assert relaxed["r"].body[0][0].quantifier == IrQuantifier(0, IrNone)


def case_relax_keeps_refs_to_semantic_rules(passes: ModuleType) -> None:
    """Only flagged rules relax; everything else is untouched."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("x"), PLUS)),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast) == ast


def case_relax_does_not_descend_into_groups(passes: ModuleType) -> None:
    """Arm-level items only — a noise ref inside an inline group keeps min."""
    group = IrAlternation(IrSequence(IrItem(IrRuleRef("ws"), PLUS)))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group)),
            IrRule("ws", IrItem(IrLiteral(" "), PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = rules_by_name(passes.relax_non_semantic(ast))
    inner = relaxed["r"].body[0][0].atom
    assert isinstance(inner, IrAlternation)
    assert inner[0][0].quantifier == PLUS


def case_relax_is_a_noop_when_the_ref_is_already_optional(
    passes: ModuleType,
) -> None:
    """A noise ref already at min=0 is untouched (idempotent, no double-relax)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), STAR)),
            IrRule("ws", IrItem(IrLiteral(" "), PLUS), semantic=False),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast) == ast


def case_relax_preserves_the_semantic_flags(passes: ModuleType) -> None:
    """The noise flag itself survives the rewrite (ast.non_semantic stable)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"))),
            IrRule("ws", IrItem(IrLiteral(" "), PLUS), semantic=False),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast).non_semantic == frozenset({"ws"})


# ── composition ───────────────────────────────────────────────────────


def case_build_codegen_grammar_composes_all_three_passes(
    passes: ModuleType,
) -> None:
    """Groups hoist, arms hoist, noise refs relax — in that order."""
    group = IrAlternation(IrRuleRef("x"))
    ast = IrAst(
        IrSeq(
            IrRule(
                "alt",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("x"))),
                    IrSequence(IrItem(group, STAR), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), PLUS), semantic=False),
        ),
        "alt",
    )
    result = rules_by_name(passes.build_codegen_grammar(ast))
    assert "alt-item" in result  # group hoisted to a helper
    assert "alt-arm2" in result  # multi-item arm hoisted
    arm_items = result["alt-arm2"].body[0]
    assert arm_items[0] == IrItem(IrRuleRef("alt-item"), STAR)
    assert arm_items[1].quantifier == IrQuantifier(0, 1)  # ws ref relaxed


CASES: dict[str, Callable[[ModuleType], None]] = {
    "test_hoist_groups_extracts_quantified_ref_group": (
        case_hoist_groups_extracts_quantified_ref_group
    ),
    "test_hoist_groups_leaves_literal_only_groups_inline": (
        case_hoist_groups_leaves_literal_only_groups_inline
    ),
    "test_hoist_groups_appends_helpers_after_the_original_rules": (
        case_hoist_groups_appends_helpers_after_the_original_rules
    ),
    "test_hoist_arms_extracts_the_multi_item_arm": (
        case_hoist_arms_extracts_the_multi_item_arm
    ),
    "test_hoist_arms_leaves_every_arm_a_unit_ref": (
        case_hoist_arms_leaves_every_arm_a_unit_ref
    ),
    "test_hoist_arms_inserts_arm_rules_right_after_their_alternation": (
        case_hoist_arms_inserts_arm_rules_right_after_their_alternation
    ),
    "test_hoist_arms_keeps_an_empty_arm_in_place": (
        case_hoist_arms_keeps_an_empty_arm_in_place
    ),
    "test_hoist_arms_skips_non_alternation_rules": (
        case_hoist_arms_skips_non_alternation_rules
    ),
    "test_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms": (
        case_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms
    ),
    "test_hoist_arms_empty_arm_does_not_advance_the_counter": (
        case_hoist_arms_empty_arm_does_not_advance_the_counter
    ),
    "test_hoist_arms_raises_on_a_name_collision": (
        case_hoist_arms_raises_on_a_name_collision
    ),
    "test_relax_sets_min_zero_on_noise_refs": (case_relax_sets_min_zero_on_noise_refs),
    "test_relax_keeps_refs_to_semantic_rules": (
        case_relax_keeps_refs_to_semantic_rules
    ),
    "test_relax_does_not_descend_into_groups": (
        case_relax_does_not_descend_into_groups
    ),
    "test_relax_is_a_noop_when_the_ref_is_already_optional": (
        case_relax_is_a_noop_when_the_ref_is_already_optional
    ),
    "test_relax_preserves_the_semantic_flags": (
        case_relax_preserves_the_semantic_flags
    ),
    "test_build_codegen_grammar_composes_all_three_passes": (
        case_build_codegen_grammar_composes_all_three_passes
    ),
}


def make_passes_tests(passes: ModuleType) -> dict[str, Callable[[], None]]:
    """Bind the shared passes-suite bodies to ``passes``.

    :param passes: ``lexic.compile.passes`` — the module under test.
    :returns: ``{test function name: zero-arg callable}``, ready for
        ``globals().update(...)`` in a mirror test module.
    """
    return {name: partial(case, passes) for name, case in CASES.items()}
