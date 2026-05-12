"""build_transformer — IR specs + classes → Lark Transformer."""

from __future__ import annotations

import lark

from lexic.base import GrammarModel
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.parsing.lark_builder import LarkBuilder
from lexic.parsing.transformer.build_transformer import build_transformer
from tests.unit.lexic.parsing.conftest import make_spec


def test_transformer_round_trip_value_str_literal():
    """Build a transformer and round-trip a value_str literal."""
    spec = make_spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    builder = LarkBuilder([spec])
    grammar_str, start = builder.build_grammar()

    class Greet(GrammarModel):
        """Greeting"""

        value: str = "hi"

    Greet.__grammar__ = spec  # type: ignore[assignment] Replace in Task 18
    classes = {"Greet": Greet}

    parser = lark.Lark(grammar_str, parser="earley", start=start)
    tree = parser.parse("hi")
    transformer = build_transformer([spec], classes)
    result = transformer.transform(tree)
    assert isinstance(result, Greet)
    assert result.value == "hi"


def test_transformer_round_trip_sequence():
    """Build a transformer and round-trip a sequence."""
    inner_spec = make_spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer_spec = make_spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )

    class Expr(GrammarModel):
        """Expression"""

        value: str

    Expr.__grammar__ = inner_spec  # type: ignore[assignment] Replace in Task 18

    class Root(GrammarModel):
        """Root rule"""

        expr: Expr

    Root.__grammar__ = outer_spec  # type: ignore[assignment] Replace in Task 18

    classes = {"Expr": Expr, "Root": Root}
    builder = LarkBuilder([outer_spec, inner_spec])
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", start=start)
    tree = parser.parse("abc")
    transformer = build_transformer([outer_spec, inner_spec], classes)
    result = transformer.transform(tree)
    assert isinstance(result, Root)
    assert isinstance(result.expr, Expr)
    assert result.expr.value == "abc"
