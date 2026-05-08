"""FlavourEmitter ABC — DEFAULT_HANDLERS + decorators tested via a fake subclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


class FakeEscapes(EscapeCodec):
    """An identity EscapeCodec subclass — empty tables, so encode/decode are no-ops."""

    SHORT_ESCAPES = {}
    HEX_ESCAPES = ()


class _TestEmitter(FlavourEmitter):
    """A test emitter that uses the default handlers and a fake escape codec."""

    supports: ClassVar[frozenset[str]] = frozenset(
        {"literal", "char_class", "alternation", "quantifier"}
    )


@dataclass(frozen=True)
class CustomTestAtom:
    """A custom atom type for testing the ability to register extra handlers."""

    marker: str


class SingleQuote(_TestEmitter):
    """A test emitter subclass that overrides the quote character for literals."""

    quote_char = "'"


def _new(handlers=None) -> _TestEmitter:
    """Helper to create a new _TestEmitter with the default handlers plus any overrides."""
    return _TestEmitter(escapes=FakeEscapes(), handlers=handlers)


def test_default_literal_handler_quotes():
    """The default literal handler should quote the value."""
    e = _new()
    assert e.render_atom(LiteralAtom(value="hi")) == '"hi"'


def test_default_quantified_literal_appends_quantifier():
    """The default quantified literal handler should render the literal and append quantifier."""
    e = _new()
    assert e.render_atom(QuantifiedLiteralAtom(value="-", min=0, max=1)) == '"-"?'


def test_default_charclass_appends_quantifier():
    """The default char class handler should render the pattern and append quantifier."""
    e = _new()
    assert e.render_atom(CharClassAtom(pattern="[0-9]", min=1, max=None)) == "[0-9]+"


def test_default_ruleref_appends_quantifier():
    """The default ruleref handler should render the rule name and append quantifier."""
    e = _new()
    assert e.render_atom(RuleRefAtom(rule_name="x", min=0, max=1)) == "x?"


def test_default_alternation_joins_with_alt_separator():
    """The default alternation handler should join the arm rule names with alternative separator."""
    e = _new()
    assert e.render_atom(AlternationAtom(arm_rule_names=["a", "b"])) == "a | b"


def test_default_inline_alternation_wraps_with_group():
    """The default inline alternation handler should wrap the arms with a group."""
    e = _new()
    assert e.render_atom(InlineAlternationAtom(arm_rule_names=["a", "b"])) == "(a | b)"


def test_emit_rule_renders_value_str_body():
    """emit_rule should render a value_str rule by rendering its body atoms."""
    spec = RuleSpec(
        rule_name="num",
        class_name="Num",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[0-9]", 1, None)],
        field_map={},
    )
    e = _new()
    assert e.emit_rule(spec) == "num ::= [0-9]+"


def test_emit_joins_rules_with_newlines():
    """emit should join rules with newlines."""
    a = RuleSpec(
        rule_name="a",
        class_name="A",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("x")],
        field_map={},
    )
    b = RuleSpec(
        rule_name="b",
        class_name="B",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[LiteralAtom("y")],
        field_map={},
    )
    e = _new()
    assert e.emit([a, b]) == 'a ::= "x"\nb ::= "y"\n'


def test_subclass_can_override_quote_char():
    """A subclass should be able to override the quote character used for literals."""
    e = SingleQuote(escapes=FakeEscapes())
    assert e.render_atom(LiteralAtom(value="hi")) == "'hi'"


def test_subclass_can_register_extra_handler():
    """A subclass should be able to register an extra handler for a custom atom type."""
    e = _new(
        handlers={
            **FlavourEmitter.DEFAULT_HANDLERS,
            CustomTestAtom: lambda a, em: f"<{a.marker}>",
        }
    )
    assert e.render_atom(CustomTestAtom(marker="x")) == "<x>"


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
    """emit_ast joins rule lines with newline and appends a trailing newline."""
    e = _new()
    ast = _make_ast()
    result = e.emit_ast(ast)
    lines = result.split("\n")
    # Two non-empty lines + trailing empty string from split
    assert len(lines) == 3
    assert lines[-1] == ""
    assert result.endswith("\n")


def test_emit_rule_from_ast_single_rule():
    """emit_rule_from_ast produces 'name ::= body' for a single rule."""
    e = _new()
    digit_item = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    digit_seq = IrSequence(items=(digit_item,))
    digit_alt = IrAlternation(arms=(digit_seq,))
    rule = IrRule(name="myrule", body=digit_alt)
    result = e.emit_rule_from_ast(rule)
    assert result == 'myrule ::= "x"'


def test_emit_alternation_single_arm():
    """Single-arm alternation emits just the arm text (no separator)."""
    e = _new()
    item = IrItem(atom=IrLiteral("a"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "a"'


def test_emit_alternation_two_arms_joins_with_alt_separator():
    """Two-arm alternation joins arms with alt_separator."""
    e = _new()
    arm1 = IrSequence(items=(IrItem(IrLiteral("a"), Quantifier(1, 1)),))
    arm2 = IrSequence(items=(IrItem(IrLiteral("b"), Quantifier(1, 1)),))
    rule = IrRule(name="r", body=IrAlternation(arms=(arm1, arm2)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "a" | "b"'


def test_emit_sequence_two_items():
    """Two-item sequence emits items joined by a space."""
    e = _new()
    item1 = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    item2 = IrItem(atom=IrRuleRef("y"), quantifier=Quantifier(1, 1))
    rule = IrRule(
        name="r", body=IrAlternation(arms=(IrSequence(items=(item1, item2)),))
    )
    assert e.emit_rule_from_ast(rule) == 'r ::= "x" y'


def test_emit_item_literal_with_required_quantifier():
    """Required literal (Quantifier(1,1)) emits with no quantifier suffix."""
    e = _new()
    item = IrItem(atom=IrLiteral("x"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "x"'


def test_emit_item_ruleref_with_optional_quantifier():
    """Optional rule-ref (Quantifier(0,1)) emits with '?' suffix."""
    e = _new()
    item = IrItem(atom=IrRuleRef("expr"), quantifier=Quantifier(0, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= expr?"


def test_emit_ir_atom_literal():
    """IrLiteral atom emits as a quoted string."""
    e = _new()
    item = IrItem(atom=IrLiteral("hello"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= "hello"'


def test_emit_ir_atom_ruleref():
    """IrRuleRef atom emits as the rule name."""
    e = _new()
    item = IrItem(atom=IrRuleRef("expr"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= expr"


def test_emit_ir_atom_charclass():
    """IrCharClass atom passes interior pattern to render_charclass (base returns as-is)."""
    e = _new()
    item = IrItem(atom=IrCharClass("0-9"), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= 0-9"


def test_emit_ir_atom_charclass_negated_forwarded():
    """negated=True on IrCharClass is forwarded to render_charclass."""

    class _NegationAware(_TestEmitter):
        def render_charclass(
            self, canonical_pattern: str, negated: bool = False
        ) -> str:
            return f"[^{canonical_pattern}]" if negated else f"[{canonical_pattern}]"

    e = _NegationAware(escapes=FakeEscapes())
    item = IrItem(atom=IrCharClass("0-9", negated=True), quantifier=Quantifier(1, 1))
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(item,)),)))
    assert e.emit_rule_from_ast(rule) == "r ::= [^0-9]"


def test_emit_ir_atom_group():
    """IrGroup atom emits as a parenthesised alternation."""
    e = _new()
    arm = IrSequence(items=(IrItem(IrLiteral("a"), Quantifier(1, 1)),))
    group_item = IrItem(
        atom=IrGroup(body=IrAlternation(arms=(arm,))), quantifier=Quantifier(1, 1)
    )
    rule = IrRule(name="r", body=IrAlternation(arms=(IrSequence(items=(group_item,)),)))
    assert e.emit_rule_from_ast(rule) == 'r ::= ("a")'
