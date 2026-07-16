"""Adversarial depth tests — the emitter walk must be stack-safe.

Deeply nested input against a self-recursive grammar used to overflow the
Python call stack in :meth:`GrammarModel.to_text` (a mutually recursive
descent through the field-text helper). The emitter now walks an explicit
work-stack, so round-trip fidelity holds at any nesting depth.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text

# Minimal self-nesting grammar: an array of arrays (or the leaf "0").
_GRAMMAR = (
    'root  ::= array\narray ::= "[" (value ("," value)*)? "]"\nvalue ::= array | "0"\n'
)


def _nested(depth: int) -> str:
    """Return ``depth`` nested arrays wrapped around a single leaf ``0``."""
    return "[" * depth + "0" + "]" * depth


@pytest.mark.parametrize("depth", [400, 800])
def test_deep_nesting_round_trips(depth: int) -> None:
    """Parsing then re-emitting a deeply nested array is byte-identical."""
    compiled = compile_text(_GRAMMAR, cache_key=f"adversarial-deep-{depth}")
    text = _nested(depth)
    model = compiled.parse(text)
    assert model.to_text() == text
