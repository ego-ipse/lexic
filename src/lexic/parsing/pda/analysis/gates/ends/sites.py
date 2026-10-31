"""Run sites — every context a run's end is read in, and whether it decides.

A loop over one character class is cloned once per continuation its rule is
referenced under, so the lead it reads at its end (:mod:`.leads`) is the lead
of what follows THAT occurrence: the rest of its arm, then whatever follows
the rule there, up the reference chain for as long as the chain can be passed
through on class characters alone. :class:`RunSites` collects those chains
for one class over the whole grammar and solves the contexts each rule is
reached in.

A context is known only up to the start rule's end; an island interior's
analysis withholds even that, since its window does not end the document.
A rule whose contexts keep multiplying — a recursion that consumes class
characters after itself, so every level needs one more — is refused past
:data:`CONTEXT_CAP`, with a note, and its loops keep the decision they had.
"""

from __future__ import annotations

from typing import Any, Sequence

from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
    callees,
)
from lexic.parsing.earley.kernel.tables.decider import STOP_SET
from lexic.parsing.pda.analysis.gates.ends.leads import (
    EOF_LEAD,
    MIXED,
    NOTHING,
    Ahead,
    Lead,
    Reach,
    RunLeads,
    closed,
    compose,
    lead_windows,
    prepend,
)
from lexic.parsing.pda.core.charsets import CharSet

__all__ = ["CONTEXT_CAP", "RunIndex", "RunSites", "run_decides", "run_sites"]

CONTEXT_CAP = 256
"""The most distinct contexts one rule may be solved in before the class is
refused. A refusal, not a depth: under it every context is exact."""


type Frame = tuple[Sequence[IrItem], int, bool]
"""One step down to a place: an arm, the item's index in it, and whether what
follows the item there starts with the item's own further occurrences."""


class _Place(IrLeaf[IrSelf, IrSelf]):
    """Where a reference or a loop stands: its rule, and the arms down to it."""

    __slots__ = ("rule", "frames")

    rule: str
    frames: tuple[Frame, ...]

    def __init__(self, rule: str, frames: tuple[Frame, ...]) -> None:
        self.rule = rule
        self.frames = frames


class _Walk(IrLeaf[IrSelf, IrSelf]):
    """Where one arm walk stands, riding ``nc``: its rule, the item, and the
    frames down to the arm it is in."""

    __slots__ = ("rule", "item", "frames", "at")

    rule: str
    item: IrItem
    frames: tuple[Frame, ...]
    at: tuple[Sequence[IrItem], int]

    def __init__(
        self,
        rule: str,
        item: IrItem,
        frames: tuple[Frame, ...],
        at: tuple[Sequence[IrItem], int],
    ) -> None:
        self.rule = rule
        self.item = item
        self.frames = frames
        self.at = at

    def place(self, again: bool) -> _Place:
        """This item's place, what follows it starting with its own further
        occurrences when ``again``."""
        return _Place(self.rule, (*self.frames, (*self.at, again)))


def _site_ref(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """A reference is a site of the rule it names."""
    walk = nc[0]
    assert isinstance(walk, _Walk)
    place = walk.place(walk.item.quantifier.repeats())
    _sites(d).sites.setdefault(str(n), []).append(place)


def _site_group(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """A group's arms end where the group does."""
    walk = nc[0]
    assert isinstance(walk, _Walk) and isinstance(n, IrAlternation)
    frames = walk.place(walk.item.quantifier.repeats()).frames
    for arm in n:
        _sites(d).walk(walk.rule, arm, frames)


def _site_charclass(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """A loop over the run's class reads what follows it, itself excluded."""
    assert isinstance(n, IrCharClass)
    _sites(d).loop(nc[0], CharSet.from_charclass(n))


def _site_not(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """A loop over a negated class is a loop over its complement."""
    assert isinstance(n, IrNot)
    inner = n[0]
    chars = CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
    _sites(d).loop(nc[0], chars)


def _site_none(_d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf]) -> None:
    """A literal holds no site."""


_SITE_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrRuleRef, IrLambda(_site_ref)),
    IrAction(IrAlternation, IrLambda(_site_group)),
    IrAction(IrCharClass, IrLambda(_site_charclass)),
    IrAction(IrNot, IrLambda(_site_not)),
    IrAction(IrLiteral, IrLambda(_site_none)),
)
"""Open atom-type dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


def _sites(d: IrSelf) -> RunIndex:
    """The dispatching :class:`RunIndex` off the ``d`` slot."""
    assert isinstance(d, RunIndex)
    return d


class RunIndex(IrLeaf[IrSelf, IrSelf]):
    """Where every reference and every unbounded one-class loop of a grammar
    stands — one walk, shared by every run class asked about.

    :ivar rules: The rule table.
    :ivar start: The start rule's name.
    :ivar delegated: An island interior's analysis: its start rule's end is
        not the input's, so what follows it is unknown.
    :ivar sites: Rule name → each place a reference to it stands.
    :ivar loops: Run class → ``id(item)`` of each loop over it → its places.
    :ivar classes: Run class → its :class:`RunSites`, once asked for.
    :ivar callees: Rule → the rules its body references, for every solver.
    """

    __slots__ = ("rules", "start", "delegated", "sites", "loops", "classes", "callees")

    rules: dict[str, IrRule]
    start: str
    delegated: bool
    sites: dict[str, list[_Place]]
    loops: dict[CharSet, dict[int, list[_Place]]]
    classes: dict[CharSet, RunSites]
    callees: dict[str, tuple[str, ...]]

    def __init__(self, rules: dict[str, IrRule], start: str, delegated: bool) -> None:
        """Walk every arm once."""
        self.rules = rules
        self.start = start
        self.delegated = delegated
        self.sites = {}
        self.loops = {}
        self.classes = {}
        for name, rule in rules.items():
            for arm in rule.body:
                self.walk(name, arm, ())
        self.callees = callees(rules)

    def walk(
        self, rule: str, items: Sequence[IrItem], frames: tuple[Frame, ...]
    ) -> None:
        """File every site and loop of one arm, reached down ``frames``."""
        for at, item in enumerate(items):
            walk = _Walk(rule, item, frames, (items, at))
            _SITE_ATOM.resolve(item.atom).eval(self, item.atom, (walk,))

    def loop(self, walk: IrSelf, chars: CharSet) -> None:
        """File an unbounded loop under its class."""
        assert isinstance(walk, _Walk)
        if walk.item.quantifier.upper() is None:
            places = self.loops.setdefault(chars, {}).setdefault(id(walk.item), [])
            places.append(walk.place(False))

    def of(self, run: CharSet) -> RunSites:
        """The run sites of class ``run``, made once."""
        found = self.classes.get(run)
        if found is None:
            found = self.classes[run] = RunSites(self, run)
        return found


class _Down(IrLeaf[IrSelf, IrSelf]):
    """One solver, and what it found to follow each place it was asked about.

    :ivar solver: The :class:`~.leads.RunLeads` asked.
    :ivar found: ``id(place)`` → what follows it up to its rule's end.
    """

    __slots__ = ("solver", "found")

    solver: RunLeads
    found: dict[int, Ahead]

    def __init__(self, solver: RunLeads) -> None:
        self.solver = solver
        self.found = {}

    def at(self, place: _Place) -> Ahead:
        """What follows ``place`` up to its rule's end, solved once."""
        got = self.found.get(id(place))
        if got is None:
            got = NOTHING
            for items, at, again in place.frames:
                got = prepend(self.solver.after(items, at, again), got)
            self.found[id(place)] = got
        return got


class RunSites(IrLeaf[IrSelf, IrSelf]):
    """One class's run sites, and the contexts they are read in.

    What follows a place is solved when a loop's chain asks for it — its
    passage first, which alone can say a context is unknown, and its lead only
    past that — so the leads of rules no loop of the class can see past are
    never computed.

    :ivar index: The grammar's :class:`RunIndex`.
    :ivar leads: The class's leads, and what follows each place asked about.
    :ivar passages: The same, solving passages alone.
    :ivar loops: ``id(item)`` of each loop over the class → each place it
        stands.
    :ivar contexts: Rule name → the leads it is reached in, for the rules
        whose context a loop below them can see (``None`` is unknown) — or
        ``None`` until a loop asks.
    :ivar refused: Whether some rule passed :data:`CONTEXT_CAP`.
    """

    __slots__ = (
        "index",
        "leads",
        "passages",
        "loops",
        "contexts",
        "refused",
    )

    index: RunIndex
    leads: _Down
    passages: _Down
    loops: dict[int, list[_Place]]
    contexts: dict[str, set[Lead | None]] | None
    refused: bool

    def __init__(self, index: RunIndex, run: CharSet) -> None:
        """Take class ``run``'s loops off ``index``."""
        self.index = index
        self.leads = _Down(RunLeads(index.rules, index.callees, run))
        self.passages = _Down(RunLeads(index.rules, index.callees, run, marks=False))
        self.loops = index.loops.get(run, {})
        self.contexts = None
        self.refused = False

    @property
    def run(self) -> CharSet:
        """The run's class."""
        return self.leads.solver.run

    def rest(self, place: _Place) -> Ahead:
        """What follows ``place`` up to its rule's end."""
        return self.leads.at(place)

    def through(self, place: _Place) -> Reach | None:
        """How what follows ``place`` up to its rule's end is crossed on class
        characters, solved without any lead."""
        return self.passages.at(place).through

    def needs(self, loops: dict[int, list[_Place]], full: bool = False) -> set[str]:
        """The rules whose context one of ``loops`` can see: those holding one
        that passes to the rule's end, and their referrers that pass on —
        read off the full leads under ``full``, which are about to be needed,
        else off passages alone."""
        found = {
            place.rule
            for places in loops.values()
            for place in places
            if self._crosses(place, full)
        }
        pending = list(found)
        while pending:
            for place in self.index.sites.get(pending.pop(), ()):
                if place.rule not in found and self._crosses(place, full):
                    found.add(place.rule)
                    pending.append(place.rule)
        return found

    def _crosses(self, place: _Place, full: bool) -> bool:
        """Whether what follows ``place`` can be crossed on class characters."""
        if full:
            return self.rest(place).through is not None
        return self.through(place) is not None

    def _unknown_on_chain(self, key: int) -> bool:
        """Whether some passage between loop ``key`` and a context it reads is
        MIXED — then every lead that context brings is MIXED behind it."""
        loops = {key: self.loops.get(key, [])}
        places = [place for places in loops.values() for place in places]
        places += [
            place
            for rule in self.needs(loops)
            for place in self.index.sites.get(rule, ())
        ]
        for place in places:
            through = self.through(place)
            if through is not None and through.kind == MIXED:
                return True
        return False

    def _solved(self) -> dict[str, set[Lead | None]]:
        """Every context each rule a loop can see is reached in, solved once."""
        if self.contexts is None:
            self.contexts = {}
            self._solve(self.needs(self.loops, full=True))
        return self.contexts

    def _solve(self, needed: set[str]) -> None:
        """Every context each needed rule is reached in, worked to a fixpoint."""
        contexts = self.contexts
        assert contexts is not None
        contexts.update({name: set() for name in needed})
        if self.index.start in needed:
            seed = None if self.index.delegated else EOF_LEAD
            contexts[self.index.start].add(seed)
        users: dict[str, list[tuple[str, Ahead]]] = {}
        for target in sorted(needed):
            for place in self.index.sites.get(target, ()):
                here = self.rest(place)
                if here.through is None:
                    contexts[target].add(here.lead)
                elif place.rule in needed:
                    users.setdefault(place.rule, []).append((target, here))
        queue = sorted(needed)
        while queue:
            rule = queue.pop()
            for target, here in users.get(rule, ()):
                for after in list(contexts[rule]):
                    lead = compose(here, after)
                    if lead in contexts[target]:
                        continue
                    contexts[target].add(lead)
                    if len(contexts[target]) > CONTEXT_CAP:
                        self.refused = True
                        return
                    queue.append(target)

    def loop_contexts(self, key: int) -> set[Lead | None]:
        """Every lead loop ``key`` reads at its run's end."""
        out: set[Lead | None] = set()
        for place in self.loops.get(key, ()):
            rest = self.rest(place)
            if rest.through is None:
                out.add(rest.lead)
                continue
            contexts = self._solved().get(place.rule, ())
            out.update(compose(rest, after) for after in contexts)
        return out

    def decides(self, key: int, known: bool) -> bool:
        """Whether loop ``key``'s run end is read somewhere a follower needs
        part of the run — and, under ``known``, nowhere any of it is unknown:
        no context unknown, and no ending character's prefixes MIXED."""
        if known and self._unknown_on_chain(key):
            return False
        leads = self.loop_contexts(key)
        if self.refused:
            return False
        if known and any(lead is None or not closed(lead) for lead in leads):
            return False
        return any(lead_windows(self.run, lead) is not None for lead in leads)


def run_sites(analysis: Any, run: CharSet) -> RunSites:
    """``analysis``'s run sites of class ``run`` — its grammar walked once."""
    runs = analysis.follows.runs
    if not runs:
        delegated = analysis.taxonomy.delegated
        runs.append(RunIndex(analysis.rules, analysis.start, delegated))
    return runs[0].of(run)


def run_decides(
    analysis: Any, at: tuple[Sequence[IrItem], int], scope: Any, notes: Any, known: bool
) -> bool:
    """Settle item ``k``'s loop where its run ends, if some follower needs part
    of the run; under ``known`` (its route was otherwise an island), only where
    no context of it is unknown. A loop whose arm still needs text after it
    keeps its route, and nothing past the run starting in its class skips the
    walk.

    :param analysis: The grammar-analysis oracle (``Any``-typed leaf argument).
    :param at: The loop's arm, and its index there.
    :param scope: The conflict-walk scope.
    :param notes: The rule's note accumulators.
    """
    items, k = at
    if not all(analysis.item_nullable(item) for item in items[k + 1 :]):
        return False
    run = analysis.atom_first(items[k].atom)
    if not run.overlaps(analysis.cont_at(items, k, scope.tail)):
        return False
    sites = run_sites(analysis, run)
    decided = sites.decides(id(items[k]), known)
    if sites.refused:
        notes.soft.append(f"{scope.rule}[{k}]: run contexts past {CONTEXT_CAP}")
    if not decided:
        return False
    analysis.taxonomy.loops.run[id(items[k])] = run
    notes.picks_extent(f"{scope.rule}[{k}]: loop stop-set applied (run end)", STOP_SET)
    return True
