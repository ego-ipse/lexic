"""Encoding family — the codec that gives a char class's ordinals meaning."""

from __future__ import annotations

from itertools import product
from typing import Callable, cast

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrAtom, IrInt, IrNode, IrNone, IrStr, IrTuple
from lexic.ir.encoding import IrEncoding, IrTokenizer, IrUnicode
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import MAX_CODEPOINT, IrCharClass, IrChr, IrRange


def _vocab() -> IrMap:
    return IrMap(
        IrTuple(IrStr("<think>"), IrChr(0)),
        IrTuple(IrStr("</think>"), IrChr(1)),
        IrTuple(IrStr(" hi "), IrChr(2)),
    )


# ── IrUnicode ──────────────────────────────────────────────────────────


def test_unicode_is_singleton() -> None:
    """``IrUnicode()`` returns the one shared instance."""
    assert IrUnicode() is IrUnicode()


def test_unicode_resolve_single_glyph() -> None:
    """A single glyph resolves to its code point."""
    assert IrUnicode().resolve("a") == IrChr(97)


def test_unicode_resolve_multichar_is_unmapped() -> None:
    """A multi-character spelling has no single ordinal — ``IrNone``."""
    assert IrUnicode().resolve("ab") is IrNone


def test_unicode_spell_is_the_glyph() -> None:
    """Spelling a code point yields its glyph."""
    assert IrUnicode().spell(97) == IrStr("a")


def test_unicode_universe_is_max_codepoint() -> None:
    """The Unicode universe is the whole code-point range."""
    assert IrUnicode().universe == MAX_CODEPOINT


def test_unicode_is_an_encoding() -> None:
    """``IrUnicode`` is an :class:`IrEncoding`."""
    assert isinstance(IrUnicode(), IrEncoding)


# ── IrTokenizer ────────────────────────────────────────────────────────


def test_tokenizer_resolve_maps_text_to_id() -> None:
    """A token's text resolves to its vocab id."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert tok.resolve("<think>") == IrChr(0)


def test_tokenizer_resolve_unmapped_is_none() -> None:
    """Text that is not one vocab token resolves to ``IrNone``."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert tok.resolve("<nope>") is IrNone


def test_tokenizer_spell_is_inverse_of_resolve() -> None:
    """Spelling an id yields the token text (the decode inverse)."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert tok.spell(1) == IrStr("</think>")


def test_tokenizer_spell_unmapped_id_falls_back_to_bracket() -> None:
    """An id with no vocab text spells as the ``[id]`` form."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert tok.spell(99) == IrStr("[99]")


def test_tokenizer_universe_is_id_space_size() -> None:
    """The universe is one past the highest id."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert tok.universe == 3


def test_tokenizer_equality_and_hash_are_structural() -> None:
    """Two tokenizers with the same vocab are equal and hash alike."""
    a = IrTokenizer.from_vocab("gpt2", _vocab())
    b = IrTokenizer.from_vocab("gpt2", _vocab())
    assert a == b
    assert a in {b}


def test_tokenizer_repr_is_codegen() -> None:
    """The repr reproduces the constructor over both map directions."""
    tok = IrTokenizer.from_vocab("t", IrMap(IrTuple(IrStr("x"), IrChr(5))))
    assert repr(tok) == (
        "IrTokenizer(IrStr('t'), IrMap(IrTuple(IrStr('x'), IrChr(5))), "
        "IrMap(IrTuple(IrChr(5), IrStr('x'))))"
    )


def test_tokenizer_is_an_encoding_not_an_atom() -> None:
    """A tokenizer is an encoding node, but not itself a grammar atom."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert isinstance(tok, IrEncoding)
    assert isinstance(tok, IrNode)
    assert not isinstance(tok, IrAtom)


# ── complement is universe-relative (the one UTF assumption made a property) ──


def test_unicode_complement_tops_at_max_codepoint() -> None:
    """The Unicode complement spans up to ``MAX_CODEPOINT``."""
    comp = IrUnicode().complement(IrCharClass(IrChr(97), IrChr(98)))
    assert comp.intervals()[-1] == (99, MAX_CODEPOINT)


def test_tokenizer_complement_tops_at_vocab_ceiling() -> None:
    """The token complement spans only the id universe (``!<[1]>`` / ``.``)."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())  # universe 3
    comp = tok.complement(IrCharClass(IrChr(1)))
    assert comp.intervals() == [(0, 0), (2, 3)]


def test_complement_reuses_charclass_intervals_over_ranges() -> None:
    """Complement works over ranged members via the shared interval math."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    comp = tok.complement(IrCharClass(IrRange(IrChr(0), IrChr(1))))
    assert comp.intervals() == [(2, 3)]


# ── a registry is just an IrMap[IrStr, IrEncoding] (no bespoke class) ────


def test_registry_is_an_irmap_shared_by_name() -> None:
    """An encoding registry is a plain ``IrMap``; lookups share the instance."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    registry = IrMap(
        IrTuple(IrStr("unicode"), IrUnicode()),
        IrTuple(IrStr("gpt2"), tok),
    )
    assert registry.get(IrStr("gpt2")) is tok
    assert registry.get(IrStr("unicode")) is IrUnicode()


def test_from_vocab_derives_the_decode_inverse() -> None:
    """``from_vocab`` derives a decode map that inverts every encode entry."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    for text, ident in tok.encode.items():
        assert tok.decode.get(ident) == text


# ── segmentation (boundaries / tokenize) ────────────────────────────────


def _seg_tok() -> IrTokenizer:
    return IrTokenizer.from_vocab(
        "demo",
        IrMap(
            IrTuple(IrStr("<think>"), IrChr(0)),
            IrTuple(IrStr("</think>"), IrChr(1)),
            IrTuple(IrStr(" hi "), IrChr(2)),
        ),
    )


def test_boundaries_segments_into_char_aligned_spans() -> None:
    """boundaries yields (start, end, id) spans covering the input in order."""
    tok = _seg_tok()
    assert tok.boundaries("<think> hi </think>") == [(0, 7, 0), (7, 11, 2), (11, 19, 1)]


def test_tokenize_returns_the_span_ids() -> None:
    """tokenize is the id sequence of the covering spans."""
    assert _seg_tok().tokenize("<think> hi </think>") == [0, 2, 1]


def test_boundaries_is_longest_match() -> None:
    """A longer vocab token wins over a shorter prefix at the same position."""
    tok = IrTokenizer.from_vocab(
        "demo",
        IrMap(IrTuple(IrStr("ab"), IrChr(0)), IrTuple(IrStr("a"), IrChr(1))),
    )
    assert tok.tokenize("ab") == [0]


def test_boundaries_skips_unsegmentable_chars() -> None:
    """A position matching no vocab token advances with no token-match point."""
    tok = IrTokenizer.from_vocab("demo", IrMap(IrTuple(IrStr("a"), IrChr(0))))
    assert tok.boundaries("zaz") == [(1, 2, 0)]  # only the 'a' is a token point


def test_spell_reconstructs_tokenized_text() -> None:
    """Spelling the tokenized ids back concatenates to the original text."""
    tok = _seg_tok()
    text = "<think> hi </think>"
    assert "".join(str(tok.spell(i)) for i in tok.tokenize(text)) == text


# ── merge model (from_merges / ranks / ranked-merge segmentation) ────────


def _merge_vocab() -> IrMap:
    """A vocab of base chars plus the pieces the merges build up."""
    return IrMap(
        *(
            IrTuple(IrStr(s), IrChr(i))
            for i, s in enumerate(["a", "b", "c", "ab", "abc", "bc"])
        )
    )


def _merge_tok() -> IrTokenizer:
    """A merge tokenizer: (a,b)→ab rank 0, (ab,c)→abc rank 1, (b,c)→bc rank 2."""
    merges = IrTuple(
        IrTuple(IrStr("a"), IrStr("b")),
        IrTuple(IrStr("ab"), IrStr("c")),
        IrTuple(IrStr("b"), IrStr("c")),
    )
    return IrTokenizer.from_merges("demo", _merge_vocab(), merges)


def test_from_merges_carries_the_merge_model() -> None:
    """The ordered dyads round-trip through ``ranks`` into the derived ``merges``."""
    tok = _merge_tok()
    assert tok.merges == IrTuple(
        IrTuple(IrStr("a"), IrStr("b")),
        IrTuple(IrStr("ab"), IrStr("c")),
        IrTuple(IrStr("b"), IrStr("c")),
    )


def test_merges_derivation_sorts_on_rank() -> None:
    """``merges`` orders the dyads by rank, independent of map insertion order."""
    tok = _merge_tok()
    construct = cast(Callable[..., IrTokenizer], IrTokenizer)
    descending = sorted(tok.ranks.items(), key=lambda dyad_rank: -int(dyad_rank[1]))
    scrambled = IrMap(*(IrTuple(dyad, rank) for dyad, rank in descending))
    resorted = construct(tok.name, tok.encode, tok.decode, scrambled)
    assert resorted.merges == tok.merges


def test_from_merges_derives_the_decode_inverse() -> None:
    """``from_merges`` derives ``decode`` from ``encode`` like ``from_vocab``."""
    tok = _merge_tok()
    for text, ident in tok.encode.items():
        assert tok.decode.get(ident) == text


def test_from_vocab_has_empty_merges() -> None:
    """A vocab-only tokenizer carries no merges (longest-match model)."""
    assert IrTokenizer.from_vocab("v", _vocab()).merges == IrTuple()


def test_vocab_only_repr_elides_trailing_empty_ranks() -> None:
    """The trailing empty ``ranks`` is elided from a vocab-only tokenizer's repr."""
    tok = IrTokenizer.from_vocab("t", IrMap(IrTuple(IrStr("x"), IrChr(5))))
    assert "IrMap()" not in repr(tok)
    assert repr(tok) == (
        "IrTokenizer(IrStr('t'), IrMap(IrTuple(IrStr('x'), IrChr(5))), "
        "IrMap(IrTuple(IrChr(5), IrStr('x'))))"
    )


def test_merge_tokenizer_repr_shows_ranks() -> None:
    """A merge tokenizer's repr renders the stored rank map (present, not elided)."""
    tok = _merge_tok()
    assert repr(tok).endswith(
        ", IrMap(IrTuple(IrTuple(IrStr('a'), IrStr('b')), IrInt(0)), "
        "IrTuple(IrTuple(IrStr('ab'), IrStr('c')), IrInt(1)), "
        "IrTuple(IrTuple(IrStr('b'), IrStr('c')), IrInt(2))))"
    )


def test_ranks_indexes_each_dyad_by_position() -> None:
    """``ranks`` maps each merge dyad to its position (the rank), as ``IrInt``."""
    ranks = _merge_tok().ranks
    assert ranks.get(IrTuple(IrStr("a"), IrStr("b"))) == IrInt(0)
    assert ranks.get(IrTuple(IrStr("ab"), IrStr("c"))) == IrInt(1)
    assert ranks.get(IrTuple(IrStr("b"), IrStr("c"))) == IrInt(2)


def test_ranks_is_empty_for_vocab_only() -> None:
    """A vocab-only tokenizer has an empty rank index."""
    assert IrTokenizer.from_vocab("v", _vocab()).ranks == IrMap()


def test_merge_segments_to_the_highest_merge() -> None:
    """``abc`` merges (a,b) then (ab,c) into one token — a single id-4 span."""
    tok = _merge_tok()
    assert tok.boundaries("abc") == [(0, 3, 4)]
    assert tok.tokenize("abc") == [4]


def test_merge_prefers_the_lower_rank_pair() -> None:
    """When (b,c) outranks (a,b), ``abc`` splits ``a`` | ``bc`` instead."""
    merges = IrTuple(
        IrTuple(IrStr("b"), IrStr("c")),  # rank 0 — wins over (a,b)
        IrTuple(IrStr("a"), IrStr("b")),  # rank 1
    )
    tok = IrTokenizer.from_merges("demo", _merge_vocab(), merges)
    assert tok.tokenize("abc") == [0, 5]  # a, bc


def test_merge_spans_track_original_char_offsets() -> None:
    """Merged spans carry the original character offsets, in order."""
    tok = _merge_tok()
    assert tok.boundaries("bc abc") == [(0, 2, 5), (3, 6, 4)]  # 'bc', skip ' ', 'abc'


def test_merge_skips_unsegmentable_symbols() -> None:
    """A final symbol carried by no vocab entry yields no span."""
    tok = _merge_tok()
    assert tok.boundaries("zabc") == [(1, 4, 4)]  # 'z' unknown, then 'abc'


def test_merge_spell_reconstructs_text() -> None:
    """Spelling the merge-segmented ids back concatenates to the original text."""
    tok = _merge_tok()
    assert "".join(str(tok.spell(i)) for i in tok.tokenize("abc")) == "abc"


# ── fidelity: differential vs an INDEPENDENT BPE reference over a corpus ──


def _ref_bpe(
    text: str, vocab: dict[str, int], merges: list[tuple[str, str]]
) -> list[int]:
    """The reference BPE segmentation — the classic *merge-all-then-recompute*
    variant (GPT-2's ``bpe()`` loop), structurally distinct from lexic's
    one-at-a-time-leftmost :meth:`IrTokenizer._merge_segment`. Agreement across a
    corpus validates both correctness and the fixpoint's order-independence.

    :param text: The instance to segment.
    :param vocab: The spelling → id map.
    :param merges: The ordered merge dyads (rank = position).
    :returns: The covering token ids (unknown final symbols skipped).
    """
    rank = {pair: i for i, pair in enumerate(merges)}
    word = list(text)
    while len(word) >= 2:
        pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
        best = min((p for p in pairs if p in rank), key=lambda p: rank[p], default=None)
        if best is None:
            break
        merged: list[str] = []
        i = 0
        while i < len(word):
            if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                merged.append(word[i] + word[i + 1])
                i += 2
            else:
                merged.append(word[i])
                i += 1
        word = merged
    return [vocab[s] for s in word if s in vocab]


def test_merge_segmentation_matches_reference_over_corpus() -> None:
    """Over every string of length ≤5 on ``{a,b,c}``, lexic's segmentation equals
    the independent reference — a differential fidelity gate."""
    vocab_spellings = ["a", "b", "c", "ab", "bc", "abc", "cab", "abca"]
    vocab = {s: i for i, s in enumerate(vocab_spellings)}
    merges = [("a", "b"), ("b", "c"), ("ab", "c"), ("c", "ab"), ("abc", "a")]
    tok = IrTokenizer.from_merges(
        "fidelity",
        IrMap(*(IrTuple(IrStr(s), IrChr(i)) for s, i in vocab.items())),
        IrTuple(*(IrTuple(IrStr(a), IrStr(b)) for a, b in merges)),
    )
    corpus = (
        "".join(combo)
        for length in range(1, 6)
        for combo in product("abc", repeat=length)
    )
    for text in corpus:
        assert tok.tokenize(text) == _ref_bpe(text, vocab, merges), text


# ── special tokens (HF added_tokens — atomic match before the rewrite) ────


def _special_vocab() -> IrMap:
    """Two special spellings plus BPE pieces (``h``+``i``→``hi``)."""
    pairs = {"<think>": 0, "</think>": 1, "h": 2, "i": 3, "hi": 4, "!": 5}
    return IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in pairs.items()))


def _special_tok() -> IrTokenizer:
    """A merge tokenizer whose ``<think>``/``</think>`` are atomic specials."""
    return IrTokenizer.from_merges(
        "tokens",
        _special_vocab(),
        IrTuple(IrTuple(IrStr("h"), IrStr("i"))),
        IrTuple(IrStr("<think>"), IrStr("</think>")),
    )


def test_specials_match_atomically_amid_bpe() -> None:
    """A special is one token even mid-BPE; the gap still merges (h+i→hi)."""
    tok = _special_tok()
    assert tok.tokenize("<think>hi</think>!") == [0, 4, 1, 5]


def test_specials_carry_correct_char_offsets() -> None:
    """Special + gap spans cover the input with the right char offsets."""
    tok = _special_tok()
    assert tok.boundaries("<think>hi</think>!") == [
        (0, 7, 0),
        (7, 9, 4),
        (9, 17, 1),
        (17, 18, 5),
    ]


def test_specials_longest_match_wins_over_shorter() -> None:
    """A longer special is matched over a shorter overlapping one."""
    vocab = IrMap(
        IrTuple(IrStr("<a>"), IrChr(0)),
        IrTuple(IrStr("<ab>"), IrChr(1)),
        IrTuple(IrStr("x"), IrChr(2)),
    )
    tok = IrTokenizer.from_vocab("t", vocab, IrTuple(IrStr("<a>"), IrStr("<ab>")))
    assert tok.tokenize("<ab>x") == [1, 2]


def test_special_not_in_vocab_refuses() -> None:
    """A special spelling with no vocab id is a construction error."""
    with pytest.raises(UnsupportedConstructError):
        IrTokenizer.from_vocab("t", _special_vocab(), IrTuple(IrStr("<nope>")))


def test_empty_specials_elide_from_repr() -> None:
    """A tokenizer with no specials elides the field (repr-codegen stable)."""
    tok = IrTokenizer.from_vocab("t", IrMap(IrTuple(IrStr("x"), IrChr(5))))
    assert repr(tok) == (
        "IrTokenizer(IrStr('t'), IrMap(IrTuple(IrStr('x'), IrChr(5))), "
        "IrMap(IrTuple(IrChr(5), IrStr('x'))))"
    )


# ── IrUnicode.boundaries / .ids (the degenerate encoding contract) ──────


def test_unicode_boundaries_is_one_span_per_char() -> None:
    """Each character is its own ``(i, i+1, ordinal)`` span, in order."""
    assert IrUnicode().boundaries("ab") == [(0, 1, 97), (1, 2, 98)]


def test_unicode_boundaries_of_empty_text_is_empty() -> None:
    """No characters means no spans."""
    assert IrUnicode().boundaries("") == []


def test_unicode_ids_is_the_whole_codepoint_range() -> None:
    """``ids`` is every code point, as the plain ``range``."""
    assert IrUnicode().ids() == range(MAX_CODEPOINT + 1)


def test_unicode_tokenize_is_the_codepoints() -> None:
    """``tokenize`` derives through ``boundaries`` — the code points in order."""
    assert IrUnicode().tokenize("ab") == [97, 98]


# ── IrTokenizer.ids (the engine's plain-int contract) ────────────────────


def test_tokenizer_ids_is_the_vocab_id_set() -> None:
    """``ids`` is every vocab id, order-insensitive."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert set(tok.ids()) == {0, 1, 2}


def test_tokenizer_ids_are_plain_python_ints() -> None:
    """Every id ``ids`` yields is a plain ``int``, not an ``IrChr``."""
    tok = IrTokenizer.from_vocab("gpt2", _vocab())
    assert all(not isinstance(i, IrInt) for i in tok.ids())


# ── pythonic builder forms (Vocab / Merges / Specials coercion) ─────────


def test_from_vocab_accepts_a_plain_dict() -> None:
    """A plain ``dict`` vocab resolves/spells the same as the ``IrMap`` form."""
    plain = IrTokenizer.from_vocab("gpt2", {"<think>": 0, "</think>": 1, " hi ": 2})
    assert plain == IrTokenizer.from_vocab("gpt2", _vocab())


def test_from_merges_accepts_plain_python_merges() -> None:
    """Plain ``(str, str)`` merge tuples tokenize identically to the dyad form."""
    plain_merges = [("a", "b"), ("ab", "c"), ("b", "c")]
    plain = IrTokenizer.from_merges("demo", _merge_vocab(), plain_merges)
    assert plain.tokenize("abc") == _merge_tok().tokenize("abc")


def test_specials_from_plain_list_coerce_to_irtuple_of_irstr() -> None:
    """A plain list of specials coerces to an ``IrTuple`` of ``IrStr``."""
    tok = IrTokenizer.from_vocab("t", _special_vocab(), ["<think>", "</think>"])
    assert tok.specials == IrTuple(IrStr("<think>"), IrStr("</think>"))


def test_from_vocab_coerces_a_ready_irmap_by_value():
    """A ready ``IrMap`` vocab is rebuilt with ``IrChr`` ids — reducer-typed
    values (``IrInt`` / numeric ``IrStr``) feed the builders directly."""
    vocab = IrMap(IrTuple(IrStr("x"), IrInt(5)))
    tok = IrTokenizer.from_vocab("t", vocab)
    assert tok.encode.get(IrStr("x")) == IrChr(5)


# ── protocol conformance: tokenize derives from boundaries, for every encoding ──


def test_tokenize_equals_ordinals_of_boundaries_for_unicode() -> None:
    """``tokenize`` is exactly the ordinal projection of ``boundaries`` — Unicode."""
    uni = IrUnicode()
    text = "ab"
    assert uni.tokenize(text) == [ordinal for _, _, ordinal in uni.boundaries(text)]


def test_tokenize_equals_ordinals_of_boundaries_for_tokenizer() -> None:
    """``tokenize`` is exactly the ordinal projection of ``boundaries`` — tokenizer."""
    tok = _seg_tok()
    text = "<think> hi </think>"
    assert tok.tokenize(text) == [ordinal for _, _, ordinal in tok.boundaries(text)]
