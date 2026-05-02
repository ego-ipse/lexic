# tests/unit/lexic/ir/test_derive.py
"""derive_specs and friends — IR-side structural decomposition."""

from __future__ import annotations

from lexic.ir.derive import classify_kind, compute_parents
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


# ── compute_parents ───────────────────────────────────────────────────


def test_compute_parents_alternation_arms_get_parent():
    """`term ::= num | ident` makes Num and Ident parents = Term."""
    term = IrRule(
        "term",
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), Quantifier(1, None)))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z"), Quantifier(1, None)))))
    parents = compute_parents([term, num, ident])
    assert parents == {"num": "Term", "ident": "Term"}


def test_compute_parents_only_single_ruleref_arms_create_parent():
    """A multi-item arm doesn't make its rulerefs into subclasses."""
    rule = IrRule(
        "value",
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    inner = IrRule("num", _alt(_seq(_it(IrCharClass("0-9")))))
    expr = IrRule("expr", _alt(_seq(_it(IrRuleRef("num")))))
    parents = compute_parents([rule, inner, expr])
    assert parents == {"num": "Value"}  # expr is in a multi-item arm; no parent


def test_compute_parents_quantified_ruleref_arm_does_not_create_parent():
    """`alt ::= a+ | b` — `a` has a quantifier, so it's not a 'single ref'."""
    rule = IrRule(
        "alt",
        _alt(
            _seq(_it(IrRuleRef("a"), Quantifier(1, None))),
            _seq(_it(IrRuleRef("b"))),
        ),
    )
    a_rule = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    b_rule = IrRule("b", _alt(_seq(_it(IrLiteral("b")))))
    parents = compute_parents([rule, a_rule, b_rule])
    assert parents == {"b": "Alt"}


def test_compute_parents_only_alternations_contribute():
    """Sequence rules don't create parent relationships."""
    seq_rule = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("a")), _it(IrRuleRef("b")))),
    )
    a = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    b = IrRule("b", _alt(_seq(_it(IrLiteral("b")))))
    assert not compute_parents([seq_rule, a, b])


def test_compute_parents_uses_pascal_case_class_names():
    """`json-value ::= num | ident` → parents use PascalCase class names."""
    rule = IrRule(
        "json-value",
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9")))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z")))))
    parents = compute_parents([rule, num, ident])
    assert parents == {"num": "JsonValue", "ident": "JsonValue"}
