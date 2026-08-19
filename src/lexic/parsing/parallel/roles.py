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


class Separator(NamedTuple):
    """One repetition separator, with the rules a split orchestration needs.

    :ivar char: The separator character.
    :ivar container: The rule owning the ``unit item*`` arm (``members``).
    :ivar item: The repeated rule (``members-item``); ``""`` for an inline
        group (un-hoisted authored grammars — not orchestratable as-is).
    :ivar lead: The rule the item's arms lead with (``comma``); ``""`` when
        the lead is a bare literal or the arms disagree.
    """

    char: str
    container: str
    item: str
    lead: str


class Terminator(NamedTuple):
    """One repetition terminator — a repeated unit's own final character.

    ``root ::= line+`` with ``line ::= text "\\n"`` repeats a unit that ENDS
    with an anchor, so a cut after any occurrence lands between two complete
    units and each chunk is a document in its own right.

    :ivar char: The terminating character.
    :ivar container: The rule owning the repeated item.
    :ivar unit: The repeated rule.
    """

    char: str
    container: str
    unit: str


class Roles(NamedTuple):
    """One grammar's derived anchor roles.

    :ivar pairs: ``(opener, closer)`` character pairs, definition order.
    :ivar records: The separator records, definition order.
    :ivar terminators: The terminator records, definition order.
    """

    pairs: tuple[tuple[str, str], ...]
    records: tuple[Separator, ...]
    terminators: tuple[Terminator, ...] = ()

    @property
    def separators(self) -> frozenset[str]:
        """The separator characters — the scan's mark set."""
        return frozenset(record.char for record in self.records)

    @property
    def marks(self) -> frozenset[str]:
        """Every character the scan marks: separators and terminators."""
        return self.separators | {record.char for record in self.terminators}


UNIT = IrQuantifier()
"""The unit quantifier — exactly one occurrence."""


def _anchor_char(item: IrItem, anchor_set: frozenset[str]) -> str | None:
    """The item's character when it is a unit-quantified single-char anchor."""
    atom = item.atom
    if not isinstance(atom, IrLiteral) or item.quantifier != UNIT:
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


def unbounded(item: IrItem) -> bool:
    """Whether the item repeats without an upper bound."""
    return isinstance(item.quantifier.hi, IrNoneType)


def _lead_info(
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str],
) -> tuple[set[str], str] | None:
    """``(anchor chars, lead-rule name)`` for one leading item.

    The name is the OUTERMOST unit rule reference the lead resolves through
    (``comma``), or ``""`` for a bare literal lead.
    """
    char = _anchor_char(item, anchor_set)
    if char is not None:
        return ({char}, "")
    atom = item.atom
    resolvable = (
        isinstance(atom, IrRuleRef)
        and item.quantifier == UNIT
        and str(atom) in by_name
        and str(atom) not in seen
    )
    if not resolvable:
        return None
    name = str(atom)
    inner = _body_leads(by_name[name].body, by_name, anchor_set, seen | {name})
    return None if inner is None else (inner[0], name)


def _body_leads(
    body: IrAlternation,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str] = frozenset(),
) -> tuple[set[str], str] | None:
    """What EVERY arm of a repeated body leads with, or ``None``.

    A body only separates if all arms lead with anchors; the lead name is
    the arms' common rule, ``""`` when they disagree or are bare literals.
    """
    chars: set[str] = set()
    names: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        found = _lead_info(items[0], by_name, anchor_set, seen)
        if found is None:
            return None
        chars |= found[0]
        names.add(found[1])
    lead = names.pop() if len(names) == 1 else ""
    return (chars, lead)


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
    records: list[Separator] = []
    for rule in grammar.rules:
        for arm in rule.body:
            items = tuple(arm)
            pair = _arm_pair(items, anchor_set)
            if pair is not None and pair not in pairs:
                pairs.append(pair)
            for item in items:
                _repeated_separators(str(rule.name), item, by_name, anchor_set, records)
    paired = {char for pair in pairs for char in pair}
    kept = tuple(record for record in records if record.char not in paired)
    ended = tuple(
        record
        for record in _terminators(grammar, by_name, anchor_set)
        if record.char not in paired
    )
    return Roles(tuple(pairs), kept, ended)


def _trailing_char(body: IrAlternation, anchor_set: frozenset[str]) -> str | None:
    """The single anchor char EVERY arm of ``body`` ends with, else ``None``."""
    found: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        char = _anchor_char(items[-1], anchor_set)
        if char is None:
            return None
        found.add(char)
    return found.pop() if len(found) == 1 else None


def _terminators(
    grammar: IrAst, by_name: dict[str, IrRule], anchor_set: frozenset[str]
) -> list[Terminator]:
    """Every unbounded reference whose target ends with one anchor char."""
    out: list[Terminator] = []
    for rule in grammar.rules:
        for arm in rule.body:
            for item in arm:
                target = item.atom
                if not unbounded(item) or not isinstance(target, IrRuleRef):
                    continue
                unit = str(target)
                if unit not in by_name:
                    continue
                char = _trailing_char(by_name[unit].body, anchor_set)
                record = Terminator(char, str(rule.name), unit) if char else None
                if record is not None and record not in out:
                    out.append(record)
    return out


def _repeated_separators(
    container: str,
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    records: list[Separator],
) -> None:
    """Collect the separator records an unbounded item contributes."""
    if not unbounded(item):
        return
    atom = item.atom
    if isinstance(atom, IrRuleRef) and str(atom) in by_name:
        repeated, body = str(atom), by_name[str(atom)].body
    elif isinstance(atom, IrAlternation):
        repeated, body = "", atom
    else:
        return
    found = _body_leads(body, by_name, anchor_set)
    if found is None:
        return
    chars, lead = found
    for char in sorted(chars):
        record = Separator(char, container, repeated, lead)
        if record not in records:
            records.append(record)
