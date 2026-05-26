# tests/unit/lexic/ir/test_derive.py
"""derive_specs and friends — IR-side structural decomposition."""

from __future__ import annotations

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
    IrGroup,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk_2 import IrTransformer


def _seq(*items):
    return IrSequence(tuple(items))


def _alt(*arms):
    return IrAlternation(tuple(arms))


def _it(atom, q=None):
    return IrItem(atom, q if q else IrQuantifier())


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
        _alt(_seq(_it(IrCharClass("0-9"), IrQuantifier(1, None)))),
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
                    IrQuantifier(0, None),
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
                _it(IrLiteral("-"), IrQuantifier(0, 1)),
                _it(IrCharClass("0-9"), IrQuantifier(1, None)),
                _it(
                    IrGroup(
                        _alt(
                            _seq(
                                _it(IrLiteral(".")),
                                _it(IrCharClass("0-9"), IrQuantifier(1, None)),
                            )
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
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), IrQuantifier(1, None)))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z"), IrQuantifier(1, None)))))
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
            _seq(_it(IrRuleRef("a"), IrQuantifier(1, None))),
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


# ── hoist_helpers ─────────────────────────────────────────────────────


def test_hoist_no_groups_returns_unchanged():
    """A rule with no groups is returned as-is."""
    rule = IrRule("r", _alt(_seq(_it(IrRuleRef("x")))))
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_unquantified_group_with_rulerefs_stays_inline():
    """`(a | b)` no quantifier is an inline-alternation candidate; not hoisted."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(IrGroup(_alt(_seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b"))))))
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_literal_only_quantified_group_stays_inline():
    """`("foo"|"bar")+` is a regex pattern candidate; not hoisted."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(
                        _alt(_seq(_it(IrLiteral("foo"))), _seq(_it(IrLiteral("bar"))))
                    ),
                    IrQuantifier(1, None),
                )
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert not helpers
    assert out_ast == ast


def test_hoist_quantified_multi_arm_group_with_rulerefs():
    """`(a | b)+` → r-item ::= a | b; r body becomes (r-item)+."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b"))))),
                    IrQuantifier(1, None),
                )
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "r-item"
    assert helper.body == _alt(_seq(_it(IrRuleRef("a"))), _seq(_it(IrRuleRef("b"))))
    new_item = out_ast.rules[0].body.arms[0].items[0]
    assert new_item.atom == IrRuleRef("r-item")
    assert new_item.quantifier == IrQuantifier(1, None)


def test_hoist_quantified_single_arm_group_with_rulerefs():
    """`expr ::= term (op term)*` — the (op term)* group hoists to a helper."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    IrQuantifier(0, None),
                ),
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="expr")
    out_ast, helpers = hoist_helpers(ast)
    assert len(helpers) == 1
    helper = helpers[0]
    assert helper.name == "expr-item"
    assert helper.body.arms[0].items[0].atom == IrRuleRef("op")
    assert helper.body.arms[0].items[1].atom == IrRuleRef("term")
    items = out_ast.rules[0].body.arms[0].items
    assert items[0].atom == IrRuleRef("term")
    assert items[1].atom == IrRuleRef("expr-item")
    assert items[1].quantifier == IrQuantifier(0, None)


def test_hoist_assigns_unique_names_when_multiple_helpers():
    """Two hoisted groups in the same rule get distinct names."""
    rule = IrRule(
        "r",
        _alt(
            _seq(
                _it(IrGroup(_alt(_seq(_it(IrRuleRef("a"))))), IrQuantifier(1, None)),
                _it(IrGroup(_alt(_seq(_it(IrRuleRef("b"))))), IrQuantifier(1, None)),
            )
        ),
    )
    ast = IrAst(rules=(rule,), start="r")
    _out_ast, helpers = hoist_helpers(ast)
    assert sorted(h.name for h in helpers) == ["r-item", "r-item2"]


def test_hoist_preserves_ast_start():
    """The `start` field of IrAst is preserved after hoisting."""
    rule = IrRule("root", _alt(_seq(_it(IrRuleRef("x")))))
    other = IrRule("x", _alt(_seq(_it(IrLiteral("X")))))
    ast = IrAst(rules=(rule, other), start="root")
    out_ast, _helpers = hoist_helpers(ast)
    assert out_ast.start == "root"


def test_hoist_uses_irtransformer():
    """_HoistTransformer must be an IrTransformer subclass (Decision CQ #3)."""
    assert issubclass(_HoistTransformer, IrTransformer)


# ── derive_specs ──────────────────────────────────────────────────────


def test_derive_value_str_single_arm():
    """`digit ::= [0-9]+` → one value_str spec, items hold the charclass."""
    rule = IrRule(
        "digit",
        _alt(_seq(_it(IrCharClass("0-9"), IrQuantifier(1, None)))),
    )
    ast = IrAst(rules=(rule,), start="digit")
    specs = derive_specs(ast)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.rule_name == "digit"
    assert spec.class_name == "Digit"
    assert spec.kind == "value_str"
    assert spec.field_map == {}
    assert len(spec.items) == 1
    assert isinstance(spec.items[0], IrItem)
    assert spec.items[0].atom == IrCharClass("0-9")


def test_derive_value_str_multi_arm_uses_iralternation_directly():
    """Multi-arm value_str: IrAlternation directly in items, no IrGroup wrapping (decision C)."""
    rule = IrRule(
        "op",
        _alt(_seq(_it(IrLiteral("+"))), _seq(_it(IrLiteral("-")))),
    )
    ast = IrAst(rules=(rule,), start="op")
    specs = derive_specs(ast)
    spec = specs[0]
    assert spec.kind == "value_str"
    assert len(spec.items) == 1
    assert isinstance(spec.items[0], IrAlternation)
    alt = spec.items[0]
    assert len(alt.arms) == 2
    assert alt.arms[0].items[0].atom == IrLiteral("+")
    assert alt.arms[1].items[0].atom == IrLiteral("-")


def test_derive_sequence_basic():
    """`expr ::= term op term` → sequence spec; items flat."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(_it(IrRuleRef("term")), _it(IrRuleRef("op")), _it(IrRuleRef("term"))),
        ),
    )
    other = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    ast = IrAst(rules=(rule, other, op), start="expr")
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
        _alt(_seq(_it(IrRuleRef("num"))), _seq(_it(IrRuleRef("ident")))),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), IrQuantifier(1, None)))))
    ident = IrRule("ident", _alt(_seq(_it(IrCharClass("a-z"), IrQuantifier(1, None)))))
    ast = IrAst(rules=(term, num, ident), start="term")
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
        _alt(
            _seq(_it(IrRuleRef("num"))),
            _seq(_it(IrLiteral("(")), _it(IrRuleRef("expr")), _it(IrLiteral(")"))),
        ),
    )
    num = IrRule("num", _alt(_seq(_it(IrCharClass("0-9"), IrQuantifier(1, None)))))
    expr = IrRule("expr", _alt(_seq(_it(IrRuleRef("num")))))
    ast = IrAst(rules=(value, num, expr), start="value")
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
    a = IrRule("a", _alt(_seq(_it(IrLiteral("a")))))
    root = IrRule("root", _alt(_seq(_it(IrRuleRef("a")))))
    ast = IrAst(rules=(a, root), start="root")
    specs = derive_specs(ast)
    assert specs[0].rule_name == "root"


def test_derive_helper_rules_appear_in_output():
    """Hoisted helpers become real RuleSpecs in the result."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    IrQuantifier(0, None),
                ),
            )
        ),
    )
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ast = IrAst(rules=(rule, op, term), start="expr")
    specs = derive_specs(ast)
    names = {s.rule_name for s in specs}
    assert "expr-item" in names
    helper = next(s for s in specs if s.rule_name == "expr-item")
    assert helper.kind == "sequence"


def test_derive_marks_non_semantic_field_min_zero():
    """`expr ::= term ws op` with non_semantic_rules={"ws"} forces ws field min=0."""
    expr = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("term")), _it(IrRuleRef("ws")), _it(IrRuleRef("op")))),
    )
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ws = IrRule("ws", _alt(_seq(_it(IrCharClass(" \\t"), IrQuantifier(0, None)))))
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    ast = IrAst(rules=(expr, term, ws, op), start="expr")
    specs = derive_specs(ast, non_semantic_rules=frozenset({"ws"}))
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    # Find the ws item
    ws_item = next(
        i
        for i in expr_spec.items
        if isinstance(i, IrItem)
        and isinstance(i.atom, IrRuleRef)
        and i.atom.value == "ws"
    )
    assert isinstance(ws_item, IrItem)
    assert ws_item.quantifier.min == 0
    assert "ws" in expr_spec.non_semantic_fields


def test_derive_no_non_semantic_when_rule_not_in_set():
    """Without `non_semantic_rules`, ws fields stay required."""
    expr = IrRule(
        "expr",
        _alt(_seq(_it(IrRuleRef("term")), _it(IrRuleRef("ws")))),
    )
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ws = IrRule("ws", _alt(_seq(_it(IrCharClass(" \\t"), IrQuantifier(0, None)))))
    ast = IrAst(rules=(expr, term, ws), start="expr")
    specs = derive_specs(ast)  # no non_semantic_rules
    expr_spec = next(s for s in specs if s.rule_name == "expr")
    ws_item = next(
        i
        for i in expr_spec.items
        if isinstance(i, IrItem)
        and isinstance(i.atom, IrRuleRef)
        and i.atom.value == "ws"
    )
    assert isinstance(ws_item, IrItem)
    assert ws_item.quantifier.min == 1
    assert expr_spec.non_semantic_fields == frozenset()


def test_helpers_always_get_grammar_model_parent():
    """Hoisted helpers do not participate in alternation-driven parent inference."""
    rule = IrRule(
        "expr",
        _alt(
            _seq(
                _it(IrRuleRef("term")),
                _it(
                    IrGroup(_alt(_seq(_it(IrRuleRef("op")), _it(IrRuleRef("term"))))),
                    IrQuantifier(0, None),
                ),
            )
        ),
    )
    op = IrRule("op", _alt(_seq(_it(IrLiteral("+")))))
    term = IrRule("term", _alt(_seq(_it(IrCharClass("a-z")))))
    ast = IrAst(rules=(rule, op, term), start="expr")
    specs = derive_specs(ast)
    helper = next(s for s in specs if s.rule_name == "expr-item")
    assert helper.parent_class_name == "GrammarModel"


def test_field_map_tier3_pattern_positional_head():
    """First IrCharClass without Tier 2 match → 'head'."""
    items = [IrItem(IrCharClass("xyz_unmatched"), IrQuantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head"]


def test_field_map_tier3_pattern_positional_part_n():
    """Second IrCharClass without Tier 2 match → 'part_2'."""
    items = [
        IrItem(IrCharClass("xyz_unmatched"), IrQuantifier(1, 1)),
        IrItem(IrCharClass("abc_unmatched"), IrQuantifier(1, 1)),
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head", "part_2"]


def test_field_map_tier2_match_takes_precedence_over_tier3():
    """An IrCharClass matching the Tier 2 library uses the library name."""
    items = [IrItem(IrCharClass("0-9"), IrQuantifier(1, None))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digit"]


def test_field_map_mixed_tier2_and_tier3():
    """A Tier-2 hit + Tier-3 fallback in the same rule."""
    items = [
        IrItem(IrCharClass("0-9"), IrQuantifier(1, None)),  # → 'digit'
        IrItem(
            IrCharClass("xyz_unmatched"), IrQuantifier(1, 1)
        ),  # → 'head' (first Tier-3 pattern)
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digit", "head"]


def test_field_map_irgroup_with_ruleref_named_kind():
    """IrGroup containing rulerefs (inline alternation) → 'kind' (was 'value')."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrRuleRef("a")),)),
                IrSequence((IrItem(IrRuleRef("b")),)),
            )
        )
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
    items = [IrItem(IrCharClass("NBKQR"), IrQuantifier(1, 1))]
    fm = _field_map(items)
    # Tier 3: first pattern field → 'head' (not 'nbkqr')
    assert list(fm.keys()) == ["head"]
    assert "nbkqr" not in fm


# ── has_ruleref ───────────────────────────────────────────────────────


def test_has_ruleref_returns_true_when_subtree_contains_ruleref():
    """Subtree with an IrRuleRef anywhere → True."""
    body = _alt(_seq(_it(IrRuleRef("foo"))))
    assert has_ruleref(body) is True


def test_has_ruleref_returns_false_for_subtree_without_ruleref():
    """Subtree with only literals → False."""
    body = _alt(_seq(_it(IrLiteral("a"))))
    assert has_ruleref(body) is False


# ── _EXTRACT_BODY ─────────────────────────────────────────────────────


def test_extract_body_returns_alternation_for_group_with_rulerefs():
    """IrGroup whose body contains a ruleref → the body is returned."""
    body = _alt(_seq(_it(IrRuleRef("x"))))
    g = IrGroup(body)
    assert _EXTRACT_BODY.apply(g) == body


def test_extract_body_returns_none_for_pure_literal_group():
    """IrGroup with no rulerefs anywhere → ``None``."""
    body = _alt(_seq(_it(IrLiteral("x"))))
    assert _EXTRACT_BODY.apply(IrGroup(body)) is None


def test_extract_body_returns_none_for_non_group_atom():
    """Non-IrGroup atoms — IrLiteral and IrRuleRef — always return ``None``."""
    assert _EXTRACT_BODY.apply(IrLiteral("x")) is None
    assert _EXTRACT_BODY.apply(IrRuleRef("y")) is None
