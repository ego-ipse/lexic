"""Grammar-agnostic string generator from RuleSpec IR."""

from __future__ import annotations

import random as _random

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

_ASCII_PRINTABLE = [chr(c) for c in range(32, 127)]


def _pick_count(q: Quantifier, rng: _random.Random) -> int:
    """Pick a repetition count."""
    if q.min == 0:
        return 0
    if q.max == q.min:
        return q.min
    hi = min(q.max, q.min + 2) if q.max is not None else q.min + 2
    if rng.random() < 0.7:
        return q.min
    return rng.randint(q.min + 1, hi)


def _gen_charclass(
    atom: IrCharClass, q: Quantifier, rng: _random.Random, *, negated: bool = False
) -> str:
    """Generate for a charclass by picking random chars from it and applying the quantifier."""
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    chars = parse_charclass_chars(atom.value)
    if negated:
        excluded = set(chars)
        chars = [c for c in _ASCII_PRINTABLE if c not in excluded]
    if not chars:
        return ""
    return "".join(rng.choice(chars) for _ in range(count))


def _gen_group(
    atom: IrGroup,
    q: Quantifier,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for a group by generating for its body and applying the quantifier."""
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    out: list[str] = []
    for _ in range(count):
        arm = rng.choice(atom.body.arms)
        out.append(_gen_sequence(arm, specs, rng, max_depth))
    return "".join(out)


def _gen_atom(
    item: IrItem,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for an atom rule by its kind."""
    atom, q = item.atom, item.quantifier
    if isinstance(atom, IrLiteral):
        return atom.value * _pick_count(q, rng) if q != Quantifier(1, 1) else atom.value
    if isinstance(atom, IrNot) and isinstance(atom.body, IrCharClass):
        return _gen_charclass(atom.body, q, rng, negated=True)
    if isinstance(atom, IrCharClass):
        return _gen_charclass(atom, q, rng)
    if isinstance(atom, IrRuleRef):
        count = _pick_count(q, rng)
        return "".join(
            generate(atom.value, specs, rng=rng, max_depth=max_depth - 1)
            for _ in range(count)
        )
    if isinstance(atom, IrGroup):
        return _gen_group(atom, q, specs, rng, max_depth)
    return ""


def _gen_sequence(
    seq: IrSequence,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for a sequence rule by concatenating its items."""
    return "".join(_gen_atom(it, specs, rng, max_depth) for it in seq.items)


def _gen_alternation(
    alt: IrAlternation,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for an alternation rule by picking a random arm."""
    if not alt.arms:
        return ""
    arm = rng.choice(alt.arms)
    return _gen_sequence(arm, specs, rng, max_depth)


def _gen_alternation_kind(
    spec: RuleSpec,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    """Generate for an alternation rule by picking a random arm."""
    arm_names = [
        it.atom.value
        for it in spec.items
        if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
    ]
    if not arm_names:
        return ""
    arm = rng.choice(arm_names)
    return generate(arm, specs, rng=rng, max_depth=max_depth - 1)


def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a random string matching the given rule."""
    if rng is None:
        rng = _random.Random()
    spec = specs.get(rule_name)
    if spec is None:
        return ""
    if spec.kind == "alternation":
        return _gen_alternation_kind(spec, specs, rng, max_depth)
    if spec.kind == "value_str":
        if spec.items and isinstance(spec.items[0], IrAlternation):
            return _gen_alternation(spec.items[0], specs, rng, max_depth)
        return "".join(
            _gen_atom(it, specs, rng, max_depth)
            for it in spec.items
            if isinstance(it, IrItem)
        )
    return "".join(
        _gen_atom(it, specs, rng, max_depth)
        for it in spec.items
        if isinstance(it, IrItem)
    )
