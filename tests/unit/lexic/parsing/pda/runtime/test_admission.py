"""Tests for lexic.parsing.pda.runtime.admission — the attempt-seam leaves."""

from __future__ import annotations

from lexic.ir import IrSelf, IrStr
from lexic.parsing.pda.runtime.admission import KernelCaches, admits, frames_copy
from lexic.parsing.pda.runtime.build import Frame
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone

# ── admits — the FIRST pre-filter ─────────────────────────────────────


def test_admits_none_charset_is_the_always_admitted_default():
    """A ``None`` charset is the nullable default entry — always admitted."""
    assert admits("x", None, None)
    assert admits("", None, None)


def test_admits_positive_and_negated_membership():
    """Positive sets admit members; negated sets admit non-members."""
    assert admits("a", frozenset("ab"), False)
    assert not admits("z", frozenset("ab"), False)
    assert admits("z", frozenset("ab"), True)
    assert not admits("a", frozenset("ab"), True)


def test_admits_eof_never_passes_a_negated_set():
    """The EOF sentinel is never a member of a negated set."""
    assert not admits("", frozenset("ab"), True)


# ── KernelCaches ──────────────────────────────────────────────────────


def test_kernel_caches_seed_empty_with_probe_depth_zero():
    """A fresh scratch: empty memos, probe depth zero, certainty clean."""
    caches = KernelCaches()
    assert not caches.deleg
    assert not caches.intern
    assert caches.probing == 0
    assert caches.uncertain is False


# ── frames_copy — the aliasing-true structural copy ───────────────────


def _frame(
    out: list[IrSelf],
    ends: list[int],
    sinks: list[list[IrSelf] | None] | None,
) -> Frame[IrSelf]:
    """A frame with only the lanes :func:`frames_copy` reads filled."""
    frame: Frame[IrSelf] = Frame(flat_arm(len(ends)), out, flat_clone(), 0)
    frame.ends = ends
    frame.sinks = sinks
    return frame


def test_frames_copy_preserves_the_out_to_parent_sink_aliasing():
    """A child's ``out`` IS a parent sink list; the copies must alias too.

    The aliasing is what the identity map exists for, and it survives the
    containers forking EMPTY: one original container still maps to exactly one
    container on the far side, so a value the child funnels out is the value
    the parent's slot receives.
    """
    holder: list[IrSelf] = []
    parent_sink: list[IrSelf] = [IrStr("m")]
    parent = _frame(holder, [0], [parent_sink, None])
    child = _frame(parent_sink, [0, 0], None)
    copies = frames_copy([parent, child])
    copied_sinks = copies[0].sinks
    assert copied_sinks is not None
    assert copies[1].out is copied_sinks[0]
    assert copies[1].out is not parent_sink
    assert copies[1].out == []  # forked empty; the prefix comes back at build
    copies[1].out.append(IrStr("built"))
    assert copied_sinks[0] == [IrStr("built")], "the alias must carry the value"
    assert parent_sink == [IrStr("m")], "and never reach the original"


def test_frames_copy_mutations_never_reach_the_originals():
    """Probe writes land on the copy — the live stack is untouched."""
    holder: list[IrSelf] = []
    frame = _frame(holder, [3, 7], None)
    copies = frames_copy([frame])
    copied_ends = copies[0].ends
    assert copied_ends is not None
    copied_ends[0] = 99
    copies[0].out.append(IrStr("probe"))
    assert frame.ends == [3, 7]
    assert not holder


def test_frames_copy_forks_the_containers_empty():
    """A fork starts with its own values only — the prefix is not copied.

    Copying it moved the whole accumulated parse into every fork, which on a
    grammar-sized document was 830 million list elements moved so that 14,632
    could be read. The values are still THERE — see
    :func:`test_a_forked_frame_takes_its_inherited_values_back` — they are
    just taken at the one moment a build reads them.
    """
    model = IrStr("model")
    sink: list[IrSelf] = [model]
    frame = _frame([], [0], [sink])
    copies = frames_copy([frame])
    copied_sinks = copies[0].sinks

    assert copied_sinks is not None
    assert copied_sinks[0] is not sink
    assert copied_sinks[0] == []
    assert sink == [model], "the original is untouched"


def test_a_forked_frame_takes_its_inherited_values_back():
    """The prefix returns at build — in front of what the fork itself built.

    Order matters and is the whole point: a model the fork appended belongs
    AFTER the ones that were already there, or the rebuilt sequence is the
    right values in the wrong places.
    """
    first, second = IrStr("first"), IrStr("second")
    sink: list[IrSelf] = [first]
    frame = _frame([], [0], [sink])
    forked = frames_copy([frame])[0]
    assert forked.sinks is not None
    mine = forked.sinks[0]
    assert mine is not None
    mine.append(second)

    forked.adopt_inherited()

    assert forked.sinks[0] == [first, second]
    assert sink == [first], "taking the prefix must not write the original"
    assert forked.inherited is None, "taken once, not on every build"


def test_taking_the_inherited_values_twice_does_not_double_them():
    """The second call is a no-op — a frame is built once, but say so anyway."""
    sink: list[IrSelf] = [IrStr("first")]
    forked = frames_copy([_frame([], [0], [sink])])[0]

    forked.adopt_inherited()
    forked.adopt_inherited()

    assert forked.sinks is not None
    assert forked.sinks[0] == [IrStr("first")]


def test_two_forks_of_one_stack_cannot_see_each_other():
    """Both sides of a boundary build into their own containers.

    `_side` advances two universes in step, so a value one builds must be
    invisible to the other AND to the original — this is the isolation the
    copy is responsible for, stated for the two-sided case rather than only
    the one-sided one.
    """
    sink: list[IrSelf] = [IrStr("committed")]
    frame = _frame([], [0], [sink])

    left = frames_copy([frame])[0]
    right = frames_copy([frame])[0]
    assert left.sinks is not None and right.sinks is not None
    ours, theirs = left.sinks[0], right.sinks[0]
    assert ours is not None and theirs is not None
    ours.append(IrStr("left"))
    theirs.append(IrStr("right"))

    assert left.sinks[0] == [IrStr("left")]
    assert right.sinks[0] == [IrStr("right")]
    assert sink == [IrStr("committed")]


def test_frames_copy_isolates_a_slot_assignment():
    """A probe that OVERWRITES a sink slot must not reach the live stack.

    The frame protocol delivers a completed model into its parent's slot, so a
    probe side's write is an assignment and not an append. That failure mode is
    silent where an append's is loud — a stray assignment replaces a committed
    sibling value rather than adding a visible duplicate, and the parse still
    round-trips. This pins the isolation the copy is responsible for.
    """
    committed: list[IrSelf] = [IrStr("committed")]
    sinks: list[list[IrSelf] | None] = [committed, None]
    frame = _frame([], [0, 0], sinks)
    copies = frames_copy([frame])
    copied_sinks = copies[0].sinks
    assert copied_sinks is not None
    copied_sinks[0] = [IrStr("probe")]
    copied_sinks[1] = [IrStr("probe")]
    assert sinks[0] is committed
    assert sinks[1] is None
