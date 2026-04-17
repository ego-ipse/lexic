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


def _parse_escape(s: str, i: int) -> tuple[str, int]:
    """Parse a GBNF escape sequence starting at s[i+1]. Returns (char, new_i)."""
    c = s[i + 1]
    if c == "n":
        return "\n", i + 2
    if c == "t":
        return "\t", i + 2
    if c == "r":
        return "\r", i + 2
    if c == '"':
        return '"', i + 2
    if c == "\\":
        return "\\", i + 2
    if c == "x" and i + 3 < len(s):
        return chr(int(s[i + 2 : i + 4], 16)), i + 4
    if c == "u" and i + 5 < len(s):
        return chr(int(s[i + 2 : i + 6], 16)), i + 6
    if c == "U" and i + 9 < len(s):
        return chr(int(s[i + 2 : i + 10], 16)), i + 10
    return c, i + 2


def _parse_charclass_chars(inner: str) -> list[str]:
    """Parse the interior of a GBNF bracket expression into a list of chars.

    Supports ranges (a-z), direct Unicode, and escape sequences
    (\\n \\t \\r \\xXX \\uXXXX \\UXXXXXXXX).
    """
    chars: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            ch, i = _parse_escape(inner, i)
            # Check for range after escape: e.g. \x00-\x1F
            if i < len(inner) and inner[i] == "-" and i + 1 < len(inner):
                if inner[i + 1] == "\\" and i + 2 < len(inner):
                    end_ch, i = _parse_escape(inner, i + 1)
                else:
                    end_ch = inner[i + 1]
                    i += 2
                chars.extend(chr(c) for c in range(ord(ch), ord(end_ch) + 1))
            else:
                chars.append(ch)
        elif i + 2 < len(inner) and inner[i + 1] == "-":
            chars.extend(chr(c) for c in range(ord(inner[i]), ord(inner[i + 2]) + 1))
            i += 3
        else:
            chars.append(inner[i])
            i += 1
    return chars


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
    chars = _parse_charclass_chars(inner)
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


def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a valid string for rule_name from a compiled RuleSpec dict.

    Works with any grammar — pass {rule_name: spec} from IRBuilder.build().
    max_depth caps recursion on self-referential rules (e.g., expr -> term -> expr).
    rng accepts an explicit Random instance for deterministic generation.
    """
    if rng is None:
        rng = _random.Random()

    if max_depth <= 0:
        spec = specs.get(rule_name)
        if spec is None:
            return ""
        if spec.kind == "alternation":
            first = spec.items[0] if spec.items else None
            arms = first.arm_rule_names if isinstance(first, AlternationAtom) else []
            for arm in arms:
                result = generate(arm, specs, rng=rng, max_depth=0)
                if result:
                    return result
            return ""
        # sequence / value_str: emit literals and minimum required chars.
        # For required (min >= 1) rule refs, recurse at depth=0 so alternations
        # can pick a non-recursive arm (e.g. ident/num before term-arm3).
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

    spec = specs.get(rule_name)
    if spec is None:
        return ""

    if spec.kind == "alternation":
        first = spec.items[0] if spec.items else None
        arms = first.arm_rule_names if isinstance(first, AlternationAtom) else []
        if not arms:
            return ""
        arm = rng.choice(arms)
        return generate(arm, specs, rng=rng, max_depth=max_depth - 1)

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

        elif isinstance(atom, InlineAlternationAtom):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))

        elif isinstance(atom, AlternationAtom):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))

    return "".join(parts)
