"""Sanity: codegen package importable."""

from __future__ import annotations

import inspect
from pathlib import Path

from lexic.codegen import codegen
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrQuantifier, IrRuleRef
from lexic.ir.spec import RuleSpec


def _spec(name, kind, items, field_map=None):
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
    )


def test_codegen_returns_dict_of_classes(tmp_path, monkeypatch):
    """codegen(specs, stem) writes generated/<stem>.py and returns the loaded class dict."""
    # Run with a sandbox `generated/` directory so we don't pollute the repo
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    spec = _spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    classes = codegen([spec], stem="test_codegen_simple")
    assert "Greet" in classes
    assert classes["Greet"].__grammar__.rule_name == "greet"


def test_codegen_handles_rule_refs(tmp_path, monkeypatch):
    """codegen(specs, stem) writes generated/<stem>.py and returns the loaded class dict."""
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    inner = _spec(
        "expr", "value_str", [IrItem(IrCharClass("a-z"), IrQuantifier(1, None))]
    )
    outer = _spec(
        "root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0}
    )
    classes = codegen([outer, inner], stem="test_codegen_refs")
    assert "Root" in classes
    assert "Expr" in classes


def test_codegen_no_flavour_parameter():
    """Spec invariant: codegen does not take a flavour."""
    sig = inspect.signature(codegen)
    assert "flavour" not in sig.parameters
