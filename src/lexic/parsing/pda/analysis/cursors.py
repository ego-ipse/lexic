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
    """The fixpoint constants of one FOLLOW pass.

    :ivar tgt: The FOLLOW table being grown.
    :ivar hard: ``True`` for a *hard* FOLLOW pass (nullable followers skipped).
    :ivar loopback: Whether a repeated item's own FIRST is a contribution. It
        is present in classical soft FOLLOW, absent from hard and structural
        FOLLOW because another optional occurrence is a split, not an authored
        continuation.
    :ivar nullable_first: Whether nullable-follower FIRST may contribute. The
        structural pass admits it only for once-only optional followers; repeat
        followers are generated split edges.
    """

    __slots__ = ("tgt", "hard", "loopback", "nullable_first")

    tgt: dict[str, CharSet]
    hard: bool
    loopback: bool
    nullable_first: bool

    def __init__(
        self,
        tgt: dict[str, CharSet],
        hard: bool,
        loopback: bool,
        nullable_first: bool,
    ) -> None:
        self.tgt = tgt
        self.hard = hard
        self.loopback = loopback
        self.nullable_first = nullable_first


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


class Site(IrLeaf[IrSelf, IrSelf]):
    """WHICH alternation a decision belongs to — for the note, and for the store.

    One alternation, addressed two ways because the two audiences differ: a
    reader wants a label they can find in the grammar, the gate store wants a
    key that cannot collide. A rule body is both (its name); an inline group's
    label is a bracketed tag that repeats across nested groups, so its key is
    the node's identity instead — the convention the loop gates use.

    :ivar label: The note-label prefix — a rule name, or ``rule[k]grp``.
    :ivar at: The gate-store key — the rule name, or ``id(group node)``.
    """

    __slots__ = ("label", "at")

    label: str
    at: str | int

    def __init__(self, label: str, at: str | int) -> None:
        self.label = label
        self.at = at


class Scope(IrLeaf[IrSelf, IrSelf]):
    """The enclosing rule and its FOLLOW tail — the conflict-walk context.

    :ivar rule: The enclosing rule name (the note-label anchor).
    :ivar tail: The (soft) FOLLOW char set at the arm's end.
    :ivar cont: The three continuation views at the arm's end. ``tail`` is its
        soft view; ``hard_tail`` the per-clone tail the PDA compiler bakes (a
        char in ``tail`` but not ``hard_tail`` is a soft-only follower, the F1
        escape route); ``structural_tail`` the soft view with generated repeat
        loopback omitted, so overlap found only in ``tail`` is a greedy split
        rather than an arm fork.
    :ivar body: ``True`` for a rule-body scope (``tail`` IS the rule's FOLLOW);
        ``False`` inside an inline group. The P6 noise-greedy licence is
        rule-body-only.
    """

    __slots__ = ("rule", "cont", "body")

    rule: str
    cont: Cont
    body: bool

    def __init__(self, rule: str, cont: Cont, body: bool) -> None:
        self.rule = rule
        self.cont = cont
        self.body = body

    @property
    def tail(self) -> CharSet:
        """The soft (classical) FOLLOW at the arm's end."""
        return self.cont.soft

    @property
    def hard_tail(self) -> CharSet:
        """The hard FOLLOW — the per-clone tail the compiler bakes."""
        return self.cont.hard

    @property
    def structural_tail(self) -> CharSet:
        """The soft FOLLOW with generated repeat loopback omitted."""
        return self.cont.structural


class Cont(IrLeaf[IrSelf, IrSelf]):
    """The three continuation views a decision is cut against.

    :ivar soft: The soft (classical) continuation char set.
    :ivar hard: The hard continuation — the per-clone tail a nested loop cuts to.
    :ivar structural: Soft continuation with repeat loopback omitted.
    """

    __slots__ = ("soft", "hard", "structural")

    soft: CharSet
    hard: CharSet
    structural: CharSet

    def __init__(self, soft: CharSet, hard: CharSet, structural: CharSet) -> None:
        self.soft = soft
        self.hard = hard
        self.structural = structural


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
