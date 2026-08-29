"""Conservatively prove a possessive regular-region lowering exact."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.pda.core.charsets import CharSet


class Summary(NamedTuple):
    """Exact leading characters and nullability for one expression."""

    first: CharSet
    nullable: bool


def _union(rows: Sequence[Summary]) -> Summary:
    """Summarize an alternation."""
    first = CharSet.EMPTY
    nullable = False
    for row in rows:
        first = first.union(row.first)
        nullable = nullable or row.nullable
    return Summary(first, nullable)


def _sequence(rows: Sequence[Summary]) -> Summary:
    """Summarize a concatenation."""
    first = CharSet.EMPTY
    nullable = True
    for row in rows:
        if nullable:
            first = first.union(row.first)
        nullable = nullable and row.nullable
    return Summary(first, nullable)


def _item_summary(
    item: IrItem,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    grey: set[str],
) -> Summary | None:
    """Summarize one quantified atom."""
    atom = _atom_summary(item.atom, rules, memo, grey)
    if atom is None:
        return None
    return Summary(atom.first, int(item.quantifier.lo) == 0 or atom.nullable)


def _body_summary(
    body: IrAlternation,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    grey: set[str],
) -> Summary | None:
    """Summarize one alternation body."""
    arms: list[Summary] = []
    for arm in body:
        items: list[Summary] = []
        for item in arm:
            if not isinstance(item, IrItem):
                continue
            row = _item_summary(item, rules, memo, grey)
            if row is None:
                return None
            items.append(row)
        arms.append(_sequence(items))
    return _union(arms)


def _rule_summary(
    name: str,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    grey: set[str],
) -> Summary | None:
    """Summarize one acyclic named rule."""
    known = memo.get(name)
    if known is not None:
        return known
    rule = rules.get(name)
    if rule is None or name in grey:
        return None
    grey.add(name)
    row = _body_summary(rule.body, rules, memo, grey)
    grey.remove(name)
    if row is not None:
        memo[name] = row
    return row


def _atom_summary(
    atom: IrSelf,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    grey: set[str],
) -> Summary | None:
    """Summarize one simple regular atom."""
    if isinstance(atom, IrLiteral):
        return Summary(
            CharSet.EMPTY if not atom else CharSet.from_chars(atom[0]),
            not atom,
        )
    if isinstance(atom, IrCharClass):
        return Summary(CharSet.from_charclass(atom), False)
    if isinstance(atom, IrNot):
        inner = atom[0]
        if not isinstance(inner, IrCharClass):
            return None
        return Summary(CharSet.from_not(inner), False)
    if isinstance(atom, IrRuleRef):
        return _rule_summary(str(atom), rules, memo, grey)
    if isinstance(atom, IrAlternation):
        return _body_summary(atom, rules, memo, grey)
    return None


def _overlapping_arms(
    body: IrAlternation,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
) -> bool:
    """Whether ordered atomic arms can commit before the correct arm."""
    arms = tuple(body)
    seen = CharSet.EMPTY
    nullable = False
    for index, arm in enumerate(arms):
        row = _body_summary(IrAlternation(arm), rules, memo, set())
        if (
            row is None
            or seen.overlaps(row.first)
            or (nullable and row.nullable)
            or (row.nullable and index != len(arms) - 1)
        ):
            return True
        seen = seen.union(row.first)
        nullable = nullable or row.nullable
    return False


def _upper(item: IrItem) -> int | None:
    """The finite upper bound, or ``None`` when unbounded."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


def _prove_atom(
    atom: IrSelf,
    follow: CharSet,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    active: set[tuple[str, CharSet]],
) -> bool:
    """Prove an atom deterministic under its caller's next characters."""
    if isinstance(atom, (IrLiteral, IrCharClass)):
        return True
    if isinstance(atom, IrNot):
        return isinstance(atom[0], IrCharClass)
    if isinstance(atom, IrAlternation):
        return _prove_body(atom, follow, rules, memo, active)
    if not isinstance(atom, IrRuleRef):
        return False
    name = str(atom)
    key = (name, follow)
    if key in active:
        return False
    rule = rules.get(name)
    if rule is None:
        return False
    active.add(key)
    proved = _prove_body(rule.body, follow, rules, memo, active)
    active.remove(key)
    return proved


def _prove_arm(
    arm: Sequence[IrItem],
    follow: CharSet,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    active: set[tuple[str, CharSet]],
) -> bool:
    """Prove every possessive boundary in one concatenation."""
    suffix = Summary(CharSet.EMPTY, True)
    for item in reversed(arm):
        atom = _atom_summary(item.atom, rules, memo, set())
        if atom is None:
            return False
        after = suffix.first
        if suffix.nullable:
            after = after.union(follow)
        lo = int(item.quantifier.lo)
        hi = _upper(item)
        repeats = hi is None or hi > 1
        variable = hi is None or hi != lo
        if atom.nullable and repeats:
            return False
        if (variable or atom.nullable) and atom.first.overlaps(after):
            return False
        atom_follow = after.union(atom.first) if repeats else after
        if not _prove_atom(item.atom, atom_follow, rules, memo, active):
            return False
        quantified = Summary(atom.first, lo == 0 or atom.nullable)
        suffix = _sequence((quantified, suffix))
    return True


def _prove_body(
    body: IrAlternation,
    follow: CharSet,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
    active: set[tuple[str, CharSet]],
) -> bool:
    """Prove ordered arms and every inner possessive boundary."""
    if _overlapping_arms(body, rules, memo):
        return False
    for arm in body:
        items = tuple(item for item in arm if isinstance(item, IrItem))
        if not _prove_arm(items, follow, rules, memo, active):
            return False
    return True


def prove_region(
    rules: Mapping[str, IrRule],
    opener: str,
    entry: tuple[str, ...],
    separator: str,
    terminator: str,
) -> bool:
    """Prove the delegated repeated interior's possessive boundaries exact.

    The surrounding parser owns the opener and terminator. The delegated fast
    path begins after the opener and stops before the terminator, so only the
    entry, separator-entry, and their two possible following boundaries are
    authoritative here.
    """
    memo: dict[str, Summary] = {}
    entry_rows: list[Summary] = []
    for name in entry:
        row = _rule_summary(name, rules, memo, set())
        if row is None:
            return False
        entry_rows.append(row)
    separator_row = _rule_summary(separator, rules, memo, set())
    terminator_row = _rule_summary(terminator, rules, memo, set())
    opener_row = _rule_summary(opener, rules, memo, set())
    if separator_row is None or terminator_row is None or opener_row is None:
        return False
    entry_summary = _sequence(entry_rows)
    boundary = separator_row.first.union(terminator_row.first)
    if not _prove_named_sequence(entry, boundary, rules, memo):
        return False
    if not _prove_named_sequence((separator, *entry), boundary, rules, memo):
        return False
    return not entry_summary.nullable


def _prove_named_sequence(
    names: tuple[str, ...],
    follow: CharSet,
    rules: Mapping[str, IrRule],
    memo: dict[str, Summary],
) -> bool:
    """Prove a concatenation of named rules under an external boundary."""
    items = tuple(IrItem(IrRuleRef(name)) for name in names)
    return _prove_arm(items, follow, rules, memo, set())
