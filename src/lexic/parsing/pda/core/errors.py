"""``PdaFail`` — the predictive-parse failure signal, shared across the PDA.

Homed in its own leaf module so both the runtime (:mod:`.runtime`) and the
island escape (:mod:`.islands`) can raise it without an import cycle; the
runtime re-exports it, so ``from lexic.parsing.pda.runtime.kernel.kernel import PdaFail``
still resolves.
"""

from __future__ import annotations

import sys
from typing import Any

__all__ = ["BuildFail", "IslandEscape", "PdaFail", "ProbeFork", "Suspended"]


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
        :attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone.name`), or ``""``
        when the stop was not inside a named rule.
    :ivar expected: The characters that would have been accepted here — empty
        when the raising site cannot say.
    :ivar negated: ``True`` when :attr:`expected` is an EXCLUSION set, so the
        polarity survives instead of a co-finite set being enumerated.

    The two travel together as one ``wanted`` argument because they are one
    fact — a membership set with a polarity, the engine's own ``(chars,
    negated)`` shape, which is exactly what
    :func:`~lexic.parsing.pda.compiler.program.flatten.arm_expected` hands back.

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


class BuildFail(PdaFail):
    """A model build that refuses the values it was handed — a refusing fold.

    A failure of the VALUES the parse built, not of the text it read: an
    attempted arm whose build refuses misses, as any arm that fails, and the
    gated engine, re-running the same build, refuses the same way. Kept apart
    from the :class:`~lexic.exceptions.LexicError` an island raises when its
    text means two things, which is no arm's miss."""


class ProbeFork(PdaFail):
    """An attempt boundary where taking and stopping are BOTH viable.

    Outside a stop-side probe it behaves as the :class:`PdaFail` it is — the
    parse bails and the gated engine owns the question. Inside a probe it is
    the one signal that must NOT read as "the stop side failed": the probe
    ran into a further undecidable boundary, so the stop side is treated as
    viable (over-approximation — every uncertain answer lands on bail, never
    on a silent commit).
    """


class IslandEscape[Payload](ProbeFork):
    """A greedy match that cannot answer for its rule here: ask the island.

    Raised by a rule compiled to take its longest match where the matched span
    holds a character its reference can continue with, so a shorter end might
    be the answer. The kernel site that entered the match catches it and runs
    the island with :attr:`payload`, the same question the rule's reference
    would have asked as an island. A site that does not catch it meets a
    :class:`ProbeFork`: the parse bails, and the gated engine answers.

    :ivar payload: The island reference, ``(name, cont, exact, windows)``.
    """

    __slots__ = ("payload",)

    payload: Payload

    def __init__(self, payload: Payload, pos: int) -> None:
        """Bind the island question to ask at ``pos``."""
        super().__init__(f"a longest take at {pos} holds a follower: its island", pos)
        self.payload = payload


class Suspended(BaseException):
    """An attempt sub-run left on the stack for the drive to settle.

    Raised past the parse's in-place depth, where a sub-run's caller would
    otherwise drive it one more Python level down: the caller returns instead,
    and the drive that stands at the depth settles the sub-run when its frames
    drain back to its floor, as the caller would have. A ``BaseException`` so
    that no ``PdaFail`` handler on the way reads it as a miss.

    :ivar floors: The sub-runs it leaves, innermost first — each recorded by
        the sub-run as it passes, and its caller named by the caller's own.
    """

    __slots__ = ("floors",)

    def __init__(self) -> None:
        """Start with no sub-run recorded."""
        super().__init__()
        self.floors: list[tuple[Any, ...]] = []

    @staticmethod
    def called_by(loop: Any, entry: Any) -> None:
        """Name, on the :class:`Suspended` being handled, the caller of the
        sub-run it recorded last — read from :func:`sys.exception`, so a
        caller's handler binds no name of its own."""
        up = sys.exception()
        if isinstance(up, Suspended):
            up.floors[-1] = (*up.floors[-1][:4], loop, entry)

    @staticmethod
    def splicing_into(out: list[Any]) -> None:
        """Name, on the :class:`Suspended` being handled, the list its last
        sub-run's attempt splices its kept arm into, where the audit that
        named the caller could not."""
        up = sys.exception()
        if isinstance(up, Suspended):
            *head, entry = up.floors[-1]
            if entry is not None and entry[1] is None:
                up.floors[-1] = (*head, (entry[0], out, *entry[2:]))
