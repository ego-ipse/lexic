"""Tests for compile/templating.py — generic span-based path extraction.

Exercises the module against a self-contained toy ``(k=v, ...)`` grammar,
compiled once through the standard pipeline (``compile_text``) — the whole
point of this module is genericity over any COMPILED grammar, so the fixture
is built the same way a real caller would build one, not hand-assembled IR.
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.compile import (
    KEEP,
    Keep,
    MapShape,
    SpanEntry,
    SpanLevel,
    SpanPair,
    Template,
    compile_text,
    spanify,
    template,
)
from lexic.compile.templating import skip_rules
from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.ir.base import IrSelf
from lexic.ir.mapping import IrMap
from lexic.ir.order import refs_in_order
from lexic.model import GrammarModel
from lexic.parsing import parse_model

_TOY = r"""
start ::= ws sect ws
sect ::= "(" ws entries ws ")"
entries ::= entry e-more*
e-more ::= ws "," ws entry
entry ::= key ws "=" ws val
key ::= [a-z]+
val ::= num | sect
num ::= [0-9]+
ws ::= [ \t\n]*
# @non-semantic ws
"""

_TOY_COMPILED = compile_text(_TOY)
_SHAPE = MapShape("sect", "entry", "key", "val")
_TOY_DOC = "(a=1, b=(c=22, d=(e=3)), f=4)"


def _model(value: object) -> GrammarModel:
    """Narrow a Template.run() leaf to the GrammarModel it always is."""
    return cast(GrammarModel, value)


def _section(value: object) -> dict[str, object]:
    """Narrow a Template.run() nested value to the dict it always is."""
    return cast("dict[str, object]", value)


# ── extraction basics ────────────────────────────────────────────────────


def test_single_top_level_keep_extracts_a_plain_value() -> None:
    """A single top-level KEEP extracts a plain scalar value."""
    result = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    assert _model(result["f"]).to_text() == "4"


def test_nested_spec_extracts_a_value_inside_a_section() -> None:
    """A nested spec two levels deep extracts a value inside a section."""
    result = template(_TOY_COMPILED, _SHAPE, {"b": {"c": KEEP}}).run(_TOY_DOC)
    inner = _section(result["b"])
    assert _model(inner["c"]).to_text() == "22"


def test_spec_with_multiple_keys_extracts_all_specified_values() -> None:
    """A spec naming multiple top-level keys extracts all of them at once."""
    result = template(_TOY_COMPILED, _SHAPE, {"a": KEEP, "f": KEEP}).run(_TOY_DOC)
    texts = {k: _model(v).to_text() for k, v in result.items()}
    assert texts == {"a": "1", "f": "4"}


def test_extraction_is_whitespace_insensitive() -> None:
    """The same spec extracts identically regardless of document whitespace."""
    t = template(_TOY_COMPILED, _SHAPE, {"b": {"c": KEEP}})
    result = t.run(_TOY_DOC.replace(" ", ""))
    inner = _section(result["b"])
    assert _model(inner["c"]).to_text() == "22"


def test_deep_three_level_spec_extracts_a_value() -> None:
    """A spec three levels deep extracts alongside a shallower key in one run."""
    spec = {"a": KEEP, "b": {"d": {"e": KEEP}}}
    result = template(_TOY_COMPILED, _SHAPE, spec).run(_TOY_DOC)
    leaf = _section(_section(result["b"])["d"])
    assert _model(leaf["e"]).to_text() == "3"


def test_kept_leaf_is_a_grammar_model_instance() -> None:
    """A KEEP leaf yields a real GrammarModel instance, not a raw scalar."""
    result = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    assert isinstance(result["f"], GrammarModel)


# ── spec-absent keys ─────────────────────────────────────────────────────


def test_spec_key_absent_from_document_is_omitted_from_result() -> None:
    """A spec key not present in the parsed document is absent, not an error."""
    result = template(_TOY_COMPILED, _SHAPE, {"z": KEEP}).run(_TOY_DOC)
    assert not result


# ── spanify() structural checks ──────────────────────────────────────────


def test_spanify_returns_a_span_pair_instance() -> None:
    """spanify(...) returns a SpanPair record."""
    assert isinstance(spanify(_TOY_COMPILED, _SHAPE), SpanPair)


def test_span_pair_grammar_starts_reflect_spans_sections_values_roles() -> None:
    """.spans/.sections/.values each start at their role's -tm clone or bare rule."""
    pair = spanify(_TOY_COMPILED, _SHAPE)
    assert pair.spans.start == "start-tm"
    assert pair.sections.start == "sect-tm"
    assert pair.values.start == "val"


def test_one_span_pair_serves_two_different_templates() -> None:
    """A single spanify() SpanPair drives two Templates with different specs."""
    pair = spanify(_TOY_COMPILED, _SHAPE)
    first = Template(pair, {"f": KEEP}).run(_TOY_DOC)
    second = Template(pair, {"a": KEEP}).run(_TOY_DOC)
    assert _model(first["f"]).to_text() == "4"
    assert _model(second["a"]).to_text() == "1"


# ── skip_rules() ─────────────────────────────────────────────────────────


def test_skip_rules_twins_every_rule_when_shared_is_empty() -> None:
    """skip_rules produces exactly one -sk twin per rule when shared is empty."""
    grammar = _TOY_COMPILED.codegen_grammar
    twins = skip_rules(grammar)
    names = {r.name for r in grammar.rules}
    assert {r.name for r in twins} == {name + "-sk" for name in names}


def test_skip_rules_remaps_internal_refs_to_twin_names() -> None:
    """A twinned rule's IrRuleRef children point at the -sk twin names."""
    twins = {r.name: r for r in skip_rules(_TOY_COMPILED.codegen_grammar)}
    refs: list[str] = []
    refs_in_order(twins["start-sk"].body, refs)
    assert refs == ["ws-sk", "sect-sk"]


def test_skip_rules_leaves_a_shared_rule_untwinned_and_its_refs_unremapped() -> None:
    """A rule named in shared is not twinned, and refs to it stay bare."""
    grammar = _TOY_COMPILED.codegen_grammar
    twins = {r.name: r for r in skip_rules(grammar, shared=frozenset({"ws"}))}
    assert "ws-sk" not in twins
    refs: list[str] = []
    refs_in_order(twins["start-sk"].body, refs)
    assert "ws" in refs


# ── refusals ──────────────────────────────────────────────────────────────


def test_spanify_refuses_a_shape_naming_an_unknown_rule() -> None:
    """spanify refuses a shape whose entry rule the grammar never defines."""
    unknown = MapShape("sect", "nope", "key", "val")
    with pytest.raises(UnsupportedConstructError, match="is not a rule of the grammar"):
        spanify(_TOY_COMPILED, unknown)


def test_spanify_refuses_an_unknown_key_field_name() -> None:
    """spanify refuses a shape naming a key field the entry binding lacks."""
    unknown = MapShape("sect", "entry", "nope", "val")
    with pytest.raises(UnsupportedConstructError, match="not a binding field"):
        spanify(_TOY_COMPILED, unknown)


def test_spanify_refuses_an_unknown_value_field_name() -> None:
    """spanify refuses a shape naming a value field the entry binding lacks."""
    unknown = MapShape("sect", "entry", "key", "nope")
    with pytest.raises(UnsupportedConstructError, match="not a binding field"):
        spanify(_TOY_COMPILED, unknown)


def test_template_refuses_spec_value_that_is_neither_keep_nor_mapping() -> None:
    """A spec leaf that is neither KEEP nor a nested mapping is refused."""
    pair = spanify(_TOY_COMPILED, _SHAPE)
    with pytest.raises(
        UnsupportedConstructError, match="must be KEEP or a nested mapping"
    ):
        Template(pair, {"x": "not-keep-or-mapping"})


def test_template_run_refuses_unparseable_text() -> None:
    """Template.run raises, message tagged with the document path, on bad text."""
    t = template(_TOY_COMPILED, _SHAPE, {"f": KEEP})
    with pytest.raises(UnsupportedConstructError, match="template at"):
        t.run("not a valid document")


def test_spanify_refuses_a_section_that_cannot_reach_the_entry() -> None:
    """spanify refuses a shape.section from which shape.entry is unreachable."""
    unreachable = MapShape("num", "entry", "key", "val")
    with pytest.raises(UnsupportedConstructError, match="cannot reach shape.entry"):
        spanify(_TOY_COMPILED, unreachable)


# ── spine membership / repr / interning ──────────────────────────────────


def test_template_and_related_nodes_are_irself_instances() -> None:
    """Template, SpanPair, MapShape, KEEP and Template.spec all ride the spine."""
    t = template(_TOY_COMPILED, _SHAPE, {"b": {"c": KEEP}})
    for node in (t, t.span, _SHAPE, KEEP, t.spec):
        assert isinstance(node, IrSelf)


def test_keep_call_returns_the_interned_singleton() -> None:
    """Keep() always returns the one interned KEEP instance."""
    assert Keep() is KEEP


def test_spec_repr_is_pinned_codegen_form() -> None:
    """The lifted spec's repr is the pinned codegen form of the nested dict."""
    t = Template(spanify(_TOY_COMPILED, _SHAPE), {"b": {"c": KEEP}})
    assert (
        repr(t.spec) == "Spec(IrTuple(IrStr('b'), Spec(IrTuple(IrStr('c'), Keep()))))"
    )


# ── MapShape ──────────────────────────────────────────────────────────────


def test_map_shape_fields_are_readable_by_name() -> None:
    """MapShape is pure data — its four fields read back the names given."""
    assert _SHAPE.section == "sect"
    assert _SHAPE.entry == "entry"
    assert _SHAPE.key_field == "key"
    assert _SHAPE.value_field == "val"


# ── template() vs Template(spanify(...)) equivalence ─────────────────────


def test_template_and_template_of_spanify_produce_equivalent_results() -> None:
    """template() and Template(spanify(...)) behave identically for the same inputs."""
    spec = {"b": {"c": KEEP}}
    via_template = template(_TOY_COMPILED, _SHAPE, spec).run(_TOY_DOC)
    via_spanify = Template(spanify(_TOY_COMPILED, _SHAPE), spec).run(_TOY_DOC)
    template_leaf = _model(_section(via_template["b"])["c"]).to_text()
    spanify_leaf = _model(_section(via_spanify["b"])["c"]).to_text()
    assert template_leaf == spanify_leaf


# ── the run product is on the spine ──────────────────────────────────────


def test_run_returns_an_ir_map() -> None:
    """run() yields an IrMap — the extraction level is an IR value."""
    out = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    assert isinstance(out, IrMap)


def test_run_keys_match_plain_strings() -> None:
    """IrStr keys hash-match plain str, so a caller subscripts natively."""
    out = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    assert set(out.keys()) == {"f"}


def test_kept_leaf_is_a_grammar_model_not_a_wrapper() -> None:
    """A KEEP leaf is the GrammarModel itself — no wrapper type."""
    out = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    assert isinstance(out["f"], GrammarModel)


def test_nested_level_is_an_ir_map_again() -> None:
    """A nested spec level extracts to another IrMap (same shape, recursive)."""
    out = template(_TOY_COMPILED, _SHAPE, {"b": {"c": KEEP}}).run(_TOY_DOC)
    assert isinstance(out["b"], IrMap)


def test_absent_key_raises_ir_key_error() -> None:
    """A spec key absent from the document is absent from the map."""
    out = template(_TOY_COMPILED, _SHAPE, {"f": KEEP}).run(_TOY_DOC)
    with pytest.raises(IrKeyError):
        _ = out["absent"]


def test_span_fold_product_is_a_span_level() -> None:
    """The span fold's product is the on-spine SpanLevel, not a plain list."""
    pair = spanify(_TOY_COMPILED, _SHAPE)
    level = parse_model(pair.sections, "(a=1, f=4)", pair.span_fold)
    assert isinstance(level, SpanLevel)
    assert all(isinstance(each, SpanEntry) for each in level)
