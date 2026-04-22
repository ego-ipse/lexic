from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.codegen.naming import assign_field_names


def test_literal_atom_has_no_field():
    atoms = [LiteralAtom("+"), LiteralAtom("-")]
    assert assign_field_names(atoms) == {}


def test_charclass_uses_known_semantic_name():
    atoms = [CharClassAtom(pattern="[0-9]", min=1, max=1)]
    assert assign_field_names(atoms) == {"digit": 0}


def test_charclass_falls_back_to_sanitized_pattern():
    atoms = [CharClassAtom(pattern="[NBKQR]", min=1, max=1)]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "nbkqr"


def test_ruleref_uses_rule_name():
    atoms = [RuleRefAtom(rule_name="expr", min=1, max=1)]
    assert assign_field_names(atoms) == {"expr": 0}


def test_collisions_are_numbered():
    atoms = [
        RuleRefAtom(rule_name="ws", min=0, max=1),
        LiteralAtom("="),
        RuleRefAtom(rule_name="ws", min=0, max=1),
    ]
    fm = assign_field_names(atoms)
    assert fm == {"ws": 0, "ws2": 2}


def test_inline_alternation_gets_value_field():
    atoms = [InlineAlternationAtom(arm_rule_names=["a", "b"])]
    assert assign_field_names(atoms) == {"value": 0}


def test_quantified_literal_named_from_lookup():
    atoms = [QuantifiedLiteralAtom(value="-", min=0, max=1)]
    assert assign_field_names(atoms) == {"sign": 0}


def test_inline_regex_named_from_first_arm():
    atoms = [
        InlineRegexAtom(regex="(true|false)", gbnf='("true"|"false")', min=1, max=1)
    ]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "true"


def test_alternation_atom_has_no_field():
    atoms = [AlternationAtom(arm_rule_names=["a", "b"])]
    assert assign_field_names(atoms) == {}
