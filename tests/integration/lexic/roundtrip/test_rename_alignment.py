"""Equality up to renaming, on the ground-truth corpus.

What this defends: a pure rename of a grammar is the SAME grammar, and the
alignment says so with the bijection that transports rule-keyed work across
it — while a different factoring of the same language is a real difference and
refuses. Both halves are needed: a comparison that accepts everything witnesses
nothing.

``RENAMED_JSON`` is ``resources/ground_truth/json.gbnf`` with every rule name
prefixed and nothing else touched — same rule order, same bodies, same
directive — so what the gate exercises is the naming, not a re-emission.
"""

from __future__ import annotations

import pathlib

import pytest

from lexic.compile import canonical_grammar, parse_grammar
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAst, align_names, canonicalize
from tests.paths import GROUND_TRUTH

RENAMED_JSON = """
# @non-semantic q-ws

q-JSON-text ::= q-ws q-value q-ws

q-begin-array     ::= q-ws "[" q-ws
q-begin-object    ::= q-ws "{" q-ws
q-end-array       ::= q-ws "]" q-ws
q-end-object      ::= q-ws "}" q-ws
q-name-separator  ::= q-ws ":" q-ws
q-value-separator ::= q-ws "," q-ws

q-ws ::= ( " " | "\\t" | "\\n" | "\\r" )*

q-value ::= q-false | q-null | q-true | q-object | q-array | q-number | q-string
q-false ::= "false"
q-null  ::= "null"
q-true  ::= "true"

q-object ::= q-begin-object ( q-member ( q-value-separator q-member )* )? \
q-end-object
q-member ::= q-string q-name-separator q-value
q-array  ::= q-begin-array ( q-value ( q-value-separator q-value )* )? q-end-array

q-number        ::= q-minus? q-int q-frac? q-exp?
q-decimal-point ::= "."
q-digit1-9      ::= [1-9]
q-e             ::= "e" | "E"
q-exp           ::= q-e ( q-minus | q-plus )? q-digit+
q-frac          ::= q-decimal-point q-digit+
q-int           ::= q-zero | ( q-digit1-9 q-digit* )
q-minus         ::= "-"
q-plus          ::= "+"
q-zero          ::= "0"
q-digit         ::= [0-9]

q-string         ::= q-quotation-mark q-char* q-quotation-mark
q-char           ::= q-unescaped
                 | q-escape ( "\\"" | "\\\\" | "/" | "b" | "f" | "n" | "r" | "t" \
| "u" q-hexdig{4} )
q-escape         ::= "\\\\"
q-quotation-mark ::= "\\""
q-unescaped      ::= [^"\\\\\\x00-\\x1F]
q-hexdig         ::= [0-9A-Fa-f]
"""


def corpus(name: str) -> str:
    """One ground-truth grammar's source text."""
    return pathlib.Path(GROUND_TRUTH / name).read_text(encoding="utf-8")


@pytest.fixture(name="json_gbnf", scope="module")
def json_gbnf_fixture() -> IrAst:
    """The corpus JSON grammar, directives bound."""
    return canonical_grammar(corpus("json.gbnf"), GBNF_FLAVOUR)


def test_the_rename_fixture_is_a_rename_and_not_a_copy(json_gbnf: IrAst) -> None:
    """The fixture really renames — otherwise the alignment gate is vacuous."""
    renamed = canonical_grammar(RENAMED_JSON, GBNF_FLAVOUR)
    assert renamed != json_gbnf
    assert {str(rule.name) for rule in renamed.rules}.isdisjoint(
        {str(rule.name) for rule in json_gbnf.rules}
    )


def test_json_aligns_with_its_pure_rename(json_gbnf: IrAst) -> None:
    """The keystone: renaming every rule is no difference at all."""
    alignment = align_names(json_gbnf, canonical_grammar(RENAMED_JSON, GBNF_FLAVOUR))
    assert len(alignment.renamings) == 1
    assert not alignment.capped
    assert dict(alignment.renamings[0]) == {
        str(rule.name): "q-" + str(rule.name) for rule in json_gbnf.rules
    }


def test_the_witness_transports_the_whole_grammar(json_gbnf: IrAst) -> None:
    """The bijection is the artifact: applied, one grammar IS the other."""
    target = canonical_grammar(RENAMED_JSON, GBNF_FLAVOUR)
    witness = align_names(json_gbnf, target).renamings[0]
    assert canonicalize(witness.renamed(json_gbnf)) == canonicalize(target)


def test_a_different_factoring_of_json_refuses(json_gbnf: IrAst) -> None:
    """``json_arr.gbnf`` describes JSON another way — not a renaming."""
    other = canonical_grammar(corpus("json_arr.gbnf"), GBNF_FLAVOUR)
    alignment = align_names(json_gbnf, other)
    assert len(alignment.renamings) == 0
    assert not alignment.capped


def test_the_cross_flavour_mirror_aligns(json_gbnf: IrAst) -> None:
    """``json.abnf`` is json.gbnf rule-for-rule: one grammar, two surfaces.

    Names survive the flavour crossing here, so the witness is the identity —
    which is a stronger statement than "they align", not a weaker one.
    """
    abnf = canonical_grammar(corpus("json.abnf"), ABNF_FLAVOUR)
    alignment = align_names(json_gbnf, abnf)
    assert len(alignment.renamings) == 1
    assert all(rename.source == rename.target for rename in alignment.renamings[0])


@pytest.mark.parametrize(
    "name", ("arithmetic.gbnf", "chess.gbnf", "list.gbnf", "think.gbnf", "vyx.gbnf")
)
def test_every_corpus_grammar_aligns_with_itself(name: str) -> None:
    """Reflexivity across the corpus — and every offered bijection is valid."""
    ast = canonical_grammar(corpus(name), GBNF_FLAVOUR)
    alignment = align_names(ast, ast)
    assert len(alignment.renamings) >= 1
    for renaming in alignment.renamings:
        assert canonicalize(renaming.renamed(ast)) == canonicalize(ast)


def test_two_corpus_grammars_do_not_align() -> None:
    """The negative across the corpus: different grammars stay different."""
    left = parse_grammar(corpus("arithmetic.gbnf"), GBNF_FLAVOUR)
    right = parse_grammar(corpus("list.gbnf"), GBNF_FLAVOUR)
    assert len(align_names(left, right).renamings) == 0
