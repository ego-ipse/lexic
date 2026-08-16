"""Addressed emission over the corpus: the text, the addresses, the spans.

`GrammarModel.emit_addressed` is the emit-side half of "products carry the
correspondences they computed". The gates here are the ones that make an
address worth carrying:

- **agreement** — the addressed walk's text IS ``to_text()``'s. They are two
  readers of one ``emit_parts`` stream and this is where a drift between them
  would surface.
- **fidelity** — every extent's span slices the emitted text to exactly the
  occurrence standing at its address, resolved through
  :meth:`~lexic.model.GrammarModel.occurrence`.
- **sharing** — the blocker this whole ask exists to survive: the spine shares
  equal nodes by identity, so an addressed walk that spliced shares would give
  seven occurrences of one ``Ws`` object one answer between them.
- **coverage** — the leaf extents tile the whole emitted text, with the
  structural literals attributed rather than left as gaps.

Documents come from ``lexic.generate`` at fixed seeds over the ground-truth
corpus rather than hand-written samples: every formulation goes through the
standard pipeline, and nothing here is tuned to one grammar's shape.
"""

from __future__ import annotations


import pytest

from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAddress, IrSpan, IrStep, census
from lexic.model import GrammarModel
from tests.addressed_helpers import leaf_spans, spelling
from tests.corpus import documents
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH

APART = frozenset({"c.gbnf", "think.gbnf", "vyx.gbnf"})
"""Left out, each for its own reason: ``c.gbnf``'s ``root ::= (declaration)*``
rolls empty on most seeds, and ``think``/``vyx`` carry token terminals. Both
shapes are exercised by the property suite's own seeds instead."""

CORPUS = tuple(name for name in GBNF_GRAMMARS if name not in APART)


def parsed(name: str) -> list[GrammarModel]:
    """Every generated document for ``name``, parsed."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    return [compiled.parse(text) for text in documents(name)]


# ── agreement: one emission, two readers ────────────────────────────────


@pytest.mark.parametrize("name", CORPUS)
def test_the_addressed_text_is_to_texts(name: str) -> None:
    """``emit_addressed().text`` and ``to_text()`` never disagree."""
    for model in parsed(name):
        assert model.emit_addressed().text == model.to_text()


# ── fidelity: an address resolves, and its span selects it ──────────────


@pytest.mark.parametrize("name", CORPUS)
def test_every_span_slices_to_its_own_occurrence(name: str) -> None:
    """Gate (i): the span of an address selects exactly what stands there."""
    for model in parsed(name):
        emission = model.emit_addressed()
        for extent in emission.extents:
            occurrence = model.occurrence(extent.address)
            assert extent.span.of(emission.text) == spelling(occurrence), (
                f"{name}: {extent.address!r} spans {extent.span!r}"
            )


@pytest.mark.parametrize("name", CORPUS)
def test_every_address_is_distinct(name: str) -> None:
    """No two occurrences share an address — the address IS the identity."""
    for model in parsed(name):
        addresses = [tuple(e.address) for e in model.emit_addressed().extents]
        assert len(set(addresses)) == len(addresses), name


@pytest.mark.parametrize("name", CORPUS)
def test_spans_nest_with_the_addresses(name: str) -> None:
    """A child's span lies inside its parent's — the tree and the text agree."""
    for model in parsed(name):
        emission = model.emit_addressed()
        by_path = {tuple(e.address): e.span for e in emission.extents}
        for path, span in by_path.items():
            if not path:
                continue
            parent = by_path[path[:-1]]
            assert parent.start <= span.start <= span.end <= parent.end, path


# ── coverage: the whole text is attributed ──────────────────────────────


@pytest.mark.parametrize("name", CORPUS)
def test_the_leaf_extents_tile_the_emitted_text(name: str) -> None:
    """Gate (iii): no gap, no overlap, structural literals included."""
    for model in parsed(name):
        emission = model.emit_addressed()
        at = 0
        for span in leaf_spans(emission.extents):
            assert span.start == at, f"{name}: gap or overlap at {at}"
            at = span.end
        assert at == len(emission.text), name


@pytest.mark.parametrize("name", CORPUS)
def test_the_root_extent_covers_everything(name: str) -> None:
    """The first extent is the model itself, spanning its whole spelling."""
    for model in parsed(name):
        emission = model.emit_addressed()
        root = emission.extents[0]
        assert root.address == IrAddress()
        assert root.span == IrSpan(0, len(emission.text))


# ── sharing: the blocker this ask exists to survive (B1) ────────────────


def json_model() -> GrammarModel:
    """``{"a": 1, "b": 1}`` under json.gbnf — equal siblings AND shared noise."""
    return compile_from_path(GROUND_TRUTH / "json.gbnf").parse('{"a": 1, "b": 1}')


def test_the_b1_fixture_really_does_share_nodes() -> None:
    """The premise: one ``Ws`` object is reached many times over, by identity.

    If this ever stops being true the sharing gates below stop testing
    anything, so the premise is asserted rather than assumed — through the
    engine's own identity walk, under its stated child definition.
    """
    entries = census(json_model())
    assert max(entry.reached for entry in entries) > 1, (
        "the fixture no longer shares any node"
    )


def test_the_value_has_far_fewer_nodes_than_the_emission_has_occurrences() -> None:
    """Why addresses exist at all, in two numbers from two products.

    The census counts distinct OBJECTS; the emission counts OCCURRENCES. The
    gap is the sharing, and it is the reason an occurrence cannot be named by
    the value standing in it.
    """
    model = json_model()
    assert len(census(model)) < len(model.emit_addressed().extents)


def test_shared_nodes_get_one_address_each_not_one_between_them() -> None:
    """Every occurrence of a shared object is addressed on its own.

    The occurrences are HELD while their ids are read: a resolved part that is
    built on the way out (a repeated field's tuple) is freed the moment its id
    is taken, and CPython hands the same address to the next one — which reads
    back as two unrelated parts being one shared object.
    """
    model = json_model()
    emission = model.emit_addressed()
    occurrences = [model.occurrence(extent.address) for extent in emission.extents]
    identities = [id(occurrence) for occurrence in occurrences]
    shared = {node for node in identities if identities.count(node) > 1}
    assert shared, "expected the fixture's shared objects to surface"
    for node in shared:
        spans = [
            extent.span
            for extent, at in zip(emission.extents, identities, strict=True)
            if at == node
        ]
        assert len({(span.start, span.end) for span in spans}) > 1, (
            "a shared object's occurrences were given one span between them"
        )


def test_equal_siblings_are_told_apart_by_index_not_value() -> None:
    """``[1, 1]``: two equal elements, two addresses, two spans."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    emission = compiled.parse("[1, 1]").emit_addressed()
    ones = [e for e in emission.extents if e.span.of(emission.text) == "1"]
    # Every extent spelling "1" has its own address — the chain of nested
    # rules over each element, times the two elements.
    assert len({tuple(e.address) for e in ones}) == len(ones)
    # And they land on exactly the two positions the document has, so no
    # occurrence of the second "1" was answered with the first one's span.
    assert {(e.span.start, e.span.end) for e in ones} == {(1, 2), (4, 5)}


# ── occurrence: the address read backwards ──────────────────────────────


def test_the_empty_address_is_the_model_itself() -> None:
    """Resolution starts at the root, which is the model handed the address."""
    model = json_model()
    assert model.occurrence(IrAddress()) is model


def test_a_step_past_the_last_slot_refuses_with_words() -> None:
    """An address the emission cannot serve raises rather than guessing."""
    model = json_model()
    with pytest.raises(UnsupportedConstructError, match="slot"):
        model.occurrence(IrAddress().child("", 99))


def test_a_step_into_a_leaf_refuses_with_words() -> None:
    """Descending past a spelling is a refusal, not an empty answer."""
    model = json_model()
    emission = model.emit_addressed()
    leaf = next(
        e.address
        for e in emission.extents
        if isinstance(model.occurrence(e.address), str)
    )
    with pytest.raises(UnsupportedConstructError, match="emits no parts"):
        model.occurrence(leaf.child("", 0))


def test_resolution_is_positional_not_by_field_name() -> None:
    """The field name is documentation; the index is what selects."""
    model = json_model()
    emission = model.emit_addressed()
    address = emission.extents[3].address
    renamed = IrAddress(*(IrStep("", step.slot) for step in address))
    assert model.occurrence(renamed) is model.occurrence(address)
