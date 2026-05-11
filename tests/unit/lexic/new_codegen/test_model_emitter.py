"""Model emitter — class-body emission (skeleton)."""

from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import NewRuleSpec
from lexic.new_codegen.model_emitter import emit_module_source


def _spec(name, kind, items, parent="GrammarModel", field_map=None):
    return NewRuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name=parent,
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )


def test_emit_value_str_class_body():
    """Value-str classes emit a single `value: str` field."""
    spec = _spec(
        "digit", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))]
    )
    src = emit_module_source([spec], stem="m")
    assert "class Digit(GrammarModel):" in src
    # Skeleton stage: pattern field emitted as plain `str`. Refined in Task 10.
    assert "value: str" in src


def test_emit_sequence_class_with_ruleref_field():
    """Sequence classes with rulerefs emit fields of the referred type."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "class Root(GrammarModel):" in src
    assert "expr: Expr" in src


def test_emit_optional_field_for_quantifier_0_1():
    """Quantifier {0,1} emits Optional[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(0, 1))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "Optional[Expr]" in src or "Expr | None" in src


def test_emit_list_field_for_quantifier_unbounded():
    """Quantifier {1,+inf} emits List[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(1, None))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "List[Expr]" in src


def test_emit_list_field_for_quantifier_zero_or_more():
    """Quantifier {0,+inf} also emits List[...] field."""
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))]
    )
    outer = _spec(
        "r",
        "sequence",
        [IrItem(IrRuleRef("expr"), Quantifier(0, None))],
        field_map={"expr": 0},
    )
    src = emit_module_source([outer, inner], stem="m")
    assert "List[Expr]" in src


def test_emit_alternation_kind_emits_pass():
    """Alternation-kind specs emit only __grammar__ + pass (no fields)."""
    spec = _spec("node", "alternation", [], field_map={})
    src = emit_module_source([spec], stem="m")
    assert "class Node(GrammarModel):" in src
    assert "pass" in src
    assert "value:" not in src


def test_emit_value_str_multi_arm():
    """Multi-arm value_str (IrAlternation in items) serialises without FIXME."""
    spec = _spec(
        "tok",
        "value_str",
        [
            IrAlternation(
                (
                    IrSequence((IrItem(IrLiteral("a")),)),
                    IrSequence((IrItem(IrLiteral("b")),)),
                )
            )
        ],
    )
    src = emit_module_source([spec], stem="m")
    assert "class Tok(GrammarModel):" in src
    assert "FIXME" not in src
    assert "IrAlternation" in src


def test_emitted_module_has_canonical_imports():
    """Emitted modules have canonical imports."""
    spec = _spec("r", "value_str", [IrItem(IrLiteral("x"))])
    src = emit_module_source([spec], stem="m")
    expected_lines = [
        "from lexic.base import GrammarModel",
        "from lexic.ir.spec import NewRuleSpec",
        "from lexic.ir.nodes import",
    ]
    for line in expected_lines:
        assert line in src, f"missing canonical import: {line}"


def test_no_fixme_in_emitted_source():
    """Decision CQ #1: never emit # FIXME placeholders."""
    grp = IrGroup(
        IrAlternation(
            (
                IrSequence((IrItem(IrLiteral("a")),)),
                IrSequence((IrItem(IrLiteral("b")),)),
            )
        )
    )
    spec = _spec("r", "value_str", [IrItem(grp, Quantifier(1, 1))])
    src = emit_module_source([spec], stem="m")
    assert "# FIXME" not in src
    assert "FIXME" not in src
