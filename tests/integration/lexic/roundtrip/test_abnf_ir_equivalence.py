"""Golden gate — the IR-native ABNF self-grammar over its fixture corpus.

Formerly pinned :data:`~lexic.grammars.abnf.ABNF_GRAMMAR` /
:data:`~lexic.grammars.abnf.ABNF_REDUCER` against the (now-deleted) Lark
meta-parser. With the Lark path gone this asserts stable invariants instead:
every gate grammar reduces to an :class:`IrAst` with the expected start rule
and rule set, unambiguously, and re-emitting through ``ABNF_FLAVOUR`` and
re-parsing preserves that rule fingerprint.

Corpus (unchanged from the Lark-era gate): the inline fixtures that
``test_compile_grammar_abnf`` / ``test_cross_flavour`` feed to
``canonical_grammar``, one fixture per Phase 3 remainder construct
(num-sequence, ``[...]`` option, trailing/inline comments, line folding, RFC
7405 ``%s``/``%i`` strings, ``%d``/``%b`` values, incremental ``=/``), plus the
``arithmetic.abnf`` and ``json.abnf`` ground-truth files.
"""

from __future__ import annotations

import pytest

from lexic.grammars.abnf import ABNF_FLAVOUR, ABNF_GRAMMAR, ABNF_REDUCER
from lexic.ir import IrAst
from lexic.parsing import is_ambiguous
from lexic.parsing.earley.normalize import normalize
from tests.reduce_helpers import reduce_text as earley_reduce
from tests.integration.lexic.roundtrip.abnf_fixtures import NON_SEMANTIC_DIRECTIVE_ABNF
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.ir_fixtures import JSON_RULE_NAMES

INLINE = {
    "non_semantic_directive": NON_SEMANTIC_DIRECTIVE_ABNF,
    "case_insensitive_literal": 'root = "Hi"\n',
    # Phase 3 remainder constructs, one fixture each.
    "num_sequence": "false = %x66.61.6c.73.65\n",
    "option_bracket": "num = sign [ digits ]\nsign = %x2D\ndigits = %x30-39\n",
    "trailing_comment": "root = digit  ; a digit\ndigit = %x30-39\n",
    "inline_comment_fold": (
        "ws = *(\n        %x20 /   ; space\n        %x09 )   ; tab\n"
    ),
    "cs_string": 'kw = %s"true"\n',
    "ci_string": 'word = %i"abc"\n',
    "dec_value": "a = %d65\n",
    "bin_range": "a = %b1000001-1011010\n",
    "incremental": 'foo = "a"\nfoo =/ "b"\nfoo =/ "c"\n',
}
"""The inline ABNF fixtures exercised by ``test_compile_grammar_abnf`` /
``test_cross_flavour``, plus one per Phase 3 remainder construct (keyed by a
stable id)."""

# Golden per-fixture fingerprint: start rule + rule names in source order.
GOLDEN: dict[str, tuple[str, tuple[str, ...]]] = {
    "non_semantic_directive": ("root", ("root", "num", "DIGIT", "WSP")),
    "case_insensitive_literal": ("root", ("root",)),
    "num_sequence": ("false", ("false",)),
    "option_bracket": ("num", ("num", "sign", "digits")),
    "trailing_comment": ("root", ("root", "digit")),
    "inline_comment_fold": ("ws", ("ws",)),
    "cs_string": ("kw", ("kw",)),
    "ci_string": ("word", ("word",)),
    "dec_value": ("a", ("a",)),
    "bin_range": ("a", ("a",)),
    "incremental": ("foo", ("foo",)),
    "arithmetic": ("root", ("root", "expr", "term", "op", "num", "DIGIT", "WSP")),
    # ABNF's json shares its non-hex-digit rules (through "zero") with the
    # RFC 8259 JSON_RULE_NAMES order, then diverges: it has no "digit" rule
    # and closes over the ABNF core rules DIGIT/HEXDIG instead of "hexdig".
    "json": (
        "JSON-text",
        JSON_RULE_NAMES[:25] + JSON_RULE_NAMES[26:31] + ("DIGIT", "HEXDIG"),
    ),
}


def corpus() -> dict[str, str]:
    """The ABNF gate corpus: the inline fixtures plus the ground-truth files."""
    result = dict(INLINE)
    for stem in ("arithmetic", "json"):
        result[stem] = (GROUND_TRUTH / f"{stem}.abnf").read_text(encoding="utf-8")
    return result


CORPUS = corpus()


def fingerprint(ast: IrAst) -> tuple[str, tuple[str, ...]]:
    """(start rule, rule names in order) — the golden-comparable shape."""
    return str(ast.start), tuple(str(r.name) for r in ast.rules)


@pytest.fixture(name="norm_grammar", scope="module")
def norm_grammar_fixture() -> IrAst:
    """The Earley-normalised ABNF self-grammar, shared across the module."""
    return normalize(ABNF_GRAMMAR)


def test_corpus_matches_golden_keys() -> None:
    """Every corpus entry has a golden fingerprint and vice versa."""
    assert set(CORPUS) == set(GOLDEN)


@pytest.mark.parametrize("key", CORPUS, ids=list(CORPUS))
def test_reduces_to_golden_fingerprint(key: str) -> None:
    """Artefact reduction yields the golden start rule and rule set."""
    ast = earley_reduce(ABNF_GRAMMAR, CORPUS[key], ABNF_REDUCER)
    assert isinstance(ast, IrAst)
    assert fingerprint(ast) == GOLDEN[key]


@pytest.mark.parametrize("key", CORPUS, ids=list(CORPUS))
def test_corpus_unambiguous(key: str, norm_grammar: IrAst) -> None:
    """Every gate grammar string has exactly one derivation."""
    assert not is_ambiguous(norm_grammar, CORPUS[key])


@pytest.mark.parametrize("key", CORPUS, ids=list(CORPUS))
def test_emit_reparse_preserves_fingerprint(key: str) -> None:
    """Emitting the reduced AST as ABNF and re-parsing keeps the rule fingerprint."""
    ast = earley_reduce(ABNF_GRAMMAR, CORPUS[key], ABNF_REDUCER)
    assert isinstance(ast, IrAst)
    reparsed = earley_reduce(ABNF_GRAMMAR, str(ABNF_FLAVOUR.apply(ast)), ABNF_REDUCER)
    assert isinstance(reparsed, IrAst)
    assert fingerprint(reparsed) == fingerprint(ast)
