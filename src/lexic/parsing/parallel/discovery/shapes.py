"""Arm shapes — the questions the split analyses ask a grammar's arms.

:mod:`~lexic.parsing.parallel.discovery.interiors`,
:mod:`~lexic.parsing.parallel.discovery.regions` and
:mod:`~lexic.parsing.parallel.roles` each read a grammar for the same three
facts: what one item spells, whether it repeats, and what every arm of an
alternation carries at one end. They live here so that changing what "spells
one character" means reaches all three at once.
"""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrRuleRef,
)

UNIT = IrQuantifier()
"""The unit quantifier — exactly one occurrence."""


def unbounded(item: IrItem) -> bool:
    """Whether the item repeats without an upper bound."""
    return isinstance(item.quantifier.hi, IrNoneType)


def literal_char(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The single character an item spells, through one unit rule reference.

    A grammar may name its punctuation (``begin-object ::= ws "{" ws``), and
    the punctuation may sit among noise, so a rule spells one character when
    exactly one of its items does.
    """
    if item.quantifier != UNIT:
        return None
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom) if len(str(atom)) == 1 else None
    if not isinstance(atom, IrRuleRef):
        return None
    target = rule_map.get(str(atom))
    arms = tuple(target.body) if target is not None else ()
    if len(arms) != 1:
        return None
    spelled = [
        char
        for inner in tuple(arms[0])
        if (char := literal_char(inner, rule_map)) is not None
    ]
    return spelled[0] if len(spelled) == 1 else None


def edge_char(
    body: IrAlternation, at: int, char_of: Callable[[IrItem], str | None]
) -> str | None:
    """The one character EVERY arm of ``body`` carries at ``at``, else ``None``.

    :param body: The alternation whose arms must agree.
    :param at: The item index within an arm — ``0`` for what an arm leads
        with, ``-1`` for what it ends with.
    :param char_of: What counts as a character there; the callers differ on
        whether that means a literal spelling or a certified anchor.
    :returns: The agreed character, or ``None`` when an arm is empty, spells
        nothing at ``at``, or the arms disagree.
    """
    found: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        char = char_of(items[at])
        if char is None:
            return None
        found.add(char)
    return found.pop() if len(found) == 1 else None
