# tests/test_lark_builder.py
from __future__ import annotations
from pathlib import Path

import pytest
import lark
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder

GRAMMAR_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "resources" / "ground_truth"
)


def _builder(grammar: str) -> LarkBuilder:
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    rules = parse_gbnf(text)
    specs = IRBuilder(rules).build()
    return LarkBuilder(specs)


@pytest.mark.parametrize(
    "grammar", ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]
)
def test_lark_grammar_is_parseable(grammar: str):
    builder = _builder(grammar)
    grammar_str, start_rule = builder.build_grammar()
    assert grammar_str.strip()
    assert start_rule
    # Must not raise
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    assert parser is not None


def test_arithmetic_lark_parses_simple():
    builder = _builder("arithmetic")
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    tree = parser.parse("x=1\n")
    assert tree is not None


def test_list_lark_parses_item():
    builder = _builder("list")
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    tree = parser.parse("- foo\n")
    assert tree is not None


def test_no_hyphen_in_lark_rule_names():
    """Lark rule names must not contain hyphens (invalid identifiers)."""
    builder = _builder("japanese")
    grammar_str, _ = builder.build_grammar()
    for line in grammar_str.splitlines():
        if ":" in line:
            rule_name = line.split(":")[0].strip()
            assert "-" not in rule_name, f"Lark rule name has hyphen: '{rule_name}'"
