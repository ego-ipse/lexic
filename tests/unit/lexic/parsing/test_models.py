"""Tests for lexic.parsing.models — the instance-parsing bridge.

RuleSpecs + generated classes → an engine-ready normalized IrAst plus a
ModelFold; ModelFold folds a ParseTree (from parse_first) into model
instances. Replaces the retired Lark build_lark/build_transformer pair.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from lexic.codegen import codegen
from lexic.compile import compile_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir.base import IrNone, IrSeq
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
from lexic.ir.operators import IrNot
from lexic.parsing import parse_first
from lexic.parsing.models import (
    ModelFold,
    _instance_run_ok,
    _lift_optional_nullables,
    _nullable_names,
    _specs_to_rules,
    _wrapper_mode,
    collapsed_instance_tables,
)
from lexic.parsing.tables import compile_tables
from tests._ir_fixtures import spec as _spec

GBNF_FLAVOUR = get_flavour("gbnf")


# ── build_instance_parser / ModelFold.for_specs — structure ────────────


def test_build_instance_parser_returns_normalized_ast_and_fold(arithmetic):
    """build_instance_parser returns (IrAst, ModelFold)."""
    _, _, _, grammar, fold = arithmetic
    assert isinstance(grammar, IrAst)
    assert isinstance(fold, ModelFold)


def test_grammar_is_normalized(arithmetic):
    """The returned grammar is Earley-normalized: parse_first accepts it directly.

    parse_first raises "run normalize() before compiling" on a raw grammar
    (tables.py), so a successful parse is itself proof of normalization.
    """
    _, _, _, grammar, _ = arithmetic
    tree = parse_first(grammar, "x=1\n")
    assert tree is not None


def test_for_specs_is_what_build_instance_parser_delegates_to():
    """build_instance_parser(specs, classes, start) == ModelFold.for_specs(...)."""
    text = 'root ::= "a" thing? ("!")? "b"\nthing ::= "T"\n'
    start, specs = compile_grammar(text, GBNF_FLAVOUR)
    classes = codegen(specs, "test_models_for_specs")
    grammar, fold = ModelFold.for_specs(specs, classes, start)
    assert isinstance(grammar, IrAst)
    assert isinstance(fold, ModelFold)


def test_wrapper_rules_exist_for_field_bearing_items(arithmetic):
    """<rule>--f<idx> wrapper rules exist for every field-bearing item, with
    the expected fold mode and original (pre-lift) quantifier lo."""
    _, _, _, _, fold = arithmetic
    assert fold.wrappers["root--f0"] == ("models", 1)
    assert fold.wrappers["expr--f0"] == ("model", 1)
    assert fold.wrappers["expr--f1"] == ("models", 0)
    assert fold.wrappers["ident--f0"] == ("text", 1)
    assert fold.wrappers["num--f0"] == ("text", 1)


def test_unquantified_literals_stay_inline_no_field(arithmetic):
    """Structural (1,1) literals never get a wrapper rule or a field.

    root-item ::= expr "=" ws term "\\n" — items 1 ('=') and 4 ('\\n') are
    unquantified literals.
    """
    _, specs, _, _, fold = arithmetic
    root_item = next(s for s in specs if s.rule_name == "root-item")
    assert 1 not in root_item.field_map.values()
    assert 4 not in root_item.field_map.values()
    assert "root-item--f1" not in fold.wrappers
    assert "root-item--f4" not in fold.wrappers


def test_collision_with_wrapper_name_raises():
    """A user rule literally named like a synthesized wrapper collides."""
    host = _spec(
        "host",
        "sequence",
        [IrItem(IrRuleRef("item"), IrQuantifier(0, 1))],
        field_map={"item": 0},
    )
    collider = _spec("host--f0", "value_str", [IrItem(IrLiteral("x"))])
    with pytest.raises(UnsupportedConstructError, match="collides with a wrapper name"):
        _specs_to_rules([host, collider], {})


# ── ModelFold.apply — fold behaviors end-to-end ─────────────────────────


def test_sequence_kwargs_via_field_map(arithmetic):
    """A sequence rule's fields map to constructor kwargs by field_map index."""
    _, _, _, grammar, fold = arithmetic
    model = fold.apply(parse_first(grammar, "x=1\n"))
    item = model.root_item[0]
    assert item.expr.term.lower == "x"
    assert item.term.digit == "1"


def test_terminal_field_empty_match_is_empty_string(arithmetic):
    """An empty terminal match (ident's [a-z0-9_]* tail, unmatched) folds to ''."""
    _, _, _, grammar, fold = arithmetic
    model = fold.apply(parse_first(grammar, "x=1\n"))
    ident = model.root_item[0].expr.term
    assert ident.head == ""


def test_ruleref_list_field_unbounded(arithmetic):
    """An unbounded ref list ('root_item', one per repetition) collects all."""
    _, _, _, grammar, fold = arithmetic
    model = fold.apply(parse_first(grammar, "x=1\ny=2\n"))
    assert len(model.root_item) == 2
    assert model.root_item[0].expr.term.lower == "x"
    assert model.root_item[1].expr.term.lower == "y"


def test_alternation_passthrough(arithmetic):
    """An alternation-kind rule ('term') folds through to its matched arm's model."""
    _, _, _, grammar, fold = arithmetic
    model = fold.apply(parse_first(grammar, "x=1\n"))
    term = model.root_item[0].expr.term
    assert type(term).__name__ == "Ident"


def test_value_str_joins_matched_text(arithmetic):
    """A value_str rule ('ws') folds to its matched span joined as one string."""
    _, _, _, grammar, fold = arithmetic
    model = fold.apply(parse_first(grammar, "x = 1\n"))
    # ident's own trailing ws eats the space before '='; root-item's ws slot
    # eats the space after '=' — two distinct single-space gaps, not one.
    assert model.root_item[0].expr.term.ws.value == " "
    assert model.root_item[0].ws.value == " "


def test_end_to_end_round_trip(arithmetic):
    """fold.apply(parse_first(...)).to_text() reproduces the input exactly."""
    _, _, _, grammar, fold = arithmetic
    text = "x=1\n"
    model = fold.apply(parse_first(grammar, text))
    assert model.to_text() == text


def test_optional_ref_absent_is_none(optional_shapes):
    """An optional ref to a non-nullable rule is None when absent."""
    _, _, _, grammar, fold = optional_shapes
    model = fold.apply(parse_first(grammar, "ab"))
    assert model.thing is None


def test_optional_ref_present_is_the_submodel(optional_shapes):
    """An optional ref to a non-nullable rule is the sub-model when present."""
    _, _, _, grammar, fold = optional_shapes
    model = fold.apply(parse_first(grammar, "aTb"))
    assert model.thing.value == "T"


def test_optional_literal_group_absent_is_none(optional_shapes):
    """An optional literal-only group ('gtext' mode) is None when absent."""
    _, _, _, grammar, fold = optional_shapes
    model = fold.apply(parse_first(grammar, "ab"))
    assert model.head is None


def test_optional_literal_group_present_is_text(optional_shapes):
    """An optional literal-only group is the matched text when present."""
    _, _, _, grammar, fold = optional_shapes
    model = fold.apply(parse_first(grammar, "a!b"))
    assert model.head == "!"


# ── _wrapper_mode ────────────────────────────────────────────────────────


def test_wrapper_mode_text_for_charclass():
    """A quantified charclass atom folds as 'text'."""
    item = IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9"))), IrQuantifier(1, IrNone))
    assert _wrapper_mode(item) == "text"


def test_wrapper_mode_text_for_not():
    """A negated charclass atom folds as 'text'."""
    item = IrItem(IrNot(IrCharClass(IrChr('"'))), IrQuantifier(0, IrNone))
    assert _wrapper_mode(item) == "text"


def test_wrapper_mode_text_for_quantified_literal():
    """A quantified (field-bearing) literal atom folds as 'text'."""
    item = IrItem(IrLiteral("x"), IrQuantifier(0, 1))
    assert _wrapper_mode(item) == "text"


def test_wrapper_mode_model_for_singular_ruleref():
    """A ruleref quantified to at most one occurrence folds as 'model'."""
    item = IrItem(IrRuleRef("foo"), IrQuantifier(0, 1))
    assert _wrapper_mode(item) == "model"


def test_wrapper_mode_models_for_unbounded_ruleref():
    """A ruleref quantified open-ended (hi=IrNone) folds as 'models'."""
    item = IrItem(IrRuleRef("foo"), IrQuantifier(0, IrNone))
    assert _wrapper_mode(item) == "models"


def test_wrapper_mode_models_for_multi_count_ruleref():
    """A ruleref quantified to more than one occurrence folds as 'models'."""
    item = IrItem(IrRuleRef("foo"), IrQuantifier(2, 5))
    assert _wrapper_mode(item) == "models"


def test_wrapper_mode_gtext_for_literal_only_group():
    """A group whose arms hold no ruleref folds as 'gtext'."""
    item = IrItem(IrAlternation(IrSequence(IrItem(IrLiteral("!")))), IrQuantifier(0, 1))
    assert _wrapper_mode(item) == "gtext"


def test_wrapper_mode_models_for_group_with_ruleref():
    """A group whose arms hold a ruleref folds as 'model'/'models' like a ref."""
    item = IrItem(
        IrAlternation(IrSequence(IrItem(IrRuleRef("bar")))), IrQuantifier(0, IrNone)
    )
    assert _wrapper_mode(item) == "models"


def test_wrapper_mode_raises_for_unknown_atom_type():
    """An atom type with no wrapper-mode rule raises UnsupportedConstructError."""
    bogus_item = cast(IrItem, SimpleNamespace(atom=42, quantifier=IrQuantifier(1, 1)))
    with pytest.raises(UnsupportedConstructError, match="no wrapper mode"):
        _wrapper_mode(bogus_item)


# ── _nullable_names ──────────────────────────────────────────────────────


def test_nullable_names_empty_literal():
    """A rule whose body is an empty literal is nullable."""
    rule = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    assert "empty" in _nullable_names([rule])


def test_nullable_names_lo_zero_item():
    """A rule whose sole item has quantifier lo=0 is nullable."""
    rule = IrRule(
        "zero_lo", IrAlternation(IrSequence(IrItem(IrLiteral("x"), IrQuantifier(0, 1))))
    )
    assert "zero_lo" in _nullable_names([rule])


def test_nullable_names_alternation_arm():
    """A rule with one empty arm (among others) is nullable."""
    rule = IrRule(
        "alt", IrAlternation(IrSequence(), IrSequence(IrItem(IrLiteral("y"))))
    )
    assert "alt" in _nullable_names([rule])


def test_nullable_names_transitive_ref():
    """A rule that refs a nullable rule is transitively nullable (fixpoint)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    transitive = IrRule(
        "transitive", IrAlternation(IrSequence(IrItem(IrRuleRef("empty"))))
    )
    names = _nullable_names([empty, transitive])
    assert "transitive" in names


def test_nullable_names_excludes_non_nullable():
    """A rule requiring a non-empty literal is not nullable."""
    rule = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    assert "solid" not in _nullable_names([rule])


# ── _lift_optional_nullables ──────────────────────────────────────────────


def test_lift_rewrites_optional_ref_to_nullable_as_mandatory():
    """An optional (0,1) ref to a nullable rule is lifted to (1,1)."""
    empty = IrRule("empty", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("empty"), IrQuantifier(0, 1)))),
    )
    lifted = _lift_optional_nullables([empty, host])
    host_lifted = next(r for r in lifted if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.atom == IrRuleRef("empty")
    assert item.quantifier == IrQuantifier(1, 1)


def test_lift_leaves_optional_ref_to_non_nullable_untouched():
    """An optional (0,1) ref to a non-nullable rule is left as-is."""
    solid = IrRule("solid", IrAlternation(IrSequence(IrItem(IrLiteral("z")))))
    host = IrRule(
        "host",
        IrAlternation(IrSequence(IrItem(IrRuleRef("solid"), IrQuantifier(0, 1)))),
    )
    lifted = _lift_optional_nullables([solid, host])
    host_lifted = next(r for r in lifted if str(r.name) == "host")
    item = host_lifted.body[0][0]
    assert item.quantifier == IrQuantifier(0, 1)


# ── collapsed_instance_tables (Task 4) ───────────────────────────────────


def test_collapsed_instance_tables_collapses_a_run_on_arithmetic(arithmetic):
    """arithmetic.gbnf's num/ident charclass runs collapse to RunTerm leaves.

    A collapsed run shows up as a ``lens == 0`` terminal — see
    :class:`~lexic.parsing.tables.TermTables`.
    """
    _, _, _, grammar, fold = arithmetic
    plain = compile_tables(grammar)
    collapsed = collapsed_instance_tables(grammar, fold)
    assert collapsed is not plain
    assert any(length == 0 for length in collapsed.terms.lens)


def test_collapsed_instance_tables_memoises_per_fold_and_grammar(arithmetic):
    """The same (fold, grammar) pair returns the identical tables object."""
    _, _, _, grammar, fold = arithmetic
    first = collapsed_instance_tables(grammar, fold)
    second = collapsed_instance_tables(grammar, fold)
    assert first is second


def test_collapsed_instance_tables_returns_plain_when_no_candidates(optional_shapes):
    """A grammar with no star/plus run candidates gets back the plain tables."""
    _, _, _, grammar, fold = optional_shapes
    plain = compile_tables(grammar)
    collapsed = collapsed_instance_tables(grammar, fold)
    assert collapsed is plain


# ── _instance_run_ok (Task 4) ─────────────────────────────────────────────


def test_instance_run_ok_true_for_bare_terminal_unit(digit_grammar):
    """A bare-terminal run unit (unit_rid == -1) is always instance-safe."""
    fold = ModelFold([], {})
    tables = compile_tables(digit_grammar)
    assert _instance_run_ok(fold, tables, -1) is True


def test_instance_run_ok_false_when_unit_is_a_specd_rule(digit_grammar):
    """A run whose unit resolves to a user rule (a RuleSpec) is not instance-safe."""
    digit_spec = _spec(
        "digit", "value_str", [IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9"))))]
    )
    fold = ModelFold([digit_spec], {})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert _instance_run_ok(fold, tables, digit_rid) is False


def test_instance_run_ok_false_when_unit_is_a_wrapper_rule():
    """A run whose unit resolves to a field-wrapper rule is not instance-safe either."""
    fold = ModelFold([], {})
    fold.wrappers["host--f0"] = ("text", 1)
    wrapper_rule = IrRule("host--f0", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    g = IrAst(rules=IrSeq(wrapper_rule), start="host--f0")
    tables = compile_tables(g)
    wrapper_rid = tables.decode.rule_ids["host--f0"]
    assert _instance_run_ok(fold, tables, wrapper_rid) is False


def test_instance_run_ok_true_when_leaf_rule_untracked_by_fold(digit_grammar):
    """A leaf rule the fold doesn't know about (no spec, no wrapper) is safe."""
    fold = ModelFold([], {})
    tables = compile_tables(digit_grammar)
    digit_rid = tables.decode.rule_ids["digit"]
    assert _instance_run_ok(fold, tables, digit_rid) is True
