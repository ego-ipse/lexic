"""Leads — where a character class's run can end, read off what follows it.

A greedy loop over a single-character class ``C`` meets the rest of the parse
at the end of its maximal ``C``-run, at some character ``t`` outside ``C``.
Whatever follows may begin with ``C`` characters before ``t``. The leftmost
take is the longest one a follower can complete, so if every follower needs
at least ``j`` of the run before ``t``, the loop must leave exactly ``j`` —
but only where leaving ``j`` is right whenever leaving more would be: the
prefixes followers accept before ``t`` must be closed under keeping their
last ``j`` characters, with the same text accepted after ``t``.

That closure is what the algebra tracks, as a :class:`Reach` kind per ending
character: every derivation reaching ``t`` does so at one exact ``j``
(:data:`FIXED`, or :data:`FULL` when it accepts every ``C``-string of that
length), or after exactly the ``C``-strings of length ``j`` or more
(:data:`FREE`). Anything else — ``t`` reached at two different ``j``, or after
a restricted prefix of varying length — is :data:`MIXED`, which is unknown:
no gate stops for it. Passages (how a construct is crossed on ``C`` alone)
carry the same kinds, because they are what shifts a later ``t``.

:class:`RunLeads` solves every rule's :class:`Ahead` for one class as a least
fixpoint; :func:`lead_windows` turns a lead into the take windows of a k-window
loop gate whose width is the grammar's own: one more than the largest closed
``j``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, Sequence

from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
    components,
    cyclic,
)
from lexic.parsing.pda.core.charsets import CharSet

__all__ = [
    "EOF_LEAD",
    "FIXED",
    "FREE",
    "FULL",
    "MIXED",
    "NO_LEAD",
    "NOTHING",
    "Ahead",
    "Lead",
    "Reach",
    "RunContext",
    "RunLeads",
    "closed",
    "compose",
    "lead_windows",
    "merge",
    "prepend",
]

FIXED, FULL, FREE, MIXED = 0, 1, 2, 3
"""Prefix-set kinds, in join order. FIXED: some strings, all of length ``j``.
FULL: every ``C``-string of length ``j``. FREE: every ``C``-string of length
``j`` or more. MIXED: none of these — unknown to a gate."""

_EOF: CharSet = CharSet.from_chars("")


class Reach(NamedTuple):
    """A prefix set's shortest length and :data:`FULL`/…/:data:`MIXED` kind."""

    j: int
    kind: int


_EMPTY = Reach(0, FULL)
"""The empty prefix — what crossing nothing costs."""


def _reach(j: int, kind: int) -> Reach:
    """A reach, normalised: the one prefix of length zero is every one."""
    return _EMPTY if not j and kind == FIXED else Reach(j, kind)


def _then(a: int, b: int) -> int:
    """The kind of a prefix of kind ``a`` followed by one of kind ``b``."""
    if MIXED in (a, b):
        return MIXED
    if FREE not in (a, b):
        return FULL if a == b == FULL else FIXED
    return FREE if FIXED not in (a, b) else MIXED


def _after(head: Reach, rest: Reach) -> Reach:
    """``head`` then ``rest``."""
    return _reach(head.j + rest.j, _then(head.kind, rest.kind))


def _either(a: Reach, b: Reach) -> Reach:
    """Two sets of prefixes before one ending character, from different
    derivations: closed only at one length — what follows ``t`` may differ."""
    if a.j != b.j:
        return Reach(min(a.j, b.j), MIXED)
    return Reach(a.j, max(a.kind, b.kind))


def _union(a: Reach | None, b: Reach | None) -> Reach | None:
    """Two passages followed by the same text: the union of their prefixes."""
    if a is None or b is None:
        return a if b is None else b
    if a.j == b.j:
        return Reach(a.j, max(a.kind, b.kind))
    low, high = (a, b) if a.j < b.j else (b, a)
    covers = low.kind == FREE and high.kind != MIXED
    return Reach(low.j, FREE if covers else MIXED)


class Lead(NamedTuple):
    """For each character ``t`` outside the run's class, the prefixes a
    follower can begin with before ``t``.

    :ivar marks: ``(characters, reach)`` pairs over disjoint character sets,
        never holding the EOF sentinel, which a negated set cannot carry.
    :ivar eof: The reach of the end of the input, or ``None``.
    """

    marks: tuple[tuple[CharSet, Reach], ...]
    eof: Reach | None


NO_LEAD = Lead((), None)
"""Nothing can follow."""

EOF_LEAD = Lead((), _EMPTY)
"""Only the end of the input follows — the start rule's own continuation."""


type RunContext = tuple[tuple[CharSet, Lead | None], ...]
"""What follows a rule's occurrence, per run class a loop below it reads at
its run's end — the part of a clone key a decided loop can see."""


class Ahead(NamedTuple):
    """What a construct leads with, and how it is crossed on class characters.

    :ivar lead: The construct's own :class:`Lead`.
    :ivar through: The prefixes a whole derivation of it spells on class
        characters alone, or ``None`` when every one holds another character.
    """

    lead: Lead
    through: Reach | None


NOTHING = Ahead(NO_LEAD, _EMPTY)
"""The empty sequence: leads with nothing, and is crossed for free."""


def _key(mark: tuple[CharSet, Reach]) -> tuple[int, int, bool, tuple[str, ...]]:
    """A deterministic order over marks."""
    chars, reach = mark
    return reach.j, reach.kind, chars.negated, tuple(sorted(chars.chars))


def _normal(marks: list[tuple[CharSet, Reach]]) -> tuple[tuple[CharSet, Reach], ...]:
    """One mark per reach, in a deterministic order."""
    if len(marks) < 2:
        return tuple(marks)
    by: dict[Reach, CharSet] = {}
    for chars, reach in marks:
        by[reach] = by[reach].union(chars) if reach in by else chars
    return tuple(sorted(((chars, reach) for reach, chars in by.items()), key=_key))


def merge(a: Lead, b: Lead) -> Lead:
    """Two leads of different derivations, character by character."""
    if b == NO_LEAD:
        return a
    if a == NO_LEAD:
        return b
    out = list(a.marks)
    for chars, reach in b.marks:
        out, chars = _fold_in(out, chars, reach)
        if not chars.is_empty():
            out.append((chars, reach))
    eof = a.eof if b.eof is None else b.eof if a.eof is None else _either(a.eof, b.eof)
    return Lead(_normal(out), eof)


def _fold_in(
    marks: list[tuple[CharSet, Reach]], chars: CharSet, reach: Reach
) -> tuple[list[tuple[CharSet, Reach]], CharSet]:
    """Split ``marks`` against one more mark; return them and what is left of it."""
    out: list[tuple[CharSet, Reach]] = []
    for held, was in marks:
        both = held.subtract(held.subtract(chars))
        if both.is_empty():
            out.append((held, was))
            continue
        only = held.subtract(chars)
        if not only.is_empty():
            out.append((only, was))
        out.append((both, _either(was, reach)))
        chars = chars.subtract(held)
    return out, chars


def shifted(lead: Lead, by: Reach) -> Lead:
    """``lead`` behind a passage ``by``."""
    if by == _EMPTY or lead == NO_LEAD:
        return lead
    marks = [(chars, _after(by, reach)) for chars, reach in lead.marks]
    eof = None if lead.eof is None else _after(by, lead.eof)
    return Lead(_normal(marks), eof)


def prepend(head: Ahead, rest: Ahead) -> Ahead:
    """``head`` followed by ``rest``."""
    if head.through is None:
        return head
    through = None if rest.through is None else _after(head.through, rest.through)
    return Ahead(merge(head.lead, shifted(rest.lead, head.through)), through)


def compose(ahead: Ahead, after: Lead | None) -> Lead | None:
    """What leads a position whose remaining arm is ``ahead`` and whose arm is
    followed by ``after`` — ``None`` where that is unknown and matters."""
    if ahead.through is None:
        return ahead.lead
    if after is None:
        return None
    return merge(ahead.lead, shifted(after, ahead.through))


def closed(lead: Lead) -> bool:
    """Whether every ending character's prefixes are closed — no MIXED."""
    reaches = [reach for _, reach in lead.marks]
    if lead.eof is not None:
        reaches.append(lead.eof)
    return all(reach.kind != MIXED for reach in reaches)


def _repeated(atom: Reach | None, lo: int, hi: int | None) -> Reach | None:
    """The passage of ``lo`` to ``hi`` copies of one whose passage is ``atom``."""
    if atom is None:
        return _EMPTY if not lo else None
    if hi == lo:
        return _reach(lo * atom.j, atom.kind) if lo else _EMPTY
    if not atom.j:
        return _EMPTY if atom.kind in (FULL, FIXED) else atom
    unit = atom.j == 1 and atom.kind in (FULL, FREE)
    if (unit and hi is None) or (atom.kind == FREE and lo):
        return Reach(lo * atom.j, FREE)
    return Reach(lo * atom.j, MIXED)


def _ah_literal(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> Ahead:
    """A literal leads with its first character outside the class."""
    solver = _solver(d)
    run = solver.run
    text = str(n)
    for j, char in enumerate(text):
        if not run.has(char):
            if not solver.marks:
                return Ahead(NO_LEAD, None)
            return Ahead(
                Lead(((CharSet.from_chars(char), _reach(j, FIXED)),), None), None
            )
    every = run == CharSet.from_chars(*set(text)) if text else True
    return Ahead(NO_LEAD, _reach(len(text), FULL if every else FIXED))


def _ah_charclass(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> Ahead:
    """A character class leads with its members outside the class."""
    assert isinstance(n, IrCharClass)
    return _solver(d).single(CharSet.from_charclass(n))


def _ah_not(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> Ahead:
    """A negated class leads like the complement it matches."""
    assert isinstance(n, IrNot)
    inner = n[0]
    chars = CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
    return _solver(d).single(chars)


def _ah_ruleref(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> Ahead:
    """A reference leads like the rule it names, as the fixpoint stands."""
    return _solver(d).rule(str(n))


def _ah_alternation(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> Ahead:
    """A group leads like all of its arms."""
    assert isinstance(n, IrAlternation)
    return _solver(d).group(n)


_AHEAD_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_ah_literal)),
    IrAction(IrCharClass, IrLambda(_ah_charclass)),
    IrAction(IrNot, IrLambda(_ah_not)),
    IrAction(IrRuleRef, IrLambda(_ah_ruleref)),
    IrAction(IrAlternation, IrLambda(_ah_alternation)),
)
"""Open atom-type dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


def _solver(d: IrSelf) -> RunLeads:
    """The dispatching :class:`RunLeads` off the ``d`` slot."""
    assert isinstance(d, RunLeads)
    return d


def joined(a: Ahead, b: Ahead) -> Ahead:
    """Two constructs' derivations taken together."""
    return Ahead(merge(a.lead, b.lead), _union(a.through, b.through))


class _Memo(NamedTuple):
    """What a solver keeps between questions.

    :ivar found: Rule name → its :class:`Ahead`, solved or being solved.
    :ivar groups: ``id(group)`` → its :class:`Ahead`, kept outside a solve.
    :ivar rests: ``(id(arm), position, again)`` → the arm, held so its identity
        stays its own, and what follows that item up to the arm's end.
    :ivar items: ``id(item)`` → its :class:`Ahead`, kept outside a solve — or
        inside one, for an item whose value read no rule.
    """

    found: dict[str, Ahead]
    groups: dict[int, Ahead]
    rests: dict[tuple[int, int, bool], tuple[Sequence[IrItem], Ahead]]
    items: dict[int, Ahead]


class RunLeads(IrLeaf[IrSelf, IrSelf]):
    """The :class:`Ahead` of each rule asked about, for one run class.

    Solved on demand: the first question about a rule solves it and every rule
    it reaches that is not yet solved, as one least fixpoint over just those —
    a loop's followers are asked about, the rest of the grammar never is. Each
    round recomputes them from their arms and joins into what they had: a join
    only lowers a ``j`` or raises a kind, both bounded, so the rounds stop, and
    every value joined describes derivations that exist.

    :ivar rules: The rule table.
    :ivar callees: Rule → the rules its body references.
    :ivar run: The run's class.
    :ivar memo: What is kept between questions (:class:`_Memo`).
    :ivar reads: How many rule values have been read — what tells an item
        that read none.
    :ivar solving: Whether a fixpoint is in progress — then nothing is kept.
    :ivar marks: Whether leads are solved at all, or passages alone — the
        cheap question a chain is asked first.
    """

    __slots__ = (
        "rules",
        "callees",
        "run",
        "memo",
        "reads",
        "solving",
        "marks",
    )

    rules: dict[str, IrRule]
    callees: Mapping[str, tuple[str, ...]]
    run: CharSet
    memo: _Memo
    reads: int
    solving: bool
    marks: bool

    def __init__(
        self,
        rules: dict[str, IrRule],
        callees: Mapping[str, tuple[str, ...]],
        run: CharSet,
        marks: bool = True,
    ) -> None:
        """Prepare to solve leads — or, without ``marks``, passages alone —
        for the run class ``run`` over ``rules``."""
        self.rules = rules
        self.callees = callees
        self.run = run
        self.memo = _Memo({}, {}, {}, {})
        self.reads = 0
        self.solving = False
        self.marks = marks

    def _solve(self, root: str) -> None:
        """Solve ``root`` and every unsolved rule it reaches, one strongly
        connected component at a time, callees first: a rule on no cycle is
        computed once, a cycle until it settles."""
        for component in components(self.callees, root, self.memo.found):
            for name in component:
                self.memo.found[name] = Ahead(NO_LEAD, None)
            self.solving = True
            changed = True
            while changed:
                changed = False
                for name in component:
                    got = self.memo.found[name]
                    for arm in self.rules[name].body:
                        got = joined(got, self.seq(arm))
                    if got != self.memo.found[name]:
                        self.memo.found[name] = got
                        changed = True
                changed = changed and cyclic(self.callees, component)
            self.solving = False

    def single(self, chars: CharSet) -> Ahead:
        """One character from ``chars``: those outside the class lead at once."""
        lead = NO_LEAD
        if self.marks:
            out = chars.subtract(self.run).subtract(_EOF)
            lead = Lead(((out, _EMPTY),), None) if not out.is_empty() else NO_LEAD
        if not chars.overlaps(self.run):
            return Ahead(lead, None)
        return Ahead(lead, Reach(1, FULL if self.run.within(chars) else FIXED))

    def rule(self, name: str) -> Ahead:
        """A rule's lead, solved on first asking; an undefined name is unknown."""
        if name not in self.rules:
            unknown = Reach(0, MIXED)
            return Ahead(
                Lead(((CharSet.ANY.subtract(self.run), unknown),), unknown), unknown
            )
        if name not in self.memo.found:
            self._solve(name)
        self.reads += 1
        return self.memo.found[name]

    def group(self, node: IrAlternation) -> Ahead:
        """An inline group's lead — kept once no fixpoint is in progress."""
        got = self.memo.groups.get(id(node))
        if got is not None:
            return got
        got = Ahead(NO_LEAD, None)
        for arm in node:
            got = joined(got, self.seq(arm))
        if not self.solving:
            self.memo.groups[id(node)] = got
        return got

    def item(self, item: IrItem) -> Ahead:
        """One item: what its atom leads with behind the copies before it, and
        its own passage — kept once no fixpoint is in progress."""
        got = self.memo.items.get(id(item))
        if got is not None:
            return got
        reads = self.reads
        got = self._item(item)
        if not self.solving or self.reads == reads:
            self.memo.items[id(item)] = got
        return got

    def _item(self, item: IrItem) -> Ahead:
        """:meth:`item`'s body."""
        atom = _AHEAD_ATOM.resolve(item.atom).eval(self, item.atom, ())
        assert isinstance(atom, Ahead)
        lo, hi = int(item.quantifier.lo), item.quantifier.upper()
        before = _repeated(atom.through, 0, None if hi is None else hi - 1)
        lead = atom.lead if before is None else shifted(atom.lead, before)
        return Ahead(lead, _repeated(atom.through, lo, hi))

    def seq(self, items: Sequence[IrItem]) -> Ahead:
        """A sequence: each item leads behind the passages of those before it.
        Nothing past the first item no derivation crosses on class characters
        alone can lead, so the walk stops there."""
        heads: list[Ahead] = []
        for item in items:
            heads.append(self.item(item))
            if heads[-1].through is None:
                break
        out = NOTHING
        for head in reversed(heads):
            out = prepend(head, out)
        return out

    def again(self, item: IrItem) -> Ahead:
        """An item's further occurrences, as many as its count still allows —
        a transient item, so never through the identity memo."""
        return self._item(IrItem(item.atom, IrQuantifier(0, item.quantifier.hi)))

    def after(self, items: Sequence[IrItem], at: int, again: bool) -> Ahead:
        """What follows item ``at`` of an arm, up to the arm's end — with the
        item's own further occurrences first when ``again``."""
        key = (id(items), at, again)
        held = self.memo.rests.get(key)
        if held is not None:
            return held[1]
        got = self.seq(items[at + 1 :])
        if again:
            got = prepend(self.again(items[at]), got)
        self.memo.rests[key] = (items, got)
        return got


def lead_windows(
    run: CharSet, lead: Lead | None
) -> tuple[tuple[CharSet, ...], ...] | None:
    """The take windows of the loop gate a run reads at its end, or ``None``
    where no closed ending character needs any of the run — then it runs to
    its end.

    At a position ``r`` characters before the run ends at ``t``, the loop takes
    another character unless ``t``'s prefixes are closed at exactly ``r``: past
    the largest such ``j`` the run is always taken. An unknown lead, and an
    ending character whose prefixes are MIXED, are never stopped for — the
    loop runs to its end there, as it did before any lead was read.
    """
    if lead is None:
        return None
    deep = [
        (chars, reach.j)
        for chars, reach in lead.marks
        if reach.j and reach.kind != MIXED
    ]
    eof = (
        lead.eof.j
        if lead.eof is not None and lead.eof.j and lead.eof.kind != MIXED
        else None
    )
    if not deep and eof is None:
        return None
    top = max([j for _, j in deep] + ([eof] if eof is not None else []))
    windows: list[tuple[CharSet, ...]] = [(run,) * (top + 1)]
    for r in range(1, top + 1):
        stop = CharSet.EMPTY
        for chars, j in deep:
            if j == r:
                stop = stop.union(chars)
        ends = CharSet.ANY.subtract(run).subtract(stop)
        if not ends.is_empty():
            windows.append((run,) * r + (ends,))
        if eof != r:
            windows.append((run,) * r + (_EOF,))
    return tuple(windows)
