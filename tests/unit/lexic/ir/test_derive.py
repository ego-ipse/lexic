# tests/unit/lexic/ir/test_derive.py
"""derive_specs and friends — IR-side structural decomposition."""

from __future__ import annotations

from lexic.ir.base import IrNone, IrSeq
from lexic.ir.derive import (
    _EXTRACT_BODY,
    _field_map,
    _HoistTransformer,
    classify_kind,
    compute_parents,
    derive_specs,
    has_ruleref,
    hoist_helpers,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrTransformer


def _charclass_plus_rule(name: str, lo: str, hi: str) -> IrRule:
    """``name ::= [lo-hi]+`` — a quantified charclass-only rule."""
    item = IrItem(IrCharClass(IrRange(IrChr(lo), IrChr(hi))), IrQuantifier(1, IrNone))
    return IrRule(name, IrAlternation(IrSequence(item)))


# ── classify_kind ─────────────────────────────────────────────────────


def test_classify_value_str_for_pure_literal_alternation():
    """`op ::= "+" | "-"` — no rulerefs anywhere → value_str."""
    rule = IrRule(
        "op",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("+"))),
            IrSequence(IrItem(IrLiteral("-"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_charclass_only():
    """`digit ::= [0-9]+` — no rulerefs → value_str."""
    rule = _charclass_plus_rule("digit", "0", "9")
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_for_named_arms():
    """`term ::= num | ident` — multiple non-empty arms with rulerefs."""
    rule = IrRule(
        "term",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))),
            IrSequence(IrItem(IrRuleRef("ident"))),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_for_single_arm_with_rulerefs():
    """`expr ::= term op term` — single arm with rulerefs."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(IrRuleRef("op")),
                IrItem(IrRuleRef("term")),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_empty_body():
    """A rule with no arms (or all empty) is value_str (degenerate)."""
    rule = IrRule("nothing", IrAlternation())
    assert classify_kind(rule) == "value_str"


def test_classify_value_str_for_literal_only_with_groups():
    """`bool ::= "true" | "false"` even when grouped → value_str."""
    rule = IrRule(
        "bool",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("true"))),
            IrSequence(IrItem(IrLiteral("false"))),
        ),
    )
    assert classify_kind(rule) == "value_str"


def test_classify_alternation_with_mixed_arms():
    """One single-ruleref arm + one multi-item arm → alternation."""
    rule = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("number"))),
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral(")")),
            ),
        ),
    )
    assert classify_kind(rule) == "alternation"


def test_classify_sequence_with_inline_group_containing_rulerefs():
    """`expr ::= term (op term)*` — single arm; the group has rulerefs but rule is sequence."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term")))
                    ),
                    IrQuantifier(0, IrNone),
                ),
            ),
        ),
    )
    assert classify_kind(rule) == "sequence"


def test_classify_value_str_for_complex_literal_group():
    """`num ::= "-"? [0-9]+ ("." [0-9]+)?` — has groups but no rulerefs → value_str."""
    rule = IrRule(
        "num",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("-"), IrQuantifier(0, 1)),
                IrItem(
                    IrCharClass(IrRange(IrChr("0"), IrChr("9"))),
                    IrQuantifier(1, IrNone),
                ),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(IrLiteral(".")),
                            IrItem(
                                IrCharClass(IrRange(IrChr("0"), IrChr("9"))),
                                IrQuantifier(1, IrNone),
                            ),
                        )
                    ),
                    IrQuantifier(0, 1),
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
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))), IrSequence(IrItem(IrRuleRef("ident")))
        ),
    )
    num = _charclass_plus_rule("num", "0", "9")
    ident = _charclass_plus_rule("ident", "a", "z")
    parents = compute_parents([term, num, ident])
    assert parents == {"num": "Term", "ident": "Term"}


def test_compute_parents_only_single_ruleref_arms_create_parent():
    """A multi-item arm doesn't make its rulerefs into subclasses."""
    rule = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))),
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral(")")),
            ),
        ),
    )
    inner = IrRule(
        "num",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    expr = IrRule("expr", IrAlternation(IrSequence(IrItem(IrRuleRef("num")))))
    parents = compute_parents([rule, inner, expr])
    assert parents == {"num": "Value"}  # expr is in a multi-item arm; no parent


def test_compute_parents_quantified_ruleref_arm_does_not_create_parent():
    """`alt ::= a+ | b` — `a` has a quantifier, so it's not a 'single ref'."""
    rule = IrRule(
        "alt",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("a"), IrQuantifier(1, IrNone))),
            IrSequence(IrItem(IrRuleRef("b"))),
        ),
    )
    a_rule = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a")))))
    b_rule = IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("b")))))
    parents = compute_parents([rule, a_rule, b_rule])
    assert parents == {"b": "Alt"}


def test_compute_parents_only_alternations_contribute():
    """Sequence rules don't create parent relationships."""
    seq_rule = IrRule(
        "expr",
        IrAlternation(IrSequence(IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b")))),
    )
    a = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a")))))
    b = IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("b")))))
    assert not compute_parents([seq_rule, a, b])


def test_compute_parents_uses_pascal_case_class_names():
    """`json-value ::= num | ident` → parents use PascalCase class names."""
    rule = IrRule(
        "json-value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))), IrSequence(IrItem(IrRuleRef("ident")))
        ),
    )
    num = IrRule(
        "num",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    ident = IrRule(
        "ident",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    parents = compute_parents([rule, num, ident])
    assert parents == {"num": "JsonValue", "ident": "JsonValue"}


# ── hoist_helpers ─────────────────────────────────────────────────────


def test_hoist_no_groups_returns_unchanged():
    """A rule with no groups is returned as-is."""
    rule = IrRule("r", IrAlternation(IrSequence(IrItem(IrRuleRef("x")))))
    ast = IrAst(
        IrSeq(
            rule,
        ),
        start="r",
    )
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_unquantified_group_with_rulerefs_stays_inline():
    """`(a | b)` no quantifier is an inline-alternation candidate; not hoisted."""
    rule = IrRule(
        "r",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("a"))),
                        IrSequence(IrItem(IrRuleRef("b"))),
                    )
                )
            )
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="r",
    )
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_literal_only_quantified_group_stays_inline():
    """`("foo"|"bar")+` is a regex pattern candidate; not hoisted."""
    rule = IrRule(
        "r",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("foo"))),
                        IrSequence(IrItem(IrLiteral("bar"))),
                    ),
                    IrQuantifier(1, IrNone),
                )
            )
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="r",
    )
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_quantified_multi_arm_group_with_rulerefs():
    """`(a | b)+` → r-item ::= a | b; r body becomes (r-item)+."""
    rule = IrRule(
        "r",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("a"))),
                        IrSequence(IrItem(IrRuleRef("b"))),
                    ),
                    IrQuantifier(1, IrNone),
                )
            )
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="r",
    )
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "r-item"
    assert helper.body == IrAlternation(
        IrSequence(IrItem(IrRuleRef("a"))), IrSequence(IrItem(IrRuleRef("b")))
    )
    new_item = out_ast.rules[0].body[0][0]
    assert new_item.atom == IrRuleRef("r-item")
    assert new_item.quantifier == IrQuantifier(1, IrNone)


def test_hoist_quantified_single_arm_group_with_rulerefs():
    """`expr ::= term (op term)*` — the (op term)* group hoists to a helper."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term")))
                    ),
                    IrQuantifier(0, IrNone),
                ),
            )
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="expr",
    )
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "expr-item"
    assert helper.body[0][0].atom == IrRuleRef("op")
    assert helper.body[0][1].atom == IrRuleRef("term")
    items = out_ast.rules[0].body[0]
    assert items[0].atom == IrRuleRef("term")
    assert items[1].atom == IrRuleRef("expr-item")
    assert items[1].quantifier == IrQuantifier(0, IrNone)


def test_hoist_assigns_unique_names_when_multiple_helpers():
    """Two hoisted groups in the same rule get distinct names."""
    rule = IrRule(
        "r",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(IrSequence(IrItem(IrRuleRef("a")))),
                    IrQuantifier(1, IrNone),
                ),
                IrItem(
                    IrAlternation(IrSequence(IrItem(IrRuleRef("b")))),
                    IrQuantifier(1, IrNone),
                ),
            )
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="r",
    )
    _out_ast, helpers = hoist_helpers(ast)
    assert sorted(h.name for h in helpers) == ["r-item", "r-item2"]


def test_hoist_preserves_ast_start():
    """The `start` field of IrAst is preserved after hoisting."""
    rule = IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("x")))))
    other = IrRule("x", IrAlternation(IrSequence(IrItem(IrLiteral("X")))))
    ast = IrAst(IrSeq(rule, other), "root")
    out_ast, _helpers = hoist_helpers(ast)
    assert out_ast.start == "root"


def test_hoist_uses_irtransformer():
    """_HoistTransformer must be an IrTransformer subclass (Decision CQ #3)."""
    assert issubclass(_HoistTransformer, IrTransformer)


# ── derive_specs ──────────────────────────────────────────────────────


def test_derive_value_str_single_arm():
    """`digit ::= [0-9]+` → one value_str spec, items hold the charclass."""
    rule = _charclass_plus_rule("digit", "0", "9")
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="digit",
    )
    specs = derive_specs(ast)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.rule_name == "digit"
    assert spec.class_name == "Digit"
    assert spec.kind == "value_str"
    assert spec.field_map == {}
    assert len(spec.items) == 1
    assert isinstance(spec.items[0], IrItem)
    assert spec.items[0].atom == IrCharClass(IrRange(IrChr("0"), IrChr("9")))


def test_derive_value_str_multi_arm_uses_iralternation_directly():
    """Multi-arm value_str: IrAlternation directly in items, no IrGroup wrapping (decision C)."""
    rule = IrRule(
        "op",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("+"))), IrSequence(IrItem(IrLiteral("-")))
        ),
    )
    ast = IrAst(
        rules=IrSeq(
            rule,
        ),
        start="op",
    )
    specs = derive_specs(ast)
    spec = specs[0]
    assert spec.kind == "value_str"
    assert len(spec.items) == 1
    assert isinstance(spec.items[0], IrAlternation)
    alt = spec.items[0]
    assert len(alt) == 2
    assert alt[0][0].atom == IrLiteral("+")
    assert alt[1][0].atom == IrLiteral("-")


def test_derive_sequence_basic():
    """`expr ::= term op term` → sequence spec; items flat."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(IrRuleRef("op")),
                IrItem(IrRuleRef("term")),
            ),
        ),
    )
    other = IrRule(
        "term",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    op = IrRule("op", IrAlternation(IrSequence(IrItem(IrLiteral("+")))))
    ast = IrAst(rules=IrSeq(rule, other, op), start="expr")
    specs = derive_specs(ast)
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    assert expr_spec.kind == "sequence"
    assert len(expr_spec.items) == 3
    assert all(
        isinstance(i, IrItem) and isinstance(i.atom, IrRuleRef) for i in expr_spec.items
    )
    # Field map maps "term" → 0, "op" → 1, "term2" → 2 (collision rename)
    assert "term" in expr_spec.field_map
    assert "op" in expr_spec.field_map
    assert "term2" in expr_spec.field_map


def test_derive_alternation_produces_abstract_plus_no_arm_specs_for_single_refs():
    """`term ::= num | ident` → 3 specs (Term abstract + Num + Ident).

    Term's items are [IrItem(IrRuleRef("num")), IrItem(IrRuleRef("ident"))];
    Num and Ident have parent=Term.
    """
    term = IrRule(
        "term",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))), IrSequence(IrItem(IrRuleRef("ident")))
        ),
    )
    num = _charclass_plus_rule("num", "0", "9")
    ident = _charclass_plus_rule("ident", "a", "z")
    ast = IrAst(rules=IrSeq(term, num, ident), start="term")
    specs = derive_specs(ast)
    by = {s.rule_name: s for s in specs}
    assert by["term"].kind == "alternation"
    assert by["term"].field_map == {}
    assert [i.atom for i in by["term"].items if isinstance(i, IrItem)] == [
        IrRuleRef("num"),
        IrRuleRef("ident"),
    ]
    assert by["num"].parent_class_name == "Term"
    assert by["ident"].parent_class_name == "Term"


def test_derive_alternation_with_multi_item_arm_synthesises_arm_spec():
    """`value ::= num | "(" expr ")"` produces Value abstract + Num parent + ValueArm2."""
    value = IrRule(
        "value",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("num"))),
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("expr")),
                IrItem(IrLiteral(")")),
            ),
        ),
    )
    num = _charclass_plus_rule("num", "0", "9")
    expr = IrRule("expr", IrAlternation(IrSequence(IrItem(IrRuleRef("num")))))
    ast = IrAst(rules=IrSeq(value, num, expr), start="value")
    specs = derive_specs(ast)
    by = {s.rule_name: s for s in specs}
    assert "value-arm2" in by
    arm2 = by["value-arm2"]
    assert arm2.kind == "sequence"
    assert arm2.parent_class_name == "Value"
    # Num still gets parent=Value (single-ref arm)
    assert by["num"].parent_class_name == "Value"


def test_derive_topo_sort_puts_start_first():
    """Topo sort puts start rule first."""
    a = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("a")))))
    root = IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("a")))))
    ast = IrAst(rules=IrSeq(a, root), start="root")
    specs = derive_specs(ast)
    assert specs[0].rule_name == "root"


def test_derive_helper_rules_appear_in_output():
    """Hoisted helpers become real RuleSpecs in the result."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term")))
                    ),
                    IrQuantifier(0, IrNone),
                ),
            )
        ),
    )
    op = IrRule("op", IrAlternation(IrSequence(IrItem(IrLiteral("+")))))
    term = IrRule(
        "term",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ast = IrAst(rules=IrSeq(rule, op, term), start="expr")
    specs = derive_specs(ast)
    names = {s.rule_name for s in specs}
    assert "expr-item" in names
    helper = next(s for s in specs if s.rule_name == "expr-item")
    assert helper.kind == "sequence"


def test_derive_marks_non_semantic_field_min_zero():
    """`expr ::= term ws op` with `ws` flagged `semantic=False` forces ws field lo=0."""
    expr = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(IrRuleRef("ws")),
                IrItem(IrRuleRef("op")),
            )
        ),
    )
    term = IrRule(
        "term",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ws = IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrChr(" "), IrChr("\t")), IrQuantifier(0, IrNone))
            )
        ),
        semantic=False,
    )
    op = IrRule("op", IrAlternation(IrSequence(IrItem(IrLiteral("+")))))
    ast = IrAst(rules=IrSeq(expr, term, ws, op), start="expr")
    specs = derive_specs(ast)
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    # Find the ws item
    ws_item = next(
        i
        for i in expr_spec.items
        if isinstance(i, IrItem) and isinstance(i.atom, IrRuleRef) and i.atom == "ws"
    )
    assert isinstance(ws_item, IrItem)
    assert ws_item.quantifier.lo == 0
    assert "ws" in expr_spec.non_semantic_fields


def test_derive_no_non_semantic_when_rule_not_in_set():
    """Without `non_semantic_rules`, ws fields stay required."""
    expr = IrRule(
        "expr",
        IrAlternation(IrSequence(IrItem(IrRuleRef("term")), IrItem(IrRuleRef("ws")))),
    )
    term = IrRule(
        "term",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ws = IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrChr(" "), IrChr("\t")), IrQuantifier(0, IrNone))
            )
        ),
    )
    ast = IrAst(rules=IrSeq(expr, term, ws), start="expr")
    specs = derive_specs(ast)  # no non_semantic_rules
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    ws_item = next(
        i
        for i in expr_spec.items
        if isinstance(i, IrItem) and isinstance(i.atom, IrRuleRef) and i.atom == "ws"
    )
    assert isinstance(ws_item, IrItem)
    assert ws_item.quantifier.lo == 1
    assert expr_spec.non_semantic_fields == frozenset()


def test_helpers_always_get_grammar_model_parent():
    """Hoisted helpers do not participate in alternation-driven parent inference."""
    rule = IrRule(
        "expr",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrRuleRef("op")), IrItem(IrRuleRef("term")))
                    ),
                    IrQuantifier(0, IrNone),
                ),
            )
        ),
    )
    op = IrRule("op", IrAlternation(IrSequence(IrItem(IrLiteral("+")))))
    term = IrRule(
        "term",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ast = IrAst(IrSeq(rule, op, term), "expr")
    specs = derive_specs(ast)
    helper = next(s for s in specs if s.rule_name == "expr-item")
    assert helper.parent_class_name == "GrammarModel"


def test_field_map_tier3_pattern_positional_head():
    """First IrCharClass without Tier 2 match → 'head'."""
    items = [
        IrItem(IrCharClass(*(IrChr(c) for c in "xyz_unmatched")), IrQuantifier(1, 1))
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head"]


def test_field_map_tier3_pattern_positional_part_n():
    """Second IrCharClass without Tier 2 match → 'part_2'."""
    items = [
        IrItem(IrCharClass(*(IrChr(c) for c in "xyz_unmatched")), IrQuantifier(1, 1)),
        IrItem(IrCharClass(*(IrChr(c) for c in "abc_unmatched")), IrQuantifier(1, 1)),
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head", "part_2"]


def test_field_map_tier2_match_takes_precedence_over_tier3():
    """An IrCharClass matching the Tier 2 library uses the library name."""
    items = [
        IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9"))), IrQuantifier(1, IrNone))
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digit"]


def test_field_map_mixed_tier2_and_tier3():
    """A Tier-2 hit + Tier-3 fallback in the same rule."""
    items = [
        IrItem(
            IrCharClass(IrRange(IrChr("0"), IrChr("9"))), IrQuantifier(1, IrNone)
        ),  # → 'digit'
        IrItem(
            IrCharClass(*(IrChr(c) for c in "xyz_unmatched")), IrQuantifier(1, 1)
        ),  # → 'head' (first Tier-3 pattern)
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digit", "head"]


def test_field_map_irgroup_with_ruleref_named_kind():
    """IrGroup containing rulerefs (inline alternation) → 'kind' (was 'value')."""
    grp = IrAlternation(
        IrSequence(
            IrItem(IrRuleRef("a")),
        ),
        IrSequence(
            IrItem(IrRuleRef("b")),
        ),
    )

    items = [IrItem(grp, IrQuantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["kind"]


def test_field_map_ruleref_unchanged_uses_rule_name():
    """Tier 3 does NOT change ruleref naming. Field name stays the rule name."""
    items = [IrItem(IrRuleRef("expr"), IrQuantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["expr"]


def test_pattern_field_falls_back_to_positional_not_sanitized():
    """A non-Tier-2 pattern produces a positional Tier-3 name, not _sanitize_pattern output."""
    items = [IrItem(IrCharClass(*(IrChr(c) for c in "NBKQR")), IrQuantifier(1, 1))]
    fm = _field_map(items)
    # Tier 3: first pattern field → 'head' (not 'nbkqr')
    assert list(fm.keys()) == ["head"]
    assert "nbkqr" not in fm


# ── has_ruleref ───────────────────────────────────────────────────────


def test_has_ruleref_returns_true_when_subtree_contains_ruleref():
    """Subtree with an IrRuleRef anywhere → True."""
    body = IrAlternation(IrSequence(IrItem(IrRuleRef("foo"))))
    assert has_ruleref(body) is True


def test_has_ruleref_returns_false_for_subtree_without_ruleref():
    """Subtree with only literals → False."""
    body = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    assert has_ruleref(body) is False


# ── _EXTRACT_BODY ─────────────────────────────────────────────────────


def test_extract_body_returns_alternation_for_group_with_rulerefs():
    """IrGroup whose body contains a ruleref → the body is returned."""
    body = IrAlternation(IrSequence(IrItem(IrRuleRef("x"))))
    g = body
    assert _EXTRACT_BODY.apply(g) == body


def test_extract_body_returns_none_for_pure_literal_group():
    """IrGroup with no rulerefs anywhere → ``None``."""
    body = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    assert _EXTRACT_BODY.apply(body) is IrNone


def test_extract_body_returns_none_for_non_group_atom():
    """Non-IrGroup atoms — IrLiteral and IrRuleRef — always return ``None``."""
    assert _EXTRACT_BODY.apply(IrLiteral("x")) is IrNone
    assert _EXTRACT_BODY.apply(IrRuleRef("y")) is IrNone
