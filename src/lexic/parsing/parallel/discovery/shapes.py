"""Arm shapes — the questions the split analyses ask a grammar's arms.

:mod:`~lexic.parsing.parallel.discovery.interiors`,
:mod:`~lexic.parsing.parallel.discovery.regions`,
:mod:`~lexic.parsing.parallel.roles` and
:mod:`~lexic.parsing.parallel.stitch.safety` read a grammar for the same
handful of facts: what one item spells, whether it repeats, what every arm of
an alternation carries at one end, and which characters a derivation can emit
— anywhere, or first. They live here so that changing what "spells one
character" means reaches all of them at once.
"""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
)
from lexic.parsing.pda.core.charsets import CharSet

UNIT = IrQuantifier()
"""The unit quantifier — exactly one occurrence."""


def unbounded(item: IrItem) -> bool:
    """Whether the item repeats without an upper bound."""
    return isinstance(item.quantifier.hi, IrNoneType)


def _one_char(text: str) -> bool:
    """Whether a spelling is exactly one character."""
    return len(text) == 1


def _any_text(text: str) -> bool:
    """Whether a spelling carries anything at all."""
    return bool(text)


def _spelling(
    item: IrItem, rule_map: dict[str, IrRule], accept: Callable[[str], bool]
) -> str | None:
    """The literal an item spells, through one unit rule reference.

    A grammar may name its punctuation (``begin-object ::= ws "{" ws``), and
    the punctuation may sit among noise, so a rule spells one literal when
    exactly one of its items does.
    """
    if item.quantifier != UNIT:
        return None
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom) if accept(str(atom)) else None
    if not isinstance(atom, IrRuleRef):
        return None
    target = rule_map.get(str(atom))
    arms = tuple(target.body) if target is not None else ()
    if len(arms) != 1:
        return None
    spelled = [
        text
        for inner in tuple(arms[0])
        if (text := _spelling(inner, rule_map, accept)) is not None
    ]
    return spelled[0] if len(spelled) == 1 else None


def literal_char(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The single character an item spells, through one unit rule reference."""
    return _spelling(item, rule_map, _one_char)


def literal_text(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The literal string an item spells, through one unit rule reference.

    A delimiter is not always one character (```` ``` ```` fences a block), so
    the interior analysis reads the whole spelling where the anchor analyses
    read only single-character ones.
    """
    return _spelling(item, rule_map, _any_text)


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


def _class_of(atom: IrNot) -> CharSet:
    """The character set a negation atom accepts."""
    inner = atom[0]
    return CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY


def emits(
    item: IrItem,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one item can emit ``char`` somewhere in its derivations.

    :param hidden: Rule names the asking scan never reads. A nested delimited
        region names its own rule there; passing EVERY name asks what an arm
        spells directly, with no reference followed.
    :param path: Rules already on the derivation path, so a cycle terminates.
    """
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return char in str(atom)
    if isinstance(atom, IrCharClass):
        return CharSet.from_charclass(atom).has(char)
    if isinstance(atom, IrNot):
        return _class_of(atom).has(char)
    if isinstance(atom, IrAlternation):
        return any(
            emits(inner, char, rule_map, hidden, path) for arm in atom for inner in arm
        )
    if isinstance(atom, IrRuleRef):
        return _ref_emits(str(atom), char, rule_map, hidden, path)
    return True


def _ref_emits(
    name: str,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a referenced rule can emit ``char``; unknown names can."""
    if name in hidden:
        return False
    target = rule_map.get(name)
    if target is None:
        return True
    return name not in path and rule_emits(
        target, char, rule_map, hidden, path | {name}
    )


def rule_emits(
    rule: IrRule,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a rule has any flat derivation that emits ``char``."""
    return any(
        emits(item, char, rule_map, hidden, path) for arm in rule.body for item in arm
    )


def leads_with(
    items: tuple[IrItem, ...],
    char: str,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether an arm can derive a string whose FIRST character is ``char``.

    Unknown atoms and cycles answer yes: a caller uses this to prove that only
    ONE arm can open with a character, and an unprovable arm must not certify.
    """
    for item in items:
        if _item_leads(item, char, rule_map, path):
            return True
        if not derives_empty(item, rule_map, frozenset()):
            return False
    return False


def _item_leads(
    item: IrItem, char: str, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether one item can derive a string starting with ``char``."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom).startswith(char)
    if isinstance(atom, IrCharClass):
        return CharSet.from_charclass(atom).has(char)
    if isinstance(atom, IrNot):
        return _class_of(atom).has(char)
    if isinstance(atom, IrAlternation):
        return any(leads_with(tuple(arm), char, rule_map, path) for arm in atom)
    if isinstance(atom, IrRuleRef):
        return _ref_leads(str(atom), char, rule_map, path)
    return True


def _ref_leads(
    name: str, char: str, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether a referenced rule can open with ``char``; unknown names can."""
    target = rule_map.get(name)
    if target is None or name in path:
        return True
    return any(
        leads_with(tuple(arm), char, rule_map, path | {name}) for arm in target.body
    )


def derives_empty(
    item: IrItem, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether an item can derive the empty string."""
    if item.quantifier.lo == 0:
        return True
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return not str(atom)
    if isinstance(atom, IrAlternation):
        return any(_arm_empty(tuple(arm), rule_map, path) for arm in atom)
    if not isinstance(atom, IrRuleRef):
        return False
    target = rule_map.get(str(atom))
    if target is None or str(atom) in path:
        return True
    return any(
        _arm_empty(tuple(arm), rule_map, path | {str(atom)}) for arm in target.body
    )


def _arm_empty(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether every item of one arm can derive the empty string."""
    return all(derives_empty(item, rule_map, path) for item in items)
