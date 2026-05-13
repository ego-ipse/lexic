"""GbnfEmitter (IrItem-shape only)."""

from __future__ import annotations

from typing import Literal

from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.escapes import GBNF_ESCAPES
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec


def _spec(
    name: str,
    kind: Literal["sequence", "alternation", "value_str"],
    items,
    field_map=None,
):
    """Helper for test_emit_*."""
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )


def test_emit_literal():
    """IrItem(IrLiteral) emits as expected."""
    s = _spec("greet", "value_str", [IrItem(IrLiteral("hello"))])
    out = GbnfEmitter(GBNF_ESCAPES).emit_rule(s)
    assert out == 'greet ::= "hello"'


def test_emit_charclass_with_quantifier():
    """IrItem(IrCharClass) with quantifier emits as expected."""
    s = _spec("digit", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    assert GbnfEmitter(GBNF_ESCAPES).emit_rule(s) == "digit ::= [0-9]+"


def test_emit_negated_charclass():
    """IrItem(IrCharClass) with negated=True emits as expected."""
    s = _spec("nq", "value_str", [IrItem(IrCharClass('"', negated=True))])
    assert GbnfEmitter(GBNF_ESCAPES).emit_rule(s) == 'nq ::= [^"]'


def test_emit_ruleref_with_quantifier():
    """IrItem(IrRuleRef) with quantifier emits as expected."""
    s = _spec("expr", "sequence", [IrItem(IrRuleRef("term"), Quantifier(1, None))])
    assert GbnfEmitter(GBNF_ESCAPES).emit_rule(s) == "expr ::= term+"


def test_emit_group_inline_alternation():
    """IrGroup(IrAlternation) emits as expected, with parentheses."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrRuleRef("a")),)),
                IrSequence((IrItem(IrRuleRef("b")),)),
            )
        )
    )
    s = _spec("r", "sequence", [IrItem(grp)])
    assert "(a | b)" in GbnfEmitter(GBNF_ESCAPES).emit_rule(s)


def test_emit_group_with_quantifier():
    """IrGroup(IrAlternation) with quantifier emits as expected."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrLiteral("foo")),)),
                IrSequence((IrItem(IrLiteral("bar")),)),
            )
        )
    )
    s = _spec("r", "value_str", [IrItem(grp, Quantifier(1, None))])
    out = GbnfEmitter(GBNF_ESCAPES).emit_rule(s)
    assert out.endswith("+")
    assert '"foo"' in out and '"bar"' in out


def test_emit_alternation_kind():
    """kind='alternation': items are IrItem(IrRuleRef(arm_name)) per arm."""
    s = _spec(
        "kind", "alternation", [IrItem(IrRuleRef("num")), IrItem(IrRuleRef("ident"))]
    )
    assert GbnfEmitter(GBNF_ESCAPES).emit_rule(s) == "kind ::= num | ident"


def test_emit_value_str_multi_arm_via_bare_alternation():
    """Decision C: multi-arm value_str places IrAlternation at items[0]."""
    alt = IrAlternation(
        (
            IrSequence((IrItem(IrLiteral("int")),)),
            IrSequence((IrItem(IrLiteral("float")),)),
        )
    )
    s = _spec("ty", "value_str", [alt])
    out = GbnfEmitter(GBNF_ESCAPES).emit_rule(s)
    assert out == 'ty ::= "int" | "float"'


def test_emit_full_grammar_concatenates():
    """Concatenation of all rules in a grammar emits as expected."""
    specs = [
        _spec("root", "sequence", [IrItem(IrRuleRef("expr"))], {"expr": 0}),
        _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]),
    ]
    out = GbnfEmitter(GBNF_ESCAPES).emit(specs)
    assert "root ::= expr" in out
    assert "expr ::= [a-z]+" in out
    assert out.endswith("\n")
