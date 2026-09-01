"""Templating carries the offsets the parse had — and both engines agree.

`SpanEntry` used to carry span TEXT only, so a consumer wanting to point at a
key in the document had to search for it — ambiguous the moment a document
repeats itself, which every real config does. The fold knew the positions:
the PDA reads them off the kernel frame it already computes the span text
from, and the tree route accumulates them over the leaves `_subtree_text`
already walks in order.

The gates: the offsets SLICE back to the entry's own text (so they are not
merely plausible), a document with duplicate spellings pins that no search is
happening, and the two engine routes produce identical offsets — a product
that differed by route would be worse than none.
"""

from __future__ import annotations

import pytest

from lexic.compile import MapShape, compile_from_path, spanify
from lexic.compile.output.templating import SpanPair
from lexic.ir import IrSpan
from lexic.parsing import parse_model
from lexic.parsing.products import _model_product, earley_model
from tests.paths import GROUND_TRUTH

DOCUMENTS = (
    '{"name": "a", "b": {"name": "c"}, "d": "name"}',
    '{"x": 1, "x2": 1}',
    "{}",
    '{"a": {"b": {"c": 2}}}',
    '{ "k" : [1, 2] , "k2" : null }',
    '{"dup": "dup", "dup2": "dup"}',
)
"""Documents chosen for repetition: several repeat a spelling across a key and
a value, which is exactly what a search-based derivation gets wrong."""

FORMULATIONS = ("json.gbnf", "json.abnf")
"""Two formulations of one language — the mechanism is not tuned to either."""


def pair_for(name: str) -> SpanPair:
    """The span pair for a JSON formulation, entry rule derived."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    return spanify(compiled, MapShape.for_entry(compiled, "member"))


@pytest.mark.parametrize("name", FORMULATIONS)
@pytest.mark.parametrize("document", DOCUMENTS)
def test_the_offsets_slice_back_to_the_entrys_own_text(
    name: str, document: str
) -> None:
    """The gate: every offset pair selects exactly the text it was captured as."""
    pair = pair_for(name)
    for entry in parse_model(pair.spans, document, pair.span_binding):
        assert entry.key_at.of(document) == entry.key
        assert entry.value_at.of(document) == entry.value


@pytest.mark.parametrize("name", FORMULATIONS)
@pytest.mark.parametrize("document", DOCUMENTS)
def test_both_engine_routes_produce_identical_entries(name: str, document: str) -> None:
    """PDA-first and forced-Earley agree on text AND offsets.

    The parity family's discipline: two routes, one answer. Offsets are
    derived differently on each (kernel frame vs. accumulated leaf lengths),
    so this is where a divergence would show.
    """
    pair = pair_for(name)
    product = _model_product(pair.spans, pair.span_binding)
    predictive = list(parse_model(pair.spans, document, pair.span_binding))
    earley = list(
        earley_model(
            product.instance_grammar, document, pair.span_binding.fold, product.tables
        )
    )
    assert predictive == earley


def test_a_repeated_spelling_is_not_re_found_by_search() -> None:
    """The key ``"name"`` and a later VALUE ``"name"`` get different offsets.

    A derivation that re-found spans by `document.index(text)` would give both
    the first occurrence's position, and this is the assertion that catches it.
    """
    pair = pair_for("json.gbnf")
    document = '{"name": "a", "d": "name"}'
    entries = list(parse_model(pair.spans, document, pair.span_binding))
    key = next(e for e in entries if e.key == '"name"')
    value = next(e for e in entries if e.value == '"name"')
    assert key.key_at == IrSpan(1, 7)
    assert value.value_at == IrSpan(19, 25)
    assert key.key_at != value.value_at


def test_offsets_are_in_document_order() -> None:
    """Entries come out in document order and their spans do not overlap."""
    pair = pair_for("json.gbnf")
    document = '{"a": 1, "b": 2, "c": 3}'
    entries = list(parse_model(pair.spans, document, pair.span_binding))
    assert [e.key for e in entries] == ['"a"', '"b"', '"c"']
    at = 0
    for entry in entries:
        assert entry.key_at.start >= at
        assert entry.key_at.end <= entry.value_at.start
        at = entry.value_at.end


def test_a_nested_level_reports_offsets_into_the_span_it_was_parsed_from() -> None:
    """A re-parsed level's offsets are relative to the text handed to it.

    Stated because it is the one thing a consumer must not get wrong: the
    outer entry's ``value_at`` locates the nested document in the OUTER text,
    and the nested entries' offsets are into that value span.
    """
    pair = pair_for("json.gbnf")
    document = '{"outer": {"inner": 1}}'
    outer = next(iter(parse_model(pair.spans, document, pair.span_binding)))
    nested_text = outer.value_at.of(document)
    assert nested_text == '{"inner": 1}'
    inner = next(iter(parse_model(pair.sections, nested_text, pair.span_binding)))
    assert inner.key_at.of(nested_text) == '"inner"'
