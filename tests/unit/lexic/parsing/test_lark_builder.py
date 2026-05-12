"""parsing.lark_builder — IrItem-only Lark grammar generation."""

from __future__ import annotations

from pathlib import Path

import lark

from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)
from lexic.parsing.lark_builder import LarkBuilder, build_lark
from tests.unit.lexic.parsing.conftest import make_spec


def test_build_grammar_simple_literal():
    """build_grammar(specs) returns a Lark grammar string."""
    s = make_spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    grammar, start = LarkBuilder([s]).build_grammar()
    assert start == "greet"
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("hi") is not None


def test_build_grammar_charclass_quantified():
    """build_grammar(specs) returns a Lark grammar string."""
    s = make_spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    grammar, start = LarkBuilder([s]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("123") is not None


def test_build_grammar_ruleref():
    """build_grammar(specs) returns a Lark grammar string."""
    inner = make_spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = make_spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    grammar, start = LarkBuilder([outer, inner]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("abc") is not None


def test_build_grammar_alternation_kind():
    """build_grammar(specs) returns a Lark grammar string."""
    a = make_spec("a", "value_str", [IrItem(IrLiteral("a"))])
    b = make_spec("b", "value_str", [IrItem(IrLiteral("b"))])
    alt = make_spec(
        "either", "alternation", [IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))]
    )
    grammar, start = LarkBuilder([alt, a, b]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("a") is not None
    assert parser.parse("b") is not None


def test_no_ws_string_check_in_source():
    """Decision CQ #2: lark_builder does not key on rule names like 'ws'."""
    src = (__file__).replace(
        "tests/unit/lexic/parsing/test_lark_builder.py",
        "src/lexic/parsing/lark_builder.py",
    )
    content = Path(src).read_text(encoding="utf-8")
    assert 'atom.name == "ws"' not in content
    assert "atom.name == 'ws'" not in content
    assert 'rule_name == "ws"' not in content


def test_build_lark_returns_parser_and_transformer_factory():
    """build_lark(specs, classes, start) returns (grammar_str, parser, transformer)."""
    inner = make_spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = make_spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    classes = {}  # transformer construction uses these — supplied by codegen
    grammar_str, parser, transformer = build_lark([outer, inner], classes, "root")
    assert isinstance(grammar_str, str)
    assert isinstance(parser, lark.Lark)
    assert isinstance(transformer, lark.Transformer)
