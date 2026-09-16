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

Three shapes are refused rather than approximated, and each would be a wrong
model rather than a slow one:

* **more than one recursive arm** — the iterations land flat in one sink, so
  which arm an iteration matched is not recoverable and the wrong routine
  would build it;
* **a routine that reads an item's EXTENT or TEXT** — those come off the
  frame's per-item end positions, and an iteration inside a loop has no
  per-item ends of its own to give;
* **captures that are not the leading recursive slot followed by the rest** —
  the synthetic array is built by position, and a routine reading some other
  slot would read a value that is not there;
* **a β that captures nothing at all** — ``A ::= A "a" | "a"`` builds a node
  per iteration whose only field is the recursive one, so the iterations leave
  NO values in the sink and their number cannot be recovered from it. The
  nesting depth is the whole information and the sink carries none of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from lexic.parsing.pda.compiler.leftrec.shape import Fold
from lexic.parsing.pda.compiler.program.lowering import shape_build
from lexic.parsing.pda.compiler.program.product import build_plan
from lexic.parsing.product import CaptureMode, RuleRoutine

_ENDS_MODES = frozenset((int(CaptureMode.TEXT), int(CaptureMode.EXTENT)))
"""Capture modes that read an item's end position off the frame."""


class FoldBuild(NamedTuple):
    """What a folding clone's completion needs.

    :ivar step: The per-iteration build — the step arm's own composed build,
        called with a synthetic sinks array.
    :ivar width: How many captured values one iteration contributes, which is
        how the flat sink is cut back into iterations.
    :ivar slots: How wide the synthetic array must be.
    """

    step: Any
    width: int
    slots: int


def fold_build(
    fold: Fold, routines: Mapping[str, RuleRoutine[Any]]
) -> FoldBuild | None:
    """The per-iteration build for one folded rule, or ``None`` to refuse it.

    :param fold: The rule's decomposition.
    :param routines: The bound product's routines, by rule name.
    :returns: The fold's build state, or ``None`` when any precondition fails
        — the caller then leaves the rule alone and it islands as before.
    """
    if len(fold.steps) != 1:
        return None
    routine = routines.get(fold.steps[0].rule)
    if routine is None or routine.construction is None:
        return None
    construction = routine.construction
    licence = construction.licence
    if licence is None:
        return None
    captures = routine.captures
    # `len(captures) == 1` is the recursive slot ALONE: the iteration captures
    # nothing, so a flat sink holds nothing to count iterations by and one
    # iteration is indistinguishable from ten.
    if len(captures) < 2 or any(one.mode in _ENDS_MODES for one in captures):
        return None
    if [one.slot for one in captures] != list(range(len(captures))):
        return None
    # The ORDINARY plan, not a second derivation of one: the fold builds
    # through the same entries the arm's own clone would have built through,
    # so the two cannot disagree about what the arm constructs.
    plan = build_plan(routine, construction, licence.order)
    return FoldBuild(
        shape_build(licence.record, plan), len(captures) - 1, len(captures)
    )
