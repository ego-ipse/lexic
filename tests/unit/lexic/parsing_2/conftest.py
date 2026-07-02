"""Shared fixtures for lexic.parsing_2 tests."""

from __future__ import annotations

import pytest

from lexic.codegen import codegen
from lexic.compile import compile_grammar
from lexic.grammars import get_flavour
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
from lexic.parsing_2.models import build_instance_parser
from tests._ir_fixtures import sss_grammar as _sss_grammar
from tests.paths import GROUND_TRUTH

_GBNF_FLAVOUR = get_flavour("gbnf")


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
    return IrAst(
        rules=IrSeq(
            IrRule(
                "digit",
                IrAlternation(
                    IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))
                ),
            )
        ),
        start="digit",
    )


def _compiled(text: str, stem: str):
    """compile_grammar + codegen + build_instance_parser, in one call.

    Shared by test_models.py's instance-parsing-bridge fixtures.

    :returns: ``(start, specs, classes, grammar, fold)``.
    """
    start, specs = compile_grammar(text, _GBNF_FLAVOUR)
    classes = codegen(specs, stem)
    grammar, fold = build_instance_parser(specs, classes, start)
    return start, specs, classes, grammar, fold


@pytest.fixture(scope="module")
def arithmetic():
    """The real arithmetic.gbnf ground-truth grammar, compiled once."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    return _compiled(text, "test_models_arith")


@pytest.fixture(scope="module")
def optional_shapes():
    """A minimal grammar isolating optional-ref / optional-literal-group folding.

    ``thing`` is non-nullable (its body can't match empty), so ``thing?`` can
    be genuinely absent — unlike a ref to a nullable rule (e.g. arithmetic's
    ``ws``), which ``_lift_optional_nullables`` rewrites to mandatory.
    """
    text = 'root ::= "a" thing? ("!")? "b"\nthing ::= "T"\n'
    return _compiled(text, "test_models_optional")
