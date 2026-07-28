"""TokenKernel — Earley over a token-segmented input (capability B)."""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple, IrUnicode, concretize
from lexic.parsing.earley.kernel.readout import accept_item
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tokenscan import TokenKernel, token_term_specs
from lexic.parsing.fold import lift_optional_nullables

_VOCAB = {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "<": 4, "/think>": 5}


def _tokenizer() -> IrTokenizer:
    return IrTokenizer.from_vocab(
        "tokens", IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in _VOCAB.items()))
    )


def _tables_for(grammar: str, tok: IrTokenizer):
    reg = IrMap(IrTuple(IrStr("unicode"), IrUnicode()), IrTuple(IrStr("tokens"), tok))
    ast = concretize(parse_grammar(grammar, GBNF_FLAVOUR), reg)
    return compile_tables(normalize(lift_optional_nullables(ast)))


def _accepts(tables, tok: IrTokenizer, text: str) -> bool:
    bounds = {s: (tid, e - s) for s, e, tid in tok.boundaries(text)}
    return accept_item(TokenKernel(tables, text, bounds).run()) >= 0


# ── the README grammar: root ::= <think> thinking </think> ──────────────


def _think_tables(tok):
    return _tables_for(
        "root ::= <think> thinking </think>\nthinking ::= !</think>*", tok
    )


def test_accepts_well_formed_think_block() -> None:
    """<think> content </think> parses (content is any non-</think> token)."""
    tok = _tokenizer()
    assert _accepts(_think_tables(tok), tok, "<think>ab</think>")


def test_accepts_empty_think_block() -> None:
    """<think></think> parses (thinking is zero-or-more)."""
    tok = _tokenizer()
    assert _accepts(_think_tables(tok), tok, "<think></think>")


def test_rejects_missing_closing_token() -> None:
    """No </think> token — the root sequence is incomplete."""
    tok = _tokenizer()
    assert not _accepts(_think_tables(tok), tok, "<think>ab")


def test_rejects_missing_opening_token() -> None:
    """No <think> token — the root cannot start."""
    tok = _tokenizer()
    assert not _accepts(_think_tables(tok), tok, "ab</think>")


def test_rejects_trailing_token_past_close() -> None:
    """A token after </think> is unconsumed — reject."""
    tok = _tokenizer()
    assert not _accepts(_think_tables(tok), tok, "<think>ab</think>b")


# ── id-granularity: a token terminal matches by id, not by chars ─────────


def test_token_match_is_id_granular_not_char_prefix() -> None:
    """`<` (id 4) does not satisfy the `<think>` (id 0) terminal."""
    tok = _tokenizer()
    tables = _tables_for("root ::= <think>", tok)
    assert _accepts(tables, tok, "<think>")
    assert not _accepts(tables, tok, "<")  # same first char, different token


def test_negated_token_matches_any_other_id() -> None:
    """!</think> admits any token except </think>."""
    tok = _tokenizer()
    tables = _tables_for("root ::= !</think>", tok)
    assert _accepts(tables, tok, "a")  # id 2 ≠ </think>
    assert not _accepts(tables, tok, "</think>")  # id 1 IS </think>


# ── token_term_specs ────────────────────────────────────────────────────


def test_token_term_specs_extracts_ids_and_polarity() -> None:
    """Positive and negated token terminals resolve to (id-set, negated)."""
    tok = _tokenizer()
    tables = _tables_for("root ::= <think> !</think>", tok)
    specs = list(token_term_specs(tables).values())
    assert (frozenset({0}), False) in specs  # <think>
    assert (frozenset({1}), True) in specs  # !</think>
