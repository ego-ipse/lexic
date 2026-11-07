"""Where a bracket's own run stands — arm sites, repeated bodies, and whether
an arm holds a run.

The walks every role derivation reads (:mod:`~lexic.parsing.parallel.roles.derive`)
and the run predicate the region plans ask: what an arm opens and closes on,
which bodies an arm repeats, and whether an arm holds ``head tail*`` itself.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrNoneType,
    IrRuleRef,
)
from lexic.parsing.parallel.discovery.shapes import (
    RuleTable,
    rule_table,
)


class BracketArm(NamedTuple):
    """One arm opening on one character and closing on another.

    :ivar opener: The character item 0 spells.
    :ivar closer: The character the LAST later item with one spells.
    :ivar rule: The rule the arm belongs to.
    :ivar arm: The arm's index in that rule's body.
    :ivar closes: The closer's item index.
    """

    opener: str
    closer: str
    rule: str
    arm: int
    closes: int


def bracket_arms(
    grammar: IrAst, char_of: Callable[[IrItem], str | None], enclosing: bool
) -> list[BracketArm]:
    """Every arm of three items or more that opens and closes on two different
    characters, read through ``char_of``, in definition order.

    The one walk both pair derivations read; each brings its own reader.
    :func:`~...roles.derive.roles` reads anchors and asks ``enclosing``:
    DELIMITING, not nesting, is its test, and a pair also serves
    :func:`~...stitch.safety.owner_excludes`, which attributes what stands
    between the delimiters to the nested region, so the arm must hold a
    reference or group there. A flat ``"{" inner "}"`` owns its own commas just
    as a nesting one does, so nothing narrower is asked. The region scan reads
    literals and keeps the provenance its stray reading needs.
    """
    out: list[BracketArm] = []
    for rule in grammar.rules:
        for at, arm in enumerate(rule.body):
            items = tuple(arm)
            if len(items) < 3:
                continue
            spelled = [char_of(item) for item in items]
            closes = max((k for k, char in enumerate(spelled) if char and k), default=0)
            opener, closer = spelled[0], spelled[closes]
            if not closes or not opener or closer == opener:
                continue
            if enclosing and not any(
                isinstance(item.atom, (IrRuleRef, IrAlternation))
                for item in items[1:closes]
            ):
                continue
            out.append(BracketArm(opener, str(closer), str(rule.name), at, closes))
    return out


class RepeatedBody(NamedTuple):
    """A body some arm repeats.

    :ivar container: The rule owning the arm.
    :ivar item: The repeated rule; ``""`` for an inline group.
    :ivar body: What repeats.
    """

    container: str
    item: str
    body: IrAlternation


def repeated_bodies(grammar: IrAst, nested: bool) -> list[RepeatedBody]:
    """Every unbounded body an arm repeats, in definition order; with
    ``nested``, the ones inside its groups too.

    The one walk both separator derivations read. A repetition is often written
    inside another group (RFC json spells its member list
    ``[ member *( value-separator member ) ]``), which the region scan reaches.
    :func:`~...roles.derive.roles` records a separator against the arm's own
    repetition, so it reads the top level only.
    """
    rule_map = rule_table(grammar)
    out: list[RepeatedBody] = []
    for rule in grammar.rules:
        for arm in rule.body:
            _collect(str(rule.name), tuple(arm), rule_map, nested, out)
    return out


def _collect(
    container: str,
    items: tuple[IrItem, ...],
    rule_map: RuleTable,
    nested: bool,
    out: list[RepeatedBody],
) -> None:
    """:func:`repeated_bodies` over one run of items."""
    for item in items:
        atom = item.atom
        target = rule_map.get(str(atom)) if isinstance(atom, IrRuleRef) else None
        if item.quantifier.unbounded() and target is not None:
            out.append(RepeatedBody(container, str(atom), target.body))
        elif item.quantifier.unbounded() and isinstance(atom, IrAlternation):
            out.append(RepeatedBody(container, "", atom))
        if nested and isinstance(atom, IrAlternation):
            for arm in atom:
                _collect(container, tuple(arm), rule_map, nested, out)


def run_owners(rule: str, arm: tuple[IrItem, ...], rules: RuleTable) -> set[str]:
    """The bracket rule if its arm holds a run (:func:`holds_run`), else the refs inside."""
    if holds_run(arm, rules):
        return {rule}
    return {
        str(ref)
        for item in arm[1:-1]
        if not isinstance(ref := item.unit_ref(), IrNoneType)
        and (target := rules.get(str(ref))) is not None
        and not isinstance(inner := target.sole_arm(), IrNoneType)
        and holds_run(tuple(inner), rules)
    }


def holds_run(arm: tuple[IrItem, ...], rules: RuleTable) -> bool:
    """Whether an arm holds ``head tail*``: an unbounded one-arm tail, lead head."""
    for head, tail in zip(arm, arm[1:]):
        ref = rules.get(str(tail.atom)) if isinstance(tail.atom, IrRuleRef) else None
        body = tail.atom if ref is None else ref.body
        if tail.quantifier.unbounded() and isinstance(body, IrAlternation):
            if len(body) == 1 and len(body[0]) == 2 and body[0][1].atom == head.atom:
                return True
    return False
