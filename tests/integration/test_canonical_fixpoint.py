"""Canonicalisation fixpoint gates — the runnable proof of Task 2.

Three properties pin the canonical form as the flavour-agnostic ground truth:

- **headline:** ``canonicalize(parse(json.gbnf)) ==
  canonicalize(parse(json.abnf)) == JSON_GRAMMAR`` — two flavours describing
  the same language reduce to the same canonical ``IrAst``;
- **emit fixpoint (per flavour):** ``canonicalize(parse(emit(canon))) == canon``
  for every ground truth — the canonical AST survives an emit/reparse
  round-trip through GBNF *and* ABNF (rewrite 8b makes empty arms stable). ABNF
  spells canonical case-sensitive literals as RFC 7405 ``%s"..."`` char-vals,
  falling back to ``%x`` num-val for quotes/controls, so the round-trip no
  longer loses case;
- **self-canon:** ``canonicalize(G) == G`` for the authored ``GBNF_GRAMMAR``,
  ``ABNF_GRAMMAR`` and ``JSON_GRAMMAR`` self-grammars (all stored in canonical
  form).
"""

from __future__ import annotations

import pytest

from lexic.compile import parse_grammar
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.grammars.gbnf import GBNF_GRAMMAR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir.canonical import canonicalize
from tests.paths import GROUND_TRUTH

_GBNF_GROUND_TRUTH = (
    "arithmetic",
    "c",
    "chess",
    "japanese",
    "json_arr",
    "json_ws",
    "list",
    "json",
)


def _canon_gbnf(stem: str):
    text = (GROUND_TRUTH / f"{stem}.gbnf").read_text(encoding="utf-8")
    return canonicalize(parse_grammar(text, GBNF_FLAVOUR))


def test_headline_json_fixpoint() -> None:
    """gbnf and abnf JSON both canonicalise to JSON_GRAMMAR."""
    gbnf = _canon_gbnf("json")
    abnf_text = (GROUND_TRUTH / "json.abnf").read_text(encoding="utf-8")
    abnf = canonicalize(parse_grammar(abnf_text, ABNF_FLAVOUR))
    assert gbnf == abnf
    assert gbnf == JSON_GRAMMAR


@pytest.mark.parametrize("stem", _GBNF_GROUND_TRUTH)
def test_gbnf_emit_fixpoint(stem: str) -> None:
    """canonicalize(parse(emit(canon))) == canon for every GBNF ground truth."""
    canon = _canon_gbnf(stem)
    emitted = str(GBNF_FLAVOUR.apply(canon))
    reparsed = canonicalize(parse_grammar(emitted, GBNF_FLAVOUR))
    assert reparsed == canon


@pytest.mark.parametrize("stem", _GBNF_GROUND_TRUTH)
def test_abnf_emit_fixpoint(stem: str) -> None:
    """canonicalize(parse(emit(canon))) == canon through ABNF for every ground truth.

    The canonical AST is flavour-agnostic, so ABNF must emit and reparse it back
    to the same shape — this is what the ``%s"..."`` / ``%x`` literal rework buys.
    """
    canon = _canon_gbnf(stem)
    emitted = str(ABNF_FLAVOUR.apply(canon))
    reparsed = canonicalize(parse_grammar(emitted, ABNF_FLAVOUR))
    assert reparsed == canon


@pytest.mark.parametrize("stem", _GBNF_GROUND_TRUTH)
def test_abnf_emit_is_idempotent(stem: str) -> None:
    """ABNF emission is stable: re-emitting the reparsed canon yields identical text."""
    canon = _canon_gbnf(stem)
    once = str(ABNF_FLAVOUR.apply(canon))
    twice = str(ABNF_FLAVOUR.apply(canonicalize(parse_grammar(once, ABNF_FLAVOUR))))
    assert once == twice


def test_canonicalize_is_idempotent_on_ground_truths() -> None:
    """Canonicalisation is a fixpoint: canonicalize(canon) == canon."""
    for stem in _GBNF_GROUND_TRUTH:
        canon = _canon_gbnf(stem)
        assert canonicalize(canon) == canon


def test_gbnf_self_grammar_is_canonical() -> None:
    """The authored GBNF self-grammar is stored in canonical form."""
    assert canonicalize(GBNF_GRAMMAR) == GBNF_GRAMMAR


def test_abnf_self_grammar_is_canonical() -> None:
    """The authored ABNF self-grammar is stored in canonical form."""
    assert canonicalize(ABNF_GRAMMAR) == ABNF_GRAMMAR


def test_json_self_grammar_is_canonical() -> None:
    """The authored JSON self-grammar is stored in canonical form."""
    assert canonicalize(JSON_GRAMMAR) == JSON_GRAMMAR
