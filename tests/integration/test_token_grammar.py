"""Token grammars end-to-end — the one interface: compile_text(tokenizer=).parse.

Grammar TEXT with token terminals → compile (parse/canonicalize/concretize/
bind/synthesize/fold) → parse an instance through lexic's own tokenization →
a round-trippable model. Capability B, README §Tokens, on the real engine.
"""

from __future__ import annotations

from itertools import product
from time import perf_counter

import pytest

from lexic.compile import (
    compile_from_path,
    compile_text,
    parse_grammar,
    reset_cache_for_tests,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import (
    IrAlphabet,
    IrCharClass,
    IrChr,
    IrLiteral,
    IrMap,
    IrStr,
    IrTokenizer,
    IrTuple,
)
from lexic.parsing.earley.kernel.tables import ParserTables, compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tokenscan import (
    TokenMaskCursor,
    split_literals,
    viable_prefix,
)
from lexic.parsing.fold import lift_optional_nullables
from tests.paths import GROUND_TRUTH

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


def test_resolution_reaches_the_engine_and_stops_there() -> None:
    """Ids are for MATCHING; the authored spelling is what the grammar SAYS.

    Concretization still happens — the codegen grammar the engine parses
    against carries the resolved id — but it no longer reaches the canonical
    AST or a class's ``__grammar__``. Binding a vocabulary must not make
    ``to_grammar()`` lossy: this test previously asserted the opposite, which
    is how the loss went unnoticed.
    """
    cg = compile_text("root ::= <think>", tokenizer=_tokenizer())
    authored = cg.grammar.rules[0].body[0][0].atom
    matched = cg.codegen_grammar.rules[0].body[0][0].atom
    assert authored == IrAlphabet("tokens", IrLiteral("<think>"))
    assert matched == IrAlphabet("tokens", IrCharClass(IrChr(0)))
    assert "<think>" in str(cg.parse("<think>").to_grammar("gbnf"))


# ── capability C: the admissible next-token mask ─────────────────────────


def test_mask_cursor_admissible_next_tokens() -> None:
    """The mask gives the admissible next-token ids at each generation step."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    cur = cg.constrain()
    assert cur.mask() == {0}  # only <think> can open
    assert not cur.accepts()
    cur.push(0)  # <think>
    # any token: a content token via !</think>*, or </think> closing the root
    assert cur.mask() == set(_VOCAB.values())
    cur.push(2)  # a  (content, via !</think>*)
    cur.push(1)  # </think>
    assert cur.mask() == set()  # nothing more admissible
    assert cur.accepts()  # a complete parse


def test_mask_equals_stateless_oracle() -> None:
    """The mask equals a brute-force viability oracle at every prefix."""
    cg = compile_text(_GRAMMAR, tokenizer=_tokenizer())
    universe = set(_VOCAB.values())

    def viable(ids: list[int]) -> bool:
        c = cg.constrain()
        for i in ids:
            c.push(i)
        # a prefix is viable if some next token is admissible OR it accepts
        return bool(c.mask()) or c.accepts()

    for prefix in ([], [0], [0, 2], [0, 2, 1]):
        cur = cg.constrain()
        for i in prefix:
            cur.push(i)
        oracle = {i for i in universe if viable(prefix + [i])}
        assert cur.mask() == oracle


def test_constrain_without_tokenizer_refuses() -> None:
    """A char grammar (no bound tokenizer) cannot produce a mask cursor."""
    cg = compile_text("root ::= [a-z]+")
    with pytest.raises(UnsupportedConstructError):
        cg.constrain()


# ── the multi-tokenizer registry surface (compile_text(registry=)) ────────


def test_registry_binds_encoding_by_grammar_name() -> None:
    """``registry=`` binds the grammar's encoding *name*, not the tokenizer's.

    The grammar references ``tokens`` (GBNF's default) while the tokenizer is
    named ``gpt2`` — the registry key decouples the two.
    """
    vocab = IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in _VOCAB.items()))
    tok = IrTokenizer.from_vocab("gpt2", vocab)
    registry = IrMap(IrTuple(IrStr("tokens"), tok))
    cg = compile_text(_GRAMMAR, registry=registry)
    assert cg.tokens.tokenizer is tok  # the sole tokenizer segments instances
    assert cg.parse("<think>ab</think>").to_text() == "<think>ab</think>"


def test_tokenizer_sugar_equals_single_entry_registry() -> None:
    """``tokenizer=`` is exactly the one-entry registry under the tokenizer name."""
    tok = _tokenizer()
    via_sugar = compile_text(_GRAMMAR, tokenizer=tok)
    reset_cache_for_tests()
    via_registry = compile_text(_GRAMMAR, registry=IrMap(IrTuple(tok.name, tok)))
    text = "<think>ab</think>"
    assert via_sugar.parse(text).dump() == via_registry.parse(text).dump()


def test_registry_and_tokenizer_compose() -> None:
    """``registry=`` and ``tokenizer=`` bind names together, not exclusively."""
    tok = _tokenizer()
    text = "<think>ab</think>"
    both = compile_text(_GRAMMAR, tokenizer=tok, registry=IrMap(IrTuple(tok.name, tok)))
    assert both.parse(text).to_text() == text


def test_conflicting_encoding_name_refuses() -> None:
    """One name bound to two different encodings is a real conflict — it raises."""
    tok = _tokenizer()
    other = IrTokenizer.from_vocab("tokens", IrMap(IrTuple(IrStr("z"), IrChr(0))))
    with pytest.raises(UnsupportedConstructError, match="different encodings"):
        compile_text(_GRAMMAR, tokenizer=tok, registry=IrMap(IrTuple(tok.name, other)))


# ── the char-heavy mask (capability C over a CHAR grammar) — F3+F4 ────────

# (grammar, its finite language, vocab) — the differential matrix. Each grammar
# stresses a different construct: bare sequences/alternation; a char class + an
# optional; a bounded quantifier.
_CHAR_CASES = [
    (
        'root ::= "c" a1 | "d" "o" "g"\na1 ::= "a" a2 | "o" "t"\na2 ::= "t" | "r"',
        {"cat", "car", "cot", "dog"},
        ["c", "a", "t", "r", "d", "o", "g", "ca", "at", "og", "dog", "x", "co"],
    ),
    (
        'root ::= [ab] "x"? "c"',
        {"ac", "bc", "axc", "bxc"},
        ["a", "b", "x", "c", "ax", "bc", "xc", "abc", "z"],
    ),
    (
        'root ::= "a" "a"? "a"? "b"',  # 1-3 a's then b: ab, aab, aaab
        {"ab", "aab", "aaab"},
        ["a", "b", "aa", "ab", "aab", "aaab", "q"],
    ),
]


def _tok(vocab: list[str]) -> IrTokenizer:
    encode = IrMap(*(IrTuple(IrStr(s), IrChr(i)) for i, s in enumerate(vocab)))
    return IrTokenizer.from_vocab("tokens", encode)


def _oracle(
    vocab: list[str], language: set[str], prefix_ids: tuple[int, ...]
) -> set[int]:
    """Brute-force truth: t admissible iff some valid word extends prefix+spell(t)."""
    prefix = "".join(vocab[i] for i in prefix_ids)
    return {
        t
        for t in range(len(vocab))
        if any(w.startswith(prefix + vocab[t]) for w in language)
    }


@pytest.mark.parametrize("grammar, language, vocab", _CHAR_CASES)
def test_char_heavy_mask_matches_brute_force_oracle(
    grammar: str, language: set[str], vocab: list[str]
) -> None:
    """The char-grammar next-token mask equals a brute-force oracle at every
    reachable prefix (≤3 tokens), across char classes / optionals / quantifiers —
    the F3+F4 soundness+completeness gate."""
    cursor = compile_text(grammar).constrain(_tok(vocab))
    ids = range(len(vocab))
    for depth in range(4):
        for combo in product(ids, repeat=depth):
            cursor.ids = list(combo)
            assert cursor.mask() == _oracle(vocab, language, combo), "".join(
                vocab[i] for i in combo
            )


def test_char_heavy_mask_start_and_accept() -> None:
    """Spot-check the char mask: only word-openers at the start; accept mid-word."""
    grammar, _, vocab = _CHAR_CASES[0]
    tok = _tok(vocab)
    cursor = compile_text(grammar).constrain(tok)
    assert {str(tok.spell(i)) for i in cursor.mask()} == {"c", "ca", "co", "d", "dog"}
    for tid in (0, 1, 2):  # c, a, t → "cat"
        cursor.push(tid)
    assert cursor.accepts()
    assert cursor.mask() == set()


def test_char_mask_cost_is_prefix_independent():
    """E6-5: mask() on the live chart does not rescan the committed prefix —
    a 600-char prefix masks in comparable time to an empty one (the old
    stateless path reparsed the whole prefix per candidate token; margin 10×
    holds ~50× of headroom against that regression)."""
    cursor = compile_text('root ::= [0-9]+"\\n"').constrain(
        _tok([str(d) for d in range(10)] + ["12", "345", "\n"])
    )

    def once() -> float:
        start = perf_counter()
        cursor.mask()
        return perf_counter() - start

    t_short = min(once() for _ in range(5))
    for _ in range(300):
        cursor.push(10)  # "12" — 600 committed chars
    t_long = min(once() for _ in range(5))
    assert t_long <= max(10 * t_short, 1e-3), (t_short, t_long)


# ── the resumable mask over a RECURSIVE grammar (json.gbnf) ──────────────

_JSON_VOCAB = ["{", "}", "[", "]", ":", ",", '"', "a", "1", "true", "null", "t"]
"""Structural chars + a string char + a digit + two multi-char tokens. ``t`` and
``true`` share a trie prefix, so the DFS must not admit one for the other."""

_NESTED = '{"a":{"a":[1,1]}}'
"""The document the walk builds — objects inside objects inside an array, so
the mask is exercised at several `{`/`[` depths."""


def _json_cursor() -> tuple[TokenMaskCursor, ParserTables, list[int]]:
    """The live cursor, the oracle's char-granular tables, and the doc's ids."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    cursor = compiled.constrain(_tok(_JSON_VOCAB))
    lifted = lift_optional_nullables(split_literals(compiled.codegen_grammar))
    ids = [_JSON_VOCAB.index(ch) for ch in _NESTED]
    return cursor, compile_tables(normalize(lifted)), ids


def _viable_mask(tables: ParserTables, prefix_ids: list[int]) -> set[int]:
    """Brute-force truth: t admissible iff prefix+spell(t) is a viable prefix."""
    text = "".join(_JSON_VOCAB[i] for i in prefix_ids)
    return {
        t
        for t, spelling in enumerate(_JSON_VOCAB)
        if viable_prefix(tables, text + spelling)
    }


def test_recursive_mask_matches_the_viable_prefix_oracle_forward() -> None:
    """Building a nested json document token by token, the live-chart mask
    equals the stateless recompute at every step — the resumable path over a
    RECURSIVE grammar (the finite-language cases cannot reach nesting)."""
    cursor, tables, ids = _json_cursor()
    for step in range(len(ids)):
        prefix = ids[:step]
        cursor.ids = list(prefix)
        assert cursor.mask() == _viable_mask(tables, prefix), _NESTED[:step]


def test_recursive_mask_survives_rollback_across_nesting_depth() -> None:
    """Reassigning ``ids`` to shorter prefixes rolls the chart back through
    `{`/`[` depth and still masks correctly — per-column truncation is sound
    across nesting, not just along a flat prefix."""
    cursor, tables, ids = _json_cursor()
    cursor.ids = list(ids)
    cursor.mask()  # commit the whole document first
    for step in range(len(ids), -1, -1):  # then walk back out, deepest first
        prefix = ids[:step]
        cursor.ids = list(prefix)
        assert cursor.mask() == _viable_mask(tables, prefix), _NESTED[:step]


def test_recursive_mask_re_extends_down_a_different_branch() -> None:
    """After rolling back to a `{`, extending with a DIFFERENT next token still
    masks correctly — a re-opened column must be char-independent (the junction
    re-seed), which a monotonic forward walk never tests."""
    cursor, tables, ids = _json_cursor()
    cursor.ids = list(ids)
    cursor.mask()
    open_brace = [_JSON_VOCAB.index("{")]
    for follower in ('"', "}"):  # a member, or the empty object
        branch = open_brace + [_JSON_VOCAB.index(follower)]
        cursor.ids = list(branch)
        assert cursor.mask() == _viable_mask(tables, branch), "{" + follower


def test_recursive_mask_accepts_only_a_complete_document() -> None:
    """``accepts()`` is false at every proper prefix and true at the whole
    document — the recursion closes exactly once."""
    cursor, _, ids = _json_cursor()
    for step in range(len(ids)):
        cursor.ids = ids[:step]
        assert not cursor.accepts(), _NESTED[:step]
    cursor.ids = list(ids)
    assert cursor.accepts()
