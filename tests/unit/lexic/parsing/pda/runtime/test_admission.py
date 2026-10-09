"""Tests for lexic.parsing.pda.runtime.admission — the attempt-seam leaves."""

from __future__ import annotations

import pytest

from lexic.exceptions import EngineInvariantError
from lexic.ir import IrSelf, IrStr
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.runtime.admission import (
    NESTING_DEPTH,
    PARSE_NESTING,
    KernelCaches,
    RunScope,
    admits,
    composes,
    frames_copy,
)
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


def test_a_fork_nested_past_the_depth_is_refused() -> None:
    """Forks nest :data:`NESTING_DEPTH` levels inside the first, and the copy
    CHECKS that rather than assuming it.

    `adopt_inherited` walks the fork chain, and a side forks again only while
    a forked verdict is asked again, at most that many sides deep. A copy one
    deeper is therefore never asked for, and if it ever were, the guard says
    so loudly rather than leaving a short model.

    A raise rather than an assert, because `-O` strips asserts and a short
    model is exactly what must not pass quietly. `RuntimeError` rather than
    `PdaFail`, because the engine seam CATCHES `PdaFail` and falls back to
    Earley — the breach would then hide behind a correct parse.
    """
    chain = [_frame([], [0], [[IrStr("a")]])]
    for _depth in range(NESTING_DEPTH + 1):
        chain.append(frames_copy([chain[-1]])[0])
        assert chain[-1].inherited is chain[-2], "the copy records its origin"
    with pytest.raises(EngineInvariantError, match=f"nest {NESTING_DEPTH} levels"):
        frames_copy([chain[-1]])


def test_a_fork_one_deep_takes_back_the_whole_chain() -> None:
    """A fork of a fork builds with its origin's values and its origin's
    origin's, oldest first, and neither origin is written to."""
    live = _frame([], [0], [[IrStr("a")]])
    forked = frames_copy([live])[0]
    _slot(forked).append(IrStr("b"))
    nested = frames_copy([forked])[0]
    _slot(nested).append(IrStr("c"))

    nested.adopt_inherited()

    assert _slot(nested) == [IrStr("a"), IrStr("b"), IrStr("c")]
    assert _slot(forked) == [IrStr("b")] and _slot(live) == [IrStr("a")]


def _slot(frame: Frame[IrSelf]) -> list[IrSelf]:
    """A one-item frame's sink."""
    sinks = frame.sinks
    assert sinks is not None and sinks[0] is not None
    return sinks[0]


def test_the_prefix_is_whole_because_one_origin_holds_it_all() -> None:
    """One adopt recovers everything, since each level owns only its own.

    The counterpart to the refusal above: given that forks do not nest, a
    single prepend IS the complete prefix. Adoption happens at the pop, so a
    frame that is still on the stack has never adopted and its sinks hold
    exactly what it appended itself.
    """
    original: list[IrSelf] = [IrStr("was-there")]
    frame = _frame([], [0], [original])
    forked = frames_copy([frame])[0]
    assert forked.sinks is not None
    mine = forked.sinks[0]
    assert mine is not None
    mine.append(IrStr("added-by-the-fork"))

    forked.adopt_inherited()

    assert forked.sinks[0] == [IrStr("was-there"), IrStr("added-by-the-fork")]
    assert original == [IrStr("was-there")], "and the original is untouched"


# ── FOLLOW composability ──────────────────────────────────────────────


def test_composes_is_true_at_end_of_input():
    """End of input always composes — nothing follows to contradict it."""
    follow = CharSet.from_chars("x")
    assert composes(follow, "abc", 3) is True


def test_composes_checks_the_next_character_against_follow():
    """A next character inside FOLLOW composes; one outside it does not."""
    follow = CharSet.from_chars("x")
    assert composes(follow, "axb", 1) is True
    assert composes(follow, "ayb", 1) is False


# ── RunScope — a retry's nested verdicts, the parse's allowance, wholeness ──


def test_a_retry_draws_from_the_parse_and_gives_back_what_it_did_not_ask():
    """Two of a retry's sixty-four are asked; the other sixty-two go back."""
    nesting = RunScope()
    assert nesting.open(64) and nesting.retry == 64
    assert nesting.take() and nesting.take()
    nesting.close()
    assert (nesting.retry, nesting.left) == (0, PARSE_NESTING - 2)


def test_a_spent_allowance_opens_no_retry_and_outside_one_nothing_is_taken():
    """Past the parse's allowance a retry is not opened at all; outside a
    retry no nested verdict is ever granted."""
    nesting = RunScope()
    assert not nesting.take()
    nesting.left = 1
    assert nesting.open(64) and nesting.retry == 1
    assert nesting.take() and not nesting.take()
    nesting.close()
    assert not nesting.open(64)


def test_a_delegate_kernel_draws_on_the_parse_s_own_allowance():
    """A kernel run inside a parse keeps a retry of its own but spends the
    same allowance, so delegate sub-runs cannot multiply the parse's bound."""
    parse = KernelCaches()
    delegate = KernelCaches(parse.scope)
    assert delegate.scope is not parse.scope
    assert delegate.scope.root is parse.scope.root
    delegate.scope.open(64)
    assert parse.scope.left == PARSE_NESTING - 64


def test_only_the_parse_s_own_run_over_its_whole_text_is_whole():
    """A delegate's root may end anywhere in its window, and a truncated
    text's end is not the document's: neither may refute a stop side against
    the text."""
    parse = KernelCaches()
    assert parse.scope.whole()
    assert not KernelCaches(parse.scope).scope.whole()
    parse.scope.cut = True
    assert not parse.scope.whole()
