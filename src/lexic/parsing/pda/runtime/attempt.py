"""Attempt-seam leaves — the admission test, the kernel scratch, the stack copy.

Shed from :mod:`lexic.parsing.pda.runtime.runtime` for the reason every leaf in
this package is shed: these take only plain values and frame lists, never the
``PdaKernel`` cursor, so ``runtime`` imports them and not the reverse. The
attempt/probe DRIVERS stay methods — their group writes the cursor's own state
(the ``PdaKernel._island`` precedent).
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.loop.kernel import Delegate
from lexic.parsing.pda.runtime.build import F_ENDS, F_OUT, F_SINKS

__all__ = ["PROBE_DEPTH", "KernelCaches", "admits", "frames_copy", "sole_admitted"]

PROBE_DEPTH = 8
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


def sole_admitted(entries: tuple[Any, ...], char: str) -> Any:
    """The single admitted entry's clone, or ``None`` when several admit.

    An attempt decision with exactly one admitted entry has no fork to audit
    and no rollback to arm — the runtime enters it as an ordinary clone
    (frame push) instead of a self-contained sub-run.
    """
    sole = None
    for chars, negated, sub in entries:
        if admits(char, chars, negated):
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
    :ivar runs: The packrat memo — ``(id(clone), pos, at_cap)`` → a finished
        attempt sub-run's ``(end, values)``, or ``None`` for one that FAILED.
        Sound because a sub-run is a pure function of the clone and position
        over one kernel's fixed text and tables — except at the probe-depth
        cap, where a boundary forks instead of resolving, hence the third key
        part. The values are immutable models, only ever ``extend``-read, so
        a hit splices the same objects the miss built (the intern memo's own
        sharing rule).
    """

    __slots__ = ("deleg", "intern", "probing", "runs")

    deleg: dict[str, dict[int, Delegate]]
    intern: dict[Any, object]
    probing: int
    runs: dict[tuple[int, int, bool], tuple[int, list[object]] | None]

    def __init__(self) -> None:
        """Seed the memos empty, the probe depth zero."""
        self.deleg = {}
        self.intern = {}
        self.probing = 0
        self.runs = {}


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
