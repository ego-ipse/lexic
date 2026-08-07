"""``PdaFail`` — the predictive-parse failure signal, shared across the PDA.

Homed in its own leaf module so both the runtime (:mod:`.runtime`) and the
island escape (:mod:`.islands`) can raise it without an import cycle; the
runtime re-exports it, so ``from lexic.parsing.pda.runtime.kernel.kernel import PdaFail``
still resolves.
"""

from __future__ import annotations

__all__ = ["PdaFail", "ProbeFork"]


class PdaFail(Exception):
    """A predictive-parse failure — internal to :mod:`lexic.parsing`.

    Raised wherever the PDA cannot proceed deterministically (a terminal
    mismatch, no viable arm, trailing input, or a fail/unresolvable island
    reference). The compile seam catches it and falls back to the full engine,
    so it is **never** user-facing.

    :ivar pos: The character offset the failing construct was attempted FROM —
        not necessarily the deepest character matched. A mismatch inside a
        literal reports the literal's start, and the optimizer merges adjacent
        exactly-once literals into one run, so the offset can sit earlier than
        the first wrong character. ``-1`` when the failure is not about a
        position at all (an islanded start rule, a start rule that produced no
        model).

    The position used to live only in the message, so the one consumer that
    wanted it read it back out of prose with a regex. It is an attribute
    because a caller asking "how far did you get?" should not have to parse an
    error string to find out. The message still spells it too — that is for
    people, and the two are written from the same value.
    """

    __slots__ = ("pos",)

    def __init__(self, message: str, pos: int = -1) -> None:
        """Bind the human-readable reason and the machine-readable position."""
        super().__init__(message)
        self.pos = pos


class ProbeFork(PdaFail):
    """An attempt boundary where taking and stopping are BOTH viable.

    Outside a stop-side probe it behaves as the :class:`PdaFail` it is — the
    parse bails and the gated engine owns the question. Inside a probe it is
    the one signal that must NOT read as "the stop side failed": the probe
    ran into a further undecidable boundary, so the stop side is treated as
    viable (over-approximation — every uncertain answer lands on bail, never
    on a silent commit).
    """
