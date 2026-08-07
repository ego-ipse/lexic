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
    :ivar rule: The rule being matched when it stopped (a
        :attr:`~lexic.parsing.pda.compiler.flatten.FlatClone.name`), or ``""``
        when the stop was not inside a named rule.
    :ivar expected: The characters that would have been accepted here — empty
        when the raising site cannot say.
    :ivar negated: ``True`` when :attr:`expected` is an EXCLUSION set, so the
        polarity survives instead of a co-finite set being enumerated.

    The two travel together as one ``wanted`` argument because they are one
    fact — a membership set with a polarity, the engine's own ``(chars,
    negated)`` shape, which is exactly what
    :func:`~lexic.parsing.pda.compiler.flatten.arm_expected` hands back.

    The position used to live only in the message, so the one consumer that
    wanted it read it back out of prose with a regex. These are attributes
    because a caller asking "how far did you get, and what did you want?"
    should not have to parse an error string to find out. The message still
    spells the position too — that half is for people, and the two are written
    from the same value. Together they are what
    :class:`~lexic.exceptions.Refusal` is built from at the product seam, which
    is where a caller finally sees them.
    """

    __slots__ = ("pos", "rule", "expected", "negated")

    def __init__(
        self,
        message: str,
        pos: int = -1,
        *,
        rule: str = "",
        wanted: tuple[tuple[str, ...], bool] = ((), False),
    ) -> None:
        """Bind the human-readable reason and the machine-readable readout."""
        super().__init__(message)
        self.pos = pos
        self.rule = rule
        self.expected, self.negated = wanted


class ProbeFork(PdaFail):
    """An attempt boundary where taking and stopping are BOTH viable.

    Outside a stop-side probe it behaves as the :class:`PdaFail` it is — the
    parse bails and the gated engine owns the question. Inside a probe it is
    the one signal that must NOT read as "the stop side failed": the probe
    ran into a further undecidable boundary, so the stop side is treated as
    viable (over-approximation — every uncertain answer lands on bail, never
    on a silent commit).
    """
