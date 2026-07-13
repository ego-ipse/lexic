"""Grammar analysis + decision taxonomy — the PDA compiler's oracle.

:class:`GrammarAnalysis`, over a *lifted codegen grammar*, runs the predictive
fixpoints (nullability, FIRST/hard-FIRST, FOLLOW/hard-FOLLOW, LL(2) prefixes) and
classifies each decision ``island`` / ``stopset`` / ``("pairs", set)`` into
:attr:`conflicts` / :attr:`demoted` / :attr:`fail_islands`, via an open dispatch
raising :exc:`~lexic.exceptions.UnsupportedConstructError` on an unknown atom.
"""

from __future__ import annotations

from typing import Mapping, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import IrAtom, IrLambda, IrLeaf, IrNoneType, IrSelf
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.pda import kwindow
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.noise import (
    noise_alphabet,
    noise_greedy_licensed,
    peek_arm_gate,
    peek_loop_gate,
    stopset_escapes_soft_follow,
)
from lexic.parsing.pda.structured import structured_arm_gate, structured_loop_gate
from lexic.parsing.pda.taxonomy import Taxonomy

__all__ = ["GrammarAnalysis", "Taxonomy", "nullable_names"]

_EOF: CharSet = CharSet.from_chars("")
"""The FOLLOW-set seed for the start rule: the empty-string end-of-input
sentinel in a positive :class:`CharSet`."""


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded)."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


# ── context cursors (ride the argument channel) ───────────────────────────


class _FollowPass(IrLeaf[IrSelf, IrSelf]):
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


class _FeedCtx(IrLeaf[IrSelf, IrSelf]):
    """FOLLOW-feed context riding ``nc`` for the :data:`_FOLLOW_FEED` bodies.

    :ivar eff: The continuation char set feeding this atom's FOLLOW.
    :ivar rule: The enclosing rule name (the recursion anchor).
    :ivar pass_: The FOLLOW pass constant (target table + hard flag).
    """

    __slots__ = ("eff", "rule", "pass_")

    eff: CharSet
    rule: str
    pass_: _FollowPass

    def __init__(self, eff: CharSet, rule: str, pass_: _FollowPass) -> None:
        self.eff = eff
        self.rule = rule
        self.pass_ = pass_


class _Notes(IrLeaf[IrSelf, IrSelf]):
    """The conflict-note accumulators for one rule, appended in place.

    :ivar hard: Island-worthy conflict notes (their presence marks an island).
    :ivar soft: Stop-set / LL(2) demotion notes.
    :ivar f1: Set when the F1 stop-set-escape branch fired (fail-island seed).
    """

    __slots__ = ("hard", "soft", "f1")

    hard: list[str]
    soft: list[str]
    f1: bool

    def __init__(self) -> None:
        self.hard = []
        self.soft = []
        self.f1 = False


class _Scope(IrLeaf[IrSelf, IrSelf]):
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


class _Cont(IrLeaf[IrSelf, IrSelf]):
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


class _ConflictCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-item conflict-classification context for the :data:`_SEQ_ATOM` bodies.

    :ivar notes: The rule's note accumulators.
    :ivar cont: The group's effective soft/hard continuation (for a group recurse).
    :ivar rule: The enclosing rule name.
    :ivar index: The item's positional index (for note labelling).
    """

    __slots__ = ("notes", "cont", "rule", "index")

    notes: _Notes
    cont: _Cont
    rule: str
    index: int

    def __init__(self, notes: _Notes, cont: _Cont, rule: str, index: int) -> None:
        self.notes = notes
        self.cont = cont
        self.rule = rule
        self.index = index


class _Nullability(IrLeaf[IrSelf, IrSelf]):
    """The nullability fixpoint as a standalone solver.

    Homes the derives-empty computation both :func:`nullable_names` (for
    :func:`~lexic.parsing.fold.lift_optional_nullables`) and
    :class:`GrammarAnalysis` need — one fixpoint, no duplication. Its growing
    ``nullable`` set is read by the shared :data:`_NULLABLE` bodies whether
    ``d`` is this solver (mid-fixpoint) or a finished :class:`GrammarAnalysis`.
    """

    __slots__ = ("rules", "nullable")

    rules: Mapping[str, IrRule]
    nullable: set[str]

    def __init__(self, rules: Mapping[str, IrRule]) -> None:
        self.rules = rules
        self.nullable = set()

    def solve(self) -> frozenset[str]:
        """Grow ``nullable`` to the least fixpoint and return it frozen."""
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                if name in self.nullable:
                    continue
                if _rule_nullable(self, rule):
                    self.nullable.add(name)
                    changed = True
        return frozenset(self.nullable)


# ── nullability dispatch bodies ───────────────────────────────────────────


def _null_ruleref(d: GrammarAnalysis | _Nullability, n: IrSelf, _nc: object) -> bool:
    """A rule ref is nullable iff its target is currently known nullable."""
    return str(n) in d.nullable


def _null_literal(_d: object, n: IrSelf, _nc: object) -> bool:
    """A literal is nullable iff it is the empty string."""
    return not str(n)


def _null_never(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class or negated class always consumes one char — never nullable."""
    return False


def _null_alternation(
    d: GrammarAnalysis | _Nullability, n: IrSelf, _nc: object
) -> bool:
    """A group is nullable iff any arm's items are all nullable."""
    assert isinstance(n, IrAlternation)
    return any(_seq_nullable(d, _items(arm)) for arm in n)


# ── FIRST dispatch bodies ─────────────────────────────────────────────────


def _first_literal(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a literal: its leading character (empty literal → empty set)."""
    text = str(n)
    return CharSet.from_chars(text[0]) if text else CharSet.EMPTY


def _first_charclass(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a char class: its member set."""
    assert isinstance(n, IrCharClass)
    return CharSet.from_charclass(n)


def _first_not(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of an ``IrNot``: the complement of its inner class (else ANY)."""
    assert isinstance(n, IrNot)
    inner = n[0]
    if isinstance(inner, IrCharClass):
        return CharSet.from_not(inner)
    return CharSet.ANY


def _first_ruleref(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a rule ref: the target's current FIRST; undefined ref → ANY."""
    got = d.first.get(str(n))
    return CharSet.ANY if got is None else got


def _first_alternation(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a group: the union of its arms' sequence FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_first(_items(arm)))
    return out


# ── hard-FIRST dispatch bodies ────────────────────────────────────────────


def _hard_terminal(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a terminal atom equals its FIRST (it is not nullable)."""
    return d.atom_first(cast(IrAtom, n))


def _hard_ruleref(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a rule ref: the target's current hard-FIRST; else ANY."""
    got = d.hard.get(str(n))
    return CharSet.ANY if got is None else got


def _hard_alternation(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a group: the union of its arms' sequence hard-FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_hard(_items(arm)))
    return out


# ── stop-set-eligibility dispatch bodies ──────────────────────────────────


def _stopset_yes(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class / negated class is a single-char loop → stop-set eligible."""
    return True


def _stopset_no(_d: object, _n: IrSelf, _nc: object) -> bool:
    """Literals, refs and groups are not stop-set loop atoms."""
    return False


# ── FOLLOW-feed dispatch bodies ───────────────────────────────────────────


def _feed_ruleref(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Union the effective continuation into a defined ref target's FOLLOW.

    :returns: ``True`` iff the target's FOLLOW set grew.
    """
    name = str(n)
    if name not in d.rules:
        return False
    ctx = cast(_FeedCtx, nc[0])
    tgt = ctx.pass_.tgt
    grown = tgt[name].union(ctx.eff)
    if grown != tgt[name]:
        tgt[name] = grown
        return True
    return False


def _feed_alternation(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Feed the effective continuation into each of a group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(_FeedCtx, nc[0])
    changed = False
    for arm in n:
        if d.feed_seq(_items(arm), ctx.eff, ctx.rule, ctx.pass_):
            changed = True
    return changed


def _feed_terminal(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A terminal atom has no sub-rule FOLLOW to update."""
    return False


# ── sequence-conflict dispatch bodies ─────────────────────────────────────


def _seq_ruleref(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Flag a rule ref whose target the grammar never defines."""
    if str(n) not in d.rules:
        ctx = cast(_ConflictCtx, nc[0])
        ctx.notes.hard.append(f"{ctx.rule}[{ctx.index}]: undefined ref {str(n)!r}")


def _seq_alternation(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Recurse conflict analysis into an inline group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(_ConflictCtx, nc[0])
    sub_arms = [_items(arm) for arm in n]
    label = f"{ctx.rule}[{ctx.index}]grp"
    scope = _Scope(ctx.rule, ctx.cont.soft, ctx.cont.hard, body=False)
    d.arm_conflicts(sub_arms, ctx.cont.soft, label, ctx.notes)
    for sub in sub_arms:
        d.seq_conflicts(sub, scope, ctx.notes)


def _seq_noop(_d: object, _n: IrSelf, _nc: object) -> None:
    """A terminal atom contributes no sequence-level conflict."""
    return None


# ── dispatch tables (open, raising default via IrTypeMap miss) ─────────────

_NULLABLE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_null_literal)),
    IrAction(IrCharClass, IrLambda(_null_never)),
    IrAction(IrNot, IrLambda(_null_never)),
    IrAction(IrRuleRef, IrLambda(_null_ruleref)),
    IrAction(IrAlternation, IrLambda(_null_alternation)),
)

_FIRST: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_first_literal)),
    IrAction(IrCharClass, IrLambda(_first_charclass)),
    IrAction(IrNot, IrLambda(_first_not)),
    IrAction(IrRuleRef, IrLambda(_first_ruleref)),
    IrAction(IrAlternation, IrLambda(_first_alternation)),
)

_HARD: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_hard_terminal)),
    IrAction(IrCharClass, IrLambda(_hard_terminal)),
    IrAction(IrNot, IrLambda(_hard_terminal)),
    IrAction(IrRuleRef, IrLambda(_hard_ruleref)),
    IrAction(IrAlternation, IrLambda(_hard_alternation)),
)

_STOPSET_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_stopset_no)),
    IrAction(IrCharClass, IrLambda(_stopset_yes)),
    IrAction(IrNot, IrLambda(_stopset_yes)),
    IrAction(IrRuleRef, IrLambda(_stopset_no)),
    IrAction(IrAlternation, IrLambda(_stopset_no)),
)

_FOLLOW_FEED: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_feed_terminal)),
    IrAction(IrCharClass, IrLambda(_feed_terminal)),
    IrAction(IrNot, IrLambda(_feed_terminal)),
    IrAction(IrRuleRef, IrLambda(_feed_ruleref)),
    IrAction(IrAlternation, IrLambda(_feed_alternation)),
)

_SEQ_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_seq_noop)),
    IrAction(IrCharClass, IrLambda(_seq_noop)),
    IrAction(IrNot, IrLambda(_seq_noop)),
    IrAction(IrRuleRef, IrLambda(_seq_ruleref)),
    IrAction(IrAlternation, IrLambda(_seq_alternation)),
)


# ── nullability helpers (shared by solver and analysis) ────────────────────


def _item_nullable(d: GrammarAnalysis | _Nullability, item: IrItem) -> bool:
    """Whether ``item`` can consume nothing: ``lo == 0`` or a nullable atom."""
    if int(item.quantifier.lo) == 0:
        return True
    return cast(bool, _NULLABLE.resolve(item.atom).eval(d, item.atom, ()))


def _seq_nullable(d: GrammarAnalysis | _Nullability, items: Sequence[IrItem]) -> bool:
    """Whether every item in a sequence arm is nullable (empty arm → True)."""
    return all(_item_nullable(d, i) for i in items)


def _rule_nullable(d: GrammarAnalysis | _Nullability, rule: IrRule) -> bool:
    """Whether any arm of ``rule`` is all-nullable."""
    return any(_seq_nullable(d, _items(arm)) for arm in rule.body)


def nullable_names(rules: Sequence[IrRule]) -> frozenset[str]:
    """The names of every rule in ``rules`` that derives the empty string.

    The single home of the nullability fixpoint —
    :func:`~lexic.parsing.fold.lift_optional_nullables` consumes it from here
    (an intra-package import) rather than keeping its own copy.
    """
    return _Nullability({str(r.name): r for r in rules}).solve()


# ── the analysis ──────────────────────────────────────────────────────────


# Taxonomy (and its _GateStore) moved to lexic.parsing.pda.taxonomy by pure
# motion (C0302 headroom, Task 6.6); re-exported above for the public surface.


class GrammarAnalysis(IrLeaf[IrSelf, IrSelf]):
    """FIRST/hard-FIRST/FOLLOW/nullability + per-rule conflict classification.

    Constructed over a lifted codegen grammar; all fixpoints run in
    ``__init__`` and the results live on the instance. The analysis IS the
    dispatcher slot ``d`` handed to every atom-type table body — its
    :attr:`first` / :attr:`hard` / :attr:`follow` / :attr:`nullable` state and
    ``seq_*`` helpers are read straight off ``d``.
    """

    __slots__ = (
        "rules",
        "start",
        "nullable",
        "first",
        "hard",
        "_follows",
        "taxonomy",
    )

    rules: dict[str, IrRule]
    start: str
    nullable: frozenset[str]
    first: dict[str, CharSet]
    hard: dict[str, CharSet]
    _follows: tuple[dict[str, CharSet], dict[str, CharSet]]
    taxonomy: Taxonomy

    def __init__(self, grammar: IrAst) -> None:
        """Run every fixpoint and classify every rule of the lifted grammar."""
        self.rules = {str(r.name): r for r in grammar.rules}
        self.start = str(grammar.start)
        self.nullable = nullable_names(list(grammar.rules))
        self.first = self._first_sets()
        self.hard = self._hard_sets()
        self._follows = (
            self._follow_fixpoint(hard=False),
            self._follow_fixpoint(hard=True),
        )
        self.taxonomy = Taxonomy()
        self._classify()

    @property
    def follow(self) -> dict[str, CharSet]:
        """Rule name → its (soft) FOLLOW :class:`CharSet`."""
        return self._follows[0]

    @property
    def hard_follow(self) -> dict[str, CharSet]:
        """Rule name → its hard FOLLOW :class:`CharSet` (nullable followers skipped)."""
        return self._follows[1]

    @property
    def conflicts(self) -> dict[str, list[str]]:
        """Rule name → island-worthy conflict notes (presence marks an island)."""
        return self.taxonomy.conflicts

    @property
    def demoted(self) -> dict[str, list[str]]:
        """Rule name → stop-set / LL(2) demotion notes."""
        return self.taxonomy.demoted

    @property
    def islands(self) -> frozenset[str]:
        """The island rule set — the names keying :attr:`conflicts`."""
        return frozenset(self.taxonomy.conflicts)

    @property
    def fail_islands(self) -> frozenset[str]:
        """Semantic F1 stop-set-escape rules — a reference must raise ``PdaFail``
        (engine fallback), not parse via longest-match. A subset of
        :attr:`islands`."""
        return frozenset(self.taxonomy.fail)

    # ── nullability queries ────────────────────────────────────────────

    def atom_nullable(self, atom: IrAtom) -> bool:
        """Whether ``atom`` can consume nothing under the final nullable set.

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(bool, _NULLABLE.resolve(atom).eval(self, atom, ()))

    def item_nullable(self, item: IrItem) -> bool:
        """Whether ``item`` can consume nothing (``lo == 0`` or nullable atom)."""
        return _item_nullable(self, item)

    # ── FIRST ──────────────────────────────────────────────────────────

    def atom_first(self, atom: IrAtom) -> CharSet:
        """FIRST set of a single atom.

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, _FIRST.resolve(atom).eval(self, atom, ()))

    def seq_first(self, items: Sequence[IrItem]) -> CharSet:
        """FIRST set of an item sequence — union until the first non-nullable."""
        out = CharSet.EMPTY
        for item in items:
            out = out.union(self.atom_first(item.atom))
            if not self.item_nullable(item):
                break
        return out

    def _first_sets(self) -> dict[str, CharSet]:
        """The per-rule FIRST fixpoint (chaotic iteration to stability)."""
        self.first = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_first(_items(arm)))
                if acc != self.first[name]:
                    self.first[name] = acc
                    changed = True
        return self.first

    # ── hard-FIRST ─────────────────────────────────────────────────────

    def atom_hard(self, atom: IrAtom) -> CharSet:
        """hard-FIRST set of a single atom (nullable prefixes contribute nothing).

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, _HARD.resolve(atom).eval(self, atom, ()))

    def seq_hard(self, items: Sequence[IrItem]) -> CharSet:
        """hard-FIRST of a sequence — the first non-nullable item's hard-FIRST."""
        for item in items:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return CharSet.EMPTY

    def hard_cont_at(
        self, items: Sequence[IrItem], k: int, hard_tail: CharSet
    ) -> CharSet:
        """hard continuation after item ``k``: the next required chars, else tail.

        :param hard_tail: The rule's hard continuation (for an all-nullable rest).
        """
        for item in items[k + 1 :]:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return hard_tail

    def _hard_sets(self) -> dict[str, CharSet]:
        """The per-rule hard-FIRST fixpoint."""
        self.hard = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_hard(_items(arm)))
                if acc != self.hard[name]:
                    self.hard[name] = acc
                    changed = True
        return self.hard

    # ── loop policy (the pivot-6 taxonomy) ─────────────────────────────

    def loop_policy(
        self, item: IrItem, rest: Sequence[IrItem]
    ) -> tuple[str, frozenset[str]] | str:
        """Classify a looping item whose FIRST overlaps its hard continuation.

        :returns: ``("pairs", set)`` for an LL(2) gate, ``"stopset"`` for a
            non-greedy single-char loop, or ``"island"`` otherwise.
        """
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if lo == 0 and hi == 1:
            taken = kwindow.atom_two_prefix(self, atom)
            skip = kwindow.two_prefix_seq(self, list(rest))
            if taken is not None and skip is not None and not taken & skip:
                return ("pairs", taken)
        if hi is None and self._stopset_eligible(atom):
            return "stopset"
        return "island"

    def _stopset_eligible(self, atom: IrAtom) -> bool:
        """Whether ``atom`` is a single-char loop atom (char class / negation)."""
        return cast(bool, _STOPSET_ATOM.resolve(atom).eval(self, atom, ()))

    def _store_loop_gate(
        self, item: IrItem, spec: tuple[tuple[CharSet, ...], ...]
    ) -> None:
        """File a demoted loop's ``taken`` windows under the item node's identity.

        :raises UnsupportedConstructError: If the same node already carries a
            *different* spec — a shared node at two decision sites with distinct
            FOLLOWs, which the identity key cannot express (a confident-wrong
            gate would be silent, so the whole grammar opts out instead).
        """
        key = id(item)
        prior = self.taxonomy.loop_gates.get(key)
        if prior is not None and prior != spec:
            raise UnsupportedConstructError(
                "pda analysis: conflicting k-window loop gates for one item node"
            )
        self.taxonomy.loop_gates[key] = spec

    def _demote_arms(
        self,
        arms: list[Sequence[IrItem]],
        ext_follow: CharSet,
        label: str,
        notes: _Notes,
    ) -> bool:
        """The rule-body arm-overlap demotion cascade — P2 k-window, then the
        P3 noise-skip peek — storing the winning gate spec in its taxonomy
        channel plus the soft note. ``False`` ⇒ the overlap stays hard."""
        gate = kwindow.arm_gate(self.rules, arms, ext_follow)
        if gate is not None:
            self.taxonomy.arm_gates[label] = tuple(
                kwindow.windows_of(s) for s in gate[1]
            )
            notes.soft.append(f"{label}: arms k-window separable (demoted)")
            return True
        w = noise_alphabet(self)
        peek = peek_arm_gate(self, arms, w)
        if peek is not None:
            self.taxonomy.pn_arm_gates[label] = (w, peek)
            notes.soft.append(f"{label}: arms noise-skip separable (demoted)")
            return True
        return False

    def _demote_struct_arm(
        self, arms: Sequence[Sequence[IrItem]], label: str, notes: _Notes
    ) -> bool:
        """The empty-arm structured-noise demotion: store the scan gate + escape
        arm index in its taxonomy channel plus the soft note. ``False`` ⇒ no
        licence (the caller keeps today's greedy behavior)."""
        gate = structured_arm_gate(self, list(arms), label)
        if gate is None:
            return False
        self.taxonomy.store_struct_arm(label, gate)
        notes.soft.append(f"{label}: empty-arm structured-noise (demoted)")
        return True

    def _demote_loop(
        self, items: Sequence[IrItem], k: int, scope: _Scope, notes: _Notes
    ) -> bool:
        """The loop take/skip demotion cascade — P2 k-window, then the P3
        noise-skip peek — storing the spec under the item node's identity plus
        the soft note. ``False`` ⇒ the decision stays an island note."""
        gate = kwindow.loop_gate(self.rules, items, k, scope.tail)
        if gate is not None:
            self._store_loop_gate(items[k], kwindow.windows_of(gate[1]))
            notes.soft.append(f"{scope.rule}[{k}]: loop k-window (demoted)")
            return True
        w = noise_alphabet(self)
        take = peek_loop_gate(self, items, k, self.cont_at(items, k, scope.tail), w)
        if take is not None:
            key = id(items[k])
            prior = self.taxonomy.pn_loop_gates.get(key)
            if prior is not None and prior != (w, take):
                raise UnsupportedConstructError(
                    "pda analysis: conflicting noise-skip loop gates for one item node"
                )
            self.taxonomy.pn_loop_gates[key] = (w, take)
            notes.soft.append(f"{scope.rule}[{k}]: loop noise-skip (demoted)")
            return True
        struct = structured_loop_gate(self, items, k, scope)
        if struct is not None:
            self.taxonomy.store_struct_loop(id(items[k]), struct)
            notes.soft.append(f"{scope.rule}[{k}]: loop structured-noise (demoted)")
            return True
        return False

    # ── FOLLOW ─────────────────────────────────────────────────────────

    def _follow_fixpoint(self, hard: bool) -> dict[str, CharSet]:
        """A per-rule FOLLOW fixpoint (EOF-seeded at the start rule).

        :param hard: When ``True``, compute *hard* FOLLOW — nullable followers
            skipped (the union of the HARD continuations every reference site
            cuts its PDA clone against); when ``False``, the classical soft FOLLOW.
        """
        tgt = {name: CharSet.EMPTY for name in self.rules}
        tgt[self.start] = _EOF
        pass_ = _FollowPass(tgt, hard)
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                for arm in rule.body:
                    if self.feed_seq(_items(arm), tgt[name], name, pass_):
                        changed = True
        return tgt

    def feed_seq(
        self,
        items: Sequence[IrItem],
        tail: CharSet,
        rule: str,
        pass_: _FollowPass,
    ) -> bool:
        """Feed FOLLOW contributions of a sequence whose continuation is ``tail``.

        Walks the arm right to left carrying the running continuation. Soft mode
        unions each nullable item's FIRST into it; hard mode uses hard-FIRST and
        *skips* nullable items (mirroring the PDA clone tails). Each atom's
        sub-rule FOLLOW update is delegated to :data:`_FOLLOW_FEED`.

        :param tail: The continuation at the arm's end (the rule's FOLLOW).
        :param pass_: The FOLLOW pass constant (target table + hard flag).
        :returns: ``True`` iff any FOLLOW set grew.
        """
        hard = pass_.hard
        changed = False
        cont = tail
        for item in reversed(items):
            atom = item.atom
            hi = _hi(item)
            eff = cont
            if hi is None or hi > 1:
                eff = eff.union(self.atom_hard(atom) if hard else self.atom_first(atom))
            ctx = _FeedCtx(eff, rule, pass_)
            if cast(bool, _FOLLOW_FEED.resolve(atom).eval(self, atom, (ctx,))):
                changed = True
            if hard:
                if not self.item_nullable(item):
                    cont = self.atom_hard(atom)
            else:
                first = self.atom_first(atom)
                cont = cont.union(first) if self.item_nullable(item) else first
        return changed

    # ── conflict classification ────────────────────────────────────────

    def _classify(self) -> None:
        """Fill :attr:`conflicts` and :attr:`demoted` from every rule."""
        for name, rule in self.rules.items():
            notes = _Notes()
            scope = _Scope(name, self.follow[name], self.hard_follow[name], body=True)
            arms = [_items(arm) for arm in rule.body]
            self.arm_conflicts(arms, self.follow[name], name, notes)
            for arm in arms:
                self.seq_conflicts(arm, scope, notes)
            if notes.hard:
                self.taxonomy.conflicts[name] = notes.hard
            if notes.soft:
                self.taxonomy.demoted[name] = notes.soft
            if notes.f1 and self.rules[name].semantic:
                self.taxonomy.fail.add(name)

    def arm_conflicts(
        self,
        arms: Sequence[Sequence[IrItem]],
        ext_follow: CharSet,
        label: str,
        notes: _Notes,
    ) -> None:
        """Flag pairwise FIRST overlaps and empty-arm-vs-FOLLOW ambiguities.

        Under P2 demotion, a k-window-separable overlap is demoted and its
        per-arm window sets are **stored** in :attr:`Taxonomy.arm_gates` (the
        gate-spec channel the clone compiler reads back). The licence is
        rule-body-only — ``label`` is then exactly the rule name, the store
        key; an inline group's overlap (a bracketed ``label``, never a rule
        name) stays a hard note, so the enclosing rule islands.

        :param ext_follow: The FOLLOW set at the alternation's end.
        :param label: The note-label prefix (rule name or group tag).
        """
        infos = [(self.seq_first(arm), _seq_nullable(self, arm)) for arm in arms]
        overlaps: list[tuple[int, int]] = []
        for i, (first_i, _) in enumerate(infos):
            for j, (first_j, _) in enumerate(infos[i + 1 :], i + 1):
                if first_i.overlaps(first_j):
                    overlaps.append((i, j))
        if overlaps:
            demoted = label in self.rules and self._demote_arms(
                list(arms), ext_follow, label, notes
            )
            if not demoted:
                for i, j in overlaps:
                    notes.hard.append(f"{label}: arms {i}/{j} FIRST overlap")
        if any(nullable for _, nullable in infos):
            greedy = [
                i
                for i, (first_i, nullable) in enumerate(infos)
                if not nullable and first_i.overlaps(ext_follow)
            ]
            if not (
                greedy
                and label in self.rules
                and self._demote_struct_arm(arms, label, notes)
            ):
                for i in greedy:
                    notes.soft.append(f"{label}: arm {i} FIRST hits FOLLOW (greedy)")

    def seq_conflicts(
        self, items: Sequence[IrItem], scope: _Scope, notes: _Notes
    ) -> None:
        """Classify every decision point in one sequence arm."""
        for k in range(len(items)):
            self._loop_conflict(items, k, scope, notes)
            self._sub_conflict(items, k, scope, notes)

    def _loop_conflict(
        self, items: Sequence[IrItem], k: int, scope: _Scope, notes: _Notes
    ) -> None:
        """Classify item ``k``'s continue/exit decision (the pivot-6 taxonomy)."""
        item = items[k]
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if hi is not None and hi <= lo:
            return
        if self.atom_nullable(atom) and (hi is None or hi - lo > 1):
            notes.hard.append(f"{scope.rule}[{k}]: unbounded loop over nullable atom")
            return
        first = self.atom_first(atom)
        if first.overlaps(self.hard_cont_at(items, k, scope.tail)):
            policy = self.loop_policy(item, items[k + 1 :])
            if policy == "island":
                if not self._demote_loop(items, k, scope, notes):
                    notes.hard.append(f"{scope.rule}[{k}]: loop overlap, not gatable")
            elif policy == "stopset":
                if not stopset_escapes_soft_follow(self, items, k, scope):
                    notes.soft.append(f"{scope.rule}[{k}]: loop stop-set applied")
                elif noise_greedy_licensed(self, items, k, scope):
                    notes.soft.append(
                        f"{scope.rule}[{k}]: loop stop-set applied (noise-greedy)"
                    )
                else:
                    notes.hard.append(
                        f"{scope.rule}[{k}]: loop stop-set escapes soft FOLLOW"
                    )
                    notes.f1 = True
            else:
                notes.soft.append(f"{scope.rule}[{k}]: LL(2) pair gate")
            return
        self._soft_gap_conflict(items, k, scope, notes)

    def _soft_gap_conflict(
        self, items: Sequence[IrItem], k: int, scope: _Scope, notes: _Notes
    ) -> None:
        """Classify a loop whose FIRST overlaps only *soft* followers.

        The hard-continuation guard above misses this class entirely: the baked
        stop-set is ``FIRST − hard cont``, so the loop greedily eats chars a
        nullable follower in the same arm needed (GBNF ``grammar``'s
        ``rules-rest*`` taking the trailing newline that belonged to the final
        ``n?``, then demanding a rule at EOF). Silent before Task 6.6 only
        because every affected spine rule was an island. Cascade: the P6
        noise-greedy licence (greedy stays sound — noise↔noise re-split), then
        the standard loop-demotion gates, else a hard note (the rule islands
        rather than carry a confident-wrong gate).
        """
        gap = self.cont_at(items, k, scope.tail).subtract(
            self.hard_cont_at(items, k, scope.tail)
        )
        if not self.atom_first(items[k].atom).overlaps(gap):
            return
        if noise_greedy_licensed(self, items, k, scope):
            notes.soft.append(
                f"{scope.rule}[{k}]: loop stop-set applied (noise-greedy)"
            )
            return
        if not self._demote_loop(items, k, scope, notes):
            notes.hard.append(
                f"{scope.rule}[{k}]: loop over-eats soft FOLLOW, not gatable"
            )

    def _sub_conflict(
        self, items: Sequence[IrItem], k: int, scope: _Scope, notes: _Notes
    ) -> None:
        """Dispatch item ``k``'s atom for undefined-ref / group-recursion checks."""
        item = items[k]
        atom = item.atom
        hi = _hi(item)
        eff = self.cont_at(items, k, scope.tail)
        hard_eff = self.hard_cont_at(items, k, scope.hard_tail)
        if hi is None or hi > 1:
            eff = eff.union(self.atom_first(atom))
            hard_eff = hard_eff.union(self.atom_hard(atom))
        ctx = _ConflictCtx(notes, _Cont(eff, hard_eff), scope.rule, k)
        _SEQ_ATOM.resolve(atom).eval(self, atom, (ctx,))

    def cont_at(self, items: Sequence[IrItem], k: int, tail: CharSet) -> CharSet:
        """The continuation char set after item ``k`` (rest of arm, then tail)."""
        rest = items[k + 1 :]
        cont = self.seq_first(rest)
        if all(self.item_nullable(i) for i in rest):
            cont = cont.union(tail)
        return cont
