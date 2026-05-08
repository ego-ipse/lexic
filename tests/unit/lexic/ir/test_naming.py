"""Tests for ir.naming, the IR field naming policy."""

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.naming import CHARCLASS_NAMES, assign_field_names


def test_literal_atom_has_no_field():
    """LiteralAtom should get no field name."""
    atoms = [LiteralAtom("+"), LiteralAtom("-")]
    assert not assign_field_names(atoms)


def test_charclass_uses_known_semantic_name():
    """If the charclass pattern is in the built-in library, we should get the known name."""
    atoms = [CharClassAtom(pattern="[0-9]", min=1, max=1)]
    assert assign_field_names(atoms) == {"digit": 0}


def test_charclass_falls_back_to_sanitized_pattern():
    """If the pattern isn't in the built-in library, we should get a sanitized version."""
    atoms = [CharClassAtom(pattern="[NBKQR]", min=1, max=1)]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "nbkqr"


def test_ruleref_uses_rule_name():
    """RuleRefAtom should get a field name based on the rule it references."""
    atoms = [RuleRefAtom(rule_name="expr", min=1, max=1)]
    assert assign_field_names(atoms) == {"expr": 0}


def test_collisions_are_numbered():
    """If the same base name is generated more than once, we get numbered suffixes."""
    atoms = [
        RuleRefAtom(rule_name="ws", min=0, max=1),
        LiteralAtom("="),
        RuleRefAtom(rule_name="ws", min=0, max=1),
    ]
    fm = assign_field_names(atoms)
    assert fm == {"ws": 0, "ws2": 2}


def test_inline_alternation_gets_value_field():
    """InlineAlternationAtom is a structural node, not a semantic one."""
    atoms = [InlineAlternationAtom(arm_rule_names=["a", "b"])]
    assert assign_field_names(atoms) == {"value": 0}


def test_quantified_literal_named_from_lookup():
    """QuantifiedLiteralAtom is a structural node, not a semantic one."""
    atoms = [QuantifiedLiteralAtom(value="-", min=0, max=1)]
    assert assign_field_names(atoms) == {"sign": 0}


def test_inline_regex_named_from_first_arm():
    """The first arm of the regex is a literal, so we get a nice name."""
    atoms = [
        InlineRegexAtom(regex="(true|false)", gbnf='("true"|"false")', min=1, max=1)
    ]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "true"


def test_alternation_atom_has_no_field():
    """AlternationAtom is a structural node, not a semantic one."""
    atoms = [AlternationAtom(arm_rule_names=["a", "b"])]
    assert not assign_field_names(atoms)


def test_charclass_names_full_table():
    """Tier 2 pattern library — 9 entries, no quantifier-baked keys."""
    expected = {
        "[0-9]": "digit",
        "[0-9a-fA-F]": "hex",
        "[a-fA-F0-9]": "hex",
        "[a-f]": "hex_lower",
        "[A-F]": "hex_upper",
        "[a-z]": "lower",
        "[A-Z]": "upper",
        "[a-zA-Z]": "letter",
        "[a-zA-Z_0-9]": "alnum",
    }
    for pattern, name in expected.items():
        assert CHARCLASS_NAMES.get(pattern) == name, (
            f"Tier 2: {pattern} → expected {name!r}, got {CHARCLASS_NAMES.get(pattern)!r}"
        )
