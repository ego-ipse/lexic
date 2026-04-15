"""Rule classification for GBNF codegen.

Classifies each parsed rule into one of:
- semantic_terminal: maps to a model with a single `value: str` field
- pure_literal_alt: alternation of literal strings, also `value: str`
- named_alt: alternation of named rule refs → abstract base + subclasses
- sequence: ordered fields
"""

from __future__ import annotations

import re

from .ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)


# ── Sequence helpers ────────────────────────────────────────────────────────

def is_ws_item(item: Item) -> bool:
    """True if the item is a reference to the ws rule."""
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def strip_ws(seq: Sequence) -> Sequence:
    """Return a copy with ws references removed."""
    return Sequence([it for it in seq.items if not is_ws_item(it)])


def is_pure_literal(item: Item) -> bool:
    """True if the item is a literal or char-class (maps to str)."""
    return isinstance(item.atom, (Literal, CharClass))


def is_pure_literal_seq(seq: Sequence) -> bool:
    """True if every item is a literal or char-class."""
    return len(seq.items) > 0 and all(is_pure_literal(it) for it in seq.items)


def is_single_ruleref(seq: Sequence) -> str | None:
    """If the sequence is exactly one rule-ref (after ws stripping), return its name."""
    stripped = strip_ws(seq)
    if len(stripped.items) != 1:
        return None
    it = stripped.items[0]
    if it.quantifier is not None:
        return None
    if isinstance(it.atom, RuleRef):
        return it.atom.name
    # Unwrap single-arm group containing a single rule ref.
    if isinstance(it.atom, Group):
        inner = it.atom.alt
        if len(inner.seqs) == 1:
            inner_stripped = strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None


def unwrap_group_alt(alt: Alternation) -> Alternation:
    """If the alternation is a single unquantified group, unwrap it."""
    if len(alt.seqs) != 1:
        return alt
    stripped = strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


def is_all_pure_literal_alt(alt: Alternation) -> bool:
    """True if all non-empty arms are pure-literal sequences."""
    for seq in alt.seqs:
        stripped = strip_ws(seq)
        if len(stripped.items) == 0:
            continue
        if not is_pure_literal_seq(stripped):
            return False
    return True


def is_inline_literal_alt_group(item: Item) -> bool:
    """True if the item is an unquantified group of all pure-literal arms."""
    if not isinstance(item.atom, Group) or item.quantifier is not None:
        return False
    return is_all_pure_literal_alt(item.atom.alt)


def to_pascal(name: str) -> str:
    """Convert a rule name like 'json-value' to PascalCase."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


# ── Structural complexity detection (D10 heuristic) ────────────────────────

def _has_any_ruleref(items: list[Item]) -> bool:
    for it in items:
        if is_ws_item(it):
            continue
        if isinstance(it.atom, RuleRef):
            return True
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if _has_any_ruleref(seq.items):
                    return True
    return False


def _has_nontrivial_nested_group(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group) and not is_all_pure_literal_alt(it.atom.alt):
            return True
    return False


def _has_group_with_alt(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group):
            if len(it.atom.alt.seqs) > 1:
                return True
            for seq in it.atom.alt.seqs:
                if _has_group_with_alt(seq.items):
                    return True
    return False


def is_structurally_complex(alt: Alternation) -> bool:
    """Heuristic: rule body is character-level pattern, not meaningful structure.

    Triggers when:
    1. A *-quantified group contains non-trivial nested groups (escape patterns).
    2. No rule refs at all AND contains groups with alternations (e.g. JSON number).
    """
    for seq in alt.seqs:
        stripped = strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_nested_group(inner_seq.items):
                        return True

    all_no_refs = True
    has_group_alt = False
    for seq in alt.seqs:
        stripped = strip_ws(seq)
        if _has_any_ruleref(stripped.items):
            all_no_refs = False
            break
        if _has_group_with_alt(stripped.items):
            has_group_alt = True

    return all_no_refs and has_group_alt


# ── Main classifier ────────────────────────────────────────────────────────

def classify_rule(rule: Rule, rules_dict: dict[str, Rule]) -> str:
    """Classify a rule as semantic_terminal, pure_literal_alt, named_alt, or sequence."""
    alt = unwrap_group_alt(rule.body)

    if is_structurally_complex(alt):
        return "semantic_terminal"

    arms = [a for a in (strip_ws(seq) for seq in alt.seqs) if len(a.items) > 0]

    if len(arms) == 0:
        return "semantic_terminal"

    # Pure literal alternation.
    if len(arms) > 1 and all(is_pure_literal_seq(a) for a in arms):
        return "pure_literal_alt"
    if (
        len(arms) == 1
        and len(arms[0].items) == 1
        and isinstance(arms[0].items[0].atom, Group)
        and arms[0].items[0].quantifier is None
        and is_all_pure_literal_alt(arms[0].items[0].atom.alt)
    ):
        return "pure_literal_alt"

    # Named-rule alternation.
    if len(arms) > 1 and any(is_single_ruleref(a) is not None for a in arms):
        return "named_alt"

    if len(arms) == 1:
        return "sequence"

    # Multi-arm, no single named ref → still named_alt with anonymous arms.
    return "named_alt"
