"""Unit tests for src/lexic/codegen/transformer.py"""

from __future__ import annotations
from pathlib import Path
from lexic.codegen.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen import codegen
import lark

# tests/unit/lexic/codegen/ -> tests/unit/lexic/ -> tests/unit/ -> tests/ -> project root
GRAMMAR_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "resources" / "ground_truth"
)


def _parse_and_transform(text: str, grammar: str):
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    classes = codegen(gpath)
    rules = parse_gbnf(gpath.read_text())
    specs = IRBuilder(rules).build()
    builder = LarkBuilder(specs)
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start)
    tree = parser.parse(text)
    transformer = builder.build_transformer(classes)
    return transformer.transform(tree)


def test_transformer_arithmetic_simple():
    result = _parse_and_transform("x=1\n", "arithmetic")
    assert result is not None
    assert result.to_text() == "x=1\n"


def test_transformer_chess_move():
    result = _parse_and_transform("1. e4 e5\n2. d4 d5\n", "chess")
    assert result is not None
    assert result.to_text() == "1. e4 e5\n2. d4 d5\n"


def test_transformer_json_empty():
    result = _parse_and_transform("{}", "json_ws")
    assert result is not None
    assert result.to_text() == "{}"
