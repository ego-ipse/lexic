"""Tests for opsis.opsis.views — the VIEWS registry and its drawn refusal."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import IrStr
from opsis.opsis.canvas import html
from opsis.opsis.scene import Ring
from opsis.opsis.views import view_body

GRAMMAR_TEXT = 'root ::= "x" num\nnum ::= [0-9]+\n'


def test_view_body_on_a_grammar_has_a_data_rule_row_per_rule():
    """view_body on a compiled grammar's IrAst draws one deixis-wired row per rule."""
    cg = compile_text(GRAMMAR_TEXT)
    out = html(view_body(cg.grammar))
    for rule in cg.grammar.rules:
        assert f'data-rule="{rule.name}"' in out


def test_view_body_on_a_model_has_the_instance_text_and_its_rule():
    """view_body on a parsed model draws the instance text and its rule's data-rule."""
    cg = compile_text(GRAMMAR_TEXT)
    model = cg.parse("x123")
    out = html(view_body(model))
    assert "x123" in out
    assert f'data-rule="{model.__grammar__.name}"' in out


def test_view_body_on_a_bare_irstr_draws_a_refusal_with_the_exception_name():
    """A type with no view is a drawn refusal carrying the real exception name."""
    out = html(view_body(IrStr("bare")))
    assert 'class="refusal"' in out
    assert "IrKeyError" in out


def test_view_body_on_a_scene_record_also_draws_a_refusal():
    """VIEWS is open: a scene citizen (Ring) has no view either — same drawn refusal."""
    out = html(view_body(Ring("x")))
    assert 'class="refusal"' in out
