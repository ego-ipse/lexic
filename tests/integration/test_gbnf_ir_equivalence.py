"""Equivalence gate — the IR-native GBNF self-grammar vs MetaGrammarParser.

Pins :data:`~lexic.grammars.gbnf.GBNF_GRAMMAR` /
:data:`~lexic.grammars.gbnf.GBNF_REDUCER` against the legacy Lark path while
both are alive: every ground-truth grammar must reduce to an IrAst exactly
equal to the meta-parser's, unambiguously. Temporary — dies with the Lark
path (Phase 6 of ``zzz_current_work/postleo/PLAN_cutover_parsing_v2.md``),
when it converts to golden expectations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_GRAMMAR, GBNF_REDUCER
from lexic.ir.nodes import IrAst
from lexic.parsing.meta_parser import MetaGrammarParser
from lexic.parsing_2 import is_ambiguous, parse_reduced
from lexic.parsing_2.normalize import normalize
from tests.paths import GROUND_TRUTH

GRAMMARS = sorted(GROUND_TRUTH.glob("*.gbnf"))


@pytest.fixture(name="norm_grammar", scope="module")
def norm_grammar_fixture() -> IrAst:
    """The Earley-normalised GBNF self-grammar, shared across the module."""
    return normalize(GBNF_GRAMMAR)


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.stem)
def test_reduces_to_meta_parser_ast(path: Path, norm_grammar: IrAst) -> None:
    """parse_reduced over the self-grammar equals the Lark meta-parser's IrAst."""
    text = path.read_text(encoding="utf-8")
    expected = MetaGrammarParser.for_flavour(GBNF_FLAVOUR).parse(text)
    got = parse_reduced(norm_grammar, text, GBNF_REDUCER)
    assert isinstance(got, IrAst)
    assert got == expected


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.stem)
def test_ground_truth_unambiguous(path: Path, norm_grammar: IrAst) -> None:
    """Every ground-truth grammar has exactly one derivation."""
    text = path.read_text(encoding="utf-8")
    assert not is_ambiguous(norm_grammar, text)
