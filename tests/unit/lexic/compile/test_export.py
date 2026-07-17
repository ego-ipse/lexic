"""Tests for compile/export.py — the reader-first .py view of a compiled grammar.

Covers: syntactic validity of the rendered source (``ast.parse``), fidelity
spot-checks against the binding view (every class / rule / bound field named),
the never-repr-a-reducer-or-lambda invariant (watch-out 4), and the small
per-helper unit shapes (field typing, optional defaults, union group types).
"""

from __future__ import annotations

import ast
import inspect
import subprocess

import pytest

from lexic.compile import (
    CompiledGrammar,
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.compile.binding import RuleBinding, compute_binding
from lexic.compile.export import (
    _binds_repr,
    _field_type,
    _group_model_type,
    _ruff_format,
    _value_str_type,
    export_module_source,
    export_source,
)
from lexic.compile.passes import build_codegen_grammar
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests.paths import GROUND_TRUTH


def _synth_binding(text: str) -> tuple[IrAst, list[RuleBinding]]:
    """canonical -> codegen grammar -> binding, for the small hand-built probes."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    codegen_grammar = build_codegen_grammar(canonical)
    return codegen_grammar, compute_binding(codegen_grammar)


def _by_name(binding: list[RuleBinding]) -> dict[str, RuleBinding]:
    return {b.rule_name: b for b in binding}


# ── syntactic validity ────────────────────────────────────────────────────


@pytest.mark.parametrize("stem", ["list", "json", "arithmetic"])
def test_export_source_is_valid_python_syntax(stem: str):
    """The rendered view parses as Python for several ground-truth grammars."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    source = export_source(cg, stem=stem)
    ast.parse(source)  # raises SyntaxError on failure


def test_export_module_source_is_valid_python_without_ruff():
    """Even the unformatted source (export_module_source, no ruff pass) parses."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    binding = compute_binding(cg.codegen_grammar)
    source = export_module_source(cg.grammar, cg.codegen_grammar, binding, stem="probe")
    ast.parse(source)


# ── fidelity spot-checks (>= 2 GT grammars) ───────────────────────────────


@pytest.mark.parametrize("stem", ["list", "json"])
def test_export_source_names_every_class_and_its_rule(stem: str):
    """Every binding's class name and rule name appear in the rendered source."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    binding = compute_binding(cg.codegen_grammar)
    source = export_source(cg, stem=stem)
    for bound in binding:
        assert f"class {bound.class_name}(" in source
        assert bound.rule_name in source


@pytest.mark.parametrize("stem", ["list", "json"])
def test_export_source_names_every_bound_field(stem: str):
    """Every sequence-kind rule's field names appear in its class body."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    binding = compute_binding(cg.codegen_grammar)
    source = export_source(cg, stem=stem)
    for bound in binding:
        for name in bound.fields:
            assert f"{name}:" in source, f"field {name!r} of {bound.class_name} missing"


# ── watch-out 4: never repr a reducer / noise map ─────────────────────────


@pytest.mark.parametrize("stem", ["list", "json", "arithmetic"])
def test_export_source_never_mentions_lambda_or_reducer(stem: str):
    """The rendered source carries pure grammar-AST reprs only — no action-algebra."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    source = export_source(cg, stem=stem)
    assert "IrLambda" not in source
    assert "Reducer" not in source


def test_export_module_source_takes_no_fold_or_reducer_argument():
    """export_module_source's signature cannot reach a CompiledGrammar's fold —
    it only ever sees the two grammars and the binding view."""
    params = set(inspect.signature(export_module_source).parameters)
    assert params == {"canonical", "codegen_grammar", "binding", "stem"}


# ── field typing / optional defaults / union groups ───────────────────────


def test_optional_field_renders_a_none_default():
    """A field whose item can match zero times is typed Optional-like with = None."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert "digit: str | None = None" in source


def test_required_field_has_no_default():
    """A required (lo >= 1) field carries no ``= None`` default."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert "word: Word\n" in source


def test_group_model_union_type_lists_every_arm_class_once():
    """A model-mode alternation field renders as a ' | '-joined class union."""
    alt = IrAlternation(
        IrSequence(IrItem(IrRuleRef("a"))), IrSequence(IrItem(IrRuleRef("b")))
    )
    class_by_rule = {"a": "A", "b": "B"}
    assert _group_model_type(alt, class_by_rule) == "A | B"


def test_value_str_pure_literal_alternation_types_as_literal():
    """A multi-arm pure-literal alternation types its permitted-value set."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("true"))),
        IrSequence(IrItem(IrLiteral("false"))),
    )
    rule = IrRule("b", body)
    assert _value_str_type(rule) == "Literal['true', 'false']"


def test_value_str_pattern_body_types_as_plain_str():
    """A single-item single-arm body is a pass-through, never Literal[...]."""
    rule = IrRule("digits", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    assert _value_str_type(rule) == "str"


def test_field_type_models_mode_is_always_a_list_never_optional():
    """A models-mode field types as list[...] regardless of ``optional``: an
    absent repetition is an empty list, not a None default."""
    item = IrItem(IrRuleRef("a"), IrQuantifier(0, IrNone))
    result = _field_type("models", item, {"a": "A"}, optional=True)
    assert result == "list[A]"


def test_binds_repr_round_trips_slot_name_and_bind():
    """Every field's item slot -> (name, IrBind repr) appears in the rendering."""
    _grammar, binding = _synth_binding("root ::= word [0-9]*\nword ::= [a-z]+\n")
    root = _by_name(binding)["root"]
    rendered = _binds_repr(root)
    for name, ibind in root.fields.items():
        assert f"{ibind.item}: ({name!r}, {ibind!r})" in rendered


# ── ruff formatting: best-effort, never fatal ─────────────────────────────


def test_ruff_format_returns_unchanged_source_when_ruff_is_unavailable(monkeypatch):
    """A missing/failing ruff is not fatal — the unformatted source passes through."""

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("no ruff on this PATH")

    monkeypatch.setattr(subprocess, "run", _boom)
    source = "x=1\n"
    assert _ruff_format(source) == source


def test_ruff_format_actually_reformats_when_available():
    """A real ruff pass reformats messy source into a different, still-valid string."""
    messy = "class   Foo( GrammarModel ):\n    value:str\n"
    formatted = _ruff_format(messy)
    assert formatted != messy
    ast.parse(formatted)


# ── public entry surface ──────────────────────────────────────────────────


def test_export_source_docstring_names_the_stem():
    """The rendered module docstring names the caller's stem."""
    cg = compile_text('root ::= "hi"\n')
    source = export_source(cg, stem="my_stem")
    assert "'my_stem'" in source


def test_export_source_default_stem_is_used_when_omitted():
    """A caller who omits ``stem`` gets the neutral default, not a crash."""
    cg = compile_text('root ::= "hi"\n')
    source = export_source(cg)
    assert "'grammar'" in source


def test_export_source_takes_a_compiled_grammar():
    """export_source's one required positional is the CompiledGrammar artefact."""
    params = inspect.signature(export_source).parameters
    assert "compiled" in params
    assert params["compiled"].annotation in (CompiledGrammar, "CompiledGrammar")
