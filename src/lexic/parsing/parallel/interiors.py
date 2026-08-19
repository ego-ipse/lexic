"""Opaque interiors — the spans a structural scan must skip, not read.

A grammar that spells strings as ``string ::= quote char* quote`` puts a
co-finite class inside a delimited region: a comma there is TEXT, not a
separator. Reading it is exactly how a naive splitter mis-cuts, and the
anchor analysis avoids that by de-certifying every character such a class
can emit — which for an RFC-shaped json is every structural character it
has, leaving nothing to split on at all.

The region is derivable, so the scan skips it instead. A rule whose one arm
opens and closes with the SAME single-character literal, repeating a body
between them, is an interior; the body's arms may begin with an escape
literal, which is what makes ``\\"`` not a closer.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrRule, IrRuleRef
from lexic.parsing.parallel.shapes import literal_char, unbounded


class Interior(NamedTuple):
    """One delimited opaque region.

    :ivar delim: The character opening and closing it.
    :ivar escape: The character that makes the next one literal, or ``""``.
    """

    delim: str
    escape: str


def _escape_char(body: str, rule_map: dict[str, IrRule]) -> str:
    """The character an arm of the interior body leads with to escape."""
    rule = rule_map.get(body)
    if rule is None:
        return ""
    for arm in rule.body:
        items = tuple(arm)
        if len(items) >= 2:
            lead = literal_char(items[0], rule_map)
            if lead is not None:
                return lead
    return ""


def _interior_of(rule: IrRule, rule_map: dict[str, IrRule]) -> Interior | None:
    """The interior ``rule`` defines, when it has the delimited shape."""
    arms = tuple(rule.body)
    if len(arms) != 1:
        return None
    items = tuple(arms[0])
    if len(items) != 3:
        return None
    opener = literal_char(items[0], rule_map)
    closer = literal_char(items[2], rule_map)
    if opener is None or opener != closer or not unbounded(items[1]):
        return None
    body = items[1].atom
    if not isinstance(body, IrRuleRef):
        return None
    return Interior(opener, _escape_char(str(body), rule_map))


_INTERIORS: dict[int, tuple[IrAst, tuple[Interior, ...]]] = {}
"""Analysis memo — id(grammar) → (grammar, interiors). The strong reference
pins the id, so a recycled id can never alias a live entry."""


def interiors(grammar: IrAst) -> tuple[Interior, ...]:
    """The grammar's derived opaque interiors, memoised per identity.

    :param grammar: The grammar to analyse.
    :returns: One :class:`Interior` per delimited region, definition order.
    """
    entry = _INTERIORS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        found = [_interior_of(rule, rule_map) for rule in grammar.rules]
        entry = (grammar, tuple(x for x in found if x is not None))
        _INTERIORS[id(grammar)] = entry
    return entry[1]
