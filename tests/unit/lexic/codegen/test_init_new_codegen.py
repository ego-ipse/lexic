"""Sanity: codegen package importable and the binding-driven entry works."""

from __future__ import annotations

import inspect
from pathlib import Path

from lexic.codegen import codegen
from lexic.codegen.binding import compute_binding
from lexic.codegen.passes import build_codegen_grammar
from lexic.compile import canonical_grammar
from lexic.grammars.gbnf import GBNF_FLAVOUR


def _codegen(text: str, stem: str) -> dict[str, type]:
    """Run the front half then emit: canonical → codegen grammar → binding → classes."""
    canonical = canonical_grammar(text, GBNF_FLAVOUR)
    codegen_grammar = build_codegen_grammar(canonical)
    binding = compute_binding(codegen_grammar)
    return codegen(canonical, codegen_grammar, binding, stem)


def test_codegen_returns_dict_of_classes(tmp_path, monkeypatch):
    """codegen(...) writes generated/<stem>.py and returns the loaded class dict."""
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    classes = _codegen('greet ::= "hi"\n', "test_codegen_simple")
    assert "Greet" in classes
    assert classes["Greet"].__grammar__.name == "greet"


def test_codegen_handles_rule_refs(tmp_path, monkeypatch):
    """codegen(...) resolves rule refs into distinct model classes."""
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    classes = _codegen("root ::= expr\nexpr ::= [a-z]+\n", "test_codegen_refs")
    assert "Root" in classes
    assert "Expr" in classes


def test_codegen_no_flavour_parameter():
    """Spec invariant: codegen does not take a flavour."""
    sig = inspect.signature(codegen)
    assert "flavour" not in sig.parameters


def test_codegen_loads_deep_ref_chain_with_resolvable_binds(tmp_path, monkeypatch):
    """A long unit-ref chain loads whole and every class's binds resolve.

    The pydantic-era assertion (``__pydantic_complete__`` after the
    leaf-first ``model_rebuild`` walk) died with the record spine —
    ``model_rebuild`` is a no-op shim now. What survives to pin: the loader
    returns every class of the chain, and each class's ``IrBind`` metadata
    resolves through the public ``bound_fields()`` with no depth limit.
    """
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    depth = 300
    lines = [f'r{i} ::= "[" r{i + 1} "]"' for i in range(depth)]
    lines.append(f'r{depth} ::= "0"')
    classes = _codegen("\n".join(lines) + "\n", "test_codegen_deep_chain")
    assert len(classes) == depth + 1
    assert all(isinstance(cls.bound_fields(), dict) for cls in classes.values())
