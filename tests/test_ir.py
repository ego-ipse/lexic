# tests/test_ir.py
from __future__ import annotations

from lexic.codegen.ir import (
    AlternationAtom,
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)


def test_literal_atom():
    a = LiteralAtom(value="=")
    assert a.value == "="


def test_charclass_atom_bounded():
    a = CharClassAtom(pattern="[a-z]", min=1, max=1)
    assert a.pattern == "[a-z]"
    assert a.min == 1
    assert a.max == 1


def test_charclass_atom_unbounded():
    a = CharClassAtom(pattern="[a-z0-9_]", min=0, max=None)
    assert a.min == 0
    assert a.max is None


def test_ruleref_atom_required():
    a = RuleRefAtom(rule_name="ws", min=1, max=1)
    assert a.rule_name == "ws"
    assert a.min == 1
    assert a.max == 1


def test_ruleref_atom_list():
    a = RuleRefAtom(rule_name="item", min=1, max=None)
    assert a.max is None


def test_alternation_atom():
    a = AlternationAtom(arm_rule_names=["ident", "num", "term-arm3"])
    assert "ident" in a.arm_rule_names
    assert len(a.arm_rule_names) == 3


def test_rulespec_sequence():
    spec = RuleSpec(
        rule_name="ident",
        class_name="Ident",
        parent_class_name="Term",
        kind="sequence",
        items=[
            CharClassAtom("[a-z]", min=1, max=1),
            CharClassAtom("[a-z0-9_]", min=0, max=None),
            RuleRefAtom("ws", min=1, max=1),
        ],
        field_map={"first": 0, "second": 1, "ws": 2},
    )
    assert spec.kind == "sequence"
    assert len(spec.items) == 3
    assert spec.field_map["ws"] == 2


def test_rulespec_alternation():
    spec = RuleSpec(
        rule_name="term",
        class_name="Term",
        parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(arm_rule_names=["ident", "num"])],
        field_map={},
    )
    assert spec.kind == "alternation"
    assert spec.field_map == {}


def test_rulespec_value_str():
    spec = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", min=0, max=None)],
        field_map={},
    )
    assert spec.kind == "value_str"
