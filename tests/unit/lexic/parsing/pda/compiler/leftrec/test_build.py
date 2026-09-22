"""Tests for lexic.parsing.pda.compiler.leftrec.build — the per-iteration build.

This module's refusals are the interesting part. Each one, if waved through,
produces a WRONG MODEL rather than a slow parse — the rule would be rewritten
into a loop and then built through a routine that does not fit its iterations,
and the parse would succeed while meaning something else.

The width is pinned too, because it is what cuts the flat sink back into
iterations: one wrong and every node past the first takes its neighbours'
values.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec.build import fold_build
from lexic.parsing.pda.compiler.leftrec.shape import Fold, Recursive, foldable
from lexic.parsing.products import _model_product
from tests.unit.lexic.parsing.pda.runtime.pda_runtime_helpers import pda_and_earley


def parts(source: str, rule: str):
    """``(fold shape, routines)`` for one rule of ``source``."""
    compiled = compile_text(source, cache_key=f"build-{hash(source)}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    analysis = GrammarAnalysis(grammar)
    rules = {str(one.name): one for one in grammar.rules}
    shape = foldable(rule, rules[rule], rules, analysis)
    return shape, _model_product(compiled.codegen_grammar, compiled.product)


_TWO_ITEM = (
    'root ::= expr "!"\nexpr ::= expr op term | term\nterm ::= [a-z]\nop ::= "+"\n'
)


def test_the_width_is_the_captures_past_the_recursive_slot() -> None:
    """``expr op term`` folds two values per iteration, not three.

    Slot 0 is the accumulator and is supplied by the fold itself; the width
    counts what the ITERATION brings. Counting the accumulator would cut the
    sink one value late on every iteration after the first.
    """
    shape, product = parts(_TWO_ITEM, "expr")
    assert shape is not None

    got = fold_build(shape, product.binding.routines)

    assert got is not None
    assert got.width == 2, "op and term"
    assert got.slots == 3, "and the accumulator ahead of them"


def test_more_than_one_recursive_arm_is_refused() -> None:
    """Which arm an iteration matched is not recoverable from a flat sink.

    The iterations land in one list with no arm tag, so a two-arm fold would
    have to guess which routine built each one. Refusing leaves the rule
    islanding, which is correct rather than merely safe.
    """
    # The shape reader declines a two-recursive-arm rule before `fold_build`
    # ever sees one, so the refusal is asserted on a shape constructed to
    # reach it — otherwise this would pin the wrong module's decision.
    shape, product = parts('root ::= x "!"\nx ::= x "d" | "a"\n', "x")
    assert shape is not None
    two_arms = Fold(shape.base, shape.steps + (shape.steps[0],))

    assert fold_build(two_arms, product.binding.routines) is None


def test_a_step_with_no_routine_is_refused() -> None:
    """A rule the binding has no routine for cannot be folded through.

    There would be nothing to call, and building the iteration some other way
    would build a different node than the arm does.
    """
    shape, product = parts(_TWO_ITEM, "expr")
    assert shape is not None
    unknown = Fold(shape.base, (Recursive(0, "no-such-rule", shape.steps[0].rest),))

    assert fold_build(unknown, product.binding.routines) is None


def test_the_plan_is_the_arms_own_plan() -> None:
    """The fold builds through the ordinary bake's plan, not a second derivation.

    Two derivations of the same plan could drift, and then one arm would build
    two different models depending on whether it was reached by the fold or by
    its own clone.
    """
    shape, product = parts(_TWO_ITEM, "expr")
    assert shape is not None
    routine = product.binding.routines[shape.steps[0].rule]
    construction = routine.construction
    assert construction is not None and construction.licence is not None

    got = fold_build(shape, product.binding.routines)

    assert got is not None
    assert got.step is not None
    assert got.slots == len(routine.captures)


def test_a_step_that_captures_nothing_folds_with_width_zero() -> None:
    """``A ::= A "a" | "a"`` folds in SHAPE and now in VALUE too.

    The β is a bare literal, so an iteration leaves nothing in the sink and the
    nesting depth is the whole information. The frame's ``count`` keeps that
    depth past the loop's close, so the build folds with a width of ZERO: one synthetic
    slot, the value so far, handed to the arm's own build once per iteration.
    """
    shape, product = parts('root ::= root "a" | "a"\n', "root")

    assert shape is not None, "the SHAPE reader takes it"
    got = fold_build(shape, product.binding.routines)
    assert got is not None, "the VALUE is the count"
    assert (got.width, got.slots) == (0, 1)


@pytest.mark.parametrize("text", ["a", "aa", "aaa", "a" * 200])
def test_a_capture_free_fold_is_the_models_earley_builds(text: str) -> None:
    """Answered on the PDA — not an island, not a fallback — with Earley's model.

    The PDA is asked directly, so a missing or wrong count cannot hide behind
    the product's fallback: it raises, or it builds a different nesting.
    """
    pda, earley = pda_and_earley('root ::= root "a" | "a"\n', text, "fold-count-parse")
    assert pda == earley
