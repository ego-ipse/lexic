"""Grammar-agnostic random string generator over a grammar ``IrAst``.

Walks a rules-by-name view of a (canonical) grammar: each rule body is an
:class:`IrAlternation` of arms, an arm a sequence of items. Generation picks a
random arm and expands each item by its atom kind and quantifier, recursing on
:class:`IrRuleRef` occurrences. ``max_depth`` decrements on each ref expansion.
"""

from __future__ import annotations

import random as _random

from lexic.ir.base import IrNoneType
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

_ASCII_PRINTABLE = [chr(c) for c in range(32, 127)]

Rules = dict[str, IrRule]


def _pick_count(q: IrQuantifier, rng: _random.Random) -> int:
    """Pick a repetition count within the quantifier's bounds."""
    if q.lo == 0:
        return 0
    if q.hi == q.lo:
        return q.lo
    hi = q.lo + 2 if isinstance(q.hi, IrNoneType) else min(q.hi, q.lo + 2)
    if rng.random() < 0.7:
        return q.lo
    return rng.randint(q.lo + 1, hi)


def _gen_charclass(
    atom: IrCharClass, q: IrQuantifier, rng: _random.Random, *, negated: bool = False
) -> str:
    """Generate for a charclass by picking chars from it and applying the quantifier."""
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    if negated:
        excluded = {chr(c) for c in atom.members()}
        chars = [c for c in _ASCII_PRINTABLE if c not in excluded]
        if not chars:
            return ""
        return "".join(rng.choice(chars) for _ in range(count))
    return "".join(chr(atom.sample(rng)) for _ in range(count))


def _gen_group(
    atom: IrAlternation,
    q: IrQuantifier,
    rules: Rules,
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for an inline group by expanding its body and applying the quantifier."""
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    return "".join(_gen_alternation(atom, rules, rng, max_depth) for _ in range(count))


def _gen_atom(
    item: IrItem,
    rules: Rules,
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate the text for one item by its atom kind and quantifier."""
    atom, q = item.atom, item.quantifier
    if isinstance(atom, IrLiteral):
        return atom * _pick_count(q, rng) if q != IrQuantifier(1, 1) else atom
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            return _gen_charclass(inner, q, rng, negated=True)
    if isinstance(atom, IrCharClass):
        return _gen_charclass(atom, q, rng)
    if isinstance(atom, IrRuleRef):
        count = _pick_count(q, rng)
        return "".join(
            generate(str(atom), rules, rng=rng, max_depth=max_depth - 1)
            for _ in range(count)
        )
    if isinstance(atom, IrAlternation):
        return _gen_group(atom, q, rules, rng, max_depth)
    return ""


def _gen_sequence(
    seq: IrSequence,
    rules: Rules,
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for a sequence arm by concatenating its items."""
    return "".join(_gen_atom(it, rules, rng, max_depth) for it in seq)


def _gen_alternation(
    body: IrAlternation,
    rules: Rules,
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for a rule body by picking a random arm and expanding it."""
    if not body:
        return ""
    arm = rng.choice(body)
    return _gen_sequence(arm, rules, rng, max_depth)


def generate(
    rule_name: str,
    rules: Rules,
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a random string matching the named rule.

    :param rule_name: The rule to expand.
    :param rules: The grammar as a rule-name → :class:`IrRule` mapping.
    :param rng: Random source; a fresh one is created when omitted.
    :param max_depth: Ref-expansion budget, decremented on each recursion.
    :returns: A random string in the rule's language (``""`` for an unknown rule).
    """
    if rng is None:
        rng = _random.Random()
    rule = rules.get(rule_name)
    if rule is None:
        return ""
    return _gen_alternation(rule.body, rules, rng, max_depth)
