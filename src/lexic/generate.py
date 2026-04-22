"""Grammar-agnostic string generator from RuleSpec IR.

Works with any GBNF grammar. Pass the result of IRBuilder.build() keyed
by rule_name. Designed to be extended for R005 constrained generation.
"""

from __future__ import annotations

import random as _random

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.charclass import parse_charclass_chars
from lexic.utils.escapes import decode_gbnf_escapes


def _pick_count(min_: int, max_: int | None, rng: _random.Random) -> int:
    """Pick a repetition count.

    Optional elements (min=0) are always omitted to keep strings minimal and
    avoid newlines in ws-like rules conflicting with structural delimiters.
    Required elements bias toward minimum; allow 1 extra with 30% probability.
    Caps at min+2 to avoid exponential blowup.
    """
    if min_ == 0:
        return 0
    if min_ == max_:
        return min_
    # Cap at min+2 to avoid blowup
    hi = min(max_, min_ + 2) if max_ is not None else min_ + 2
    # 70% chance of returning min (keep output minimal and valid)
    if rng.random() < 0.7:
        return min_
    return rng.randint(min_ + 1, hi)


# Printable ASCII used as the candidate pool for negated char classes.
# Good enough for generating valid test strings across the 7 ground-truth grammars.
# Future: replace with exrex for full Unicode-aware negation if grammars grow:
#   import exrex; return "".join(exrex.getone(pattern) for _ in range(count))
_ASCII_PRINTABLE = [chr(c) for c in range(32, 127)]


def _gen_charclass(
    pattern: str, min_: int, max_: int | None, rng: _random.Random
) -> str:
    """Generate a string matching a GBNF bracket expression."""
    count = _pick_count(min_, max_, rng)
    if count == 0:
        return ""
    inner = pattern[1:-1]  # strip [ ]
    negated = inner.startswith("^")
    if negated:
        inner = inner[1:]
    chars = parse_charclass_chars(inner)
    if negated:
        excluded = set(chars)
        chars = [c for c in _ASCII_PRINTABLE if c not in excluded]
    if not chars:
        return ""
    return "".join(rng.choice(chars) for _ in range(count))


def _gen_inline_regex(
    gbnf: str, min_: int, max_: int | None, rng: _random.Random
) -> str:
    """Generate a string from one arm of an InlineRegexAtom (using gbnf form)."""
    count = _pick_count(min_, max_, rng)
    if count == 0:
        return ""
    # Parse arms from gbnf: strip outer ( ) and split on |
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    arms = [a.strip() for a in body.split("|")]
    result = []
    for _ in range(count):
        arm = rng.choice(arms).strip()
        # Strip surrounding quotes if present: "true" → true
        if arm.startswith('"') and arm.endswith('"'):
            arm = arm[1:-1]
        result.append(decode_gbnf_escapes(arm))
    return "".join(result)


def _gen_value_str(spec: RuleSpec, rng: _random.Random) -> str:
    """Generate a string for a value_str rule.

    Two structural patterns appear in the 7 grammars:
    - Sequential: LiteralAtoms interleaved with required CharClassAtoms
      (e.g. item ::= "- " [^\\n]+ "\\n") — concatenate all items.
    - Alternation arms: only LiteralAtoms / optional CharClassAtoms
      (e.g. ws ::= | " " | "\\n") — pick one LiteralAtom arm randomly.

    Distinguishing signal: presence of a required (min >= 1) CharClassAtom.
    """
    has_required_charclass = any(
        isinstance(a, CharClassAtom) and a.min >= 1 for a in spec.items
    )
    if has_required_charclass:
        # Sequential: concatenate literals + generate required char classes
        parts: list[str] = []
        for atom in spec.items:
            if isinstance(atom, LiteralAtom):
                parts.append(decode_gbnf_escapes(atom.value))
            elif isinstance(atom, CharClassAtom) and atom.min >= 1:
                parts.append(_gen_charclass(atom.pattern, atom.min, atom.max, rng))
            elif isinstance(atom, QuantifiedLiteralAtom) and atom.min >= 1:
                parts.append(decode_gbnf_escapes(atom.value) * atom.min)
            elif isinstance(atom, InlineRegexAtom) and atom.min >= 1:
                parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.min, rng))
        return "".join(parts)
    # Alternation: pick one LiteralAtom arm
    literal_arms = [a for a in spec.items if isinstance(a, LiteralAtom)]
    if literal_arms:
        return decode_gbnf_escapes(rng.choice(literal_arms).value)
    return ""


def _get_alternation_arms(spec: RuleSpec) -> list[str]:
    first = spec.items[0] if spec.items else None
    return first.arm_rule_names if isinstance(first, AlternationAtom) else []


def _gen_alternation(
    arms: list[str],
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    if not arms:
        return ""
    arm = rng.choice(arms)
    return generate(arm, specs, rng=rng, max_depth=max_depth - 1)


def _gen_sequence(
    spec: RuleSpec,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    parts: list[str] = []
    for atom in spec.items:
        if isinstance(atom, LiteralAtom):
            parts.append(decode_gbnf_escapes(atom.value))
        elif isinstance(atom, CharClassAtom):
            parts.append(_gen_charclass(atom.pattern, atom.min, atom.max, rng))
        elif isinstance(atom, QuantifiedLiteralAtom):
            count = _pick_count(atom.min, atom.max, rng)
            parts.append(decode_gbnf_escapes(atom.value) * count)
        elif isinstance(atom, InlineRegexAtom):
            parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.max, rng))
        elif isinstance(atom, RuleRefAtom):
            count = _pick_count(atom.min, atom.max, rng)
            for _ in range(count):
                parts.append(
                    generate(atom.rule_name, specs, rng=rng, max_depth=max_depth - 1)
                )
        elif isinstance(atom, (InlineAlternationAtom, AlternationAtom)):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))
    return "".join(parts)


def _gen_sequence_min_depth(
    spec: RuleSpec,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
) -> str:
    """Emit only the minimum-required atoms of a sequence rule (recursion cap)."""
    parts: list[str] = []
    for atom in spec.items:
        if isinstance(atom, LiteralAtom):
            parts.append(decode_gbnf_escapes(atom.value))
        elif isinstance(atom, CharClassAtom) and atom.min >= 1:
            parts.append(_gen_charclass(atom.pattern, atom.min, atom.min, rng))
        elif isinstance(atom, QuantifiedLiteralAtom) and atom.min >= 1:
            parts.append(decode_gbnf_escapes(atom.value) * atom.min)
        elif isinstance(atom, InlineRegexAtom) and atom.min >= 1:
            parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.min, rng))
        elif isinstance(atom, RuleRefAtom) and atom.min >= 1:
            # Keep depth at 0 — safe as long as every alternation has a non-recursive arm
            parts.append(generate(atom.rule_name, specs, rng=rng, max_depth=0))
        # Optional (min=0) rule refs and InlineAlternationAtom: skip
    return "".join(parts)


def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a valid string for rule_name from a compiled RuleSpec dict."""
    if rng is None:
        rng = _random.Random()
    spec = specs.get(rule_name)
    if spec is None:
        return ""

    if max_depth <= 0:
        if spec.kind == "alternation":
            for arm in _get_alternation_arms(spec):
                result = generate(arm, specs, rng=rng, max_depth=0)
                if result:
                    return result
            return ""
        if spec.kind == "value_str":
            return _gen_value_str(spec, rng)
        return _gen_sequence_min_depth(spec, specs, rng)

    if spec.kind == "alternation":
        return _gen_alternation(_get_alternation_arms(spec), specs, rng, max_depth)
    if spec.kind == "value_str":
        return _gen_value_str(spec, rng)
    return _gen_sequence(spec, specs, rng, max_depth)
