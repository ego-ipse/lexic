"""Tests for lexic.parsing.pda.compiler.program.frameless — frame-less entry.

What qualifies to be entered without a frame, and the licences that read it.
The WIDE half is what these pin: a clone selecting by window or post-noise
peek has its own refusals, keeps its targets in its selection rather than in
`selectors`, and is the case a licence reading `selectors` alone gets wrong.
"""

from __future__ import annotations

from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    KWindowSelect,
    clone_arms,
)
from lexic.parsing.pda.compiler.program.opcodes import BUILD_ALT, BUILD_DISPATCH
from lexic.parsing.pda.compiler.program.specialize.frameless import (
    convert_dispatch,
    vdisp_landing,
    vdisp_target,
)
from tests.clone_walk import walk_program_clones
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_from_text

_WIDE = 'root ::= alt\nalt ::= a | b\na ::= "ab" x\nb ::= "ac" x\nx ::= "z"\n'
"""An alternation one lookahead character cannot decide.

Both arms open on ``a``, so the analysis gives the clone a `KWindowSelect`
rather than lead-char selectors — the shape this section is about.
"""


def wide_clone(pda):
    """The one clone carrying a wide selection."""
    found = [
        one
        for one in walk_program_clones(pda.program.start).values()
        if one.wide_selectors is not None
    ]
    assert len(found) == 1, f"expected one wide clone, found {len(found)}"
    return found[0]


def wide_of(clone: FlatClone):
    """The clone's selection, narrowed — every caller here has asserted one."""
    wide = clone.wide_selectors
    assert wide is not None, "this clone carries no wide selection"
    return wide


def test_a_window_selected_alternation_converts_and_keeps_its_selection():
    """The targets live in the SELECTION, and `selectors` stays empty.

    A wide clone's arms were never in `selectors`; putting its targets there
    would make the chase ask the wrong place, and leaving them as arms would
    make it push the frame the rewrite exists to elide.
    """
    clone = wide_clone(pda_from_text(_WIDE))

    assert clone.mode == BUILD_DISPATCH
    assert isinstance(clone.wide_selectors, KWindowSelect)
    assert clone.selectors == ()
    assert all(isinstance(one, FlatClone) for one in wide_of(clone).arms)


def test_an_arm_that_builds_refuses_the_wide_rewrite():
    """One arm carrying anything but a unit reference keeps the whole frame.

    The rewrite's soundness is that the alternation builds NOTHING; an arm
    with its own items is not a pass-through, so the clone keeps its frame
    even though every other arm would have qualified.

    Constructed rather than written as a grammar: `hoist_arms` guarantees
    every rule-alternation arm IS a single unit reference, so no grammar can
    express this shape — and a test that could not build it would be asserting
    a guard no input reaches.
    """
    clone = wide_clone(pda_from_text(_WIDE))
    multi = next(
        arm for target in wide_of(clone).arms for arm in clone_arms(target) if arm.n > 1
    )

    clone.mode = BUILD_ALT
    clone.wide_selectors = wide_of(clone).with_payloads(
        tuple(multi for _ in wide_of(clone).arms)
    )
    convert_dispatch(clone)

    assert clone.mode == BUILD_ALT, "an arm with items is not a pass-through"


def test_the_wide_rewrite_is_refused_where_the_lead_char_one_is():
    """`attempt` and `struct_arm` refuse a wide clone for their own reasons.

    Neither guard was relaxed: an attempt clone tries arms in order and never
    dispatches one, and an empty-arm gate must run before any dispatch. Both
    are asserted by construction rather than by finding a grammar, because a
    grammar that happens not to produce one proves nothing.
    """
    clone = wide_clone(pda_from_text(_WIDE))
    assert clone.mode == BUILD_DISPATCH  # the control: this one DOES convert

    for blocker in ("attempt", "struct_arm"):
        fresh = wide_clone(pda_from_text(_WIDE))
        fresh.mode = BUILD_ALT
        setattr(fresh, blocker, object())
        convert_dispatch(fresh)

        assert fresh.mode == BUILD_ALT, f"{blocker} did not refuse the rewrite"


def test_a_wide_dispatch_earns_no_inline_licence_from_its_default_alone():
    """The consumer audit, as a test: empty `selectors` must not read as no edges.

    `vdisp_landing` enumerated `selectors` and appended the default. For a
    wide clone `selectors` is EMPTY, so that enumeration saw the default only
    — and a licence granted on it would cover every target it never examined.
    """
    clone = wide_clone(pda_from_text(_WIDE))
    targets = wide_of(clone).arms
    assert targets, "the premise: this clone HAS targets outside `selectors`"

    licensed = vdisp_target(clone)
    every_target_lands = all(vdisp_landing(one) for one in targets)

    assert licensed == (clone.chartable is None and every_target_lands), (
        "the licence must answer for the targets in the selection, not for "
        "the default it would see by reading `selectors`"
    )
