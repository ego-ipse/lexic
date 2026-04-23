"""Unit tests for src/lexic/codegen/transformer/registry.py"""

from typing import Any

import pytest

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.codegen.transformer.registry import BUILDER_BY_ATOM, builder_for


def test_all_atom_types_registered():
    expected = {
        LiteralAtom,
        CharClassAtom,
        QuantifiedLiteralAtom,
        InlineRegexAtom,
        RuleRefAtom,
        InlineAlternationAtom,
        AlternationAtom,
    }
    assert set(BUILDER_BY_ATOM.keys()) == expected


def test_builder_for_unknown_raises():
    class FakeAtom:
        pass

    unknown: Any = FakeAtom()
    with pytest.raises(ValueError):
        builder_for(unknown)
