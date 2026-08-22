"""Routed regions — an interior the character scan can never find.

The region sweep finds a bracketed run by watching characters: an opener
raises a depth, a closer lowers it. That works while the opener MEANS
something wherever it stands. It stops working when a grammar opens its body
with a newline — every line ending in the document looks like an opener, the
depth count is noise, and a run holding the whole payload is invisible.

The document's own SHAPE knows where it is. A start rule reading
``head… interior? tail…`` says the interior stands after the head and before
the tail, and if the head is mark-terminated units followed by a mark-free
remainder, the interior opens at the first mark past that remainder. Nothing
here reads a bracket depth; the route to the interior is what locates it.

What comes back is an ordinary :class:`~...discovery.regions.Region`, so the
existing division, stand-in shell and stitch handle it exactly as they handle
a region the sweep found. This module is a second SOURCE of regions, not a
second way to split one.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing.parallel.discovery.regions import Region, nearest_mark
from lexic.parsing.parallel.discovery.shapes import (
    UNIT,
    derives_empty,
    emit_charset,
    first_charset,
    literal_text,
    rule_emits,
    unbounded,
)
from lexic.parsing.parallel.stitch.safety import terminates_once
from lexic.parsing.pda.core.charsets import CharSet

_PLANS: dict[int, tuple[IrAst, "RoutedPlan | None"]] = {}
"""Route memo — id(grammar) → (grammar, plan). The strong reference pins the
id, so a recycled id can never alias a live entry."""


class RoutedPlan(NamedTuple):
    """A delimited interior reached by the start rule's own route.

    :ivar rule: The rule a piece of the interior parses under.
    :ivar item: The repeated unit inside it.
    :ivar opening: The character opening the interior.
    :ivar closing: The character closing it.
    :ivar mark: The unit's terminator — where the interior may be cut.
    :ivar lead: What a head unit before the interior can begin with; the
        locator walks those lines off before the interior can start.
    :ivar tail: What may stand after the closing character.
    :ivar at: The interior's item index in the start rule's arm.
    :ivar run: The repetition's item index inside the interior.
    :ivar rooted: The grammar rooted at the interior, which a piece parses
        under. Built once with the plan so its tables compile once.
    """

    rule: str
    item: str
    opening: str
    closing: str
    mark: str
    lead: CharSet
    tail: CharSet
    at: int
    run: int
    rooted: IrAst


def _optional_ref(item: IrItem) -> str | None:
    """The rule an optional single-occurrence item references."""
    atom = item.atom
    optional = item.quantifier.lo == 0 and not unbounded(item)
    return str(atom) if optional and isinstance(atom, IrRuleRef) else None


def _delimited_arm(
    items: tuple[IrItem, ...], rules: dict[str, IrRule]
) -> tuple[str, str, str, str] | None:
    """``(rule, opening, item, closing)`` when an arm delimits one repetition.

    An arm that is one bare reference is followed: a body offering
    ``inline | block`` names its alternatives rather than spelling them, and
    the delimited shape lives in the rule the arm names.
    """
    named = items[0].atom if len(items) == 1 else None
    if isinstance(named, IrRuleRef) and items[0].quantifier == UNIT:
        below = rules.get(str(named))
        arms = tuple(below.body) if below is not None else ()
        found = _delimited_arm(tuple(arms[0]), rules) if len(arms) == 1 else None
        return None if found is None else (str(named), *found[1:])
    if len(items) != 3 or not unbounded(items[1]):
        return None
    opening = literal_text(items[0], rules)
    closing = literal_text(items[2], rules)
    repeated = items[1].atom
    if opening is None or closing is None or not isinstance(repeated, IrRuleRef):
        return None
    single = len(opening) == 1 and len(closing) == 1
    return ("", opening, str(repeated), closing) if single else None


def _forced(target: IrRule, at: int, rules: dict[str, IrRule]) -> bool:
    """Whether arm ``at`` of ``target`` is the only one a document can take.

    The arms must be told apart by their first character alone — an inline
    body opening with a space against a block body opening with a newline.
    Anything overlapping leaves the route a guess, and a guess declines.
    """
    firsts = [first_charset(tuple(arm), rules, frozenset()) for arm in target.body]
    chosen = firsts[at]
    return not any(
        chosen.overlaps(other) for index, other in enumerate(firsts) if index != at
    )


def _head_lead(
    before: tuple[IrItem, ...], mark: str, rules: dict[str, IrRule]
) -> CharSet | None:
    """What a repeated head unit begins with, when the head has the shape.

    Everything before the interior must be either a repetition whose units end
    at the mark — lines the locator can walk off — or a remainder that cannot
    reach the mark at all. The two must be distinguishable by first character,
    or the locator cannot tell where the head stops repeating.
    """
    lead = CharSet.EMPTY
    rest = CharSet.EMPTY
    for item in before:
        atom = item.atom
        repeated = unbounded(item) and isinstance(atom, IrRuleRef)
        if repeated and terminates_once_ref(str(atom), mark, rules):
            lead = lead.union(first_charset((item,), rules, frozenset()))
            continue
        if rule_emits_item(item, mark, rules):
            return None
        rest = rest.union(first_charset((item,), rules, frozenset()))
    return None if lead.overlaps(rest) else lead


def terminates_once_ref(name: str, mark: str, rules: dict[str, IrRule]) -> bool:
    """Whether the named rule's every derivation ends at ``mark``, once."""
    target = rules.get(name)
    return target is not None and bool(
        literal_text(tuple(tuple(target.body)[0])[-1], rules) == mark
    )


def rule_emits_item(item: IrItem, mark: str, rules: dict[str, IrRule]) -> bool:
    """Whether one item can emit ``mark`` anywhere in its derivations."""
    atom = item.atom
    if not isinstance(atom, IrRuleRef):
        return bool(emit_charset(item, rules, frozenset()).has(mark))
    target = rules.get(str(atom))
    return target is None or rule_emits(target, mark, rules, frozenset(), frozenset())


def routed_plan(grammar: IrAst) -> RoutedPlan | None:
    """The interior the start rule's route reaches, memoised per identity.

    :param grammar: The codegen grammar.
    :returns: The plan, or ``None`` when any of the route's conditions is
        unproven — a competing arm the first character cannot separate, a head
        that can itself reach the mark, or a unit whose terminator is not its
        own final edge.
    """
    entry = _PLANS.get(id(grammar))
    if entry is None:
        entry = (grammar, _derive_routed(grammar))
        _PLANS[id(grammar)] = entry
    return entry[1]


def _derive_routed(grammar: IrAst) -> RoutedPlan | None:
    """Walk the start arm for an optional interior every proof admits."""
    rules = {str(rule.name): rule for rule in grammar.rules}
    start = rules.get(str(grammar.start))
    arms = tuple(start.body) if start is not None else ()
    items = tuple(arms[0]) if len(arms) == 1 else ()
    for at, item in enumerate(items):
        found = _routed_at(grammar, rules, items, at) if _optional_ref(item) else None
        if found is not None:
            return found
    return None


def _routed_at(
    grammar: IrAst,
    rules: dict[str, IrRule],
    items: tuple[IrItem, ...],
    at: int,
) -> RoutedPlan | None:
    """The plan the optional item at ``at`` admits, if every proof holds."""
    target = rules.get(_optional_ref(items[at]) or "")
    if target is None:
        return None
    for index, arm in enumerate(target.body):
        shape = _delimited_arm(tuple(arm), rules)
        if shape is None or not _forced(target, index, rules):
            continue
        found = _proven(grammar, rules, items, (at, shape, str(target.name)))
        if found is not None:
            return found
    return None


def _proven(
    grammar: IrAst,
    rules: dict[str, IrRule],
    items: tuple[IrItem, ...],
    candidate: tuple[int, tuple[str, str, str, str], str],
) -> RoutedPlan | None:
    """Discharge the head, tail and terminator proofs for one candidate arm."""
    at, (named, opening, unit, closing), owner = candidate
    inner = rules.get(unit)
    if inner is None:
        return None
    mark = literal_text(tuple(tuple(inner.body)[0])[-1], rules)
    if mark is None or len(mark) != 1 or not terminates_once(grammar, unit, mark):
        return None
    lead = _head_lead(items[:at], mark, rules)
    tail = _tail_charset(items[at + 1 :], rules)
    if lead is None or tail is None:
        return None
    piece = named or owner
    return RoutedPlan(
        piece,
        unit,
        opening,
        closing,
        mark,
        lead,
        tail,
        at,
        1,
        IrAst(grammar.rules, piece),
    )


def _tail_charset(
    after: tuple[IrItem, ...], rules: dict[str, IrRule]
) -> CharSet | None:
    """What may follow the closing character, when everything after can vanish."""
    found = CharSet.EMPTY
    for item in after:
        if not derives_empty(item, rules, frozenset()):
            return None
        found = found.union(emit_charset(item, rules, frozenset()))
    return found


def locate(text: str, plan: RoutedPlan) -> Region | None:
    """Where the routed interior stands in ``text``, or ``None``.

    The head's repeated units are walked off a line at a time — each ends at
    the mark, and its first character says it is one — and the first mark past
    the remainder opens the interior. The closer is the document's own tail,
    behind whatever the start rule allows to follow it.
    """
    at = 0
    while at < len(text) and plan.lead.has(text[at]):
        nxt = text.find(plan.mark, at)
        if nxt == -1:
            return None
        at = nxt + 1
    opens = text.find(plan.mark, at)
    closes = _tail_closer(text, plan)
    if opens == -1 or closes is None or closes <= opens:
        return None
    if text[opens] != plan.opening:
        return None
    marks = _interior_marks(text, opens, closes, plan.mark)
    return Region(opens, closes, plan.rule, marks)


def _tail_closer(text: str, plan: RoutedPlan) -> int | None:
    """The closing character at the document's end, behind its allowed tail."""
    at = len(text) - 1
    while at >= 0 and plan.tail.has(text[at]) and text[at] != plan.closing:
        at -= 1
    return at if at >= 0 and text[at] == plan.closing else None


def _interior_marks(text: str, opens: int, closes: int, mark: str) -> tuple[int, ...]:
    """Every unit terminator inside the interior, in document order.

    The unit's own ``terminates_once`` proof is what makes a bare search
    exact: a terminator can only stand at a unit's final edge, so every
    occurrence between the delimiters ends one.
    """
    found: list[int] = []
    at = text.find(mark, opens + 1)
    while at != -1 and at < closes:
        found.append(at)
        at = text.find(mark, at + 1)
    return tuple(found)


def divide(text: str, region: Region, workers: int) -> list[str] | None:
    """The interior cut into ``workers`` pieces, or ``None`` if it will not.

    Each piece wears the region's own delimiters, so it is a document under the
    region's rule and costs its own text. The cut lands AFTER a terminator,
    because a terminated unit owns its final character — the separated
    division in :mod:`~...discovery.regions` hands that character to a lead
    instead, which would leave every piece here missing an edge.
    """
    lo, hi = region.opener + 1, region.closer
    if workers < 2 or not region.marks:
        return None
    target = (hi - lo) / workers
    cuts: list[int] = []
    for step in range(1, workers):
        after = nearest_mark(region.marks, lo + step * target) + 1
        if after not in cuts and after < hi:
            cuts.append(after)
    bounds = [lo, *cuts, hi]
    widest = max(bounds[at + 1] - bounds[at] for at in range(len(bounds) - 1))
    if len(bounds) < 3 or widest > 2 * target:
        return None
    opening, closing = text[region.opener], text[region.closer]
    return [
        opening + text[bounds[at] : bounds[at + 1]] + closing
        for at in range(len(bounds) - 1)
    ]
