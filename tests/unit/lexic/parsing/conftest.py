"""Shared fixtures for lexic.parsing tests."""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests._ir_fixtures import digit_grammar as _digit_grammar
from tests._ir_fixtures import sss_grammar as _sss_grammar
from tests.paths import GROUND_TRUTH


@pytest.fixture
def expr_grammar() -> IrAst:
    """Recursive: expr = '(' expr ')' / digit ; digit = [0-9]."""
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
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


@pytest.fixture
def sss_grammar() -> IrAst:
    """Genuinely ambiguous: s = s s / 'a'.

    Over 'aaa' this has exactly 2 derivations (Catalan C_2):
    ``(s(s(a) s(a)) s(a))`` and ``(s(a) s(s(a) s(a)))``.
    """
    return _sss_grammar()


@pytest.fixture
def expr_plus_grammar() -> IrAst:
    """Ambiguous arithmetic: e = e '+' e / 'a'.

    Over 'a+a+a' this has exactly 2 derivations (left- vs right-associative).
    """
    e_rule = IrRule(
        "e",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("e")),
                IrItem(IrLiteral("+")),
                IrItem(IrRuleRef("e")),
            ),
            IrSequence(IrItem(IrLiteral("a"))),
        ),
    )
    return IrAst(rules=IrSeq(e_rule), start="e")


@pytest.fixture
def digit_grammar() -> IrAst:
    """digit = [0-9] ; minimal single-rule grammar."""
    return _digit_grammar()


@pytest.fixture(scope="module")
def arithmetic():
    """The real arithmetic.gbnf ground truth, compiled through the full pipeline."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    return compile_text(text)


@pytest.fixture(scope="module")
def optional_shapes():
    """A minimal grammar isolating optional-ref / optional-literal folding.

    ``thing`` is non-nullable (its body can't match empty), so ``thing?`` can
    be genuinely absent — unlike a ref to a nullable rule (e.g. arithmetic's
    ``ws``), which :func:`~lexic.parsing.fold.lift_optional_nullables`
    rewrites to mandatory.
    """
    text = 'root ::= "a" thing? ("!")? "b"\nthing ::= "T"\n'
    return compile_text(text)
