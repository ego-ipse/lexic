# tests/unit/lexic/ir/test_derive.py
"""derive_specs and friends — IR-side structural decomposition."""

from __future__ import annotations

from lexic.ir.derive import classify_kind
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)


def _seq(*items):
    return IrSequence(tuple(items))


def _alt(*arms):
    return IrAlternation(tuple(arms))


def _it(atom, q=None):
    return IrItem(atom, q if q else Quantifier())


# ── classify_kind ─────────────────────────────────────────────────────


def test_classify_value_str_for_pure_literal_alternation():
    """`op ::= "+" | "-"` — no rulerefs anywhere → value_str."""
    rule = IrRule(
        "op",
        _alt(
            _seq(_it(IrLiteral("+"))),
            _seq(_it(IrLiteral("-"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_charclass_only():
    """`digit ::= [0-9]+` — no rulerefs → value_str."""
    rule = IrRule(
        "digit",
        _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_for_named_arms():
    """`term ::= num | ident` — multiple non-empty arms with rulerefs."""
    rule = IrRule(
        "term",
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrRuleRef("ident"))),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_for_single_arm_with_rulerefs():
    """`expr ::= term op term` — single arm with rulerefs."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(IrRuleRef("op")),
                _it(IrRuleRef("term")),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_empty_body():
    """A rule with no arms (or all empty) is value_str (degenerate)."""
    rule = IrRule("nothing", _alt())
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_literal_only_with_groups():
    """`bool ::= "true" | "false"` even when grouped → value_str."""
    rule = IrRule(
        "bool",
        _alt(
            _seq(_it(IrLiteral("true"))),
            _seq(_it(IrLiteral("false"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_with_mixed_arms():
    """One single-ruleref arm + one multi-item arm → alternation."""
    rule = IrRule(
        "value",
        _alt(
            _seq(_it(IrRuleRef("number"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_with_inline_group_containing_rulerefs():
    """`expr ::= term (op term)*` — single arm; the group has rulerefs but rule is sequence."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    Quantifier(0, None),
                ),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_complex_literal_group():
    """`num ::= "-"? [0-9]+ ("." [0-9]+)?` — has groups but no rulerefs → value_str."""
    rule = IrRule(
        "num",
        _alt(
            _seq(
                _it(IrLiteral("-"), Quantifier(0, 1)),
                _it(IrCharClass("0-9"), Quantifier(1, None)),
                _it(
                    IrGroup(
                        _alt(
                            _seq(
                                _it(IrLiteral(".")),
                                _it(IrCharClass("0-9"), Quantifier(1, None)),
                            )
                        )
                    ),
                    Quantifier(0, 1),
                ),
            ),
        ),
    )
    assert classify_kind(rule) == "value_str"
