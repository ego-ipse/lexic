"""FlavourEmitter ABC — IrItem-shape emit chain tested via a fake subclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec


class FakeEscapes(EscapeCodec):
    """An identity EscapeCodec subclass — empty tables, so encode/decode are no-ops."""

    SHORT_ESCAPES = {}
    HEX_ESCAPES = ()


class _TestEmitter(FlavourEmitter):
    """A test emitter that uses the default handlers and a fake escape codec."""

    supports: ClassVar[frozenset[str]] = frozenset(
        {"literal", "char_class", "alternation", "quantifier"}
    )

    def emit_item(self, item: IrItem) -> str:
        """Public proxy for testing the protected _emit_item method."""
        return self._emit_item(item)

    def emit_ir_atom(self, atom: IrAtom) -> str:
        """Public proxy for testing the protected _emit_ir_atom method."""
        return self._emit_ir_atom(atom)


class SingleQuote(_TestEmitter):
    """A test emitter subclass that overrides the quote character for literals."""

    quote_char = "'"


def _new() -> _TestEmitter:
    return _TestEmitter(escapes=FakeEscapes())


# ── _emit_item (IrItem-shape dispatch) ────────────────────────────────────────


def test_emit_item_literal_quotes():
    """Emit a literal with default quoting."""
    e = _new()
    assert e.emit_item(IrItem(IrLiteral("hi"))) == '"hi"'


def test_emit_item_quantified_literal_appends_quantifier():
    """Test that quantified literals append the quantifier suffix."""
    e = _new()
    assert e.emit_item(IrItem(IrLiteral("-"), Quantifier(0, 1))) == '"-"?'


def test_emit_item_charclass_appends_quantifier():
    """Test that quantified character classes append the quantifier suffix."""
    e = _new()
    assert e.emit_item(IrItem(IrCharClass("0-9"), Quantifier(1, None))) == "0-9+"


def test_emit_item_ruleref_appends_quantifier():
    """Test that quantified rule references append the quantifier suffix."""
    e = _new()
    assert e.emit_item(IrItem(IrRuleRef("x"), Quantifier(0, 1))) == "x?"


def test_emit_body_alternation_kind_joins_arms():
    """Test that alternation rules join arms with the separator."""
    e = _new()
    spec = RuleSpec(
        "r",
        "R",
        "GrammarModel",
        "alternation",
        items=[IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))],
        field_map={},
    )
    assert e.emit_rule(spec) == "r ::= a | b"


def test_emit_ir_atom_group_wraps_with_parens():
    """Test that groups are wrapped with parentheses."""
    e = _new()
    arm = IrSequence(items=(IrItem(IrRuleRef("a")),))
    assert e.emit_ir_atom(IrGroup(body=IrAlternation(arms=(arm,)))) == "(a)"


def test_emit_rule_renders_value_str_body():
    """Test that value_str rules are emitted correctly."""
    spec = RuleSpec(
        "num",
        "Num",
        "GrammarModel",
        "value_str",
        items=[IrItem(IrCharClass("0-9"), Quantifier(1, None))],
        field_map={},
    )
    e = _new()
    assert e.emit_rule(spec) == "num ::= 0-9+"


def test_emit_joins_rules_with_newlines():
    """Test that multiple rules are joined with newlines."""
    a = RuleSpec(
        "a",
        "A",
        "GrammarModel",
        "value_str",
        items=[IrItem(IrLiteral("x"))],
        field_map={},
    )
    b = RuleSpec(
        "b",
        "B",
        "GrammarModel",
        "value_str",
        items=[IrItem(IrLiteral("y"))],
        field_map={},
    )
    e = _new()
    assert e.emit([a, b]) == 'a ::= "x"\nb ::= "y"\n'


def test_subclass_overrides_quote_char():
    """Test that subclasses can override the quote character."""
    e = SingleQuote(escapes=FakeEscapes())
    assert e.emit_item(IrItem(IrLiteral("hi"))) == "'hi'"


def test_unknown_atom_raises():
    """Test that emitting an unknown atom type raises UnsupportedConstructError."""

    @dataclass
    class _Unknown:
        pass

    e = _new()
    with pytest.raises(UnsupportedConstructError):
        e.emit_ir_atom(_Unknown())  # type: ignore[arg-type]


# ── IR-AST emit chain tests ───────────────────────────────────────────


def _make_ast() -> IrAst:
    """Build a 2-rule IrAst: root = digit; digit = [0-9]."""
    digit_item = IrItem(atom=IrCharClass("0-9"), quantifier=Quantifier(1, 1))
    digit_seq = IrSequence(items=(digit_item,))
    digit_alt = IrAlternation(arms=(digit_seq,))
    digit_rule = IrRule(name="digit", body=digit_alt)

    ref_item = IrItem(atom=IrRuleRef("digit"), quantifier=Quantifier(1, 1))
    ref_seq = IrSequence(items=(ref_item,))
    ref_alt = IrAlternation(arms=(ref_seq,))
    root_rule = IrRule(name="root", body=ref_alt)

    return IrAst(rules=(root_rule, digit_rule), start="root")


def test_emit_ast_produces_two_lines_terminated_with_newline():
    """Test that emitting an AST produces lines terminated with a newline."""
    e = _new()
    ast = _make_ast()
    result = e.emit_ast(ast)
    lines = result.split("\n")
    assert len(lines) == 3
    assert lines[-1] == ""
    assert result.endswith("\n")


def test_emit_rule_from_ast_single_rule():
    """Test that a single rule is emitted correctly from AST."""
    e = _new()
    digit_item = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    digit_seq = IrSequence(items=(digit_item,))
    digit_alt = IrAlternation(arms=(digit_seq,))
    rule = IrRule(name="myrule", body=digit_alt)
    assert e.emit_rule_from_ast(rule) == 'myrule ::= "x"'


def test_emit_alternation_single_arm():
    """Test that an alternation with a single arm is emitted correctly."""
    e = _new()
    item = IrItem(atom=IrLiteral("a"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "a"'


def test_emit_alternation_two_arms_joins_with_alt_separator():
    """Test that alternation with multiple arms joins them with the separator."""
    e = _new()
    arm1 = IrSequence(items=(IrItem(IrLiteral("a"), Quantifier(1, 1)),))
    arm2 = IrSequence(items=(IrItem(IrLiteral("b"), Quantifier(1, 1)),))
    rule = IrRule(name="r", body=IrAlternation(arms=(arm1, arm2)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "a" | "b"'


def test_emit_sequence_two_items():
    """Test that sequences with multiple items are emitted in order."""
    e = _new()
    item1 = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    item2 = IrItem(atom=IrRuleRef("y"), quantifier=Quantifier(1, 1))
    rule = IrRule(
        name="r", body=IrAlternation(arms=(IrSequence(items=(item1, item2)),))
    )
    assert e.emit_rule_from_ast(rule) == 'r ::= "x" y'


def test_emit_item_literal_with_required_quantifier():
    """Test that a required-quantifier literal does not emit the quantifier."""
    e = _new()
    item = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "x"'


def test_emit_item_ruleref_with_optional_quantifier():
    """Test that an optional-quantifier rule ref emits the quantifier."""
    e = _new()
    item = IrItem(atom=IrRuleRef("expr"), quantifier=Quantifier(0, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= expr?"


def test_emit_ir_atom_literal():
    """Test that literals are emitted with quotes."""
    e = _new()
    item = IrItem(atom=IrLiteral("hello"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "hello"'


def test_emit_ir_atom_ruleref():
    """Test that rule references are emitted without quotes."""
    e = _new()
    item = IrItem(atom=IrRuleRef("expr"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= expr"


def test_emit_ir_atom_charclass():
    """Test that character classes are emitted correctly."""
    e = _new()
    item = IrItem(atom=IrCharClass("0-9"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= 0-9"


def test_emit_ir_atom_charclass_negated_forwarded():
    """Test that IrNot(IrCharClass) is forwarded to render_charclass with negated=True."""

    class _NegationAware(_TestEmitter):
        def render_charclass(
            self, canonical_pattern: str, negated: bool = False
        ) -> str:
            return f"[^{canonical_pattern}]" if negated else f"[{canonical_pattern}]"

    e = _NegationAware(escapes=FakeEscapes())
    item = IrItem(atom=IrNot(IrCharClass("0-9")), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= [^0-9]"


def test_emit_ir_atom_group():
    """Test that groups are emitted with parentheses around their body."""
    e = _new()
    arm = IrSequence(items=(IrItem(IrLiteral("a"), Quantifier(1, 1)),))
    group_item = IrItem(
        atom=IrGroup(body=IrAlternation(arms=(arm,))), quantifier=Quantifier(1, 1)
    )
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(group_item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= ("a")'
