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
    """A child's ``out`` IS a parent sink list; the copies must alias too."""
    holder: list[IrSelf] = []
    parent_sink: list[IrSelf] = [IrStr("m")]
    parent = _frame(holder, [0], [parent_sink, None])
    child = _frame(parent_sink, [0, 0], None)
    copies = frames_copy([parent, child])
    copied_sinks = copies[0].sinks
    assert copied_sinks is not None
    assert copies[1].out is copied_sinks[0]
    assert copies[1].out is not parent_sink
    assert copies[1].out == [IrStr("m")]


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


def test_frames_copy_shares_sink_contents_but_not_the_lists():
    """Models inside sinks are immutable — shared; the lists are not."""
    model = IrStr("model")
    sink: list[IrSelf] = [model]
    frame = _frame([], [0], [sink])
    copies = frames_copy([frame])
    copied_sinks = copies[0].sinks
    assert copied_sinks is not None
    copied = copied_sinks[0]
    assert copied is not sink
    assert copied is not None and copied[0] is model


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
