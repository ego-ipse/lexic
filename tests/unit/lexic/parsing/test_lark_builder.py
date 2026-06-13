"""parsing.lark_builder — IrItem-only Lark grammar generation."""

from __future__ import annotations

from pathlib import Path

import lark
import pytest

from lexic.ir.base import IrNone, IrStr
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.parsing.lark_builder import LarkBuilder, build_lark, literal_to_regex_pattern
from tests._ir_fixtures import item, spec
from tests.unit.lexic.conftest import make_inner_outer_specs
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
    s = make_spec(
        "d",
        "value_str",
        [IrItem(IrCharClass(IrRange("0", "9")), IrQuantifier(1, IrNone))],
    )
    grammar, start = LarkBuilder([s]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("123") is not None


def test_build_grammar_ruleref():
    """build_grammar(specs) returns a Lark grammar string."""
    inner, outer = make_inner_outer_specs()
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
    inner, outer = make_inner_outer_specs()
    classes = {}  # transformer construction uses these — supplied by codegen
    grammar_str, parser, transformer = build_lark([outer, inner], classes, "root")
    assert isinstance(grammar_str, str)
    assert isinstance(parser, lark.Lark)
    assert isinstance(transformer, lark.Transformer)


def test_literal_with_newline_escapes_to_n() -> None:
    """Raw \\n must round-trip through Lark as the escape sequence \\n."""
    s = spec("line", "sequence", items=[item(IrLiteral("\n"))], field_map={"lit": 0})
    grammar, start = LarkBuilder([s]).build_grammar()
    assert '"\\n"' in grammar
    lark.Lark(grammar, parser="earley", start=start)  # must not raise


def test_charclass_with_slash_escapes_in_regex() -> None:
    """`/` inside a char class must be backslash-escaped in the Lark regex."""
    s = spec(
        "op",
        "sequence",
        items=[item(IrCharClass(IrStr("-+*/")))],
        field_map={"head": 0},
    )
    grammar, start = LarkBuilder([s]).build_grammar()
    assert "/[-+*\\/]/" in grammar
    lark.Lark(grammar, parser="earley", start=start)  # must not raise


# ── literal_to_regex_pattern ──────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("abc", "abc"),
        ("a.b", r"a\.b"),
        ("a*b", r"a\*b"),
        ("a+b", r"a\+b"),
        ("a?b", r"a\?b"),
        ("a^b", r"a\^b"),
        ("a$b", r"a\$b"),
        ("[x]", r"\[x\]"),
        ("(x)", r"\(x\)"),
        ("{1}", r"\{1\}"),
        ("a|b", r"a\|b"),
        ("a/b", r"a\/b"),
        ("a\\b", r"a\\b"),
        ("a\nb", r"a\nb"),
        ("a\rb", r"a\rb"),
        ("a\tb", r"a\tb"),
        ("", ""),
    ],
)
def test_literal_to_regex_pattern_escaping(value: str, expected: str) -> None:
    """literal_to_regex_pattern escapes metacharacters correctly."""
    assert literal_to_regex_pattern(value) == expected


def test_literal_to_regex_pattern_plain_chars_unchanged() -> None:
    """Plain alphanumeric characters are returned unchanged."""
    assert literal_to_regex_pattern("hello123") == "hello123"
