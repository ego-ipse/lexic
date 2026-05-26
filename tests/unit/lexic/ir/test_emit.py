"""Tests for ir/emit.py — render_specs."""

from lexic.ir.emit import render_specs
from lexic.ir.nodes import IrItem, IrLiteral
from lexic.ir.spec import RuleSpec


def _spec(name: str, kind: str = "value_str") -> RuleSpec:
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind,
        items=[IrItem(atom=IrLiteral("x"))],
        field_map={},
    )


def test_render_specs_invokes_flavour_per_rule():
    calls: list[str] = []

    def fake_flavour(rule):
        calls.append(rule.name)
        return f"<{rule.name}>"

    out = render_specs([_spec("a"), _spec("b")], fake_flavour)
    assert calls == ["a", "b"]
    assert "<a>" in out
    assert "<b>" in out


def test_render_specs_joins_with_newlines_and_trailing_newline():
    out = render_specs([_spec("a"), _spec("b")], lambda r: "X")
    assert out == "X\nX\n"
