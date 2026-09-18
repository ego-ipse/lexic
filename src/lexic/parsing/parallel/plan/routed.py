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
from lexic.parsing.caches import memo
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
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.stitch.safety import terminates_once
from lexic.parsing.pda.core.charsets import CharSet

_PLANS: dict[int, tuple[IrAst, "RoutedPlan | None"]] = memo({})
"""Route memo — id(grammar) → (grammar, plan). The strong reference pins the
id, so a recycled id can never alias a live entry."""


class RoutedPlan(NamedTuple):
    """An interior reached by the start rule's own route.

    Two kinds, told apart by :attr:`whole`. A DELIMITED interior is bounded in
    the text by an opening and a closing character (``"\n" item* ">"``), and a
    piece is made parseable by re-wearing both. A TERMINATED one has no opener
    at all (``line* blank``): it runs to the end of its enclosing node, and a
    piece is made parseable by re-wearing the enclosing rule's own TAIL — the
    same trick, with the unit's terminator standing in for a closing delimiter.

    :ivar rule: The rule a piece of the interior parses under.
    :ivar item: The repeated unit inside it.
    :ivar opening: What a piece wears on the left; empty for a terminated
        interior, which opens with its first unit and nothing else.
    :ivar closing: What a piece wears on the right — the closing delimiter, or
        the enclosing rule's tail.
    :ivar mark: The unit's terminator — where the interior may be cut.
    :ivar lead: What a head unit before the interior can begin with; the
        locator walks those lines off before the interior can start.
    :ivar tail: What may stand after the closing character.
    :ivar at: The interior's item index in the start rule's arm.
    :ivar run: The repetition's item index inside the interior.
    :ivar rooted: The grammar rooted at the interior, which a piece parses
        under. Built once with the plan so its tables compile once.
    :ivar whole: The interior is its enclosing node's WHOLE extent, so there is
        nothing in the text to search for and the region is bounded by that
        extent rather than found. A fact about the shape, not a missing value:
        a terminated interior has no opener to locate.
    :ivar before: The text standing before the interior in the enclosing arm —
        ``"<<<\n"`` for a wrapped body, empty where the interior starts the
        document. With :attr:`after` it is what bounds a whole-extent interior,
        which is the thing a delimited one reads off its delimiters instead.
    :ivar after: The text standing after it, likewise.
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
    whole: bool = False
    before: str = ""
    after: str = ""


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


def _terminated_arm(
    items: tuple[IrItem, ...], rules: dict[str, IrRule]
) -> tuple[str, str, str, str] | None:
    """``("", "", item, tail)`` when an arm is a repetition then its tail.

    ``para ::= line* blank`` — the repetition LEADS the arm and the rest of the
    arm is what closes it. There is no opening delimiter, so a piece wears
    nothing on the left; what makes it parseable is wearing the tail, exactly
    as a delimited piece is made parseable by wearing its delimiters.

    The tail must spell a literal, because a piece has to be able to WEAR it.
    An arm whose tail is a character class or another repetition is refused:
    there would be no one string to append.
    """
    if len(items) < 2 or not unbounded(items[0]):
        return None
    repeated = items[0].atom
    if not isinstance(repeated, IrRuleRef):
        return None
    spelled = [literal_text(one, rules) for one in items[1:]]
    if any(one is None for one in spelled):
        return None
    return ("", "", str(repeated), "".join(one for one in spelled if one))


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
    """Whether the named rule's EVERY arm ends at ``mark``, once.

    Every arm, not the first: a head unit the locator walks off by lines must
    end at the mark on every derivation, or a line matching another arm would
    carry the walk past its own end.
    """
    target = rules.get(name)
    arms = tuple(target.body) if target is not None else ()
    return bool(arms) and all(
        bool(items) and literal_text(items[-1], rules) == mark
        for items in (tuple(arm) for arm in arms)
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
    """Walk the start arm for an interior every proof admits.

    Delimited first, because it is the certain shape and the one that has
    always been served; a terminated interior is looked for only where no
    delimited one is found, so no grammar changes the route it takes today.
    """
    rules = {str(rule.name): rule for rule in grammar.rules}
    start = rules.get(str(grammar.start))
    arms = tuple(start.body) if start is not None else ()
    items = tuple(arms[0]) if len(arms) == 1 else ()
    for at, item in enumerate(items):
        found = _routed_at(grammar, rules, items, at) if _optional_ref(item) else None
        if found is not None:
            return found
    for at, item in enumerate(items):
        found = _terminated_at(grammar, rules, items, at)
        if found is not None:
            return found
    return None


def _terminated_at(
    grammar: IrAst,
    rules: dict[str, IrRule],
    items: tuple[IrItem, ...],
    at: int,
) -> RoutedPlan | None:
    """The terminated interior the item at ``at`` reaches, if it reaches one.

    The item's OWN rule must be the interior, and that is a correctness bound
    rather than conservatism: the route expresses two slots, so a repetition
    one rule deeper — ``root ::= open body close`` with ``body ::= para+`` —
    would have its run written into the wrong node's field, a wrong model
    rather than a refusal. Serving that shape means making the route a path,
    not relaxing this.
    """
    atom = items[at].atom
    if not isinstance(atom, IrRuleRef):
        return None
    name = str(atom)
    target = rules.get(name)
    arms = tuple(target.body) if target is not None else ()
    if len(arms) != 1:
        return None
    inner = tuple(one for one in tuple(arms[0]) if isinstance(one, IrItem))
    shape = _terminated_arm(inner, rules)
    if shape is None:
        return None
    return _proven_terminated(grammar, rules, items, (at, shape, name))


def _proven_terminated(
    grammar: IrAst,
    rules: dict[str, IrRule],
    items: tuple[IrItem, ...],
    candidate: tuple[int, tuple[str, str, str, str], str],
) -> RoutedPlan | None:
    """Discharge the terminator proof for a terminated interior.

    The SAME proof the delimited route discharges — ``terminates_once`` on the
    repeated unit — and nothing weaker. A unit whose mark is not its own final
    edge is refused here exactly as it is there.
    """
    at, (_named, _opening, unit, tail), owner = candidate
    inner = rules.get(unit)
    if inner is None or not tail:
        return None
    mark = literal_text(tuple(tuple(inner.body)[0])[-1], rules)
    if mark is None or len(mark) != 1 or not terminates_once(grammar, unit, mark):
        return None
    before = _spelled_run(items[:at], rules)
    after = _spelled_run(items[at + 1 :], rules)
    if before is None or after is None:
        return None  # a neighbour whose width the text cannot be read for
    return RoutedPlan(
        owner,
        unit,
        "",
        tail,
        mark,
        CharSet.EMPTY,
        CharSet.EMPTY,
        at,
        0,
        # Rooted at the START rule, not at the interior's own. A piece rooted
        # at the interior fails predictively — a greedy repetition eats the
        # tail the piece wears, leaving nothing for the terminator — and falls
        # back to Earley. Under the start rule the same text is one complete
        # document and settles predictively.
        # `grammar` ITSELF, not an equal copy: tables and per-worker replicas
        # are keyed by grammar identity, so a copy compiles a second set of
        # everything the enclosing parse already has and every worker builds
        # its own replica of it.
        grammar,
        whole=True,
        before=before,
        after=after,
    )


def _spelled_run(items: tuple[IrItem, ...], rules: dict[str, IrRule]) -> str | None:
    """What a run of arm items spells, or ``None`` when any of them cannot.

    A whole-extent interior is bounded by its neighbours' widths, so every
    neighbour has to spell a fixed string. One that does not — a repetition, a
    character class — leaves the interior's start unknowable without parsing,
    and the plan declines rather than guessing at it.
    """
    out: list[str] = []
    for item in items:
        spelled = literal_text(item, rules)
        if spelled is None:
            return None
        out.append(spelled)
    return "".join(out)


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

    A WHOLE-extent interior is not searched for: it runs from its enclosing
    node's start to that node's own tail, and both are read off the neighbours'
    fixed widths. The final mark is the tail — the repetition's run ends before
    it, which is what leaves each piece able to wear one of its own.
    """
    if plan.whole:
        return _whole_region(text, plan)
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


def _whole_region(text: str, plan: RoutedPlan) -> Region | None:
    """The region a whole-extent interior occupies, bounded by its neighbours."""
    if not text.startswith(plan.before) or not text.endswith(plan.after):
        return None
    lo = len(plan.before)
    hi = len(text) - len(plan.after)
    tail = text.rfind(plan.mark, lo, hi)
    if tail < lo:
        return None
    marks = _interior_marks(text, lo - 1, tail, plan.mark)
    return Region(lo - 1, tail, plan.rule, marks)


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


def divide(
    text: str, region: Region, workers: int, plan: RoutedPlan
) -> list[str] | None:
    """The interior cut into ``workers`` pieces, or ``None`` if it will not.

    Each piece wears what makes it a document under the region's rule: a
    delimited interior's own delimiters, or — for a whole-extent one — nothing
    on the left and the enclosing rule's TAIL on the right. Both are the same
    idea: a piece is parseable because it ends the way its rule ends.

    The cut lands AFTER a terminator, because a terminated unit owns its
    final character — the separated
    division in :mod:`~...discovery.regions` hands that character to a lead
    instead, which would leave every piece here missing an edge.
    """
    lo, hi = region.opener + 1, region.closer
    # The user-pinned floor applies to ACTUAL pieces, not just the document:
    # capacity caps the division exactly as the sweep path's ``choose`` does,
    # so a small interior at a high worker count declines rather than paying
    # sub-2 KiB parses.
    workers = min(workers, (hi - lo) // MIN_CHUNK)
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
    if plan.whole:
        return [
            text[bounds[at] : bounds[at + 1]] + plan.closing
            for at in range(len(bounds) - 1)
        ]
    opening, closing = text[region.opener], text[region.closer]
    return [
        opening + text[bounds[at] : bounds[at + 1]] + closing
        for at in range(len(bounds) - 1)
    ]
