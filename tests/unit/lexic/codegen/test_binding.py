"""Tests for codegen/binding.py — the per-rule binding view."""

from __future__ import annotations

import pytest

from lexic.codegen.binding import (
    bind_fields,
    class_name_for,
    classify_rule,
    compute_binding,
    mode_for,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrChr, IrNone, IrSeq
from lexic.ir.bind import IrBind
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

_DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
_RANGE_AC = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
_OPT = IrQuantifier(0, 1)
_STAR = IrQuantifier(0, IrNone)


# ── class naming ──────────────────────────────────────────────────────


def test_class_name_pascalcases_hyphens_and_underscores():
    """Both canonical hyphens and legacy underscores split words."""
    assert class_name_for("jp-char") == "JpChar"
    assert class_name_for("json_ws") == "JsonWs"


def test_class_name_suffixes_python_keywords():
    """A rule named after a keyword still yields a legal class name."""
    assert class_name_for("true") == "True_"


# ── kind classification ───────────────────────────────────────────────


def test_classify_value_str_without_rulerefs():
    """A body with no IrRuleRef anywhere is value_str, even multi-arm."""
    rule = IrRule("v", IrAlternation(IrLiteral("a"), IrLiteral("b")))
    assert classify_rule(rule) == "value_str"


def test_classify_alternation_needs_two_non_empty_arms():
    """Multiple ref-bearing arms classify as alternation."""
    rule = IrRule("a", IrAlternation(IrRuleRef("x"), IrRuleRef("y")))
    assert classify_rule(rule) == "alternation"


def test_classify_sequence_when_one_arm_is_empty():
    """An empty alternate arm does not promote a sequence to alternation."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrRuleRef("x"))), IrSequence()))
    assert classify_rule(rule) == "sequence"


# ── field naming cascade ──────────────────────────────────────────────


def test_fields_tier1_ruleref_uses_rule_name_underscored():
    """A ref field is named after its rule, hyphens to underscores."""
    fields = bind_fields(IrSequence(IrItem(IrRuleRef("jp-char"))), frozenset())
    assert fields == {"jp_char": IrBind(0, "model")}


def test_fields_tier2_charclass_library_hit():
    """[0-9] hits the pattern library as ``digit``."""
    fields = bind_fields(IrSequence(IrItem(_DIGIT, _STAR)), frozenset())
    assert fields == {"digit": IrBind(0, "text")}


def test_fields_tier3_positional_head_then_part_n():
    """Unmatched pattern fields fall through to head / part_2."""
    novel = IrCharClass(IrChr("!"), IrChr("?"))
    fields = bind_fields(
        IrSequence(IrItem(novel, _STAR), IrItem(novel, _STAR)), frozenset()
    )
    assert list(fields) == ["head", "part_2"]


def test_fields_structural_literal_produces_no_field():
    """A unit-quantified literal is matched text, never a field."""
    fields = bind_fields(
        IrSequence(IrItem(IrLiteral("=")), IrItem(IrRuleRef("x"))), frozenset()
    )
    assert fields == {"x": IrBind(1, "model")}


def test_fields_quantified_literal_names_from_the_library():
    """A quantified literal DOES bind, named by the literal table."""
    fields = bind_fields(IrSequence(IrItem(IrLiteral("-"), _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "text")}


def test_fields_collisions_get_numeric_suffixes():
    """Repeated base names count up: ws, ws2."""
    ws = IrItem(IrRuleRef("ws"))
    fields = bind_fields(IrSequence(ws, IrItem(IrLiteral(",")), ws), frozenset())
    assert list(fields) == ["ws", "ws2"]


def test_fields_collisions_count_up_a_third_time():
    """A third occurrence of the same base name continues the suffix run."""
    ws = IrItem(IrRuleRef("ws"))
    fields = bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws, IrItem(IrLiteral(";")), ws),
        frozenset(),
    )
    assert list(fields) == ["ws", "ws2", "ws3"]


def test_fields_non_semantic_ref_flags_the_bind():
    """A ref to a noise rule binds with semantic=False."""
    fields = bind_fields(IrSequence(IrItem(IrRuleRef("ws"))), frozenset({"ws"}))
    assert fields == {"ws": IrBind(0, "model", False)}


def test_fields_unknown_atom_type_raises():
    """The tier-2 table refuses an atom type it does not know.

    ``IrNot`` cannot occur in a canonical grammar (rewrite 4 eliminates it),
    so the binding tables deliberately omit it — the dispatch default must
    refuse it loudly rather than drop the field.
    """
    with pytest.raises(UnsupportedConstructError):
        bind_fields(IrSequence(IrItem(IrNot(IrLiteral("a")))), frozenset())


# ── group naming ──────────────────────────────────────────────────────


def test_fields_ref_bearing_group_is_named_kind():
    """A group containing rulerefs binds the structural slot name ``kind``."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"kind": IrBind(0, "model")}


def test_fields_literal_group_named_from_first_atom():
    """A literal-only group names itself from its first arm's first atom."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral("+"))), IrLiteral("*"))
    fields = bind_fields(IrSequence(IrItem(group, _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "gtext")}


def test_fields_literal_group_named_from_charclass_slug_fallback():
    """A literal-only group whose first atom is a non-library charclass names
    itself from the pattern slug (Tier-2 slug fallback, not the library)."""
    group = IrAlternation(IrSequence(IrItem(_RANGE_AC)))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"a_c": IrBind(0, "gtext")}


def test_fields_literal_group_with_unslugable_charclass_falls_to_tier3():
    """A charclass whose pattern has no identifier-safe characters at all
    (its slug is empty) falls through the reserved "cc" hint to Tier-3."""
    group = IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("@")))))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"head": IrBind(0, "gtext")}


# ── fold modes ────────────────────────────────────────────────────────


def test_mode_repeated_ref_is_models():
    """hi > 1 (or unbounded) on a ref yields the list mode."""
    assert mode_for(IrItem(IrRuleRef("x"), _STAR)) == "models"


def test_mode_optional_ref_is_model():
    """hi == 1 keeps the single-model mode even when optional."""
    assert mode_for(IrItem(IrRuleRef("x"), _OPT)) == "model"


def test_mode_bounded_multi_count_ref_is_models():
    """A bounded count above one (2,5) also yields the list mode."""
    assert mode_for(IrItem(IrRuleRef("x"), IrQuantifier(2, 5))) == "models"


def test_mode_unknown_atom_type_raises():
    """The mode table refuses an atom type it does not know (IrNot cannot
    occur in a canonical grammar; the raising default keeps it loud)."""
    with pytest.raises(UnsupportedConstructError):
        mode_for(IrItem(IrNot(IrLiteral("a"))))


def test_mode_ref_bearing_group_follows_quantifier():
    """A ref-bearing group folds like a ref: model vs models by hi."""
    group = IrAlternation(IrRuleRef("a"))
    assert mode_for(IrItem(group)) == "model"
    assert mode_for(IrItem(group, _STAR)) == "models"


# ── compute_binding over a small grammar ──────────────────────────────


def _small_ast() -> IrAst:
    """start → choice ws?; choice → a | b; a/b value rules; ws noise."""
    return IrAst(
        IrSeq(
            IrRule(
                "start",
                IrSequence(IrItem(IrRuleRef("choice")), IrItem(IrRuleRef("ws"), _OPT)),
            ),
            IrRule("choice", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
            IrRule("a", IrLiteral("a")),
            IrRule("b", IrLiteral("b")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR), semantic=False),
        ),
        "start",
    )


def test_compute_binding_assigns_alternation_arm_parents():
    """Rules named as unit-ref arms inherit the alternation's class."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["a"].parent_class_name == "Choice"
    assert by_name["b"].parent_class_name == "Choice"
    assert by_name["choice"].parent_class_name == "GrammarModel"


def test_compute_binding_orders_parents_before_subclasses():
    """A binding never precedes the binding of its parent class."""
    bindings = compute_binding(_small_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for binding in bindings:
        if binding.parent_class_name in positions:
            assert positions[binding.parent_class_name] < positions[binding.class_name]


def test_compute_binding_starts_with_the_start_rule():
    """The start rule (parentless here) leads the emission order."""
    assert compute_binding(_small_ast())[0].rule_name == "start"


def test_compute_binding_flags_noise_fields_from_the_ast():
    """ast.non_semantic drives the per-field semantic flag."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["start"].fields["ws"].semantic is False
    assert by_name["start"].fields["choice"].semantic is True


def test_compute_binding_alternation_and_value_str_have_no_fields():
    """Only sequence-kind rules carry field bindings."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["choice"].fields == {}
    assert by_name["a"].fields == {}
