"""A text arm matched by its language — where matching item by item is not exact.

The PDA matches a text-only arm one item at a time, and a quantified item takes
as much as its gate lets it. That is exact only where an item can never take a
character its successor needs. Where it can — ``[a]* [a;]`` on ``a``, or
``";"? [a;]`` on ``;`` — the item takes it, the successor fails, and the arm
"does not derive" text that is in its language.

Such an arm is MARKED at compile time (:func:`needs_language`), and its attempt
entry matches through a :class:`ForcedEnd`: the arm's automaton
(:func:`language_of`), and the one end the rule's continuation lets the rest
start at. A marked arm never falls back to the item-wise matcher: one whose
automaton cannot be built bails instead. Every other arm keeps the item-wise
matcher untouched.

The test is conservative in one direction only. An arm wrongly marked costs a
scan; an arm wrongly left unmarked is the fault this module exists to remove.
Wherever a FIRST cannot be bounded, the answer is "every character", which
marks; wherever the automaton meets something it does not model, it refuses.
"""

from __future__ import annotations

import sys
from contextvars import ContextVar, Token
from types import TracebackType
from typing import NamedTuple

from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone, clone_arms
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    GATE_KWIN,
    GATE_STOP,
    OP_AVDISP,
    OP_AVSTR,
    OP_CC,
    OP_CC1,
    OP_GRP,
    OP_LEAF1,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_V1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
)
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.errors import ProbeFork

__all__ = [
    "ForcedEnd",
    "Language",
    "ScanTally",
    "language_of",
    "needs_language",
    "reads_language",
]

RESCAN_BUDGET = 4
"""How many document lengths of re-read characters one parse's scans may spend."""

STATE_CAP = 4096
"""Most states one arm's automaton may have.

A bound on compile-time work and on the per-character step, not on
correctness: a marked arm too large for it has no automaton, and bails.
"""

_TEXT_MODES = frozenset((BUILD_VALUE_STR, BUILD_TRANSPARENT, BUILD_DISPATCH))
"""Clone modes whose language is their text: a value, a group, a pass-through."""

_TERMINALS = frozenset((OP_LIT, OP_LIT1, OP_CC, OP_CC1))
_LITERALS = frozenset((OP_LIT, OP_LIT1))
_CLONE_REFS = frozenset(
    (OP_REF, OP_REF1, OP_GRP, OP_VSTR, OP_VRUN, OP_V1, OP_VDISP, OP_LEAF1)
    + (OP_AVSTR, OP_AVDISP)
)
"""Item op-codes whose payload is a clone the arm's language runs through."""


class NotRegular(Exception):
    """The arm reaches something its text language cannot be read from."""


Edge = tuple[frozenset[str], bool, int]
"""One transition: ``(chars, negated, target state)``."""


class Language(NamedTuple):
    """One arm's language as a position automaton, run in one pass.

    :ivar edges: Per state, its character transitions.
    :ivar closure: Per state, every state reachable from it on no character.
    :ivar start: The closure of the start state.
    :ivar accept: The accepting state.
    """

    edges: tuple[tuple[Edge, ...], ...]
    closure: tuple[frozenset[int], ...]
    start: frozenset[int]
    accept: int

    def scan(self, text: str, pos: int, upto: int) -> tuple[list[int], int]:
        """Every end the arm accepts at, from ``pos``, reading no further than
        ``upto``.

        :returns: The accepting ends, ascending, and where the scan stopped:
            the first position no live state could read past, or ``upto``
            with a state still live.
        """
        states = self.start
        ends: list[int] = []
        at = pos
        while True:
            if self.accept in states:
                ends.append(at)
            if at >= len(text) or at >= upto:
                return ends, at
            states = self._step(states, text[at])
            if not states:
                return ends, at
            at += 1

    def _step(self, states: frozenset[int], ch: str) -> frozenset[int]:
        """The states one character leads to."""
        nxt: set[int] = set()
        for state in states:
            for chars, negated, target in self.edges[state]:
                if (ch not in chars) if negated else (ch in chars):
                    nxt |= self.closure[target]
        return frozenset(nxt)


def _closure(eps: list[list[int]], state: int) -> frozenset[int]:
    """Every state reachable from ``state`` on empty moves."""
    seen = {state}
    work = [state]
    while work:
        for target in eps[work.pop()]:
            if target not in seen:
                seen.add(target)
                work.append(target)
    return frozenset(seen)


# ── the forced end: what a marked arm's matcher answers ──────────────────


class Reach(NamedTuple):
    """Where a marked arm's one viable reading ends.

    :ivar stop: The end position.
    """

    stop: int

    def end(self) -> int:
        """The end — the one question the consult path asks a match."""
        return self.stop


class ScanTally:
    """One parse's account of the characters its language scans re-read.

    Owned by the parse: the kernel opens it when a parse starts and closes it
    when it ends, and every scan in the parse — its sub-runs, probes and audits
    included — charges the one account. A scan reading again what an earlier
    scan already read pays for it, before it reads, and the parse bails once it
    has paid :data:`RESCAN_BUDGET` times its document's length. It holds counts
    and no text.

    :ivar reach: The furthest position any scan has read to.
    :ivar rescans: Characters scans have read again behind :attr:`reach`.
    :ivar limit: The most re-read characters the parse may spend.
    :ivar token: The account this one stands in front of while open.
    """

    __slots__ = ("reach", "rescans", "limit", "token")

    reach: int
    rescans: int
    limit: int
    token: Token[ScanTally | None] | None

    def __init__(self, length: int) -> None:
        self.reach = 0
        self.rescans = 0
        self.limit = RESCAN_BUDGET * max(length, 1)
        self.token = None

    def __enter__(self) -> ScanTally:
        """Open the account, unless a parse already owns one on this thread."""
        if _TALLY.get() is None:
            self.token = _TALLY.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        """Close the account this one opened."""
        if self.token is not None:
            _TALLY.reset(self.token)
            self.token = None

    def bound(self, pos: int) -> int:
        """How far a scan from ``pos`` may read: past the budget left behind
        :attr:`reach` it would re-read more than the parse may spend; where
        that budget covers everything up to the reach, it reads freely."""
        left = pos + self.limit - self.rescans
        return left if left < self.reach else sys.maxsize

    def charge(self, pos: int, stop: int) -> None:
        """Pay for a scan that read from ``pos`` to ``stop``."""
        self.rescans += max(0, min(stop, self.reach) - pos)
        self.reach = max(self.reach, stop)


_TALLY: ContextVar[ScanTally | None] = ContextVar("scan_tally", default=None)
"""The running parse's account, or ``None`` outside one."""


class ForcedEnd(NamedTuple):
    """A marked arm's whole-extent matcher: its language, and the one end the
    rule's continuation lets the rest start at.

    An end whose next character nothing that may follow this occurrence can
    start with — the rule's soft FOLLOW and the occurrence's own tail, a
    repetition's loopback included — is dead. Exactly one surviving end is the arm's only
    viable reading; none is a miss; more than one is a choice this matcher
    does not make, so the parse bails to the gated engine. So does an arm with
    no automaton: the item-wise matcher is the one it was marked to replace.

    :ivar lang: The arm's automaton, or ``None`` where it has none.
    :ivar follow: What may follow this occurrence.
    """

    lang: Language | None
    follow: CharSet

    def match(self, text: str, pos: int) -> Reach | None:
        """The arm's one viable end from ``pos``, or ``None`` where it has none.

        :raises ProbeFork: When two ends are viable, the arm has no automaton,
            no parse owns a scan account, or the account is spent — the gated
            engine answers each time.
        """
        tally = _TALLY.get()
        if self.lang is None or tally is None:
            raise ProbeFork(f"attempt at {pos}: this arm cannot be read here", pos)
        upto = tally.bound(pos)
        ends, stop = self.lang.scan(text, pos, upto)
        tally.charge(pos, stop)
        if stop >= upto:
            raise ProbeFork(f"language scan at {pos}: the rescan budget is spent", pos)
        viable = [end for end in ends if self._composes(text, end)]
        if len(viable) > 1:
            raise ProbeFork(
                f"attempt at {pos}: one arm ends at {viable[0]} or {viable[1]} "
                "and both could compose",
                pos,
            )
        return Reach(viable[0]) if viable else None

    def _composes(self, text: str, end: int) -> bool:
        """Whether something may follow the rule at ``end``."""
        return end >= len(text) or self.follow.has(text[end])


def reads_language(clone: FlatClone) -> bool:
    """Whether one of ``clone``'s attempt entries is read by its language."""
    if clone.attempt is None:
        return False
    for entry in clone.attempt[1]:
        runarm = entry[-1].runarm
        if runarm is not None and isinstance(runarm.payloads[0], ForcedEnd):
            return True
    return False


# ── building the automaton ────────────────────────────────────────────────


class _Builder:
    """Thompson construction over flat arms, one fragment per call.

    :ivar edges: Per state, its character transitions.
    :ivar eps: Per state, its empty moves.
    :ivar active: The clones on the current path — a repeat means recursion.
    """

    __slots__ = ("edges", "eps", "active")

    def __init__(self) -> None:
        self.edges: list[list[Edge]] = []
        self.eps: list[list[int]] = []
        self.active: set[int] = set()

    def state(self) -> int:
        """A fresh state.

        :raises NotRegular: Past :data:`STATE_CAP`.
        """
        if len(self.edges) >= STATE_CAP:
            raise NotRegular("too many states")
        self.edges.append([])
        self.eps.append([])
        return len(self.edges) - 1

    def char(self, chars: frozenset[str], negated: bool) -> tuple[int, int]:
        """One character of a class."""
        s, e = self.state(), self.state()
        self.edges[s].append((chars, negated, e))
        return s, e

    def literal(self, text: str) -> tuple[int, int]:
        """A literal's characters in order."""
        s = e = self.state()
        for ch in text:
            nxt = self.state()
            self.edges[e].append((frozenset((ch,)), False, nxt))
            e = nxt
        return s, e

    def arm(self, arm: FlatArm) -> tuple[int, int]:
        """An arm: its items in sequence."""
        s = e = self.state()
        for i in range(arm.n):
            fs, fe = self.item(arm, i)
            self.eps[e].append(fs)
            e = fe
        return s, e

    def item(self, arm: FlatArm, i: int) -> tuple[int, int]:
        """One quantified item: ``lo`` copies, then optional ones or a loop."""
        lo, hi = arm.los[i], arm.his[i]
        s = e = self.state()
        for _ in range(lo):
            fs, fe = self.atom(arm, i)
            self.eps[e].append(fs)
            e = fe
        if hi < 0:
            fs, fe = self.atom(arm, i)
            self.eps[e].append(fs)
            self.eps[fe].append(fs)
            self.eps[fe].append(e)
            return s, e
        end = self.state()
        self.eps[e].append(end)
        for _ in range(hi - lo):
            fs, fe = self.atom(arm, i)
            self.eps[e].append(fs)
            self.eps[fe].append(end)
            e = fe
        return s, end

    def atom(self, arm: FlatArm, i: int) -> tuple[int, int]:
        """One occurrence of item ``i``'s atom.

        :raises NotRegular: On an island, a fail-island or a consult.
        """
        kind, payload = arm.kinds[i], arm.payloads[i]
        if kind in _LITERALS:
            return self.literal(payload)
        if kind in _TERMINALS:
            return self.char(*payload)
        if kind in _CLONE_REFS:
            return self.clone(payload)
        raise NotRegular(f"op {kind} has no text language")

    def clone(self, clone: FlatClone) -> tuple[int, int]:
        """A clone: the alternation of its arms, or of a dispatch's targets.

        :raises NotRegular: On recursion, or a clone that builds a structure.
        """
        if id(clone) in self.active or clone.mode not in _TEXT_MODES:
            raise NotRegular(f"clone {clone.name!r} is not a text language")
        self.active.add(id(clone))
        s, e = self.state(), self.state()
        for fs, fe in self._branches(clone):
            self.eps[s].append(fs)
            self.eps[fe].append(e)
        self.active.discard(id(clone))
        return s, e

    def _branches(self, clone: FlatClone) -> list[tuple[int, int]]:
        """The fragments a clone alternates between."""
        if clone.mode != BUILD_DISPATCH:
            return [self.arm(arm) for arm in clone_arms(clone)]
        targets, empty = dispatch_targets(clone)
        branches = [self.clone(target) for target in targets]
        if empty:
            s = self.state()
            branches.append((s, s))
        return branches


def dispatch_targets(clone: FlatClone) -> tuple[list[FlatClone], bool]:
    """A dispatch clone's targets — through a wide selection as through lead
    characters — and whether its default is the empty arm.

    :raises NotRegular: On a target that is not a clone.
    """
    wide = clone.wide_selectors
    if wide is not None:
        targets = list(wide.arms)
    else:
        targets = [target for _chars, _negated, target in clone.selectors]
    default = clone.default
    empty = default is DISPATCH_EMPTY
    if default is not None and not empty:
        targets.append(default)
    if not all(isinstance(target, FlatClone) for target in targets):
        raise NotRegular(f"dispatch {clone.name!r} holds a target that is not a clone")
    return targets, empty


def language_of(arm: FlatArm) -> Language | None:
    """The arm's automaton, or ``None`` where it has no text language here."""
    builder = _Builder()
    try:
        builder.state()  # state 0 is the start
        fs, fe = builder.arm(arm)
    except NotRegular:
        return None
    builder.eps[0].append(fs)
    edges = tuple(tuple(out) for out in builder.edges)
    closure = tuple(_closure(builder.eps, s) for s in range(len(edges)))
    return Language(edges, closure, closure[0], fe)


# ── which arms need it ────────────────────────────────────────────────────


class Lead(NamedTuple):
    """What a fragment can start with, and whether it can be empty.

    :ivar first: Its first characters.
    :ivar nullable: Whether it derives the empty string.
    """

    first: CharSet
    nullable: bool


_EVERY = Lead(CharSet.ANY, True)
"""The answer where a fragment cannot be bounded — it marks."""


def needs_language(arm: FlatArm) -> bool:
    """Whether matching ``arm`` item by item can miss text in its language.

    A quantified item takes while its gate admits the next character. An
    attempt gate bails only where its stored continuation admits it, and the
    analysis fills that only when the rest of the arm can be empty; a stop
    gate takes on its own set. So where the rest cannot be empty and the loop
    can go on with a character the rest starts with, the item steals it.
    Asked at every depth: an item inside a referenced text clone, against the
    rest of its own arm.
    """
    return _arm_steals(arm, set())


def _arm_steals(arm: FlatArm, active: set[int]) -> bool:
    """Whether some item of ``arm``, or of a clone under it, steals."""
    for i in range(arm.n):
        if _item_steals(arm, i) or _inner_steals(arm, i, active):
            return True
    return False


def _item_steals(arm: FlatArm, i: int) -> bool:
    """Whether item ``i``'s loop can take a character the rest of the arm needs.

    A fixed count decides nothing. A ``k``-window gate is never marked: the
    analysis grants one only where the loop's take windows and its exit
    windows separate at ``k`` — and the exit side is FIRST\\ :sub:`k` of the
    arm's own rest, FOLLOW-extended
    (:func:`~lexic.parsing.pda.analysis.gates.kwindow.loop_gate`), or the
    ``k``-deep FOLLOW where the loop ends the arm
    (:func:`~lexic.parsing.pda.analysis.gates.kwindow.follow_loop_gate`) — so
    it takes nowhere the rest could start. Every
    other loop takes while its admission set holds the next character, so it
    steals where that set meets the FIRST of a rest that cannot be empty.
    """
    if arm.los[i] == arm.his[i] or arm.gate_kinds[i] == GATE_KWIN:
        return False
    rest = _seq_lead(arm, i + 1)
    return not rest.nullable and _takes(arm, i).overlaps(rest.first)


def _takes(arm: FlatArm, i: int) -> CharSet:
    """The characters item ``i``'s loop goes on at: a stop gate's own set, else
    its atom's FIRST."""
    if arm.gate_kinds[i] == GATE_STOP:
        chars, negated = arm.gate_data[i]
        return CharSet(chars, negated)
    return _atom_lead(arm, i).first


def _inner_steals(arm: FlatArm, i: int, active: set[int]) -> bool:
    """Whether a clone item ``i`` reaches holds a stealing item. A clone whose
    structure is not modelled here is assumed to."""
    if arm.kinds[i] not in _CLONE_REFS:
        return False
    clone = arm.payloads[i]
    if id(clone) in active:
        return False
    try:
        subs = _clone_arms(clone)
    except NotRegular:
        return True
    active.add(id(clone))
    found = any(_arm_steals(sub, active) for sub in subs)
    active.discard(id(clone))
    return found


def _clone_arms(clone: FlatClone) -> list[FlatArm]:
    """A clone's arms, through a dispatch's targets (an empty default has
    none; :func:`_clone_lead` reads it as nullability)."""
    if clone.mode != BUILD_DISPATCH:
        return clone_arms(clone)
    targets, _empty = dispatch_targets(clone)
    return [arm for target in targets for arm in _clone_arms(target)]


def _seq_lead(arm: FlatArm, start: int) -> Lead:
    """FIRST and nullability of ``arm``'s items from ``start`` on."""
    first = CharSet.EMPTY
    for i in range(start, arm.n):
        lead = _atom_lead(arm, i)
        first = first.union(lead.first)
        if not (lead.nullable or arm.los[i] == 0):
            return Lead(first, False)
    return Lead(first, True)


def _atom_lead(arm: FlatArm, i: int) -> Lead:
    """FIRST and nullability of item ``i``'s atom (not its quantifier)."""
    kind, payload = arm.kinds[i], arm.payloads[i]
    if kind in _LITERALS:
        return Lead(CharSet.from_chars(payload[:1]), payload == "")
    if kind in _TERMINALS:
        return Lead(CharSet(payload[0], payload[1]), False)
    if kind in _CLONE_REFS:
        return _clone_lead(payload, set())
    return _EVERY


def _clone_lead(clone: FlatClone, active: set[int]) -> Lead:
    """FIRST and nullability of a clone: the union over its arms. A clone
    whose structure is not modelled here reads as every character."""
    if id(clone) in active:
        return _EVERY
    try:
        arms = _clone_arms(clone)
        empty = clone.mode == BUILD_DISPATCH and dispatch_targets(clone)[1]
    except NotRegular:
        return _EVERY
    active.add(id(clone))
    first, nullable = CharSet.EMPTY, empty
    for arm in arms:
        lead = _seq_lead(arm, 0)
        first, nullable = first.union(lead.first), nullable or lead.nullable
    active.discard(id(clone))
    return Lead(first, nullable)
