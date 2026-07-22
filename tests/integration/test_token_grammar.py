"""Token grammars end-to-end — the one interface: compile_text(tokenizer=).parse.

Grammar TEXT with token terminals → compile (parse/canonicalize/concretize/
bind/synthesize/fold) → parse an instance through lexic's own tokenization →
a round-trippable model. Capability B, README §Tokens, on the real engine.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text, parse_grammar, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.encoding import IrTokenizer
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrAlphabet, IrCharClass, IrChr, IrLiteral

_VOCAB = {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "<": 4, "/think>": 5}
_GRAMMAR = "root ::= <think> thinking </think>\nthinking ::= !</think>*"


def _tokenizer() -> IrTokenizer:
    return IrTokenizer.from_vocab(
        "tokens", IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in _VOCAB.items()))
    )


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_grammar_text_parses_to_alphabet_terminals() -> None:
    """The README token grammar parses to IrAlphabet terminals (no tokenizer)."""
    ast = parse_grammar(_GRAMMAR, GBNF_FLAVOUR)
    root = ast.rules[0].body[0]
    assert root[0].atom == IrAlphabet("tokens", IrLiteral("<think>"))
    assert root[2].atom == IrAlphabet("tokens", IrLiteral("</think>"))


def test_one_interface_parses_a_token_instance() -> None:
    """compile_text(grammar, tokenizer=).parse(text) returns a model."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    model = cg.parse("<think>ab</think>")
    assert model.dump() == {
        "tok": "<think>",
        "thinking": {"value": "ab"},
        "tok2": "</think>",
    }


def test_token_instance_round_trips() -> None:
    """A parsed token instance round-trips char-exact through to_text."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    for text in ("<think>ab</think>", "<think></think>", "<think>a</think>"):
        assert cg.parse(text).to_text() == text


def test_token_instance_matches_id_granular() -> None:
    """A '<' (id 4) does not satisfy the '<think>' (id 0) opening terminal."""
    cg = compile_text("root ::= <think>", tokenizer=_tokenizer())
    assert cg.parse("<think>").to_text() == "<think>"
    with pytest.raises(UnsupportedConstructError):
        cg.parse("<")  # same first char, different token


def test_negated_token_admits_other_ids() -> None:
    """thinking ::= !</think>* consumes any non-</think> tokens."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    assert cg.parse("<think>a<b</think>").to_text() == "<think>a<b</think>"


def test_missing_closing_token_rejects() -> None:
    """No </think> token — the parse fails."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    with pytest.raises(UnsupportedConstructError):
        cg.parse("<think>ab")


def test_id_form_token_grammar_parses() -> None:
    """The <[id]> id form works through the same interface."""
    cg = compile_text("root ::= <[0]> <[1]>", tokenizer=_tokenizer())
    assert cg.parse("<think></think>").to_text() == "<think></think>"


def test_concretised_grammar_has_resolved_ids() -> None:
    """After compile, a text-form token's canonical grammar carries its id."""
    cg = compile_text("root ::= <think>", tokenizer=_tokenizer())
    atom = cg.grammar.rules[0].body[0][0].atom
    assert atom == IrAlphabet("tokens", IrCharClass(IrChr(0)))
