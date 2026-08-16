"""Tests for compile/pipeline/moments.py — the retaining compile product."""

from __future__ import annotations

import pytest

from lexic.compile import (
    GRAMMAR_MOMENTS,
    GrammarMoments,
    build_codegen_grammar,
    canonical_grammar,
    compile_from_path,
)
from lexic.compile.pipeline.passes import hoist_arms, hoist_groups, relax_non_semantic
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAst, IrItem, IrQuantifier, IrRule, IrRuleRef
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.compile.pipeline.passes_cases import STAR, three_pass_ast


def rules_by_name(ast: IrAst) -> dict[str, IrRule]:
    """The grammar's rules, keyed by name."""
    return {str(rule.name): rule for rule in ast.rules}


def corpus(name: str) -> IrAst:
    """One ground-truth grammar, canonical and directive-bound."""
    text = (GROUND_TRUTH / name).read_text(encoding="utf-8")
    return canonical_grammar(text, GBNF_FLAVOUR)


@pytest.fixture(name="staged_ast")
def staged_ast_fixture() -> IrAst:
    """A grammar every one of the three passes has something to do to."""
    return three_pass_ast()


# ── the fused form and the moments are one composition ─────────────────


def test_build_codegen_grammar_composes_all_three_passes(staged_ast: IrAst) -> None:
    """Groups hoist, arms hoist, noise refs relax — in that order."""
    result = rules_by_name(build_codegen_grammar(staged_ast))
    assert "alt-item" in result  # group hoisted to a helper
    assert "alt-arm2" in result  # multi-item arm hoisted
    arm_items = result["alt-arm2"].body[0]
    assert arm_items[0] == IrItem(IrRuleRef("alt-item"), STAR)
    assert arm_items[1].quantifier == IrQuantifier(0, 1)  # ws ref relaxed


def test_the_fused_form_is_the_moments_last_grammar(staged_ast: IrAst) -> None:
    """One composition: the fused answer IS a moment, not a second run."""
    assert build_codegen_grammar(staged_ast) == GrammarMoments.of(staged_ast).relaxed


def test_the_moments_are_the_pipeline_order() -> None:
    """The record IS the sequence — adjacent moments are adjacent fields."""
    moments = GrammarMoments.of(corpus("json.gbnf"))
    assert len(moments) == len(GRAMMAR_MOMENTS)
    assert moments[0] is moments.canonical
    assert moments[-1] is moments.resolved


def test_each_moment_is_the_stage_applied_to_the_one_before(
    staged_ast: IrAst,
) -> None:
    """Every moment is its own stage's product, in order."""
    moments = GrammarMoments.of(staged_ast)
    assert moments.canonical is staged_ast
    assert moments.grouped == hoist_groups(staged_ast)
    assert moments.armed == hoist_arms(moments.grouped)
    assert moments.relaxed == relax_non_semantic(moments.armed)


# ── a no-op moment is a fact, not an omission ──────────────────────────


def test_a_grammar_with_nothing_to_relax_says_so() -> None:
    """``c.gbnf`` declares ``@non-semantic ws`` and relaxes NOTHING.

    Its ``ws`` is not nullable, and relaxing a required ref to a non-nullable
    rule would widen the accepted language. The stage runs and changes
    nothing, which the product states rather than hides.
    """
    ast = corpus("c.gbnf")
    assert "ws" in ast.non_semantic
    assert GrammarMoments.of(ast).no_ops() == ("relaxed", "resolved")


def test_a_grammar_whose_arms_are_already_single_refs_says_so() -> None:
    """``chess.gbnf``: one pass of three changes anything at all."""
    assert GrammarMoments.of(corpus("chess.gbnf")).no_ops() == (
        "armed",
        "relaxed",
        "resolved",
    )


def test_a_grammar_the_whole_pipeline_leaves_alone_says_so() -> None:
    """``list.gbnf`` is already in codegen shape — every stage is a no-op."""
    moments = GrammarMoments.of(corpus("list.gbnf"))
    assert moments.no_ops() == GRAMMAR_MOMENTS[1:]
    assert moments.resolved == moments.canonical


def test_a_grammar_every_pass_touches_names_only_the_unrun_stage() -> None:
    """``json.gbnf``: all three passes do something; only concretize idles."""
    assert GrammarMoments.of(corpus("json.gbnf")).no_ops() == ("resolved",)


def test_no_ops_never_names_the_state_the_pipeline_was_handed() -> None:
    """``canonical`` is an input, not a stage — it cannot be a no-op."""
    for name in ("json.gbnf", "list.gbnf", "chess.gbnf"):
        assert "canonical" not in GrammarMoments.of(corpus(name)).no_ops()


# ── the compilation runs through the product ───────────────────────────


def test_the_artefact_is_built_from_its_own_moments() -> None:
    """Not a re-run: the artefact's grammar and classes ARE the moments'."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    assert compiled.codegen_grammar is compiled.moments.grammar.resolved
    assert compiled.classes is compiled.moments.classes


def test_the_moments_compose_to_the_artefacts_codegen_grammar() -> None:
    """The corpus gate: the retained stages compose to what was compiled."""
    for name in ("json.gbnf", "arithmetic.gbnf", "chess.gbnf", "list.gbnf"):
        compiled = compile_from_path(GROUND_TRUTH / name)
        assert compiled.codegen_grammar == build_codegen_grammar(compiled.grammar)
        assert compiled.moments.grammar.canonical == compiled.grammar


def test_the_binding_moment_is_the_folds_own_binding() -> None:
    """The binding view is kept, not recomputed for a caller that asks."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    binding = compiled.moments.binding
    assert {bound.class_name for bound in binding} <= set(compiled.classes)
    assert len(binding) == len(compiled.moments.grammar.resolved.rules)


def test_a_moments_product_is_a_record_of_its_three_parts() -> None:
    """``CompileMoments`` IS its fields — grammar, binding, classes."""
    compiled = compile_from_path(GROUND_TRUTH / "list.gbnf")
    grammar, binding, classes = compiled.moments
    assert isinstance(grammar, GrammarMoments)
    assert (binding, classes) == (compiled.moments.binding, compiled.classes)
