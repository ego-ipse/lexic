"""Equivalence gate — the IR-native ABNF self-grammar vs MetaGrammarParser.

Pins :data:`~lexic.grammars.abnf.ABNF_GRAMMAR` /
:data:`~lexic.grammars.abnf.ABNF_REDUCER` against the legacy Lark path while
both are alive: every ABNF grammar string used in
``tests/integration/test_compile_grammar_abnf.py`` and ``test_cross_flavour.py``
must reduce to an IrAst exactly equal to the meta-parser's, unambiguously.
Temporary — dies with the Lark path (Phase 6 of
``zzz_current_work/postleo/PLAN_cutover_parsing_v2.md``), when it converts to
golden expectations.

Scope note: the corpus is the grammar strings those two suites feed to
``compile_grammar``/``MetaGrammarParser`` — ``arithmetic.abnf`` plus the inline
fixtures. ``json.abnf`` is intentionally excluded: it exercises the
still-pending Phase 3 parity constructs (num-sequence ``%x..``, ``[...]``
option, trailing comments), which are covered by the Lark path's own unit
tests until the engine surface closes.
"""

from __future__ import annotations

import pytest

from lexic.grammars.abnf import ABNF_FLAVOUR, ABNF_GRAMMAR, ABNF_REDUCER
from lexic.ir.nodes import IrAst
from lexic.parsing.meta_parser import MetaGrammarParser
from lexic.parsing_2 import is_ambiguous, parse_reduced
from lexic.parsing_2.normalize import normalize
from tests.paths import GROUND_TRUTH

_INLINE = {
    "non_semantic_directive": (
        "; @non-semantic WSP\n"
        "root = num WSP\n"
        "num  = 1*DIGIT\n"
        "DIGIT = %x30-39\n"
        "WSP  = %x20 / %x09\n"
    ),
    "case_insensitive_literal": 'root = "Hi"\n',
}
"""The inline ABNF fixtures exercised by ``test_compile_grammar_abnf`` /
``test_cross_flavour`` (keyed by a stable id)."""


def _corpus() -> dict[str, str]:
    """The ABNF gate corpus: the inline fixtures plus ``arithmetic.abnf``."""
    corpus = dict(_INLINE)
    corpus["arithmetic"] = (GROUND_TRUTH / "arithmetic.abnf").read_text(
        encoding="utf-8"
    )
    return corpus


_CORPUS = _corpus()


@pytest.fixture(name="norm_grammar", scope="module")
def norm_grammar_fixture() -> IrAst:
    """The Earley-normalised ABNF self-grammar, shared across the module."""
    return normalize(ABNF_GRAMMAR)


@pytest.mark.parametrize("text", _CORPUS.values(), ids=_CORPUS.keys())
def test_reduces_to_meta_parser_ast(text: str, norm_grammar: IrAst) -> None:
    """parse_reduced over the self-grammar equals the Lark meta-parser's IrAst."""
    expected = MetaGrammarParser.for_flavour(ABNF_FLAVOUR).parse(text)
    got = parse_reduced(norm_grammar, text, ABNF_REDUCER)
    assert isinstance(got, IrAst)
    assert got == expected


@pytest.mark.parametrize("text", _CORPUS.values(), ids=_CORPUS.keys())
def test_corpus_unambiguous(text: str, norm_grammar: IrAst) -> None:
    """Every gate grammar string has exactly one derivation."""
    assert not is_ambiguous(norm_grammar, text)
