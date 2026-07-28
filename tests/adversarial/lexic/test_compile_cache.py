"""Adversarial: an explicit cache_key must never serve a stale grammar.

``compile_text(text, cache_key=K)`` folds the content stem into the key, so
the same ``K`` with different source text can never collide into the first
text's :class:`CompiledGrammar` (which would yield silent wrong parses).
Graduated from ``repro_cache_key_stale.py``.
"""

from __future__ import annotations

from lexic.compile import compile_text


def test_same_key_different_text_serves_each_own_grammar() -> None:
    """Two grammars under one cache_key each parse their own input."""
    first = compile_text('g ::= "1"\n', cache_key="stale-guard")
    second = compile_text('g ::= "2"\n', cache_key="stale-guard")
    assert first is not second
    assert first.parse("1").to_text() == "1"
    assert second.parse("2").to_text() == "2"


def test_same_key_same_text_hits_the_memo() -> None:
    """Identical text under one cache_key returns the cached object."""
    first = compile_text('g ::= "z"\n', cache_key="hit-memo")
    second = compile_text('g ::= "z"\n', cache_key="hit-memo")
    assert first is second
