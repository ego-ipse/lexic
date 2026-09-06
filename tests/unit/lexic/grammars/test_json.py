"""Tests for src/lexic/grammars/json.py — the hand-authored JSON IR grammar."""

from __future__ import annotations

import json as stdlib_json  # oracle only — never in src

import pytest

from lexic.compile import compile_ast
from lexic.compile.pipeline.moments import build_codegen_grammar
from lexic.compile.pipeline.rulemap import compute_binding
from lexic.compile.pipeline.synthesis import synthesize
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    IrAst,
    IrCharClass,
    IrInt,
    IrLiteral,
    IrMap,
    IrNone,
    IrRange,
    IrRule,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
    fold_name,
)
from tests.unit.lexic.parsing.ir_fixtures import JSON_RULE_NAMES

# ── Basic structure ───────────────────────────────────────────────────


def test_json_grammar_is_ir_ast():
    """`JSON_GRAMMAR` is an :class:`IrAst`."""
    assert isinstance(JSON_GRAMMAR, IrAst)


def test_json_grammar_start_rule():
    """`JSON_GRAMMAR.start` is ``\"json-text\"`` — canonicalize's rewrite 7
    folds the RFC 8259 ``JSON-text`` spelling to lowercase (JSON_GRAMMAR is
    itself in canonical form, per the ``canonicalize(G) == G`` fixpoint)."""
    assert JSON_GRAMMAR.start == "json-text"


def test_json_grammar_rule_count():
    """`JSON_GRAMMAR` contains 32 rules (the full RFC 8259 set)."""
    assert len(JSON_GRAMMAR.rules) == 32


def test_json_grammar_expected_rule_names():
    """`JSON_GRAMMAR` contains every RFC 8259 rule name, canonically folded.

    ``JSON_RULE_NAMES`` (shared with the raw-parse equivalence fixture, which
    intentionally sees the un-folded source spelling) stays mixed-case;
    ``JSON_GRAMMAR`` itself is canonical, so the expected set is folded here.
    """
    actual = {r.name for r in JSON_GRAMMAR.rules}
    assert actual == {fold_name(name) for name in JSON_RULE_NAMES}


# ── Canonical-form choices ────────────────────────────────────────────


def find_rule(name: str) -> IrRule:
    """Return the named rule from JSON_GRAMMAR."""
    for rule in JSON_GRAMMAR.rules:
        if rule.name == name:
            return rule
    raise KeyError(name)  # pragma: no cover


def test_begin_object_left_brace_is_ir_literal():
    """``begin-object``'s ``{`` is an :class:`IrLiteral`, not a char class."""
    rule = find_rule("begin-object")
    seq = rule.body[0]
    # structure: ws { ws — the literal is the middle item
    middle = seq[1]
    assert isinstance(middle.atom, IrLiteral)
    assert middle.atom == IrLiteral("{")


def test_unescaped_uses_positive_ir_ranges():
    """``unescaped`` is expressed as positive :class:`IrRange` spans (no negation).

    ABNF cannot express negated char classes, so the canonical form uses
    ``%x20-21 / %x23-5B / %x5D-10FFFF`` positive ranges.
    """
    rule = find_rule("unescaped")
    seq = rule.body[0]
    atom = seq[0].atom
    assert isinstance(atom, IrCharClass)
    elements = list(atom)
    assert all(isinstance(el, IrRange) for el in elements), (
        f"Expected only IrRange elements, got: {elements}"
    )
    assert len(elements) == 3


def test_false_rule_is_ir_literal():
    """``false`` is a multi-char :class:`IrLiteral`, not individual char classes."""
    rule = find_rule("false")
    seq = rule.body[0]
    atom = seq[0].atom
    assert isinstance(atom, IrLiteral)
    assert atom == IrLiteral("false")


def test_null_rule_is_ir_literal():
    """``null`` is an :class:`IrLiteral`."""
    rule = find_rule("null")
    seq = rule.body[0]
    assert seq[0].atom == IrLiteral("null")


def test_true_rule_is_ir_literal():
    """``true`` is an :class:`IrLiteral`."""
    rule = find_rule("true")
    seq = rule.body[0]
    assert seq[0].atom == IrLiteral("true")


def test_ws_uses_charclass():
    """``ws`` uses a single :class:`IrCharClass` for the four whitespace chars."""
    rule = find_rule("ws")
    seq = rule.body[0]
    atom = seq[0].atom
    assert isinstance(atom, IrCharClass)


# ── Pipeline smoke tests ──────────────────────────────────────────────


def json_ast_with_non_semantic() -> IrAst:
    """``JSON_GRAMMAR`` rebound with the ``ws`` rule flagged ``semantic=False``."""
    rules = (
        IrRule(r.name, r.body, semantic=False) if r.name == "ws" else r
        for r in JSON_GRAMMAR.rules
    )
    return IrAst(rules=IrSeq(*rules), start=JSON_GRAMMAR.start)


def test_binding_view_succeeds():
    """``compute_binding`` runs without error and returns a non-empty list."""
    binding = compute_binding(build_codegen_grammar(json_ast_with_non_semantic()))
    assert isinstance(binding, list)
    assert len(binding) > 0


def test_binding_view_includes_start_rule():
    """The binding view includes the start rule (folded name)."""
    binding = compute_binding(build_codegen_grammar(json_ast_with_non_semantic()))
    names = {b.rule_name for b in binding}
    assert "json-text" in names


def test_codegen_produces_classes():
    """``synthesize(...)`` builds the model classes without error.

    The class name folds from the canonical (lowercase) rule name, so
    ``json-text`` -> ``JsonText``, not the old acronym-cased ``JSONText``.
    """
    canonical = json_ast_with_non_semantic()
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    classes = synthesize(codegen_grammar, binding, "json_grammar_test")
    assert isinstance(classes, dict)
    assert len(classes) > 0
    assert "JsonText" in classes


# ── JSON_REDUCER — scalars ─────────────────────────────────────────────


def reduce(text: str) -> IrSelf:
    """Reduce ``text`` through ``JSON_GRAMMAR``/``JSON_REDUCER``."""
    return compile_ast(JSON_GRAMMAR).reduce(text, JSON_REDUCER)


def test_reduce_true_is_irint_one():
    """``true`` reduces to ``IrInt(1)``."""
    assert reduce("true") == IrInt(1)


def test_reduce_false_is_irint_zero():
    """``false`` reduces to ``IrInt(0)``."""
    assert reduce("false") == IrInt(0)


def test_reduce_null_is_irnone():
    """``null`` reduces to the ``IrNone`` singleton, by identity."""
    assert reduce("null") is IrNone


def test_reduce_integer_is_irint():
    """A plain integer reduces to ``IrInt``."""
    assert reduce("42") == IrInt(42)


def test_reduce_negative_integer_is_irint():
    """A negative integer reduces to ``IrInt`` (sign-aware decode)."""
    assert reduce("-7") == IrInt(-7)


def test_reduce_fractional_number_raises():
    """A fractional number refuses — the IR carries no float leaf."""
    with pytest.raises(UnsupportedConstructError, match="no float leaf"):
        reduce("1.5")


def test_reduce_exponent_number_raises():
    """An exponent number refuses — the IR carries no float leaf."""
    with pytest.raises(UnsupportedConstructError, match="no float leaf"):
        reduce("1e5")


# ── JSON_REDUCER — strings ──────────────────────────────────────────────


def test_reduce_plain_string():
    """A string with no escapes reduces to its own text."""
    assert reduce('"hello"') == IrStr("hello")


@pytest.mark.parametrize(
    "text,expected",
    [
        ('"a\\nb"', "a\nb"),
        ('"a\\tb"', "a\tb"),
        ('"a\\"b"', 'a"b'),
        ('"a\\\\b"', "a\\b"),
        ('"a\\/b"', "a/b"),
    ],
)
def test_reduce_short_escape(text: str, expected: str):
    """Each short escape decodes to its literal character."""
    assert reduce(text) == IrStr(expected)


def test_reduce_unicode_escape():
    """A ``\\uXXXX`` escape decodes to its BMP glyph."""
    assert reduce('"\\u0041"') == IrStr("A")


def test_reduce_astral_surrogate_pair_matches_stdlib():
    """A surrogate-pair escape combines into its astral code point."""
    text = '"\\ud83d\\ude00"'
    assert reduce(text) == IrStr(stdlib_json.loads(text))


def test_reduce_literal_astral_char_passes_through():
    """A literal (unescaped) astral char in the source text is unchanged."""
    assert reduce('"😀"') == IrStr("😀")


# ── JSON_REDUCER — objects / arrays ──────────────────────────────────────


def test_reduce_object_is_irmap_with_decoded_keys_and_typed_values():
    """An object reduces to an ``IrMap`` of decoded string keys → typed values."""
    doc = reduce('{"a": 1, "b": true}')
    assert doc == IrMap(
        IrTuple(IrStr("a"), IrInt(1)),
        IrTuple(IrStr("b"), IrInt(1)),
    )


def test_reduce_array_is_irtuple_of_typed_values():
    """An array reduces to a plain tuple of typed values."""
    assert reduce("[1, null, false]") == IrTuple(IrInt(1), IrNone, IrInt(0))


def test_reduce_nested_object_and_array():
    """A nested document reduces recursively through the same reductions."""
    doc = reduce('{"xs": [1, {"y": 2}]}')
    assert doc == IrMap(
        IrTuple(
            IrStr("xs"),
            IrTuple(IrInt(1), IrMap(IrTuple(IrStr("y"), IrInt(2)))),
        ),
    )


def test_reduce_empty_object():
    """An empty object reduces to an empty ``IrMap``."""
    assert reduce("{}") == IrMap()


def test_reduce_empty_array():
    """An empty array reduces to an empty tuple."""
    assert reduce("[]") == IrTuple()


def test_reduce_is_whitespace_insensitive():
    """Extra whitespace around tokens does not change the reduced value."""
    assert reduce('{"a":1,"b":2}') == reduce(' { "a" : 1 , "b" : 2 } ')


# ── JSON_REDUCER — oracle: agreement with stdlib ``json`` ────────────────


def _de_ir(value: object) -> object:
    """De-IR shim — reduce IR values to stdlib-json shapes (type-faithful)."""
    if value is IrNone:
        return None
    if isinstance(value, IrMap):
        return {str(k): _de_ir(v) for k, v in value.items()}
    if isinstance(value, tuple) and not isinstance(value, str):
        return [_de_ir(v) for v in value]
    if isinstance(value, IrInt):
        return int(value)
    return str(value)


@pytest.mark.parametrize(
    "text",
    [
        '{"a": [1, 2, 3], "b": {"c": null, "d": true, "e": false}}',
        '["\\u0041\\ud83d\\ude00", "plain", 0, -12]',
        "{}",
        "[]",
        '{"nested": {"deep": [1, [2, [3]]]}}',
    ],
)
def test_reduce_matches_stdlib_oracle(text: str):
    """The de-IR'd reduction matches ``json.loads`` on a handful of documents."""
    assert _de_ir(reduce(text)) == stdlib_json.loads(text)
