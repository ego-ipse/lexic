"""Shared test bodies for the codegen/compile ``passes`` mirrors.

``lexic.codegen.passes`` and ``lexic.compile.passes`` are byte-identical
modules (``compile.passes`` supersedes ``codegen.passes`` — see
``zzz_current_work/260716-ir-native/PLAN_v4.md`` Task 2; codegen stays until
a later task deletes it). Maintaining two verbatim copies of the same test
suite trips pylint's whole-tree duplicate-code check (R0801), so the actual
test bodies live here ONCE as module-level functions taking the module under
test as their sole parameter. ``tests/unit/lexic/codegen/test_passes.py`` and
``tests/unit/lexic/compile/test_passes.py`` each import their own target
module and call :func:`make_passes_tests` to populate their globals — two
real, independently collected test modules, one source of truth for the
bodies.
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

_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _rules_by_name(ast: IrAst) -> dict[str, IrRule]:
    return {str(rule.name): rule for rule in ast.rules}


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


# ── hoist_groups ──────────────────────────────────────────────────────


def _case_hoist_groups_extracts_quantified_ref_group(passes: ModuleType) -> None:
    """A starred ref-bearing group becomes a <rule>-item helper rule."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral(",")), IrItem(IrRuleRef("x"))))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrSequence(IrItem(IrRuleRef("x")), IrItem(group, _STAR))),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    result = _rules_by_name(passes.hoist_groups(ast))
    assert "r-item" in result
    body_item = result["r"].body[0][1]
    assert body_item == IrItem(IrRuleRef("r-item"), _STAR)


def _case_hoist_groups_leaves_literal_only_groups_inline(passes: ModuleType) -> None:
    """A quantified pure-literal group stays a pattern, not a rule."""
    group = IrAlternation(IrLiteral("+"), IrLiteral("-"))
    ast = IrAst(IrSeq(IrRule("r", IrItem(group, _PLUS))), "r")
    hoisted = passes.hoist_groups(ast)
    assert [str(rule.name) for rule in hoisted.rules] == ["r"]


def _case_hoist_groups_appends_helpers_after_the_original_rules(
    passes: ModuleType,
) -> None:
    """Helper rules land at the end, originals keep their order."""
    group = IrAlternation(IrRuleRef("x"))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group, _STAR)),
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


def _case_hoist_arms_extracts_the_multi_item_arm(passes: ModuleType) -> None:
    """The non-ref arm becomes alt-arm2, indexed over non-empty arms."""
    result = _rules_by_name(passes.hoist_arms(_alt_ast()))
    assert "alt-arm2" in result
    assert result["alt-arm2"].body == IrAlternation(
        IrSequence(IrItem(IrLiteral("y")), IrItem(IrRuleRef("ws")))
    )


def _case_hoist_arms_leaves_every_arm_a_unit_ref(passes: ModuleType) -> None:
    """Post-pass, the alternation's non-empty arms are single unit refs."""
    result = _rules_by_name(passes.hoist_arms(_alt_ast()))
    assert result["alt"].body == IrAlternation(
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    )


def _case_hoist_arms_inserts_arm_rules_right_after_their_alternation(
    passes: ModuleType,
) -> None:
    """Arm rules follow the alternation, before later rules."""
    order = [str(rule.name) for rule in passes.hoist_arms(_alt_ast()).rules]
    assert order == ["alt", "alt-arm2", "x", "ws"]


def _case_hoist_arms_keeps_an_empty_arm_in_place(passes: ModuleType) -> None:
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
    result = _rules_by_name(passes.hoist_arms(ast))
    assert IrSequence() in tuple(result["alt"].body)
    assert "alt-arm2" in result


def _case_hoist_arms_skips_non_alternation_rules(passes: ModuleType) -> None:
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


def _case_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms(
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
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )
    result = _rules_by_name(passes.hoist_arms(ast))
    assert "alt-arm3" in result
    assert "alt-arm2" not in result


def _case_hoist_arms_empty_arm_does_not_advance_the_counter(
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
            IrRule("ws", IrItem(IrLiteral(" "), _STAR)),
        ),
        "alt",
    )
    result = _rules_by_name(passes.hoist_arms(ast))
    assert "alt-arm2" in result
    assert list(result["alt"].body) == [
        IrSequence(IrItem(IrRuleRef("x"))),
        IrSequence(),
        IrSequence(IrItem(IrRuleRef("alt-arm2"))),
    ]


def _case_hoist_arms_raises_on_a_name_collision(passes: ModuleType) -> None:
    """A user rule already named <rule>-arm<N> is refused, not shadowed."""
    ast = _alt_ast()
    ast = IrAst(IrSeq(*ast.rules, IrRule("alt-arm2", IrLiteral("!"))), ast.start)
    with pytest.raises(UnsupportedConstructError, match="collides"):
        passes.hoist_arms(ast)


# ── relax_non_semantic ────────────────────────────────────────────────


def _case_relax_sets_min_zero_on_noise_refs(passes: ModuleType) -> None:
    """A required ref to a semantic=False rule becomes optional."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), _PLUS)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = _rules_by_name(passes.relax_non_semantic(ast))
    assert relaxed["r"].body[0][0].quantifier == IrQuantifier(0, IrNone)


def _case_relax_keeps_refs_to_semantic_rules(passes: ModuleType) -> None:
    """Only flagged rules relax; everything else is untouched."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("x"), _PLUS)),
            IrRule("x", IrLiteral("x")),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast) == ast


def _case_relax_does_not_descend_into_groups(passes: ModuleType) -> None:
    """Arm-level items only — a noise ref inside an inline group keeps min."""
    group = IrAlternation(IrSequence(IrItem(IrRuleRef("ws"), _PLUS)))
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(group)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    relaxed = _rules_by_name(passes.relax_non_semantic(ast))
    inner = relaxed["r"].body[0][0].atom
    assert isinstance(inner, IrAlternation)
    assert inner[0][0].quantifier == _PLUS


def _case_relax_is_a_noop_when_the_ref_is_already_optional(
    passes: ModuleType,
) -> None:
    """A noise ref already at min=0 is untouched (idempotent, no double-relax)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"), _STAR)),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast) == ast


def _case_relax_preserves_the_semantic_flags(passes: ModuleType) -> None:
    """The noise flag itself survives the rewrite (ast.non_semantic stable)."""
    ast = IrAst(
        IrSeq(
            IrRule("r", IrItem(IrRuleRef("ws"))),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "r",
    )
    assert passes.relax_non_semantic(ast).non_semantic == frozenset({"ws"})


# ── composition ───────────────────────────────────────────────────────


def _case_build_codegen_grammar_composes_all_three_passes(
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
                    IrSequence(IrItem(group, _STAR), IrItem(IrRuleRef("ws"))),
                ),
            ),
            IrRule("x", IrLiteral("x")),
            IrRule("ws", IrItem(IrLiteral(" "), _PLUS), semantic=False),
        ),
        "alt",
    )
    result = _rules_by_name(passes.build_codegen_grammar(ast))
    assert "alt-item" in result  # group hoisted to a helper
    assert "alt-arm2" in result  # multi-item arm hoisted
    arm_items = result["alt-arm2"].body[0]
    assert arm_items[0] == IrItem(IrRuleRef("alt-item"), _STAR)
    assert arm_items[1].quantifier == IrQuantifier(0, 1)  # ws ref relaxed


_CASES: dict[str, Callable[[ModuleType], None]] = {
    "test_hoist_groups_extracts_quantified_ref_group": (
        _case_hoist_groups_extracts_quantified_ref_group
    ),
    "test_hoist_groups_leaves_literal_only_groups_inline": (
        _case_hoist_groups_leaves_literal_only_groups_inline
    ),
    "test_hoist_groups_appends_helpers_after_the_original_rules": (
        _case_hoist_groups_appends_helpers_after_the_original_rules
    ),
    "test_hoist_arms_extracts_the_multi_item_arm": (
        _case_hoist_arms_extracts_the_multi_item_arm
    ),
    "test_hoist_arms_leaves_every_arm_a_unit_ref": (
        _case_hoist_arms_leaves_every_arm_a_unit_ref
    ),
    "test_hoist_arms_inserts_arm_rules_right_after_their_alternation": (
        _case_hoist_arms_inserts_arm_rules_right_after_their_alternation
    ),
    "test_hoist_arms_keeps_an_empty_arm_in_place": (
        _case_hoist_arms_keeps_an_empty_arm_in_place
    ),
    "test_hoist_arms_skips_non_alternation_rules": (
        _case_hoist_arms_skips_non_alternation_rules
    ),
    "test_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms": (
        _case_hoist_arms_numbers_over_non_empty_arms_not_hoisted_arms
    ),
    "test_hoist_arms_empty_arm_does_not_advance_the_counter": (
        _case_hoist_arms_empty_arm_does_not_advance_the_counter
    ),
    "test_hoist_arms_raises_on_a_name_collision": (
        _case_hoist_arms_raises_on_a_name_collision
    ),
    "test_relax_sets_min_zero_on_noise_refs": (_case_relax_sets_min_zero_on_noise_refs),
    "test_relax_keeps_refs_to_semantic_rules": (
        _case_relax_keeps_refs_to_semantic_rules
    ),
    "test_relax_does_not_descend_into_groups": (
        _case_relax_does_not_descend_into_groups
    ),
    "test_relax_is_a_noop_when_the_ref_is_already_optional": (
        _case_relax_is_a_noop_when_the_ref_is_already_optional
    ),
    "test_relax_preserves_the_semantic_flags": (
        _case_relax_preserves_the_semantic_flags
    ),
    "test_build_codegen_grammar_composes_all_three_passes": (
        _case_build_codegen_grammar_composes_all_three_passes
    ),
}


def make_passes_tests(passes: ModuleType) -> dict[str, Callable[[], None]]:
    """Bind the shared passes-suite bodies to ``passes``.

    :param passes: ``lexic.codegen.passes`` or ``lexic.compile.passes`` —
        the module under test.
    :returns: ``{test function name: zero-arg callable}``, ready for
        ``globals().update(...)`` in a mirror test module.
    """
    return {name: partial(case, passes) for name, case in _CASES.items()}
