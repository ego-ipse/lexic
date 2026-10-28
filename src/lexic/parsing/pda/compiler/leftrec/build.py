"""Folding the iterations back into the model the grammar's arms build.

The rewrite parses `A ::= A β | γ` as `(γ)(β)*`; this is the other half. Each
iteration is folded through the ROUTINE OF THE ARM it came from — the hoisted
`A-arm` rule whose construction takes the recursive slot and the rest of `β` —
so `A(A(A(γ, β), β), β)` comes out left-nested through the same constructors,
with the same fields, as the arm would have built it.

**No new build machinery.** A composed build reads its values out of a sinks
array by item slot, so one iteration is that same build handed a SYNTHETIC
array: slot 0 holding the value accumulated so far, and the rest holding that
iteration's own captures. The model is therefore identical by construction
rather than by comparison — it is the arm's own build, called with the arm's
own values.

**Several recursive arms** each build through their own routine. Their
iterations cannot land flat in one sink — two arms can capture the same number
of values of the same kinds, so which arm an iteration matched would not be
recoverable — so the step group reports one record per iteration naming the arm
it took (:class:`~lexic.parsing.pda.compiler.program.flatten.FoldArms`), and the
fold builds each through that arm.

Two shapes are refused rather than approximated, and each would be a wrong
model rather than a slow one:

* **a routine that reads an item's EXTENT or TEXT** — those come off the
  frame's per-item end positions, and an iteration inside a loop has no
  per-item ends of its own to give;
* **captures that are not the leading recursive slot followed by the rest** —
  the synthetic array is built by position, and a routine reading some other
  slot would read a value that is not there.

A β that captures nothing at all — ``A ::= A "a" | "a"``, a node per
iteration whose only field is the recursive one — leaves no value in the sink,
so its number is not recovered from values: the frame's own iteration count
(:attr:`~lexic.parsing.pda.runtime.build.Frame.count`), which a fold's last
loop keeps past its close, says how many times it went round, and the fold
folds that many times with a width of zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lexic.parsing.pda.compiler.leftrec.shape import Fold, Recursive
from lexic.parsing.pda.compiler.program.bake.lowering import (
    FoldBuild,
    FoldStep,
    no_shape_build,
    shape_build,
)
from lexic.parsing.pda.compiler.program.bake.product import build_plan
from lexic.parsing.product import CaptureMode, RuleRoutine

_ENDS_MODES = frozenset((int(CaptureMode.TEXT), int(CaptureMode.EXTENT)))
"""Capture modes that read an item's end position off the frame."""


def fold_build(
    fold: Fold, routines: Mapping[str, RuleRoutine[Any]]
) -> FoldBuild | None:
    """The per-iteration build for one folded rule, or ``None`` to refuse it.

    :param fold: The rule's decomposition.
    :param routines: The bound product's routines, by rule name.
    :returns: The fold's build state, or ``None`` when any arm fails a
        precondition — the caller then leaves the rule alone and it islands as
        before.
    """
    built = [_step_build(step, routines) for step in fold.steps]
    arms = tuple(step for step in built if step is not None)
    if len(arms) != len(built):
        return None
    if len(arms) == 1:
        one = arms[0]
        return FoldBuild(one.build, one.slots - 1, one.slots)
    return FoldBuild(no_shape_build, 0, 0, arms)


def _step_build(
    step: Recursive, routines: Mapping[str, RuleRoutine[Any]]
) -> FoldStep | None:
    """One recursive arm's iteration build, or ``None`` when it cannot fold."""
    routine = routines.get(step.rule)
    if routine is None or routine.construction is None:
        return None
    construction = routine.construction
    licence = construction.licence
    if licence is None:
        return None
    captures = routine.captures
    # `len(captures) == 1` is the recursive slot ALONE: the iteration captures
    # nothing, and its depth comes from the loop's recorded count (width 0).
    if not captures or any(one.mode in _ENDS_MODES for one in captures):
        return None
    if [one.slot for one in captures] != list(range(len(captures))):
        return None
    # The ORDINARY plan, not a second derivation of one: the fold builds
    # through the same entries the arm's own clone would have built through,
    # so the two cannot disagree about what the arm constructs.
    plan = build_plan(routine, construction, licence.order)
    return FoldStep(shape_build(licence.record, plan), len(captures))
