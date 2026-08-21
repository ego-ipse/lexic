"""Attempt-seam leaves — the admission test, the kernel scratch, the stack copy.

Shed from :mod:`lexic.parsing.pda.runtime.kernel.kernel` for the reason every leaf in
this package is shed: these take only plain values and frame lists, never the
``PdaKernel`` cursor, so ``runtime`` imports them and not the reverse. The
attempt/probe DRIVERS stay methods — their group writes the cursor's own state
(the ``PdaKernel._island`` precedent).
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.earley.kernel.loop.kernel import Delegate
from lexic.parsing.pda.runtime.build import (
    F_ARM,
    F_CLONE,
    F_COUNT,
    F_ENDS,
    F_I,
    F_MODE,
    F_OUT,
    F_SINKS,
    F_START,
)

__all__ = [
    "PROBE_DEPTH",
    "control_signature",
    "pending_values",
    "value_shape",
    "values_agree",
    "KernelCaches",
    "admits",
    "frames_copy",
    "sole_admitted",
]

PROBE_DEPTH = 24
"""Stop-probe nesting cap. Past it a boundary reads as undecidable
(:class:`~lexic.parsing.pda.core.errors.ProbeFork` — viable, so the parse
bails to the gated engine); the cap only ever costs a fallback, never a
wrong commit."""


def admits(char: str, chars: Any, negated: Any) -> bool:
    """Whether an attempt entry's FIRST pre-filter admits the lookahead.

    ``chars is None`` is the nullable default entry — always admitted.
    """
    if chars is None:
        return True
    return (char != "" and char not in chars) if negated else char in chars


def sole_admitted(entries: tuple[Any, ...], text: str, pos: int) -> Any:
    """The single admitted entry's clone, or ``None`` when several admit.

    Admission is the first-char pre-filter AND the leading-prefix pattern
    (one C-level match per candidate) AND the arm's FIRST_k window — most
    overlapping-FIRST decisions collapse to a single survivor at their
    discriminator, and a sole survivor has no fork to audit and no rollback
    to arm: the runtime enters it as an ordinary clone (frame push) instead
    of a sub-run.
    """
    char = text[pos : pos + 1]
    sole = None
    for chars, negated, prefix, window, sub in entries:
        # `admits` read in place — this scan is the densest call site in the
        # engine (1.72 per character of vyx corpus), and the test is a set
        # membership either way.
        if chars is not None and (
            (char == "" or char in chars) if negated else (char not in chars)
        ):
            continue
        if prefix is not None and prefix.match(text, pos) is None:
            continue
        if window is not None and window.match(text, pos) is None:
            continue
        if sole is not None:
            return None
        sole = sub
    return sole


class KernelCaches(IrLeaf[IrSelf, IrSelf]):
    """One kernel run's scratch — the memos and the stop-probe depth.

    :ivar deleg: Island name → its wrapped interior delegate table.
    :ivar intern: The sub-model intern memo (repeated identical sub-models
        built once and shared within one run).
    :ivar probing: The live stop-probe nesting depth. A boundary inside a
        probe resolves by a NESTED probe — its completion is the outer
        answer, its failure lets the outer probe drive on — capped at
        :data:`PROBE_DEPTH`, past which a boundary raises
        :class:`~lexic.parsing.pda.core.errors.ProbeFork` (undecidable reads
        as viable).
    :ivar uncertain: Set when a probe's drive resolved a both-viable
        boundary GREEDILY (probes never nest — the exponential chain of a
        rules-list grammar probing every later line is cut to one linear
        drive); the probe's outcome is then a SAMPLED path, and the outer
        verdict treats it conservatively — an uncertain outcome on a
        decisive side reads as a fork, which is a fallback, never a wrong
        commit.
    """

    __slots__ = ("deleg", "intern", "probing", "uncertain")

    deleg: dict[str, dict[int, Delegate]]
    intern: dict[Any, object]
    probing: int
    uncertain: bool

    def __init__(self) -> None:
        """Seed the memos empty, the probe depth zero, certainty clean."""
        self.deleg = {}
        self.intern = {}
        self.probing = 0
        self.uncertain = False


def frames_copy(stack: list[list[Any]]) -> list[list[Any]]:
    """A structural copy of the frame stack, aliasing topology preserved.

    Frames alias each other: a frame's ``F_OUT`` IS the run holder, a parent's
    per-item sink list, or (through a transparent frame) an ancestor's — so a
    plain per-frame copy would break the funnels. Every list is duplicated
    once via an identity map and every reference re-resolved through it;
    model objects inside sinks are immutable and stay shared.
    """
    remap: dict[int, list[Any]] = {}
    copies: list[list[Any]] = []
    for frame in stack:
        new = list(frame)
        new[F_ENDS] = _dup(frame[F_ENDS], remap)
        new[F_OUT] = _dup(frame[F_OUT], remap)
        sinks = frame[F_SINKS]
        if sinks is not None:
            new[F_SINKS] = [
                slot if slot is None else _dup(slot, remap) for slot in sinks
            ]
        copies.append(new)
    return copies


def _dup(lst: list[Any], remap: dict[int, list[Any]]) -> list[Any]:
    """``lst``'s one copy — the identity map keeps aliases aliased."""
    got = remap.get(id(lst))
    if got is None:
        got = list(lst)
        remap[id(lst)] = got
    return got


def control_signature(stack: list[list[Any]], pos: int) -> tuple[Any, ...]:
    """What a probe side must SHARE with the other to have a common future.

    The stack IS the continuation, so two sides at the same position with the
    same control state consume the same remaining text and build the same
    additional values — which is what lets a boundary be settled without
    running either side to end-of-input.

    Deliberately excludes every value container (``F_OUT`` / ``F_SINKS``): the
    two sides differing THERE is the fact being measured, and folding it into
    the signature would mean the sides never converge. Arm and clone enter by
    identity — the flat program is immutable and shared across every parse, so
    ``id`` is a stable key here rather than an accident of allocation.

    The iteration count is normalised by :func:`_count_key`, and that is what
    makes convergence possible at all: the take side has taken one iteration
    the stop side has not, so their raw counts differ FOREVER and no two states
    would ever match.
    """
    return (
        pos,
        len(stack),
        tuple(
            (
                id(frame[F_ARM]),
                frame[F_I],
                _count_key(frame),
                frame[F_MODE],
                id(frame[F_CLONE]),
                frame[F_START],
            )
            for frame in stack
        ),
    )


_COUNT_FREE = -1
"""The count key of a loop whose exact iteration count can no longer constrain
anything — past its mandatory floor with no ceiling to hit."""


def _count_key(frame: list[Any]) -> int:
    """A frame's iteration count, or :data:`_COUNT_FREE` when it cannot matter.

    A count constrains the future only while it can still decide something: it
    is below the item's mandatory ``lo``, or the item has a ``hi`` to run into.
    Past ``lo`` on an unbounded item every further iteration is permitted, so
    the exact number is not part of the state — and collapsing it is what lets
    a side that took one more iteration converge with one that did not.
    """
    arm = frame[F_ARM]
    i = frame[F_I]
    if i >= arm.n:
        return _COUNT_FREE
    count = frame[F_COUNT]
    if arm.his[i] >= 0 or count < arm.los[i]:
        return count
    return _COUNT_FREE


def value_shape(stack: list[list[Any]]) -> tuple[Any, ...]:
    """Every value container's length — the watermark taken AT the boundary.

    Both sides of a boundary are copies of one live stack, so everything
    already in a container when the fork was taken is identical between them
    by construction. Only what is appended AFTER can differ, and this is what
    lets :func:`pending_values` compare the delta instead of the whole
    accumulated state — the difference between O(built-since) and O(built), and
    the difference between a linear parse and a quadratic one.
    """
    return tuple(
        (
            len(frame[F_OUT]),
            ()
            if frame[F_SINKS] is None
            else tuple(0 if slot is None else len(slot) for slot in frame[F_SINKS]),
        )
        for frame in stack
    )


def pending_values(
    stack: list[list[Any]], shape: tuple[Any, ...] = ()
) -> tuple[Any, ...]:
    """Every value a probe side has built SINCE ``shape`` was taken.

    Containers grow by append, so the watermark's prefix is common to both
    sides and re-comparing it is pure waste — measured as 92% of the parse and
    the whole of its residual superlinearity. A container that came back
    SHORTER than its watermark was not appended to but replaced, and there the
    watermark means nothing: it is compared whole, which is the conservative
    reading.

    Frames deeper than ``shape`` did not exist at the boundary and are compared
    in full.

    Aliased containers (a frame's ``F_OUT`` IS a parent's sink slot) are read
    twice; harmless for an equality test, and cheaper than resolving identity.
    """
    out: list[Any] = []
    for depth, frame in enumerate(stack):
        was_out, was_sinks = shape[depth] if depth < len(shape) else (0, ())
        out.append(_since(frame[F_OUT], was_out))
        sinks = frame[F_SINKS]
        if sinks is None:
            out.append(())
            continue
        out.append(
            tuple(
                ()
                if slot is None
                else _since(slot, was_sinks[k] if k < len(was_sinks) else 0)
                for k, slot in enumerate(sinks)
            )
        )
    return tuple(out)


def _since(container: list[Any], mark: int) -> tuple[Any, ...]:
    """``container``'s tail past ``mark`` — or all of it if it shrank."""
    return tuple(container) if len(container) < mark else tuple(container[mark:])


def values_agree(left: Any, right: Any) -> bool:
    """Whether two :func:`pending_values` snapshots mean the same thing.

    Structural to the leaves, then :func:`~lexic.parsing.earley.kernel.forest
    .ambiguity.same_value` — the SAME question the end-of-input comparison
    asks, asked earlier. A shape mismatch is a disagreement, never an error:
    the caller's next move on "these differ" is always the conservative one.
    """
    if isinstance(left, tuple) or isinstance(right, tuple):
        if not (isinstance(left, tuple) and isinstance(right, tuple)):
            return False
        if len(left) != len(right):
            return False
        return all(values_agree(a, b) for a, b in zip(left, right))
    return bool(same_value(left, right))
