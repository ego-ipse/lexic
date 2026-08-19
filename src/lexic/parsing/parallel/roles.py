"""Role derivation — what a grammar's anchor characters DO at a split point.

The window scan needs three character roles: openers and closers (the
depth count), and separators (the split candidates). The demonstrable
shapes are derived from the grammar, never hardcoded per formulation:

- **Pair** — an arm opening with a unit single-char anchor literal whose
  LAST anchor literal closes over a reference or group interior:
  ``"{" ws members "}" ws`` derives the pair ``{`` → ``}`` (trailing noise
  after the closer is fine; a closer is the last structural mark, not the
  last item).
- **Separator** — the anchor literal every arm of a repeated body leads
  with: a rule referenced with an unbounded quantifier (the hoisted
  ``(sep unit)*`` shape) or an inline unbounded group. The lead resolves
  through unit rule references — ``members-item ::= comma member`` with
  ``comma ::= ","`` derives ``,``.

Single-char roles only: a multi-char separator has no character class the
scan's regex alternates over, and stays out of v2 by design.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrRuleRef,
)
from lexic.parsing.parallel.anchors import anchors


class Roles(NamedTuple):
    """One grammar's derived anchor roles.

    :ivar pairs: ``(opener, closer)`` character pairs, definition order.
    :ivar separators: The repetition-separator characters.
    """

    pairs: tuple[tuple[str, str], ...]
    separators: frozenset[str]


_UNIT = IrQuantifier()


def _anchor_char(item: IrItem, anchor_set: frozenset[str]) -> str | None:
    """The item's character when it is a unit-quantified single-char anchor."""
    atom = item.atom
    if not isinstance(atom, IrLiteral) or item.quantifier != _UNIT:
        return None
    text = str(atom)
    return text if len(text) == 1 and text in anchor_set else None


def _arm_pair(
    items: tuple[IrItem, ...], anchor_set: frozenset[str]
) -> tuple[str, str] | None:
    """The arm's opener/closer pair, when it has the bracketing shape."""
    if len(items) < 3:
        return None
    opener = _anchor_char(items[0], anchor_set)
    if opener is None:
        return None
    closer_at = next(
        (
            j
            for j in range(len(items) - 1, 0, -1)
            if _anchor_char(items[j], anchor_set) is not None
        ),
        0,
    )
    closer = _anchor_char(items[closer_at], anchor_set)
    if closer is None or closer == opener:
        return None
    interior = any(
        isinstance(item.atom, (IrRuleRef, IrAlternation)) for item in items[1:closer_at]
    )
    return (opener, closer) if interior else None


def _unbounded(item: IrItem) -> bool:
    """Whether the item repeats without an upper bound."""
    return isinstance(item.quantifier.hi, IrNoneType)


def _lead_chars(
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str],
) -> set[str] | None:
    """The anchor chars ``item`` can lead with, resolving unit rule refs."""
    char = _anchor_char(item, anchor_set)
    if char is not None:
        return {char}
    atom = item.atom
    resolvable = (
        isinstance(atom, IrRuleRef)
        and item.quantifier == _UNIT
        and str(atom) in by_name
        and str(atom) not in seen
    )
    if not resolvable:
        return None
    name = str(atom)
    return _leading_separators(by_name[name].body, by_name, anchor_set, seen | {name})


def _leading_separators(
    body: IrAlternation,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str] = frozenset(),
) -> set[str] | None:
    """The chars opening EVERY arm of a repeated body, or ``None`` when an
    arm opens with something else — a body only separates if all arms do."""
    out: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        found = _lead_chars(items[0], by_name, anchor_set, seen)
        if found is None:
            return None
        out |= found
    return out


def roles(grammar: IrAst) -> Roles:
    """Derive the grammar's opener/closer pairs and repetition separators.

    :param grammar: The grammar to analyse (the codegen grammar for a
        compiled artefact — repetition groups are hoisted there, so the
        ``(sep unit)*`` shape appears as an unbounded rule reference).
    :returns: The derived :class:`Roles`; empty roles when nothing matches.
    """
    anchor_set = anchors(grammar)
    by_name: dict[str, IrRule] = {str(rule.name): rule for rule in grammar.rules}
    pairs: list[tuple[str, str]] = []
    separators: set[str] = set()
    for rule in grammar.rules:
        for arm in rule.body:
            items = tuple(arm)
            pair = _arm_pair(items, anchor_set)
            if pair is not None and pair not in pairs:
                pairs.append(pair)
            for item in items:
                _repeated_separators(item, by_name, anchor_set, separators)
    paired = {char for pair in pairs for char in pair}
    return Roles(tuple(pairs), frozenset(separators - paired))


def _repeated_separators(
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    separators: set[str],
) -> None:
    """Collect the separators an unbounded item contributes, into ``separators``."""
    if not _unbounded(item):
        return
    atom = item.atom
    if isinstance(atom, IrRuleRef) and str(atom) in by_name:
        body = by_name[str(atom)].body
    elif isinstance(atom, IrAlternation):
        body = atom
    else:
        return
    found = _leading_separators(body, by_name, anchor_set)
    if found is not None:
        separators |= found
