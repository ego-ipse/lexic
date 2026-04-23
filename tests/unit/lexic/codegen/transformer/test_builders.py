"""Unit tests for src/lexic/codegen/transformer/builders.py"""

from lark import Token

from lexic.base import GrammarModel
from lexic.ir import (
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.codegen.transformer.builders import (
    CharClassFieldBuilder,
    InlineAlternationBuilder,
    InlineRegexBuilder,
    ListFieldBuilder,
    OptionalFieldBuilder,
    QuantifiedLiteralBuilder,
    RuleRefBuilder,
)
from lexic.codegen.transformer.context import BuildContext, FieldResult, SkipField


def _spec(items):
    return RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=items,
        field_map={},
    )


def _mktoken(text: str) -> Token:
    return Token("X", text)


class _Ws(GrammarModel):
    value: str = ""


class _Expr(GrammarModel):
    value: str = ""


# ---------------------------------------------------------------------------
# CharClassFieldBuilder
# ---------------------------------------------------------------------------


def test_charclass_single_char():
    atom = CharClassAtom(pattern="[0-9]", min=1, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(_mktoken("7"),), hints={"d": str})
    assert CharClassFieldBuilder().build(atom, "d", ctx) == FieldResult(
        value="7", consumed=1
    )


def test_charclass_multi_char_consumes_consecutive_tokens():
    atom = CharClassAtom(pattern="[0-9]", min=1, max=None)
    ctx = BuildContext(
        spec=_spec([atom]),
        children=(_mktoken("1"), _mktoken("2"), _mktoken("3")),
        hints={"d": str},
    )
    assert CharClassFieldBuilder().build(atom, "d", ctx) == FieldResult(
        value="123", consumed=3
    )


def test_charclass_optional_with_no_child_returns_empty():
    atom = CharClassAtom(pattern="[+-]", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"opt": str})
    assert CharClassFieldBuilder().build(atom, "opt", ctx) == FieldResult(
        value="", consumed=0
    )


# ---------------------------------------------------------------------------
# QuantifiedLiteralBuilder
# ---------------------------------------------------------------------------


def test_quantified_literal_present_consumes_one():
    atom = QuantifiedLiteralAtom(value="-", min=0, max=1)
    ctx = BuildContext(
        spec=_spec([atom]), children=(_mktoken("-"),), hints={"sign": str}
    )
    assert QuantifiedLiteralBuilder().build(atom, "sign", ctx) == FieldResult(
        value="-", consumed=1
    )


def test_quantified_literal_absent_returns_empty():
    atom = QuantifiedLiteralAtom(value="-", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"sign": str})
    assert QuantifiedLiteralBuilder().build(atom, "sign", ctx) == FieldResult(
        value="", consumed=0
    )


# ---------------------------------------------------------------------------
# InlineRegexBuilder
# ---------------------------------------------------------------------------


def test_inline_regex_present_consumes_one():
    atom = InlineRegexAtom(regex="[0-9]+", gbnf="[0-9]+", min=1, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(_mktoken("42"),), hints={"n": str})
    assert InlineRegexBuilder().build(atom, "n", ctx) == FieldResult(
        value="42", consumed=1
    )


def test_inline_regex_absent_returns_empty():
    atom = InlineRegexAtom(regex="[0-9]+", gbnf="[0-9]+", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"n": str})
    assert InlineRegexBuilder().build(atom, "n", ctx) == FieldResult(
        value="", consumed=0
    )


# ---------------------------------------------------------------------------
# RuleRefBuilder
# ---------------------------------------------------------------------------


def test_ruleref_ws_with_child_consumes():
    atom = RuleRefAtom(rule_name="ws", min=1, max=1)
    child = _Ws(value=" ")
    ctx = BuildContext(spec=_spec([atom]), children=(child,), hints={"ws": _Ws})
    assert RuleRefBuilder().build(atom, "ws", ctx) == FieldResult(
        value=child, consumed=1
    )


def test_ruleref_ws_without_child_returns_empty_instance():
    atom = RuleRefAtom(rule_name="ws", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"ws": _Ws})
    result = RuleRefBuilder().build(atom, "ws", ctx)
    assert isinstance(result, FieldResult)
    assert result.consumed == 0
    assert isinstance(result.value, _Ws)


def test_ruleref_nonws_with_child_consumes():
    atom = RuleRefAtom(rule_name="expr", min=1, max=1)
    child = _Expr(value="1+1")
    ctx = BuildContext(spec=_spec([atom]), children=(child,), hints={"expr": _Expr})
    assert RuleRefBuilder().build(atom, "expr", ctx) == FieldResult(
        value=child, consumed=1
    )


def test_ruleref_nonws_missing_child_with_str_hint_returns_empty():
    atom = RuleRefAtom(rule_name="expr", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"expr": str})
    assert RuleRefBuilder().build(atom, "expr", ctx) == FieldResult(
        value="", consumed=0
    )


def test_ruleref_nonws_missing_child_with_model_hint_skips():
    atom = RuleRefAtom(rule_name="expr", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"expr": _Expr})
    assert isinstance(RuleRefBuilder().build(atom, "expr", ctx), SkipField)


# ---------------------------------------------------------------------------
# InlineAlternationBuilder
# ---------------------------------------------------------------------------


def test_inline_alternation_consumes_token():
    atom = InlineAlternationAtom(arm_rule_names=["a", "b"])
    ctx = BuildContext(
        spec=_spec([atom]), children=(_mktoken("hello"),), hints={"v": str}
    )
    assert InlineAlternationBuilder().build(atom, "v", ctx) == FieldResult(
        value="hello", consumed=1
    )


# ---------------------------------------------------------------------------
# OptionalFieldBuilder
# ---------------------------------------------------------------------------


def test_optional_empty_returns_none():
    wrapped = OptionalFieldBuilder(CharClassFieldBuilder())
    atom = CharClassAtom(pattern="[0-9]", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"opt": str})
    assert wrapped.build(atom, "opt", ctx) == FieldResult(value=None, consumed=0)


def test_optional_with_child_delegates_to_inner():
    wrapped = OptionalFieldBuilder(CharClassFieldBuilder())
    atom = CharClassAtom(pattern="[0-9]", min=0, max=1)
    ctx = BuildContext(
        spec=_spec([atom]), children=(_mktoken("5"),), hints={"opt": str}
    )
    assert wrapped.build(atom, "opt", ctx) == FieldResult(value="5", consumed=1)


# ---------------------------------------------------------------------------
# ListFieldBuilder
# ---------------------------------------------------------------------------


def test_list_collects_while_inner_matches():
    wrapped = ListFieldBuilder(CharClassFieldBuilder(), inner_type=str)
    atom = CharClassAtom(pattern="[0-9]", min=0, max=None)
    ctx = BuildContext(
        spec=_spec([atom]),
        children=(_mktoken("1"), _mktoken("2"), _mktoken("3")),
        hints={"xs": list[str]},
    )
    result = wrapped.build(atom, "xs", ctx)
    assert isinstance(result, FieldResult)
    assert result.consumed == 3


def test_list_with_grammarmodel_inner_collects_matching_models():
    class _Item(GrammarModel):
        value: str = ""

    atom = RuleRefAtom(rule_name="item", min=0, max=None)
    a, b = _Item(value="a"), _Item(value="b")
    ctx = BuildContext(
        spec=_spec([atom]), children=(a, b), hints={"items": list[_Item]}
    )
    result = ListFieldBuilder(RuleRefBuilder(), inner_type=_Item).build(
        atom, "items", ctx
    )
    assert isinstance(result, FieldResult)
    assert result.value == [a, b]
    assert result.consumed == 2
