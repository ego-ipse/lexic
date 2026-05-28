"""Tests for ir/emit.py — render_specs."""

from lexic.ir.emit import render_specs
from lexic.ir.nodes import IrItem, IrLiteral
from lexic.ir.spec import RuleSpec
from tests._ir_fixtures import Kind, spec


def _spec(name: str, kind: Kind = "value_str") -> RuleSpec:
    return spec(name, kind, [IrItem(atom=IrLiteral("x"))])


def test_render_specs_invokes_flavour_per_rule():
    """render_specs calls the flavour callable once per rule in order."""
    calls: list[str] = []

    def fake_flavour(rule):
        calls.append(rule.name)
        return f"<{rule.name}>"

    out = render_specs([_spec("a"), _spec("b")], fake_flavour)
    assert calls == ["a", "b"]
    assert "<a>" in out
    assert "<b>" in out


def test_render_specs_joins_with_newlines_and_trailing_newline():
    """render_specs produces newline-separated lines with a trailing newline."""
    out = render_specs([_spec("a"), _spec("b")], lambda r: "X")
    assert out == "X\nX\n"
