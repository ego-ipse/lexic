"""Tests for src/lexic/grammars/json.py — the hand-authored JSON IR grammar."""

from __future__ import annotations

from lexic.codegen import codegen
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir.derive import derive_specs
from lexic.ir.nodes import (
    IrAst,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRule,
)
from tests._ir_fixtures import JSON_RULE_NAMES

# ── Basic structure ───────────────────────────────────────────────────


def test_json_grammar_is_ir_ast():
    """`JSON_GRAMMAR` is an :class:`IrAst`."""
    assert isinstance(JSON_GRAMMAR, IrAst)


def test_json_grammar_start_rule():
    """`JSON_GRAMMAR.start` is ``\"JSON-text\"``."""
    assert JSON_GRAMMAR.start == "JSON-text"


def test_json_grammar_rule_count():
    """`JSON_GRAMMAR` contains 32 rules (the full RFC 8259 set)."""
    assert len(JSON_GRAMMAR.rules) == 32


def test_json_grammar_expected_rule_names():
    """`JSON_GRAMMAR` contains every RFC 8259 rule name."""
    actual = {r.name for r in JSON_GRAMMAR.rules}
    assert actual == set(JSON_RULE_NAMES)


# ── Canonical-form choices ────────────────────────────────────────────


def _find_rule(name: str) -> IrRule:
    """Return the named rule from JSON_GRAMMAR."""
    for rule in JSON_GRAMMAR.rules:
        if rule.name == name:
            return rule
    raise KeyError(name)  # pragma: no cover


def test_begin_object_left_brace_is_ir_literal():
    """``begin-object``'s ``{`` is an :class:`IrLiteral`, not a char class."""
    rule = _find_rule("begin-object")
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
    rule = _find_rule("unescaped")
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
    rule = _find_rule("false")
    seq = rule.body[0]
    atom = seq[0].atom
    assert isinstance(atom, IrLiteral)
    assert atom == IrLiteral("false")


def test_null_rule_is_ir_literal():
    """``null`` is an :class:`IrLiteral`."""
    rule = _find_rule("null")
    seq = rule.body[0]
    assert seq[0].atom == IrLiteral("null")


def test_true_rule_is_ir_literal():
    """``true`` is an :class:`IrLiteral`."""
    rule = _find_rule("true")
    seq = rule.body[0]
    assert seq[0].atom == IrLiteral("true")


def test_ws_uses_charclass():
    """``ws`` uses a single :class:`IrCharClass` for the four whitespace chars."""
    rule = _find_rule("ws")
    seq = rule.body[0]
    atom = seq[0].atom
    assert isinstance(atom, IrCharClass)


# ── Pipeline smoke tests ──────────────────────────────────────────────


def _json_ast_with_non_semantic() -> IrAst:
    """``JSON_GRAMMAR`` rebound with ``ws`` marked non-semantic."""
    return IrAst(
        rules=JSON_GRAMMAR.rules,
        start=JSON_GRAMMAR.start,
        non_semantic=frozenset({"ws"}),
    )


def test_derive_specs_succeeds():
    """``derive_specs(ast)`` runs without error and returns a list."""
    specs = derive_specs(_json_ast_with_non_semantic())
    assert isinstance(specs, list)
    assert len(specs) > 0


def test_derive_specs_includes_start_rule():
    """The derived spec list includes a spec for the start rule."""
    specs = derive_specs(_json_ast_with_non_semantic())
    names = {s.rule_name for s in specs}
    assert "JSON-text" in names


def test_codegen_produces_classes():
    """``codegen(specs, ...)`` generates Pydantic classes without error."""
    specs = derive_specs(_json_ast_with_non_semantic())
    classes = codegen(specs, "json_grammar_test")
    assert isinstance(classes, dict)
    assert len(classes) > 0
    assert "JSONText" in classes
