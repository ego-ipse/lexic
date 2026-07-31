"""``PdaFail`` — the predictive-parse failure signal, shared across the PDA.

Homed in its own leaf module so both the runtime (:mod:`.runtime`) and the
island escape (:mod:`.islands`) can raise it without an import cycle; the
runtime re-exports it, so ``from lexic.parsing.pda.runtime.runtime import PdaFail``
still resolves.
"""

from __future__ import annotations

__all__ = ["PdaFail", "ProbeFork"]


class PdaFail(Exception):
    """A predictive-parse failure — internal to :mod:`lexic.parsing`.

    Raised wherever the PDA cannot proceed deterministically (a terminal
    mismatch, no viable arm, trailing input, or a fail/unresolvable island
    reference). Carries the failing position and a short reason for debugging;
    the compile seam catches it and falls back to the full engine, so it is
    **never** user-facing.
    """


class ProbeFork(PdaFail):
    """An attempt boundary where taking and stopping are BOTH viable.

    Outside a stop-side probe it behaves as the :class:`PdaFail` it is — the
    parse bails and the gated engine owns the question. Inside a probe it is
    the one signal that must NOT read as "the stop side failed": the probe
    ran into a further undecidable boundary, so the stop side is treated as
    viable (over-approximation — every uncertain answer lands on bail, never
    on a silent commit).
    """
