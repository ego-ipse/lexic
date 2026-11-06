"""Prefixes — whether a loop's complete units can spell into what follows the loop.

The exact-match noise gate takes another iteration wherever a complete unit
matches at the cursor, so it takes text of the loop's follower ``F`` in two
ways, which :func:`spells_into` decides:

- a complete unit at the cursor is the whole of, or a proper prefix of, an
  ``F`` string;
- a complete unit runs on past a shorter complete one, ``u₂ = u₁·v`` with ``v``
  a nonempty prefix of an ``F`` string — EXTEND's exact, local form.

A follower that runs off its arm goes on (:class:`After`): past a rule body
into what follows the rule at its reference sites
(:meth:`~lexic.parsing.pda.analysis.gates.ends.sites.RunIndex.rests`), past an
inline group into one character of its FOLLOW and then anything.

Both sides are Thompson NFAs over character sets, built from the rules only as
far as a walk goes. A reference recurring on its own path, an undefined rule,
a bound past :data:`COPIES` and a build past :data:`BUDGET` states read as
``Σ*``, and each rule's follow has one entry state; all are supersets, so the
answer errs only toward yes. A unit's side is built once per analysis
(:class:`Spelled`) with the characters it can read first, so a follower that
starts with none of them is answered before its own side is built.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAtom,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.gates.ends.sites import run_index
from lexic.parsing.pda.core.charsets import CharSet

__all__ = [
    "BUDGET",
    "COPIES",
    "PAIRS",
    "After",
    "Nfa",
    "Spelled",
    "spelled",
    "spells_into",
]

BUDGET = 4096
"""States one walk's build may add before a reference reads as ``Σ*``."""

COPIES = 8
"""The widest finite bound copied out; past it an item reads as its star."""

PAIRS = 200_000
"""Walk states one question visits before it answers yes unproved."""

Moves = list[tuple[CharSet, int]]


class After(NamedTuple):
    """What follows a sequence that runs out.

    :ivar rule: The rule whose body the sequence ends, or ``None`` for an
        inline group.
    :ivar tail: That end's FOLLOW, read where ``rule`` is ``None``.
    """

    rule: str | None
    tail: CharSet


class Nfa(IrLeaf[IrSelf, IrSelf]):
    """A Thompson NFA over character sets, grown fragment by fragment.

    A fragment runs from the state it is given to the state it returns, and
    every state it adds reaches that end. A reference's body and a rule's
    follow wait in :attr:`pending` until a closure reaches their entry.

    :ivar analysis: The grammar-analysis oracle.
    :ivar moves: State → its ``(label, target)`` character moves.
    :ivar eps: State → its empty-move targets.
    :ivar pending: Entry state → the rule, the end its body joins (``None``
        for a follow), and the rules expanded on its path.
    :ivar reach: State → its ε-closure's character moves and the closure.
    :ivar memo: ``"follow"``: rule → this walk's follow entry; ``"label"``:
        ``id`` of a one-character atom → its set; ``"single"``: rule →
        whether it derives only one-character strings; ``"mark"``: the state
        count this walk's build started from (``BUDGET`` counts from it).
    """

    __slots__ = ("analysis", "moves", "eps", "pending", "reach", "memo")

    analysis: Any
    moves: list[Moves]
    eps: list[list[int]]
    pending: dict[int, tuple[str, int | None, frozenset[str]]]
    reach: dict[int, tuple[Moves, frozenset[int]]]
    memo: dict[str, Any]

    def __init__(self, analysis: Any) -> None:
        self.analysis = analysis
        self.moves = []
        self.eps = []
        self.pending = {}
        self.reach = {}
        self.memo = {"follow": {}, "label": {}, "single": {}, "mark": 0}

    def state(self) -> int:
        """A fresh state."""
        self.moves.append([])
        self.eps.append([])
        return len(self.moves) - 1

    def step(self, start: int, label: CharSet) -> int:
        """One character move out of ``start``; its target."""
        end = self.state()
        self.moves[start].append((label, end))
        return end

    def anything(self, start: int) -> int:
        """``Σ*`` from ``start``; its end."""
        loop = self.state()
        self.eps[start].append(loop)
        self.moves[loop].append((CharSet.ANY, loop))
        return loop

    def closure(self, state: int) -> tuple[Moves, frozenset[int]]:
        """``state``'s ε-closure's character moves, and the closure; whatever
        waits in it is built first, so it never grows after."""
        found = self.reach.get(state)
        if found is not None:
            return found
        held, stack = {state}, [state]
        while stack:
            here = stack.pop()
            if here in self.pending:
                self._expand(here)
            for there in self.eps[here]:
                if there not in held:
                    held.add(there)
                    stack.append(there)
        found = self.reach[state] = (
            [m for h in held for m in self.moves[h]],
            frozenset(held),
        )
        return found

    def _expand(self, state: int) -> None:
        """Build what waits at ``state``."""
        name, end, path = self.pending.pop(state)
        if end is None:
            sites = run_index(self.analysis)
            if name == sites.start and sites.delegated:
                self.anything(state)
            for rest in sites.rests(name):
                tail = state
                for step in rest.steps:
                    tail = self.seq(step, tail, frozenset())
                self.eps[tail].append(self.follow(rest.holder))
            return
        self.eps[_group(self, self.analysis.rules[name].body, (state, path))].append(
            end
        )

    def follow(self, rule: str) -> int:
        """The entry state of what follows ``rule``, one per rule and walk."""
        follows = self.memo["follow"]
        entry = follows.get(rule)
        if entry is None:
            entry = follows[rule] = self.state()
            self.pending[entry] = (rule, None, frozenset())
        return entry

    def seq(self, items: Sequence[IrItem], start: int, path: frozenset[str]) -> int:
        """A sequence's fragment from ``start``; its end."""
        for item in items:
            start = self.item(item, start, path)
        return start

    def item(self, item: IrItem, start: int, path: frozenset[str]) -> int:
        """``lo`` copies, then up to ``hi`` optional ones, or a loop."""
        lo, hi = int(item.quantifier.lo), item.quantifier.upper()
        if lo > COPIES or (hi is not None and hi > COPIES):
            lo, hi = 0, None
        for _ in range(lo):
            start = self.atom(item.atom, start, path)
        if hi == lo:
            return start
        if hi is None:
            loop = self.state()
            self.eps[start].append(loop)
            self.eps[self.atom(item.atom, loop, path)].append(loop)
            return loop
        ends = [start]
        for _ in range(hi - lo):
            start = self.atom(item.atom, start, path)
            ends.append(start)
        out = self.state()
        for end in ends:
            self.eps[end].append(out)
        return out

    def atom(self, atom: IrAtom, start: int, path: frozenset[str]) -> int:
        """An atom's fragment from ``start``; its end.

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(int, ATOMS.resolve(atom).eval(self, atom, (start, path)))


def _literal(d: IrSelf, n: IrSelf, nc: Sequence[object]) -> int:
    """A literal: one move per character."""
    nfa, end = cast(Nfa, d), cast(int, nc[0])
    for ch in str(n):
        end = nfa.step(end, CharSet.from_chars(ch))
    return end


def _class(d: IrSelf, n: IrSelf, nc: Sequence[object]) -> int:
    """A one-character atom: one move over its set, read once per node (the
    grammar's nodes outlive the NFA)."""
    nfa = cast(Nfa, d)
    labels = nfa.memo["label"]
    label = labels.get(id(n))
    if label is None:
        label = labels[id(n)] = nfa.analysis.atom_first(n)
    return nfa.step(cast(int, nc[0]), label)


def _alphabet(d: IrSelf, _n: IrSelf, nc: Sequence[object]) -> int:
    """A token atom: any one character, a superset."""
    return cast(Nfa, d).step(cast(int, nc[0]), CharSet.ANY)


def _group(d: IrSelf, n: IrSelf, nc: Sequence[object]) -> int:
    """A group's arms side by side, joined at one end (one arm needs none)."""
    nfa, start, path = cast(Nfa, d), cast(int, nc[0]), cast(frozenset[str], nc[1])
    arms = cast(IrAlternation, n)
    if len(arms) == 1:
        return nfa.seq(arms[0], start, path)
    out = nfa.state()
    for arm in arms:
        nfa.eps[nfa.seq(arm, start, path)].append(out)
    return out


def _ruleref(d: IrSelf, n: IrSelf, nc: Sequence[object]) -> int:
    """A reference: one move over its FIRST where every string it derives is
    one character, else its body waiting at a fresh entry; ``Σ*`` where it is
    undefined, recurs on its path, or the walk's build is past its budget."""
    nfa, start, path, name = (
        cast(Nfa, d),
        cast(int, nc[0]),
        cast(frozenset[str], nc[1]),
        str(n),
    )
    if (
        name not in nfa.analysis.rules
        or name in path
        or len(nfa.moves) - nfa.memo["mark"] > BUDGET
    ):
        return nfa.anything(start)
    if _single(nfa, name, frozenset()):
        return nfa.step(start, nfa.analysis.first[name])
    entry, end = nfa.state(), nfa.state()
    nfa.eps[start].append(entry)
    nfa.pending[entry] = (name, end, path | {name})
    return end


ATOMS: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_literal)),
    IrAction(IrCharClass, IrLambda(_class)),
    IrAction(IrNot, IrLambda(_class)),
    IrAction(IrAlphabet, IrLambda(_alphabet)),
    IrAction(IrRuleRef, IrLambda(_ruleref)),
    IrAction(IrAlternation, IrLambda(_group)),
)
"""Open atom-type NFA construction; an unregistered atom raises."""


def _single(nfa: Nfa, name: str, seen: frozenset[str]) -> bool:
    """Whether every string rule ``name`` derives is one character, so its
    FIRST is its whole language."""
    singles = nfa.memo["single"]
    found = singles.get(name)
    if found is None:
        rule = nfa.analysis.rules.get(name)
        found = singles[name] = (
            rule is not None
            and name not in seen
            and all(
                len(arm) == 1 and _one_char(nfa, arm[0], seen | {name})
                for arm in rule.body
            )
        )
    return cast(bool, found)


def _one_char(nfa: Nfa, item: IrItem, seen: frozenset[str]) -> bool:
    """Whether ``item`` matches exactly one character, once."""
    if int(item.quantifier.lo) != 1 or item.quantifier.upper() != 1:
        return False
    return cast(bool, ONE_CHAR.resolve(item.atom).eval(nfa, item.atom, (seen,)))


ONE_CHAR: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(lambda _d, n, _nc: len(str(n)) == 1)),
    IrAction(IrCharClass, IrLambda(lambda *_a: True)),
    IrAction(IrNot, IrLambda(lambda *_a: True)),
    IrAction(IrAlphabet, IrLambda(lambda *_a: False)),
    IrAction(IrRuleRef, IrLambda(lambda d, n, nc: _single(d, str(n), nc[0]))),
    IrAction(IrAlternation, IrLambda(lambda *_a: False)),
)
"""Open atom-type one-character test; an unregistered atom raises."""


class Spelled(NamedTuple):
    """One unit's side of every walk an analysis asks about it.

    :ivar nfa: The NFA the unit is built in; each walk adds its follower.
    :ivar begin: The unit's first state.
    :ivar done: The unit's end.
    :ivar past: The unit's states, read in step with a shorter unit, as that
        one completes; ``None`` where the read passed :data:`PAIRS`.
    :ivar leads: The characters the unit can read first, at the cursor or
        from :attr:`past`.
    """

    nfa: Nfa
    begin: int
    done: int
    past: frozenset[int] | None
    leads: CharSet


def spelled(analysis: Any, unit: IrAtom) -> Spelled:
    """``unit``'s :class:`Spelled`, built once, kept with the analysis."""
    held = analysis.follows.spelled
    found = held.get(str(unit))
    if found is None:
        nfa = Nfa(analysis)
        begin = nfa.state()
        done = nfa.atom(unit, begin, frozenset())
        past = _past(nfa, begin, done)
        leads = CharSet.ANY if past is None else analysis.atom_first(unit)
        for state in past or ():
            for label, _target in nfa.closure(state)[0]:
                leads = leads.union(label)
        found = held[str(unit)] = Spelled(nfa, begin, done, past, leads)
    return cast(Spelled, found)


def _past(nfa: Nfa, begin: int, done: int) -> frozenset[int] | None:
    """The states a unit stands in, read in step with a shorter one, as the
    shorter completes."""
    found: set[int] = set()
    seen = {(begin, begin)}
    stack = [(begin, begin)]
    while stack:
        short, long = stack.pop()
        moves, complete = nfa.closure(short)
        if done in complete:
            found.add(long)
        if len(seen) > PAIRS:
            return None
        for a, p in moves:
            for b, q in nfa.closure(long)[0]:
                if a.overlaps(b) and (p, q) not in seen:
                    seen.add((p, q))
                    stack.append((p, q))
    return frozenset(found)


def spells_into(
    analysis: Any, unit: IrAtom, items: Sequence[IrItem], after: After | None
) -> bool:
    """Whether a complete ``unit`` at the cursor is a prefix of a string of
    ``items`` and what ``after`` spells (nothing where ``None``), or runs on
    past a shorter complete ``unit`` by a nonempty prefix of one.

    One walk, by character sets that meet, from the cursor (phase 1) and from
    each state the unit stands in as a shorter one completes (phase 2, which
    must read a character to become phase 3). Reaching the unit's end in
    phase 1 or 3 is the answer: every follower state reaches some string's
    end.
    """
    side = spelled(analysis, unit)
    if side.past is None:
        return True
    ahead = analysis.seq_first(items)
    if after is not None and all(analysis.item_nullable(item) for item in items):
        ahead = ahead.union(after.tail)
    if not analysis.atom_nullable(unit) and not side.leads.overlaps(ahead):
        return False
    start = _follower(side.nfa, items, after)
    return _walk(
        side, [(side.begin, start, 1), *((state, start, 2) for state in side.past)]
    )


def _follower(nfa: Nfa, items: Sequence[IrItem], after: After | None) -> int:
    """The follower's side, added to the unit's NFA for one walk; its first
    state."""
    nfa.memo["follow"], nfa.memo["mark"] = {}, len(nfa.moves)
    start = nfa.state()
    end = nfa.seq(items, start, frozenset())
    if after is not None and after.rule is not None:
        nfa.eps[end].append(nfa.follow(after.rule))
    elif after is not None:
        nfa.anything(nfa.step(end, after.tail))
    return start


def _walk(side: Spelled, walks: list[tuple[int, int, int]]) -> bool:
    """Whether the walk from ``walks`` reaches the unit's end from the cursor,
    or past a shorter unit by a character."""
    nfa = side.nfa
    seen = set(walks)
    while walks:
        here, there, phase = walks.pop()
        moves, held = nfa.closure(here)
        if phase != 2 and side.done in held:
            return True
        if len(seen) > PAIRS:
            return True
        moved = 3 if phase == 2 else phase
        for a, q in moves:
            for b, r in nfa.closure(there)[0]:
                if a.overlaps(b) and (q, r, moved) not in seen:
                    seen.add((q, r, moved))
                    walks.append((q, r, moved))
    return False
