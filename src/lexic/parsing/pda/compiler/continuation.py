"""What may follow an island REFERENCE, and whether that bounds the island.

Two questions the clone compiler asks once per island and carries on the
:class:`~lexic.parsing.pda.compiler.specs.IslandRef` it emits. Both are about
the island's *occurrence* — what the enclosing grammar puts after it — and
neither is answerable from the island rule's own FOLLOW, which is what made
them worth a module of their own rather than two more methods on a compiler
that already has enough.

The seam reads the first to decide whether a shorter completion could compose
with the caller (:mod:`lexic.parsing.pda.runtime.islands`), and the second to
decide whether one sub-parse at an exact width settles the island instead of a
doubling climb.
"""

from __future__ import annotations

import math
from typing import Iterator

from lexic.ir import IrAlternation, IrItem, IrNoneType, IrRule, IrRuleRef
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.windows import (
    END,
    MORE,
    FollowWindows,
    Pref,
    extend_follow,
)
from lexic.parsing.pda.analysis.predicates import (
    Span,
    rule_alphabets,
    rule_spans,
    seq_span,
)
from lexic.parsing.pda.compiler.specs import arm_items
from lexic.parsing.pda.core.charsets import CharSet


def _repeats(item: IrItem) -> bool:
    """Whether ``item`` can occur more than once in a row."""
    hi = item.quantifier.hi
    return isinstance(hi, IrNoneType) or int(hi) > 1


WINDOW = 2
"""How deep :meth:`IslandContinuations.windows` reads a continuation. Two is
measured to settle a shorter end a space or newline ends (abnf-meta's rule
continuation, ` /`) that one character cannot."""


Groups = tuple[tuple[list[IrItem], int], ...]
"""The inline groups a reference sits in, outermost first: each enclosing arm's
items and the group item's index in it."""

Site = tuple[str, list[IrItem], int, Groups]
"""A reference to an island: its rule, its arm's items, its index, its groups."""


class IslandContinuations:
    """One grammar's island continuations, derived once and memoised.

    :ivar analysis: The grammar analysis the sets are derived from.
    :ivar islands: The island rule names — the rules whose own arms are never
        reference sites, because an island is never cloned.
    """

    __slots__ = (
        "analysis",
        "islands",
        "_follows",
        "_alphabets",
        "_windows",
        "_deep",
        "_where",
    )

    analysis: GrammarAnalysis
    islands: frozenset[str]
    _follows: dict[tuple[str, int], CharSet]
    _alphabets: dict[str, CharSet] | None
    _windows: dict[tuple[str, int], tuple[Pref, ...]]
    _deep: FollowWindows | None
    _where: dict[int, Span] | None

    def __init__(self, analysis: GrammarAnalysis, islands: frozenset[str]) -> None:
        """Bind the analysis and island set; derive nothing until asked."""
        self.analysis = analysis
        self.islands = islands
        self._follows = {}
        self._alphabets = None
        self._windows = {}
        self._deep = None
        self._where = None

    def follow(self, name: str, site: IrItem | None = None) -> CharSet:
        """What may follow island ``name`` where it is REFERENCED, unioned.

        The seam's two-ends evidence. It is deliberately not the island rule's
        own FOLLOW, and deliberately not one site's continuation either.

        *Not the rule's FOLLOW*, because the fixpoint walks the island's own
        arms too: ``expr ::= expr op term`` puts ``op``'s FIRST into
        FOLLOW(``expr``) purely because the rule places ``expr`` before ``op``.
        A shorter end followed by ``+`` is then the island continuing ITSELF,
        which longest-match absorbs under the same arm — not the caller
        accepting it.

        *Not one site's continuation*, because the caller may reach the island
        through more than one arm and the PDA commits to an arm BEFORE
        entering. With ``root ::= expr "+" term nl | expr nl`` the two sites
        see ``{'+'}`` and ``{'\\n'}``, and ``a+b\\n`` derives both ways meaning
        two different things. The union asks whether the shorter end could
        compose with ANY way back into the caller, which is the question.

        The island's own arms contribute nothing because an island rule is
        never cloned — its internal recursion is resolved inside the Earley
        sub-parse and never reaches a reference site here.

        *What follows ONE occurrence*, not the item as a whole. A reference
        that can repeat (``sec+``) is followed by its next occurrence too, and
        a shorter end that another ``sec`` would continue is two carvings of
        the caller's repetition, which longest-match must not settle. So such
        a site adds the island's own FIRST. That is a different node, unlike
        the island's own arms above. A reference inside a repeated GROUP
        needs nothing here: the group arrives hoisted, and its rule's FOLLOW
        already carries the loopback.

        *Only sites that can share a position with this one.* The union is for
        a derivation the PDA did not take, placing the island at another site
        at the SAME text position. A site whose possible document positions
        cannot meet this one's (:meth:`_meets`) cannot be that derivation.

        :param name: The island rule name.
        :param site: The reference being compiled; ``None`` unions every site.
        :returns: The union over external reference sites; empty when the
            island is referenced from nowhere (the start rule itself), which
            carries no evidence and accepts plain longest-match.
        """
        key = (name, id(site))
        cached = self._follows.get(key)
        if cached is not None:
            return cached
        analysis = self.analysis
        found = CharSet.EMPTY
        for rule, items, at, groups in self._sites(name, site):
            tail = self._group_tail(analysis.follow[rule], groups)
            found = found.union(analysis.cont_at(items, at, tail))
            if _repeats(items[at]):  # the next occurrence follows this one
                found = found.union(analysis.atom_first(items[at].atom))
        self._follows[key] = found
        return found

    def windows(self, name: str, site: IrItem | None = None) -> tuple[Pref, ...]:
        """What may follow island ``name``, :data:`WINDOW` characters deep.

        The same occurrence continuation as :meth:`follow`, as FIRST-k windows:
        the rest of each site's arm, END-extended by what follows its rule
        (FOLLOW-k, repeat loopback folded in), unioned over the sites, plus the
        island's own windows where the site repeats. The two-ends check reads
        it only where :meth:`follow` already admits the next character, so a
        shorter end followed by a space that no continuation can follow with
        the next character is not mistaken for one that composes.

        Built from one FOLLOW-k fixpoint per grammar, and only when asked.

        :param name: The island rule name.
        :param site: The reference being compiled; ``None`` unions every site.
        :returns: The window set; empty when referenced from nowhere.
        """
        key = (name, id(site))
        cached = self._windows.get(key)
        if cached is not None:
            return cached
        if self._deep is None:
            analysis = self.analysis
            self._deep = FollowWindows(analysis.rules, analysis.start, WINDOW)
        deep = self._deep
        found: set[Pref] = set()
        for rule, items, at, groups in self._sites(name, site):
            rest = extend_follow(
                deep.solver.arm_prefixes(items[at + 1 :], WINDOW),
                _group_windows(deep, deep.follow[rule], groups),
                WINDOW,
            )
            if _repeats(items[at]):
                rest = _after_repeats(deep.solver.rule_prefixes(name, WINDOW), rest)
            found |= rest
        # A window the full width deep may go on past it (FIRST-k stops walking
        # once every state is that wide), so only a shorter END is complete.
        self._windows[key] = tuple(
            (chars, MORE if state == END and len(chars) >= WINDOW else state)
            for chars, state in found
        )
        return self._windows[key]

    def _sites(self, name: str, site: IrItem | None) -> Iterator[Site]:
        """Every external reference to island ``name`` that can stand where
        ``site`` does: rule, arm items, index, and the groups it sits in.

        An island's own arms are never entry sites: an island is never cloned,
        so its internal recursion never reaches a reference here. A reference
        inside an inline group is a site like any other.
        """
        # A delegate's analysis starts at its island, and its window rebases
        # every position: nothing there is a document position, so no narrowing.
        narrow = site is not None and not self.analysis.taxonomy.delegated
        where = self._places().get(id(site)) if narrow else None
        for rule, body in self.analysis.rules.items():
            if rule in self.islands:
                continue
            for arm in body.body:
                for items, at, groups in _references(name, arm_items(arm), ()):
                    place = self._places().get(id(items[at]), _ANYWHERE)
                    if where is None or _meets(where, place):
                        yield rule, items, at, groups

    def _group_tail(self, tail: CharSet, groups: Groups) -> CharSet:
        """What follows a reference's innermost group, from what follows its
        rule: through each enclosing group, outermost first — the rest of the
        group's arm, and the group again where it repeats."""
        analysis = self.analysis
        for items, at in groups:
            after = analysis.cont_at(items, at, tail)
            if _repeats(items[at]):
                after = after.union(analysis.atom_first(items[at].atom))
            tail = after
        return tail

    def _places(self) -> dict[int, Span]:
        """Every top-level reference item's possible document positions, by
        identity. Built once, on the document grammar."""
        if self._where is None:
            self._where = site_positions(self.analysis.rules, self.analysis.start)
        return self._where

    def bounds(self, name: str, cont: CharSet) -> bool:
        """Can island ``name``'s extent be read off one linear scan for ``cont``?

        When the island can derive no character of its own continuation, no
        completion of it reaches past the first continuation character after
        the cursor: the island would have to consume that character to get
        there, and it cannot. So the extent is bounded by that position, the
        window is exactly that wide, and ONE sub-parse at that width settles
        the island — no 256-character floor, no doubling, no re-parse of the
        same characters at five widths.

        This does not weaken the two-ends refusal. A completion end BEFORE the
        bound is exactly the case that refusal already handles, and it is
        handled inside this window as it was inside a climbing one; the bound
        only removes ends that could not exist.

        An island whose alphabet MEETS its continuation keeps the climb — a
        string literal that can hold its own terminator is the shape, and
        there the first continuation character says nothing about the extent.

        :param name: The island rule name.
        :param cont: The occurrence continuation from :meth:`follow`.
        :returns: ``True`` when the scan is a sound bound.
        """
        if cont.is_empty() or cont.negated:
            return False  # nothing to scan for, or a set no scan enumerates
        if self._alphabets is None:
            self._alphabets = rule_alphabets(self.analysis.rules)
        held = self._alphabets.get(name)
        return held is not None and not held.overlaps(cont)


_ANYWHERE: Span = (0.0, math.inf)
"""A position nothing was proved about."""


def _meets(one: Span, other: Span) -> bool:
    """Whether two position intervals share a position."""
    return one[0] <= other[1] and other[0] <= one[1]


def _hull(old: Span | None, new: Span) -> Span:
    """The smallest interval holding both."""
    return new if old is None else (min(old[0], new[0]), max(old[1], new[1]))


def _in_groups(rules: dict[str, IrRule]) -> set[str]:
    """Every rule referenced from inside an inline group, at any depth. Their
    positions are not traced, so they are taken to be anywhere."""
    found: set[str] = set()
    pending = [
        list(item.atom)
        for rule in rules.values()
        for arm in rule.body
        for item in arm_items(arm)
        if isinstance(item.atom, IrAlternation)
    ]
    while pending:
        for arm in pending.pop():
            for item in arm_items(arm):
                if isinstance(item.atom, IrRuleRef):
                    found.add(str(item.atom))
                elif isinstance(item.atom, IrAlternation):
                    pending.append(list(item.atom))
    return found


def site_positions(rules: dict[str, IrRule], start: str) -> dict[int, Span]:
    """Where in the document each top-level rule reference can begin, by item
    identity: an interval over-approximating every absolute position.

    The start rule begins at 0. A reference begins where its rule does plus
    what its arm's earlier items can span, and a rule begins wherever any of
    its references can (the hull over every path, so a nullable prefix pulls
    the low end down). A repeating reference also covers its later
    occurrences. An interval still growing after one round per rule is on a
    recursion and has no high end; the loop runs until nothing moves, so that
    widening reaches every reference downstream of it.
    """
    spans = rule_spans(rules)
    refs = [
        (rule, items, at)
        for rule, body in rules.items()
        for items in (arm_items(arm) for arm in body.body)
        for at, item in enumerate(items)
        if isinstance(item.atom, IrRuleRef)
    ]
    starts: dict[str, Span] = {name: _ANYWHERE for name in _in_groups(rules)}
    starts[start] = _hull(starts.get(start), (0.0, 0.0))
    sites: dict[int, Span] = {}
    rounds, changed = 0, True
    while changed:
        changed, late = False, rounds > len(rules)
        for rule, items, at in refs:
            here = starts.get(rule)
            if here is None:
                continue
            place = _place(here, items, at, spans)
            sites[id(items[at])] = _hull(sites.get(id(items[at])), place)
            changed |= _widen(starts, str(items[at].atom), place, late)
        rounds += 1
    return sites


def _place(here: Span, items: list[IrItem], at: int, spans: dict[str, Span]) -> Span:
    """Where item ``at`` can begin, given where its arm begins: after what the
    earlier items can span, and, if it repeats, through its later
    occurrences too."""
    before = seq_span(items[:at], spans)
    later = seq_span([items[at]], spans)[1] if _repeats(items[at]) else 0.0
    return (here[0] + before[0], here[1] + before[1] + later)


def _widen(starts: dict[str, Span], name: str, place: Span, late: bool) -> bool:
    """Take ``place`` into rule ``name``'s start interval; a high end still
    rising ``late`` in the fixpoint is on a recursion and becomes unbounded.
    Returns whether it moved."""
    old = starts.get(name)
    grown = _hull(old, place)
    if late and old is not None and grown[1] > old[1]:
        grown = (grown[0], math.inf)
    if grown == old:
        return False
    starts[name] = grown
    return True


def _after_repeats(occurrence: set[Pref], rest: set[Pref]) -> set[Pref]:
    """What follows one occurrence of a repeating reference: the rest of its
    arm, or another occurrence followed by the same again.

    Grown to its fixpoint, which a window this shallow reaches in a step or two.
    """
    after = set(rest)
    while True:
        grown = rest | extend_follow(occurrence, after, WINDOW)
        if grown == after:
            return after
        after = grown


def _references(
    name: str, items: list[IrItem], groups: Groups
) -> Iterator[tuple[list[IrItem], int, Groups]]:
    """Every reference to rule ``name`` in an arm, inline groups entered."""
    for at, item in enumerate(items):
        atom = item.atom
        if isinstance(atom, IrRuleRef) and str(atom) == name:
            yield items, at, groups
        elif isinstance(atom, IrAlternation):
            inner = (*groups, (items, at))
            for arm in atom:
                yield from _references(name, arm_items(arm), inner)


def _group_windows(deep: FollowWindows, tail: set[Pref], groups: Groups) -> set[Pref]:
    """:meth:`IslandContinuations._group_tail` as windows: the rest of each
    enclosing group's arm, END-extended outward, the group again where it
    repeats."""
    for items, at in groups:
        after = extend_follow(
            deep.solver.arm_prefixes(items[at + 1 :], WINDOW), tail, WINDOW
        )
        if _repeats(items[at]):
            group = items[at].atom
            assert isinstance(group, IrAlternation)
            after = _after_repeats(deep.solver.group_prefixes(group, WINDOW), after)
        tail = after
    return tail
