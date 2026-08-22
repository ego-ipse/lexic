"""Opaque interiors — the spans a structural scan must skip, not read.

A grammar that spells strings as ``string ::= quote char* quote`` puts a
co-finite class inside a delimited region: a comma there is TEXT, not a
separator. Reading it is exactly how a naive splitter mis-cuts, and the
anchor analysis avoids that by de-certifying every character such a class
can emit — which for an RFC-shaped json is every structural character it
has, leaving nothing to split on at all.

The region is derivable, so the scan skips it instead. A rule whose one arm
opens with a literal spelling and closes with the SAME spelling carries one:
the items BETWEEN them are opaque when none of them can emit the delimiter's
lead character, or — for a one-character delimiter — when the body's arms lead
with an escape literal, which is what makes ``\\"`` not a closer. Items after
the closing delimiter stay visible; the region ends where the closer does. So
```` fence ::= tick3 info nl fenceline* tick3 nl ```` hides its interior
newlines and exposes its final one, on the same reading that hides a comma in
a string.

Deriving the shape does not license skipping it. A scan that pairs delimiter
occurrences from the left is exact only when every occurrence of the lead
character IS a delimiter, and :func:`interiors` certifies that by
reachability: no rule reachable without descending into the region may spell
that character. Shapes failing it stay in :func:`interior_shapes`, for the
analyses that anchor an occurrence some other way.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAlternation, IrAst, IrItem, IrRule, IrRuleRef, IrSelf
from lexic.parsing.parallel.discovery.shapes import (
    emits,
    literal_char,
    literal_text,
    rule_emits,
    unbounded,
)


class Interior(NamedTuple):
    """One delimited opaque region.

    :ivar rule: The rule whose single arm carries it.
    :ivar delim: The spelling that both opens and closes it.
    :ivar escape: The character that makes the next one literal, or ``""``.
    :ivar opens: Item index of the opening delimiter.
    :ivar closes: Item index of the closing delimiter.
    """

    rule: str
    delim: str
    escape: str
    opens: int
    closes: int


def _escape_char(body: str, rule_map: dict[str, IrRule], seen: frozenset[str]) -> str:
    """The character an arm of the interior body leads with to escape.

    An arm that is one bare reference is followed: hoisting ``char ::= unescaped
    | "\\\\" escaped`` into a named second arm moves the escape one rule down
    without changing what the body derives.
    """
    rule = rule_map.get(body)
    if rule is None or body in seen:
        return ""
    for arm in rule.body:
        items = tuple(arm)
        if len(items) >= 2 and (lead := literal_char(items[0], rule_map)) is not None:
            return lead
        nested = items[0].atom if len(items) == 1 else None
        if isinstance(nested, IrRuleRef):
            found = _escape_char(str(nested), rule_map, seen | {body})
            if found:
                return found
    return ""


def _closing_at(
    items: tuple[IrItem, ...], delim: str, rule_map: dict[str, IrRule]
) -> int | None:
    """The first item past the opener that spells ``delim`` again."""
    return next(
        (
            at
            for at in range(1, len(items))
            if literal_text(items[at], rule_map) == delim
        ),
        None,
    )


def _opacity(
    inner: tuple[IrItem, ...], delim: str, rule_map: dict[str, IrRule]
) -> str | None:
    """What keeps the span between the delimiters opaque, or ``None``.

    ``""`` says nothing inside can spell the delimiter's lead character at
    all; an escape character says the body's own arms make an occurrence
    literal. A body with neither is not a region a scan may skip.
    """
    lead = delim[0]
    if not any(emits(item, lead, rule_map, frozenset(), frozenset()) for item in inner):
        return ""
    if len(delim) != 1 or len(inner) != 1 or not unbounded(inner[0]):
        return None
    body = inner[0].atom
    if not isinstance(body, IrRuleRef):
        return None
    return _escape_char(str(body), rule_map, frozenset()) or None


def _interior_of(rule: IrRule, rule_map: dict[str, IrRule]) -> Interior | None:
    """The interior ``rule`` defines, when it has the delimited shape."""
    arms = tuple(rule.body)
    if len(arms) != 1:
        return None
    items = tuple(arms[0])
    if len(items) < 3:
        return None
    delim = literal_text(items[0], rule_map)
    closes = _closing_at(items, delim, rule_map) if delim is not None else None
    if delim is None or closes is None:
        return None
    escape = _opacity(items[1:closes], delim, rule_map)
    if escape is None:
        return None
    return Interior(str(rule.name), delim, escape, 0, closes)


def _refs(atom: IrSelf) -> frozenset[str]:
    """Every rule name an atom references, nested alternations included."""
    if isinstance(atom, IrRuleRef):
        return frozenset({str(atom)})
    if not isinstance(atom, IrAlternation):
        return frozenset()
    found: set[str] = set()
    for arm in atom:
        for item in arm:
            found |= _refs(item.atom)
    return frozenset(found)


def _reachable_without(
    grammar: IrAst, rule_map: dict[str, IrRule], skip: str
) -> frozenset[str]:
    """Rules reachable from the start without descending into ``skip``."""
    seen: set[str] = set()
    pending = [str(grammar.start)]
    while pending:
        name = pending.pop()
        rule = rule_map.get(name)
        if name in seen or name == skip or rule is None:
            continue
        seen.add(name)
        for arm in rule.body:
            for item in arm:
                pending.extend(_refs(item.atom))
    return frozenset(seen)


def _sole_delimiter(
    grammar: IrAst, rule_map: dict[str, IrRule], region: Interior
) -> bool:
    """Whether only this region's own rule spells its lead character.

    Hiding every reference turns :func:`~...shapes.rule_emits` into "what does
    this arm spell DIRECTLY", so the question is asked once per reachable
    rule rather than once per derivation path.
    """
    opaque = frozenset(rule_map)
    return not any(
        rule_emits(rule_map[name], region.delim[0], rule_map, opaque, frozenset())
        for name in _reachable_without(grammar, rule_map, region.rule)
    )


_SHAPES: dict[int, tuple[IrAst, tuple[Interior, ...]]] = {}
"""Shape memo — id(grammar) → (grammar, shapes). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def interior_shapes(grammar: IrAst) -> tuple[Interior, ...]:
    """Every delimited region the grammar's rule shapes define.

    Certifying WHERE such a region may be recognised is the caller's question:
    :func:`interiors` answers it by reachability, and a plan that knows where
    its units begin can anchor one this analysis alone cannot.

    :param grammar: The grammar to analyse.
    :returns: One :class:`Interior` per delimited shape, definition order.
    """
    entry = _SHAPES.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        found = [_interior_of(rule, rule_map) for rule in grammar.rules]
        entry = (grammar, tuple(x for x in found if x is not None))
        _SHAPES[id(grammar)] = entry
    return entry[1]


_INTERIORS: dict[int, tuple[IrAst, tuple[Interior, ...]]] = {}
"""Certified-skippable memo, keyed and pinned like :data:`_SHAPES`."""


def interiors(grammar: IrAst) -> tuple[Interior, ...]:
    """The regions a left-to-right scan may pair anywhere in the document.

    :param grammar: The grammar to analyse.
    :returns: The certified regions, definition order.
    """
    entry = _INTERIORS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        found = tuple(
            region
            for region in interior_shapes(grammar)
            if _sole_delimiter(grammar, rule_map, region)
        )
        entry = (grammar, found)
        _INTERIORS[id(grammar)] = entry
    return entry[1]


def interior_rules(grammar: IrAst) -> frozenset[str]:
    """Rules whose spans the structural scanner actually treats as opaque."""
    return frozenset(region.rule for region in interiors(grammar))


def hides(grammar: IrAst, region: Interior, watched: frozenset[str]) -> bool:
    """Whether ``region``'s own span can carry any of ``watched``.

    A region a scan would read the same way skipped or not is pure cost: it
    adds its delimiter to the swept characters and a search to every
    occurrence. Only regions that would otherwise MISLEAD are worth skipping.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    items = tuple(tuple(rule_map[region.rule].body)[0])
    return any(
        emits(item, char, rule_map, frozenset(), frozenset())
        for item in items[region.opens : region.closes + 1]
        for char in watched
    )


def skip_table(regions: tuple[Interior, ...]) -> dict[str, tuple[Interior, ...]]:
    """Lead character → the regions it may open, longest delimiter first.

    One character can lead more than one spelling (```` ` ```` opens both a
    code span and a fence), and the longer spelling is the one a scan must
    test first or it splits the longer delimiter in half.
    """
    found: dict[str, list[Interior]] = {}
    for region in regions:
        found.setdefault(region.delim[0], []).append(region)
    return {
        lead: tuple(sorted(entries, key=lambda region: -len(region.delim)))
        for lead, entries in found.items()
    }


type Skip = tuple[str, str, int]
"""One region as the sweep consumes it: delimiter, escape, delimiter width.

The width is carried rather than measured because the sweep hands this to
:func:`skip_delimited` once per delimited span of the document, and three
``len`` calls there were measurably the whole cost of carrying a delimiter
longer than one character.
"""


def skip_leads(regions: tuple[Interior, ...]) -> dict[str, Skip]:
    """Lead character → the one region it opens.

    The region sweep tests this table once per structural character of a
    document, so the answer is a lookup rather than a search — which is what
    :func:`skip_table` is for, where a position is already known. A lead
    character opening two spellings has no single answer and is dropped: the
    sweep reaches it by that character alone and cannot tell them apart.
    """
    table = skip_table(regions)
    return {
        lead: (entries[0].delim, entries[0].escape, len(entries[0].delim))
        for lead, entries in table.items()
        if len(entries) == 1
    }


def skip_opaque(text: str, at: int, candidates: tuple[Interior, ...]) -> int:
    """Past the region opening at ``at``, or ``at`` when none opens there."""
    for region in candidates:
        if text.startswith(region.delim, at):
            return skip_delimited(
                text, at, (region.delim, region.escape, len(region.delim))
            )
    return at


def skip_delimited(text: str, start: int, skip: Skip) -> int:
    """Where the region opened at ``start`` ends (past its closer).

    ``start`` when the delimiter does not stand there in full — the sweep
    reaches here on its lead character alone. A one-character delimiter cannot
    fail that test, so the width settles it before any comparison runs.
    """
    delim, escape, width = skip
    if width != 1 and not text.startswith(delim, start):
        return start
    if delim == escape:
        return len(text)
    at = text.find(delim, start + width)
    while at != -1:
        before = at - 1
        while escape and before > start and text[before] == escape:
            before -= 1
        if not escape or (at - before - 1) % 2 == 0:
            return at + width
        at = text.find(delim, at + 1)
    return len(text)
