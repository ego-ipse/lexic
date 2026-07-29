"""Analysis context cursors — the small data records that ride the ``nc`` channel.

Split out of :mod:`lexic.parsing.pda.analysis.analysis` by pure motion (the
noise/structured/taxonomy/kwindow precedent, for C0302 headroom). These are
inert :class:`~lexic.ir.base.IrLeaf` records — a FOLLOW pass constant, the
FOLLOW-feed / conflict-walk contexts, and the note accumulators — carrying no
behaviour and no dependency on :mod:`analysis`, so they move cleanly and the
analysis (and its dispatch bodies) import them back.
"""

from __future__ import annotations

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.pda.core.charsets import CharSet


class FollowPass(IrLeaf[IrSelf, IrSelf]):
    """The fixpoint-constant of one FOLLOW pass: target table + hard flag.

    :ivar tgt: The FOLLOW table being grown (soft or hard).
    :ivar hard: ``True`` for a *hard* FOLLOW pass (nullable followers skipped).
    """

    __slots__ = ("tgt", "hard")

    tgt: dict[str, CharSet]
    hard: bool

    def __init__(self, tgt: dict[str, CharSet], hard: bool) -> None:
        self.tgt = tgt
        self.hard = hard


class FeedCtx(IrLeaf[IrSelf, IrSelf]):
    """FOLLOW-feed context riding ``nc`` for the ``_FOLLOW_FEED`` bodies.

    :ivar eff: The continuation char set feeding this atom's FOLLOW.
    :ivar rule: The enclosing rule name (the recursion anchor).
    :ivar pass_: The FOLLOW pass constant (target table + hard flag).
    """

    __slots__ = ("eff", "rule", "pass_")

    eff: CharSet
    rule: str
    pass_: FollowPass

    def __init__(self, eff: CharSet, rule: str, pass_: FollowPass) -> None:
        self.eff = eff
        self.rule = rule
        self.pass_ = pass_


class Notes(IrLeaf[IrSelf, IrSelf]):
    """The conflict-note accumulators for one rule, appended in place.

    :ivar hard: Island-worthy conflict notes (their presence marks an island).
    :ivar soft: Stop-set / LL(2) demotion notes.
    :ivar f1: Set when the F1 stop-set-escape branch fired (fail-island seed).
    :ivar covered: How many of :attr:`hard` an attempt licence covers (the
        ungatable-loop notes filed into ``Taxonomy.attempt_loops``); a rule
        whose every hard note is covered or a body-arm overlap is attemptable.
    """

    __slots__ = ("hard", "soft", "f1", "covered")

    hard: list[str]
    soft: list[str]
    f1: bool
    covered: int

    def __init__(self) -> None:
        self.hard = []
        self.soft = []
        self.f1 = False
        self.covered = 0


class Scope(IrLeaf[IrSelf, IrSelf]):
    """The enclosing rule and its FOLLOW tail — the conflict-walk context.

    :ivar rule: The enclosing rule name (the note-label anchor).
    :ivar tail: The (soft) FOLLOW char set at the arm's end.
    :ivar hard_tail: The *hard* FOLLOW at the arm's end — the per-clone tail the
        PDA compiler bakes; a char in ``tail`` but not ``hard_tail`` is a
        soft-only follower (the F1 escape route).
    :ivar body: ``True`` for a rule-body scope (``tail`` IS the rule's FOLLOW);
        ``False`` inside an inline group. The P6 noise-greedy licence is
        rule-body-only.
    """

    __slots__ = ("rule", "tail", "hard_tail", "body")

    rule: str
    tail: CharSet
    hard_tail: CharSet
    body: bool

    def __init__(
        self, rule: str, tail: CharSet, hard_tail: CharSet, body: bool
    ) -> None:
        self.rule = rule
        self.tail = tail
        self.hard_tail = hard_tail
        self.body = body


class Cont(IrLeaf[IrSelf, IrSelf]):
    """A soft/hard continuation pair — the set a decision is cut against.

    :ivar soft: The soft (classical) continuation char set.
    :ivar hard: The hard continuation — the per-clone tail a nested loop cuts to.
    """

    __slots__ = ("soft", "hard")

    soft: CharSet
    hard: CharSet

    def __init__(self, soft: CharSet, hard: CharSet) -> None:
        self.soft = soft
        self.hard = hard


class ConflictCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-item conflict-classification context for the ``_SEQ_ATOM`` bodies.

    :ivar notes: The rule's note accumulators.
    :ivar cont: The group's effective soft/hard continuation (for a group recurse).
    :ivar rule: The enclosing rule name.
    :ivar index: The item's positional index (for note labelling).
    """

    __slots__ = ("notes", "cont", "rule", "index")

    notes: Notes
    cont: Cont
    rule: str
    index: int

    def __init__(self, notes: Notes, cont: Cont, rule: str, index: int) -> None:
        self.notes = notes
        self.cont = cont
        self.rule = rule
        self.index = index
