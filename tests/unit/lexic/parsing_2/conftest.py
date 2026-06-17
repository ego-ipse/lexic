"""Shared fixtures for lexic.parsing_2 tests."""

from __future__ import annotations

import pytest

from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)


@pytest.fixture
def expr_grammar() -> IrAst:
    """Recursive: expr = '(' expr ')' / digit ; digit = [0-9]."""
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange("0", "9"))))),
    )
    expr = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral(")")),
            ),
            IrSequence(IrItem(IrRuleRef("digit"))),
        ),
    )
    return IrAst(rules=IrSeq(expr, digit), start="expr")
