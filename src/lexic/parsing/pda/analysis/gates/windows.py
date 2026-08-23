"""FIRST_k windows — what a decision point can see ahead.

``KWindowFirst`` computes the k-window of a position and ``FollowWindows``
extends it past the end of a rule, over the ``END``/``MORE``/``UNK``
vocabulary they both speak. The gates in ``kwindow`` are the consumers:
this module only answers what is VISIBLE, never what to do about it.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.core.charsets import CharSet

__all__ = [
    "END",
    "FollowWindows",
    "KWindowFirst",
    "MORE",
    "Pref",
    "UNK",
    "collide",
    "extend_follow",
    "separable",
    "windows_of",
]


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


END, MORE, UNK = "END", "MORE", "UNK"
"""A prefix state: END — the tuple is a complete derivation (may be extended by
FOLLOW); MORE — a longer derivation exists past the window; UNK — the window is
poisoned (an unexpanded/over-wide construct), which collides with everything."""
_STATE_CAP = 3000
"""Per-arm prefix-set cap; a wider fan-out poisons the arm to ``{((), UNK)}``
rather than enumerating exponentially (the poc's ``_STATE_CAP``)."""
Pref = tuple[tuple[CharSet, ...], str]
"""One FIRST_k prefix: a ``≤k``-length CharSet tuple plus its END/MORE/UNK state."""


class _Budget(IrLeaf[IrSelf, IrSelf]):
    """The remaining window budget ``r`` an atom may consume, riding ``nc``."""

    __slots__ = ("r",)

    r: int

    def __init__(self, r: int) -> None:
        self.r = r


def _kp_literal(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A literal contributes one per-char CharSet tuple (END if it fits ``r``)."""
    r = _budget(nc)
    text = str(n)
    tup = tuple(CharSet.from_chars(c) for c in text[:r])
    return {(tup, END if len(text) <= r else MORE)}


def _kp_charclass(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> set[Pref]:
    """A char class contributes its exact member CharSet, one position, END."""
    assert isinstance(n, IrCharClass)
    return {((CharSet.from_charclass(n),), END)}


def _kp_not(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> set[Pref]:
    """An ``IrNot`` contributes the complement CharSet, one position, END."""
    assert isinstance(n, IrNot)
    inner = n[0]
    cs = CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
    return {((cs,), END)}


def _kp_ruleref(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A rule ref's prefixes are the target rule's FIRST_r (cycle-guarded)."""
    return _kw(d).rule_prefixes(str(n), _budget(nc))


def _kp_alternation(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> set[Pref]:
    """A group's prefixes are the union of its arms' FIRST_r, memoised."""
    assert isinstance(n, IrAlternation)
    return _kw(d).group_prefixes(n, _budget(nc))


_KW_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_kp_literal)),
    IrAction(IrCharClass, IrLambda(_kp_charclass)),
    IrAction(IrNot, IrLambda(_kp_not)),
    IrAction(IrRuleRef, IrLambda(_kp_ruleref)),
    IrAction(IrAlternation, IrLambda(_kp_alternation)),
)
"""Open atom-type prefix dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


def _budget(nc: Sequence[IrSelf]) -> int:
    """The remaining window budget off the ``nc`` cursor."""
    ctx = nc[0]
    assert isinstance(ctx, _Budget)
    return ctx.r


def _kw(d: IrSelf) -> "KWindowFirst":
    """The dispatching :class:`KWindowFirst` off the ``d`` slot."""
    assert isinstance(d, KWindowFirst)
    return d


class KWindowFirst(IrLeaf[IrSelf, IrSelf]):
    """FIRST_k as sets of ``≤k``-length CharSet tuples, memoised per (rule, budget).

    Construct per window ``k`` over one grammar's rule table; :meth:`arm_prefixes`
    /:meth:`rule_prefixes` compute the bounded-lookahead prefix set of an arm or
    rule (recursion cycle-guarded via :attr:`busy` — a re-entered rule yields the
    poisoning ``{((), UNK)}``). The atom step routes through :data:`_KW_ATOM`; the
    analysis IS the dispatcher slot ``d`` and the per-atom budget rides ``nc``.

    :ivar rules: The rule table (name → :class:`~lexic.ir.grammar.nodes.IrRule`).
    :ivar k: The window width.
    :ivar memo: ``(rule, budget)`` → its prefix set. An inline group is keyed
        by its node ``id`` instead of a name — it is a nameless rule, and the
        two key spaces are the same pair the gate store keeps apart.
    :ivar busy: keys currently being computed (cycle guard).
    """

    __slots__ = ("rules", "k", "memo", "busy")

    rules: Mapping[str, IrRule]
    k: int
    memo: dict[tuple[str | int, int], set[Pref]]
    busy: set[tuple[str | int, int]]

    def __init__(self, rules: Mapping[str, IrRule], k: int) -> None:
        """Prepare the FIRST_k solver over ``rules`` at window ``k``."""
        self.rules = rules
        self.k = k
        self.memo = {}
        self.busy = set()

    def rule_prefixes(self, name: str, r: int) -> set[Pref]:
        """FIRST_r of rule ``name`` — the union of its arms' prefixes.

        A recursive re-entry (``name`` already on the stack) or an undefined rule
        yields ``{((), UNK)}`` (poison), keeping unbounded recursion finite and
        conservative.
        """
        key = (name, r)
        if key in self.memo:
            return self.memo[key]
        if key in self.busy or name not in self.rules:
            return {((), UNK)}
        self.busy.add(key)
        out: set[Pref] = set()
        for arm in self.rules[name].body:
            out |= self.arm_prefixes(_items(arm), r)
        self.busy.discard(key)
        self.memo[key] = out
        return out

    def group_prefixes(self, group: IrAlternation, r: int) -> set[Pref]:
        """FIRST_r of an inline group — its arms' prefixes, memoised.

        A group is a rule without a name, so it earns :meth:`rule_prefixes`'
        memo and cycle guard under its node identity. Without it the walk
        re-derives every nested group once per path that reaches it, which
        ``@lexical`` inlining turns from a few repeats into millions: vyx's
        maximal variant made 1.39 M ``arm_prefixes`` calls off 9.7 k real ones.
        """
        key = (id(group), r)
        got = self.memo.get(key)
        if got is not None:
            return got
        if key in self.busy:
            return {((), UNK)}
        self.busy.add(key)
        out: set[Pref] = set()
        for arm in group:
            out |= self.arm_prefixes(_items(arm), r)
        self.busy.discard(key)
        self.memo[key] = out
        return out

    def atom_prefixes(self, atom: IrSelf, r: int) -> set[Pref]:
        """FIRST_r of a single atom (``r <= 0`` is the exhausted-window MORE state).

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        if r <= 0:
            return {((), MORE)}
        return _resolve(_KW_ATOM, atom).eval(self, atom, (_Budget(r),))

    def _apply(self, states: set[Pref], atom: IrSelf) -> set[Pref]:
        """Extend each END prefix (with window room) by ``atom``; others pass through."""
        nxt: set[Pref] = set()
        for tup, state in states:
            if state != END or len(tup) >= self.k:
                nxt.add((tup, state))
                continue
            for atup, astate in self.atom_prefixes(atom, self.k - len(tup)):
                nxt.add((tup + atup, astate))
        return nxt

    def arm_prefixes(self, items: Sequence[IrItem], r: int) -> set[Pref]:
        """FIRST_r of a sequence arm — sequential composition over its items.

        Each item's quantifier is unrolled up to ``min(hi, r)`` reps (``r`` for an
        unbounded loop): an optional item (``lo == 0``) keeps the pre-item states,
        each rep past ``lo`` accumulates. When ``lo`` exceeds the window budget
        (``lo > reps``) the derivation cannot complete inside the window, so the
        states after ``reps`` unrollings are unioned in with END demoted to MORE
        rather than dropped — dropping them silently empties a non-nullable arm
        (the retired ``prefixes.py`` vanishing-derivation hole). Prefixes are
        truncated to ``r`` (a truncated END becomes MORE). A per-arm fan-out past
        :data:`_STATE_CAP` poisons the arm to ``{((), UNK)}``.

        :raises UnsupportedConstructError: On an empty prefix set — unproducible
            from a parsed grammar (only a zero-arm empty-language alternation),
            but this is the silent-wrong-parse surface, so the invariant is a
            real raise (never an ``-O``-stripped assert) and the compile seam's
            opt-out turns it into "no PDA for this grammar".
        """
        states: set[Pref] = {((), END)}
        for item in items:
            if all(state != END or len(tup) >= r for tup, state in states):
                break
            lo = int(item.quantifier.lo)
            hi = item.quantifier.hi
            hi_i = None if isinstance(hi, IrNoneType) else int(hi)
            reps = r if hi_i is None else min(hi_i, r)
            acc: set[Pref] = set(states) if lo == 0 else set()
            cur = set(states)
            for rep in range(1, reps + 1):
                cur = self._apply(cur, item.atom)
                if rep >= lo:
                    acc |= cur
                if len(acc) > _STATE_CAP:
                    return {((), UNK)}
            if lo > reps:
                acc |= {(t, MORE if s == END else s) for t, s in cur}
            elif reps == 0:
                acc |= states
            states = {(tup[:r], state if len(tup) <= r else MORE) for tup, state in acc}
        if not states:
            raise UnsupportedConstructError(
                "kwindow: arm_prefixes yielded an empty prefix set "
                "(empty-language alternation arm)"
            )
        return states


def _resolve(table: IrTypeMap, atom: IrSelf) -> IrSelf:
    """Resolve ``atom`` in ``table`` (the raising-default open dispatch)."""
    return table.resolve(atom)


def collide(a: Pref, b: Pref) -> bool:
    """Whether two prefixes overlap positionwise over their min window.

    Two prefixes collide when every position of the shorter one's CharSet
    overlaps the other's — a shorter prefix (a nullable/short arm) collides with
    any longer prefix sharing its lead, which is exactly why ε keeps states short
    and short states are un-separable (the nullable hole closed structurally).
    """
    ta, tb = a[0], b[0]
    m = min(len(ta), len(tb))
    return all(ta[i].overlaps(tb[i]) for i in range(m))


def separable(sets: Sequence[set[Pref]]) -> bool:
    """Whether the prefix sets are pairwise collision-free (the decision separates).

    All-or-nothing per decision: any cross-branch collision fails the whole
    decision (it stays an island).
    """
    for i, sa in enumerate(sets):
        for sb in sets[i + 1 :]:
            if any(collide(pa, pb) for pa in sa for pb in sb):
                return False
    return True


def _follow_prefs(follow: "CharSet | set[Pref]") -> set[Pref]:
    """Normalise a FOLLOW argument to a window set.

    A single :class:`CharSet` is the ``k = 1`` special case — one END-extension
    position, unknown past it (an empty CharSet contributes nothing, the old
    ``not follow.is_empty()`` guard); a :class:`FollowWindows` set rides through
    verbatim.
    """
    if isinstance(follow, CharSet):
        return set() if follow.is_empty() else {((follow,), UNK)}
    return follow


def extend_follow(prefs: set[Pref], follow: "CharSet | set[Pref]", k: int) -> set[Pref]:
    """Extend each short END prefix by the FOLLOW windows, capping at ``k``.

    An END prefix shorter than ``k`` can be continued by whatever follows the
    rule at its call site. ``follow`` is either a single :class:`CharSet` — the
    ``k = 1`` FOLLOW special case that appends that one char set then marks the
    result UNK (past FOLLOW is unknown; chess ``nonpawn`` separates only with
    this) — or a full FOLLOW\\ :sub:`k` window set (:class:`FollowWindows`),
    each window spliced on and truncated to the remaining budget. A prefix
    already at ``k`` (or not END) rides through unchanged. The one mechanism:
    the single-CharSet path is the one-position, one-window degenerate case.
    """
    fw = _follow_prefs(follow)
    out: set[Pref] = set()
    for tup, state in prefs:
        if state != END or len(tup) >= k or not fw:
            out.add((tup, state))
            continue
        room = k - len(tup)
        for ftup, fstate in fw:
            clipped = ftup[:room]
            if len(ftup) > room:
                merged = MORE
            elif fstate == END:
                merged = END
            else:
                merged = fstate
            out.add((tup + clipped, merged))
    return out


def _window_key(win: tuple[CharSet, ...]) -> tuple[tuple[bool, tuple[str, ...]], ...]:
    """A deterministic sort key for a CharSet window (per-position polarity+chars)."""
    return tuple((cs.negated, tuple(sorted(cs.chars))) for cs in win)


def windows_of(prefs: set[Pref]) -> tuple[tuple[CharSet, ...], ...]:
    """The gate-spec windows of a prefix set — tags dropped, dedup'd, sorted.

    The END/MORE/UNK tag is irrelevant to the runtime's positionwise consistency
    test (separability guarantees at most one branch matches), so the stored spec
    is just the CharSet tuples; sorting makes the compiled spec deterministic and
    directly comparable.
    """
    return tuple(sorted({tup for tup, _tag in prefs}, key=_window_key))


class FollowWindows(IrLeaf[IrSelf, IrSelf]):
    """FOLLOW\\ :sub:`k` as per-rule CharSet windows — FOLLOW deepened to ``k``.

    For each rule ``R``, :attr:`follow`\\ ``[R]`` is the set of ``≤k``-length
    prefix windows (:data:`Pref`) that can appear immediately after a complete
    ``R`` at any reference site. It is a fixpoint over the grammar, EOF-seeded at
    the start rule: for every occurrence of ``R`` in a rule ``P``'s arm, the set
    unions :meth:`~KWindowFirst.arm_prefixes` of the arm's remainder (with ``R``'s
    own loop-back folded in) END-extended by :attr:`follow`\\ ``[P]``. Inline
    groups recurse — a ref inside a group inherits the group's continuation.

    Built lazily by the caller — only the nullable-greedy arm demotion asks for
    it, so a grammar that never hits that branch never runs this fixpoint.

    :ivar rules: The rule table (name → :class:`~lexic.ir.grammar.nodes.IrRule`).
    :ivar start: The start rule name (the EOF seed site).
    :ivar k: The window width.
    :ivar solver: The shared FIRST\\ :sub:`k` solver — its ``arm_prefixes`` builds
        the remainder windows and drives the separability check downstream.
    :ivar follow: Rule name → its FOLLOW\\ :sub:`k` window set.
    """

    __slots__ = ("rules", "start", "k", "solver", "follow")

    rules: Mapping[str, IrRule]
    start: str
    k: int
    solver: KWindowFirst
    follow: dict[str, set[Pref]]

    def __init__(self, rules: Mapping[str, IrRule], start: str, k: int) -> None:
        """Run the FOLLOW\\ :sub:`k` fixpoint over ``rules`` at window ``k``."""
        self.rules = rules
        self.start = start
        self.k = k
        self.solver = KWindowFirst(rules, k)
        self.follow = {name: set() for name in rules}
        if start in self.follow:
            self.follow[start] = {((), END)}
        self._solve()

    def _solve(self) -> None:
        """Grow every rule's FOLLOW\\ :sub:`k` window set to the least fixpoint."""
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                tail = self.follow[name]
                for arm in rule.body:
                    if self._feed_arm(_items(arm), tail):
                        changed = True

    def _feed_arm(self, items: Sequence[IrItem], tail: set[Pref]) -> bool:
        """Feed FOLLOW\\ :sub:`k` contributions of one arm continued by ``tail``."""
        changed = False
        for i, item in enumerate(items):
            rest = self._rest_windows(items, i, tail)
            atom = item.atom
            if isinstance(atom, IrRuleRef):
                if self._grow(str(atom), rest):
                    changed = True
            elif isinstance(atom, IrAlternation):
                for sub in atom:
                    if self._feed_arm(_items(sub), rest):
                        changed = True
        return changed

    def _rest_windows(
        self, items: Sequence[IrItem], i: int, tail: set[Pref]
    ) -> set[Pref]:
        """Windows following item ``i``: the remainder's prefixes (item ``i``'s
        loop-back folded in) END-extended by ``tail``."""
        item = items[i]
        hi = item.quantifier.hi
        if isinstance(hi, IrNoneType) or int(hi) > 1:
            loop = IrItem(item.atom, IrQuantifier(0, hi))
            rest_items: list[IrItem] = [loop, *items[i + 1 :]]
        else:
            rest_items = list(items[i + 1 :])
        prefs = self.solver.arm_prefixes(rest_items, self.k)
        return extend_follow(prefs, tail, self.k)

    def _grow(self, name: str, windows: set[Pref]) -> bool:
        """Union ``windows`` into rule ``name``'s FOLLOW set; ``True`` if it grew."""
        if name not in self.follow:
            return False
        merged = self.follow[name] | windows
        if merged != self.follow[name]:
            self.follow[name] = merged
            return True
        return False
