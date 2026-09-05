"""Tests for what a measured row IS — its identity and its result digests.

The comparator's whole defence is here: a pair of timings means something only
when both arms measured the same row and built the same product.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from lexic.compile import compile_text
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    Observation,
    RowContract,
    read_observation,
    shape,
)


type _Value = int | str | tuple
"""What these fixtures hold: a leaf, or a nested record (records are tuples)."""


class _Node(NamedTuple):
    """A two-field record, for reading the rendering by eye."""

    left: _Value
    right: _Value


class _Renamed(NamedTuple):
    """The same shape and the same values under different field names."""

    first: _Value
    second: _Value


def _model(source: str, text: str):
    """One document's model under one grammar."""
    return compile_text(source).parse(text)


def test_two_trees_over_one_document_render_differently() -> None:
    """The digest the comparator needs is structural, not textual.

    Both grammars accept ``ab`` and both models emit ``ab``, so a digest of
    the emitted text calls them the same product. They are not: one is a single
    matched string, the other two named children.
    """
    flat = _model('root ::= "ab"', "ab")
    nested = _model('root ::= x y\nx ::= "a"\ny ::= "b"', "ab")

    assert flat.to_text() == nested.to_text()
    assert shape(flat) != shape(nested)


def test_a_generated_model_renders_the_fields_the_grammar_named() -> None:
    """The names in the rendering are the model's own bound field names."""
    model = _model('root ::= head tail\nhead ::= "a"\ntail ::= "b"', "ab")

    rendered = shape(model)

    assert "head=" in rendered and "tail=" in rendered


def test_the_same_document_twice_renders_identically() -> None:
    """Deterministic, or every pair would refuse itself."""
    source = 'root ::= item+\nitem ::= "- " [a-z]+ "\\n"\n'
    once = _model(source, "- alpha\n- beta\n")
    again = _model(source, "- alpha\n- beta\n")

    assert shape(once) == shape(again)


def test_two_documents_of_one_grammar_render_differently() -> None:
    """Field VALUES are part of the shape, not only the classes."""
    source = 'root ::= item+\nitem ::= "- " [a-z]+ "\\n"\n'

    assert shape(_model(source, "- alpha\n")) != shape(_model(source, "- beta\n"))


def test_the_rendering_names_each_class_and_reads_in_field_order() -> None:
    """Order carries meaning: two swapped fields are two different products."""
    assert shape(_Node("a", "b")) == "_Node(left=str:'a',right=str:'b')"
    assert shape(_Node("b", "a")) != shape(_Node("a", "b"))
    assert (
        shape(_Node(_Node(1, 2), ()))
        == "_Node(left=_Node(left=int:1,right=int:2),right=tuple())"
    )


def test_renaming_a_field_changes_the_product_and_the_rendering() -> None:
    """Field naming is part of the typed model, so it is part of its identity.

    Two records with one class name, one shape and one pair of values, differing
    only in what their fields are CALLED, are two different products — and a
    rendering blind to names accepted the pair as equal.
    """
    _Renamed.__name__ = _Node.__name__

    assert _Node(1, 2) == _Renamed(1, 2)
    assert shape(_Node(1, 2)) != shape(_Renamed(1, 2))


def test_a_plain_tuple_carries_no_field_names() -> None:
    """A tuple has positions, not fields, and must not grow invented ones."""
    assert shape((1, 2)) == "tuple(int:1,int:2)"
    assert shape(((1,), 2)) == "tuple(tuple(int:1),int:2)"


def test_a_deeply_nested_product_renders_rather_than_recursing() -> None:
    """Depth is the grammar's, so the walk cannot be the interpreter's stack."""
    deep: _Value = ()
    for _level in range(10_000):
        deep = _Node(deep, ())

    rendered = shape(deep)

    assert rendered.count("_Node(") == 10_000
    assert rendered.endswith("tuple()" + ",right=tuple())" * 10_000)


def test_an_observation_survives_the_wire_with_both_digests() -> None:
    """Both digests travel, or the comparator cannot ask for either."""
    observation = Observation(1.5, 2.5, "text", "shape", "accepted", True, 8)

    assert read_observation(observation.wire()) == observation


def test_a_contract_names_every_field_that_differs() -> None:
    """Mismatch is reported by field, in declaration order."""
    contract = RowContract(
        PROTOCOL,
        "lexic-pda",
        "json",
        "abc123",
        (),
        (),
        "def456",
        2403,
        "corpus",
        "typed model",
        1,
        True,
        CLOCKS,
    )

    assert contract.mismatch(contract) == ()
    assert contract.mismatch(contract._replace(cores=8, scale="full")) == (
        "scale",
        "cores",
    )


def test_an_observation_missing_a_digest_is_not_read_as_empty() -> None:
    """An older harness's payload refuses rather than comparing as blank."""
    wire = Observation(1.0, 1.0, "text", "shape", "accepted", None, 1).wire()
    del wire["shape_digest"]

    with pytest.raises(KeyError):
        read_observation(wire)
