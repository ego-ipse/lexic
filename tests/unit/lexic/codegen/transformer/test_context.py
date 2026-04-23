"""Unit tests for src/lexic/codegen/transformer/context.py"""

import dataclasses

import pytest

from lexic.ir import RuleSpec
from lexic.codegen.transformer.context import (
    BuildContext,
    FieldResult,
    SKIP_FIELD,
    SkipField,
)


def _spec(items):
    return RuleSpec(
        rule_name="r",
        class_name="R",
        parent_class_name="GrammarModel",
        kind="sequence",
        items=items,
        field_map={},
    )


def test_build_context_is_immutable():
    ctx = BuildContext(spec=_spec([]), children=("a", "b", "c"), hints={}, cursor=0)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        setattr(ctx, "cursor", 5)


def test_build_context_peek_exhausted():
    empty = BuildContext(spec=_spec([]), children=(), hints={})
    assert empty.exhausted() is True
    assert empty.peek() is None
    populated = BuildContext(spec=_spec([]), children=("x",), hints={})
    assert populated.exhausted() is False
    assert populated.peek() == "x"


def test_field_result_is_frozen():
    r = FieldResult(value=42, consumed=1)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        setattr(r, "value", 43)


def test_skip_field_singleton():
    assert isinstance(SKIP_FIELD, SkipField)
