"""Tests for lexic.parsing.pda.runtime.attempt — the attempt-seam leaves."""

from __future__ import annotations

from typing import Any

from lexic.ir import IrSelf, IrStr
from lexic.parsing.pda.runtime.attempt import KernelCaches, admits, frames_copy
from lexic.parsing.pda.runtime.build import F_ENDS, F_OUT, F_SINKS

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
    """A fresh scratch: empty memos, probe depth zero."""
    caches = KernelCaches()
    assert caches.deleg == {}
    assert caches.intern == {}
    assert caches.probing == 0


# ── frames_copy — the aliasing-true structural copy ───────────────────


def _frame(
    out: list[IrSelf],
    ends: list[int],
    sinks: list[list[IrSelf] | None] | None,
) -> list[Any]:
    """A frame — the engine's own flat ``list[Any]`` record; only the slots
    :func:`frames_copy` reads are filled."""
    frame: list[Any] = [None] * 9
    frame[F_OUT] = out
    frame[F_ENDS] = ends
    frame[F_SINKS] = sinks
    return frame


def test_frames_copy_preserves_the_out_to_parent_sink_aliasing():
    """A child's F_OUT IS a parent sink list; the copies must alias too."""
    holder: list[IrSelf] = []
    parent_sink: list[IrSelf] = [IrStr("m")]
    parent = _frame(holder, [0], [parent_sink, None])
    child = _frame(parent_sink, [0, 0], None)
    copies = frames_copy([parent, child])
    assert copies[1][F_OUT] is copies[0][F_SINKS][0]
    assert copies[1][F_OUT] is not parent_sink
    assert copies[1][F_OUT] == [IrStr("m")]


def test_frames_copy_mutations_never_reach_the_originals():
    """Probe writes land on the copy — the live stack is untouched."""
    holder: list[IrSelf] = []
    frame = _frame(holder, [3, 7], None)
    copies = frames_copy([frame])
    copies[0][F_ENDS][0] = 99
    copies[0][F_OUT].append(IrStr("probe"))
    assert frame[F_ENDS] == [3, 7]
    assert holder == []


def test_frames_copy_shares_sink_contents_but_not_the_lists():
    """Models inside sinks are immutable — shared; the lists are not."""
    model = IrStr("model")
    sink: list[IrSelf] = [model]
    frame = _frame([], [0], [sink])
    copies = frames_copy([frame])
    assert copies[0][F_SINKS][0] is not sink
    assert copies[0][F_SINKS][0][0] is model
