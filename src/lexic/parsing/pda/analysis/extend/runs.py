"""Runs — what a run lets EXTEND drop, read off the grammar alone.

A run is an item ``C*`` over one character set. Where two readings of a
sequence part inside a run class S, R3 (:mod:`.lengthen`) needs three facts
about the strings that follow, none of which reads the EXTEND maps:

- :func:`led` — every string beginning in S is a droppable leading S-run, then
  a character outside S;
- :func:`heads` — which characters those are;
- :func:`apart` — two arms sharing first characters part on such a run, so
  neither arm's string is a proper prefix of the other's.

Each is kept in the build's :class:`~.maps.Confinement` once read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAtom,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.extend.maps import Arm, Confinement, RunKey
from lexic.parsing.pda.analysis.predicates import item_nullable, seq_nullable
from lexic.parsing.pda.core.charsets import CharSet

if TYPE_CHECKING:  # `analysis` imports this module, so the reference is mutual
    from lexic.parsing.pda.analysis.analysis import GrammarAnalysis

_DEPTH = 24
"""How many items deep :func:`led` and :func:`heads` read before answering
conservatively — a recursive rule unfolds without end."""

_UNIT_DEPTH = 8
"""How many unit rules :func:`is_run` and :func:`leading_run` read through."""


def _one_char(_d: object, n: IrSelf, _nc: object) -> bool:
    """A literal is one character set only when it is one character long."""
    return len(str(n)) == 1


def _a_set(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A class, or its negation, is one character set."""
    return True


def _not_a_set(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A token, a reference or a group is no single character set."""
    return False


def _no_arms(_d: object, _n: IrSelf, _nc: object) -> None:
    """A terminal stands for no arms."""
    return None


def _ruleref_arms(d: GrammarAnalysis, n: IrSelf, _nc: object) -> list[Arm] | None:
    """A reference stands for its rule's arms; an undefined one for none."""
    rule = d.rules.get(str(n))
    return None if rule is None else list(rule.body)


def _group_arms(_d: object, n: IrSelf, _nc: object) -> list[Arm]:
    """A group stands for its own arms."""
    assert isinstance(n, IrAlternation)
    return list(n)


ONE_SET: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_one_char)),
    IrAction(IrCharClass, IrLambda(_a_set)),
    IrAction(IrNot, IrLambda(_a_set)),
    IrAction(IrAlphabet, IrLambda(_not_a_set)),
    IrAction(IrRuleRef, IrLambda(_not_a_set)),
    IrAction(IrAlternation, IrLambda(_not_a_set)),
)
"""Whether an atom matches exactly one character of one set."""

ARMS: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_no_arms)),
    IrAction(IrCharClass, IrLambda(_no_arms)),
    IrAction(IrNot, IrLambda(_no_arms)),
    IrAction(IrAlphabet, IrLambda(_no_arms)),
    IrAction(IrRuleRef, IrLambda(_ruleref_arms)),
    IrAction(IrAlternation, IrLambda(_group_arms)),
)
"""The arms an atom stands for, ``None`` for a terminal."""


def atom_arms(d: GrammarAnalysis, atom: IrAtom) -> list[Arm] | None:
    """The arms ``atom`` stands for — a rule's or a group's — or ``None``."""
    return cast("list[Arm] | None", ARMS.resolve(atom).eval(d, atom, ()))


def is_run(d: GrammarAnalysis, item: IrItem) -> bool:
    """Whether ``item`` is ``C*`` over one character set, directly or as a
    unit rule's sole item."""
    for _ in range(_UNIT_DEPTH + 1):
        atom, quantifier = item.atom, item.quantifier
        if int(quantifier.lo) == 0 and quantifier.unbounded():
            return bool(ONE_SET.resolve(atom).eval(d, atom, ()))
        arms = atom_arms(d, atom) if quantifier.once() else None
        if arms is None or len(arms) != 1 or len(arms[0]) != 1:
            return False
        item = arms[0][0]
    return False


def run_chars(d: GrammarAnalysis, memo: Confinement) -> CharSet:
    """Every character some run of the grammar holds; R3 asks its K inside."""
    if not memo.runs:
        out = CharSet.EMPTY
        for rule in d.rules.values():
            for arm in rule.body:
                for item in arm:
                    if is_run(d, item):
                        out = out.union(d.atom_first(item.atom))
        memo.runs.append(out)
    return memo.runs[0]


def leading_run(
    d: GrammarAnalysis, memo: Confinement, items: Arm, starts: CharSet
) -> CharSet | None:
    """The class of the runs a string of ``items`` begins with, where it begins
    in ``starts``; ``None`` where one such string begins otherwise, or where
    reading it takes more than :data:`_UNIT_DEPTH` rules."""
    key = _key(items, starts)
    held = memo.leads.get(key)
    if held is None:
        held = memo.leads[key] = (tuple(items), _leading_run(d, items, starts, 0))
    return held[1]


def _key(items: Arm, run: CharSet) -> RunKey:
    """A memo key for ``items`` read against ``run``, by the items' identity."""
    return tuple(map(id, items)), run


def _leading_run(
    d: GrammarAnalysis, items: Arm, starts: CharSet, depth: int
) -> CharSet | None:
    """:func:`leading_run`, ``depth`` rules in, read past each item that can
    vanish."""
    out = CharSet.EMPTY
    for item in items:
        if d.atom_first(item.atom).overlaps(starts):
            got = _item_run(d, item, starts, depth)
            if got is None:
                return None
            out = out.union(got)
        if not item_nullable(d, item):
            break
    return out


def _item_run(
    d: GrammarAnalysis, item: IrItem, starts: CharSet, depth: int
) -> CharSet | None:
    """The run class one item begins with where it begins in ``starts``."""
    if is_run(d, item):
        return d.atom_first(item.atom)
    arms = atom_arms(d, item.atom)
    if arms is None or depth > _UNIT_DEPTH:
        return None
    out = CharSet.EMPTY
    for arm in arms:
        got = _leading_run(d, arm, starts, depth + 1)
        if got is None:
            return None
        out = out.union(got)
    return out


def led(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int = 0
) -> bool:
    """Whether every string of ``items`` beginning in ``run`` is a droppable
    leading ``run`` prefix, then a character outside ``run``."""
    key = _key(items, run)
    held = memo.led.get(key)
    if held is None:
        held = memo.led[key] = (tuple(items), _led(d, memo, items, run, depth))
    return held[1]


def _led(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int
) -> bool:
    """:func:`led`, read at the first item."""
    if not items or depth > _DEPTH:
        return not items
    item, rest = items[0], items[1:]
    if not d.atom_first(item.atom).overlaps(run):
        nullable = item_nullable(d, item)
        return led(d, memo, rest, run, depth + 1) if nullable else True
    if is_run(d, item):
        return not seq_nullable(d, rest) and led(d, memo, rest, run, depth + 1)
    return _led_arms(d, memo, items, run, depth)


def _led_arms(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int
) -> bool:
    """:func:`led` at a first item that stands for arms: its absence, where it
    can be absent, and each arm followed by the rest.

    A further occurrence is not read. An arm reaches what follows it only
    through items that can vanish, so such an arm is nullable, and so is the
    item: its remaining occurrences vanish exactly when the rest does, and
    reading them reads the same arms again before the rest."""
    item, rest = items[0], items[1:]
    arms = atom_arms(d, item.atom)
    lo, hi = int(item.quantifier.lo), item.quantifier.upper()
    if arms is None:
        return False
    if hi == 0:
        return led(d, memo, rest, run, depth + 1)
    if lo == 0 and not led(d, memo, rest, run, depth + 1):
        return False
    return all(led(d, memo, [*arm, *rest], run, depth + 1) for arm in arms)


def heads(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int = 0
) -> CharSet:
    """The first character outside ``run`` of each string of ``items``: its
    first, or the one past its leading ``run`` prefix. Read as :func:`led`
    reads; too deep to read is anything."""
    key = _key(items, run)
    held = memo.heads.get(key)
    if held is None:
        held = memo.heads[key] = (tuple(items), _heads(d, memo, items, run, depth))
    return held[1]


def _heads(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int
) -> CharSet:
    """:func:`heads`, read at the first item."""
    if not items or depth > _DEPTH:
        return CharSet.EMPTY if not items else CharSet.ANY
    item, rest = items[0], items[1:]
    first = d.atom_first(item.atom)
    if not first.overlaps(run):
        nullable = item_nullable(d, item)
        return first.union(heads(d, memo, rest, run, depth + 1)) if nullable else first
    if is_run(d, item):
        return first.subtract(run).union(heads(d, memo, rest, run, depth + 1))
    return _heads_arms(d, memo, items, run, depth)


def _heads_arms(
    d: GrammarAnalysis, memo: Confinement, items: Arm, run: CharSet, depth: int
) -> CharSet:
    """:func:`heads` at a first item that stands for arms, read as
    :func:`_led_arms` reads it."""
    item, rest = items[0], items[1:]
    arms = atom_arms(d, item.atom)
    if arms is None:
        return CharSet.ANY
    lo, hi = int(item.quantifier.lo), item.quantifier.upper()
    out = CharSet.EMPTY
    if lo == 0 or hi == 0:
        out = heads(d, memo, rest, run, depth + 1)
    if hi == 0:
        return out
    for arm in arms:
        out = out.union(heads(d, memo, [*arm, *rest], run, depth + 1))
    return out


def apart(d: GrammarAnalysis, memo: Confinement, one: Arm, other: Arm) -> bool:
    """Whether two arms sharing first characters part on a shared leading run:
    both are led by it, and their heads never meet."""
    if run_chars(d, memo).is_empty():
        return False
    key = (id(one), id(other))
    held = memo.apart.get(key)
    if held is not None and held[0] is one and held[1] is other:
        return held[2]
    got = _apart(d, memo, one, other)
    memo.apart[key] = (one, other, got)
    return got


def _apart(d: GrammarAnalysis, memo: Confinement, one: Arm, other: Arm) -> bool:
    """:func:`apart`, unkept."""
    first = d.seq_first(one)
    shared = first.subtract(first.subtract(d.seq_first(other)))
    if not shared.within(run_chars(d, memo)):
        return False
    mine, theirs = (
        leading_run(d, memo, one, shared),
        leading_run(d, memo, other, shared),
    )
    if mine is None or theirs is None:
        return False
    run = mine.union(theirs)
    if run.is_empty() or not shared.within(run):
        return False
    if not (led(d, memo, one, run) and led(d, memo, other, run)):
        return False
    return not heads(d, memo, one, run).overlaps(heads(d, memo, other, run))
