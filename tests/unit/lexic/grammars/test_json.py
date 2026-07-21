"""Tests for src/lexic/grammars/json.py — the hand-authored JSON IR grammar."""

from __future__ import annotations

from lexic.compile.pipeline.binding import compute_binding
from lexic.compile.pipeline.passes import build_codegen_grammar
from lexic.compile.pipeline.synthesis import synthesize
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir.base import IrSeq
from lexic.ir.canonical import fold_name
from lexic.ir.nodes import (
    IrAst,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRule,
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
