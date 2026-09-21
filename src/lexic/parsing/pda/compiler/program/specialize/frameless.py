"""FRAME-LESS ENTRY — what qualifies, and the licences that read it.

One subject, and the entanglement is the subject: `vstr_inlinable` and
`vdisp_landing` both answer *can this clone be entered without a frame*, and
`convert_dispatch` is what makes a clone answer yes. Splitting them by caller
rather than by question put a cycle between the halves and left the licences
in one module and the rewrite that creates their subject in another.

**Where a dispatch clone keeps its targets follows how it selects.** A
lead-char clone carries them in ``selectors``; one selecting by window or
post-noise peek carries them in its own selection and leaves ``selectors``
empty. Every licence here reads whichever holds them — one reading
``selectors`` alone sees a wide clone's default and would grant a licence over
targets it never examined.

A leaf: it imports the flat records and the op-codes, and nothing else in the
package imports it back.
"""

from __future__ import annotations

from typing import Any

from lexic.parsing.pda.compiler.program.flatten import (
    CHARTABLE_CAP,
    FlatArm,
    FlatClone,
    clone_arms,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    OP_LEAF1,
    OP_REF,
    OP_REF1,
    TERMINAL_OPS,
)


def vstr_inlinable(clone: Any) -> bool:
    """The ``OP_VSTR`` licence: a terminal-only ``value_str`` clone.

    Never an attempt clone — the inline matcher selects one arm by FIRST,
    which is exactly the decision an attempt clone exists to NOT make that
    way — and never a windowed / peeked / struct-gated clone: the inline
    matcher's ``select_arm`` reads ``selectors`` only, and a gated clone's
    live arms hang off its gate structures (a k-window ``value_str`` inlined
    here selected from an EMPTY list and failed every mandatory iteration —
    latent while such rules islanded, exposed when they began to run).
    """
    return (
        clone.mode == BUILD_VALUE_STR
        and clone.attempt is None
        and clone.wide_selectors is None
        and clone.struct_arm is None
        and all(
            all(kind in TERMINAL_OPS for kind in arm.kinds) for arm in clone_arms(clone)
        )
    )


def vdisp_landing(target: Any) -> bool:
    """Whether one chase step ends somewhere the inline matcher can run.

    Recursion terminates because a cycle of dispatch selectors is left
    recursion, which the analysis refuses before any clone exists — the same
    argument :func:`bake_chartables`' fixpoint rests on.
    """
    if not isinstance(target, FlatClone):
        return False  # DISPATCH_EMPTY: an empty arm is not a value_str match
    if target.mode != BUILD_DISPATCH:
        return vstr_inlinable(target)
    if target.wide_selectors is not None:
        # A wide dispatch keeps its targets in the SELECTION; `selectors` is
        # empty for it, so enumerating that alone would see the default and
        # grant this licence over every target it never examined. Enumerated
        # here rather than refused: the licence is about where the chase can
        # LAND, and a wide hop lands in the same places a lead-char hop does.
        steps = list(target.wide_selectors.arms)
    else:
        steps = [step for _chars, _negated, step in target.selectors]
    if target.default is not None:
        steps.append(target.default)
    return bool(steps) and all(vdisp_landing(step) for step in steps)


def vdisp_target(clone: Any) -> bool:
    """The :data:`OP_VDISP` licence: a chase that always lands frame-lessly.

    The chase is a lead-char walk and the match is then the landed clone's
    ordinary ``vstr_once`` — so the pair inlines whenever every clone the chase
    can reach is :func:`vstr_inlinable`. Product-neutral by construction: the
    same ``vstr_once``, on the same clone, at the same position, same sink.

    A TABLED clone is refused because :data:`OP_VSTR` already answers it by
    lookup; a missing default is not refused, since the chase then raises on a
    miss exactly as the entry path does.
    """
    if not isinstance(clone, FlatClone) or clone.mode != BUILD_DISPATCH:
        return False
    return clone.chartable is None and vdisp_landing(clone)


def dispatch_chartable(clone: FlatClone) -> "dict[str, object] | None":
    """The table of a dispatch clone whose every target is itself tabled.

    A dispatch alternation is a pass-through: the target's model IS the model the
    entry reports. So when every selector's target can answer one character from
    its own table, the whole chase collapses into one composed lookup — the
    character-wide models of a lexical alternation, without the chase.
    """
    if clone.wide_selectors is not None:
        # REFUSED, not enumerated. This table answers ONE character by
        # lookup, and a wide selection is by definition one that a single
        # character cannot make — a window match or a post-noise peek. There
        # is no per-character answer to compose, and `selectors` being empty
        # for such a clone would otherwise compose an EMPTY table that admits
        # nothing while reading as a complete one.
        return None
    table: dict[str, object] = {}
    for chars, negated, target in clone.selectors:
        if negated or "" in chars or len(chars) > CHARTABLE_CAP:
            return None
        sub = target.chartable
        if sub is None:
            return None
        for char in chars:
            model = sub.get(char)
            if model is None:
                return None  # the selector admits what the target refuses
            table.setdefault(char, model)
        if len(table) > CHARTABLE_CAP:
            return None
    return table or None


def unit_ref_target(arm: FlatArm) -> "FlatClone | None":
    """The arm's sole exactly-once clone reference, or ``None``.

    ``OP_REF1`` and ``OP_LEAF1`` count as well as ``OP_REF``: all three are the
    same fact — an exactly-once reference whose payload is the target clone —
    and only how the driver reaches it differs. Omitting one costs the
    alternation its frame-less dispatch, which is a frame and a model per
    occurrence, not a missed micro-optimisation. The main pass never sees one (calls
    specialise after this runs); :func:`~lexic.parsing.pda.compiler.program.lower
    .flatten_clones` does, when it optimises the attempt sub-clones, which
    share their parent's already-specialised arm.
    """
    if arm.n != 1 or arm.los[0] != 1 or arm.his[0] != 1:
        return None
    if arm.kinds[0] not in (OP_REF, OP_REF1, OP_LEAF1):
        return None
    return arm.payloads[0]


def convert_dispatch(clone: FlatClone) -> None:
    """Rewrite a qualifying ``alternation`` clone into a dispatch table.

    Qualifies when every arm is a single unit clone reference and the default
    (if any) is empty or itself a unit clone reference — the exact shape
    hoist_arms guarantees for rule alternations. The alternation is a
    pass-through, so entering the selected target with the parent's sink is
    observationally identical to the frame it replaces.

    HOW the arm is chosen does not bear on that: a clone selecting by window
    or post-noise peek qualifies on the same terms as one selecting by lead
    char, and keeps its selection. Its targets are rebuilt INTO that selection
    rather than into ``selectors``, which stays empty for a wide clone, so the
    chase asks the selection and there is no second place to look.

    Sound because the choice is made before the target's own attempt or struct
    decision at the same cursor, and the cursor does not move across the
    chase — so the target faces exactly the position the frame would have
    handed it.
    """
    if clone.mode != BUILD_ALT:
        return
    if clone.struct_arm is not None:
        return  # an empty-arm gate must run before any dispatch
    if clone.attempt is not None:
        return  # an attempt clone tries arms in order, never dispatches one
    wide = clone.wide_selectors
    arms = (
        wide.arms
        if wide is not None
        else tuple(arm for _chars, _negated, arm in clone.selectors)
    )
    targets = [unit_ref_target(arm) for arm in arms]
    if not targets or any(target is None for target in targets):
        return
    default: Any = None
    if clone.default is not None:
        if clone.default.n == 0:
            default = DISPATCH_EMPTY
        else:
            default = unit_ref_target(clone.default)
            if default is None:
                return
    if wide is not None:
        clone.wide_selectors = wide.with_payloads(tuple(targets))
    else:
        clone.selectors = tuple(
            (chars, negated, target)
            for (chars, negated, _arm), target in zip(clone.selectors, targets)
        )
    clone.default = default
    clone.mode = BUILD_DISPATCH
