"""Tests for lexic.ir.text.tokenizer — the vocabulary and its segmenters.

Real-vocabulary (GPT-2/Qwen/Gemma) coverage lives in
``tests/integration/lexic/tokens/``; this file targets ``IrTokenizer``'s own
builders and segmentation models against small hand-built vocabularies.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrChr, IrInt, IrMap, IrNone, IrStr, IrTuple
from lexic.ir.text.pipeline import IrTokenPipeline
from lexic.ir.text.tokenizer import (
    IrLongestMatch,
    IrRankedMerge,
    IrTokenizer,
    _identifier,
    _spelling,
    _vocab_map,
)


def test_from_vocab_segments_by_longest_match():
    """A vocab-only tokenizer segments greedily by longest match."""
    tok = IrTokenizer.from_vocab("v", {"a": 0, "ab": 1, "b": 2})
    assert tok.segmenter is IrLongestMatch()
    assert tok.tokenize("ab") == [1]
    assert tok.tokenize("aab") == [0, 1]


def test_from_vocab_boundaries_report_char_aligned_spans():
    """Each single-char token reports its own [start, end) span."""
    tok = IrTokenizer.from_vocab("v", {"a": 0, "b": 1})
    assert tok.boundaries("ab") == [(0, 1, 0), (1, 2, 1)]


def test_from_merges_runs_the_ranked_merge_fixpoint():
    """A BPE vocab/merge pair reduces to the merged token, lowest rank first."""
    vocab = {"a": 0, "b": 1, "ab": 2, "c": 3, "abc": 4}
    merges = [("a", "b"), ("ab", "c")]
    tok = IrTokenizer.from_merges("v", vocab, merges)
    assert tok.segmenter is IrRankedMerge()
    assert tok.tokenize("abc") == [4]


def test_resolve_and_spell_are_inverses_over_the_vocab():
    """resolve() and spell() invert each other for a mapped spelling."""
    tok = IrTokenizer.from_vocab("v", {"a": 0, "b": 1})
    resolved = tok.resolve("a")
    assert resolved == tok.encode["a"]
    assert isinstance(resolved, IrChr)
    assert tok.spell(int(resolved)) == "a"


def test_resolve_returns_irnone_for_an_unmapped_spelling():
    """A spelling outside the vocab resolves to IrNone."""
    tok = IrTokenizer.from_vocab("v", {"a": 0})
    assert tok.resolve("z") is IrNone


def test_spell_falls_back_to_bracketed_id_for_an_unmapped_ordinal():
    """An unmapped ordinal spells as its bracketed id."""
    tok = IrTokenizer.from_vocab("v", {"a": 0})
    assert str(tok.spell(99)) == "[99]"


def test_universe_is_the_highest_id_and_minus_one_when_empty():
    """universe is the max id, or -1 for an empty vocab."""
    tok = IrTokenizer.from_vocab("v", {"a": 0, "b": 5})
    assert tok.universe == 5
    empty = IrTokenizer.from_vocab("v", {})
    assert empty.universe == -1


def test_specials_match_atomically_before_the_segmentation_model():
    """A special spelling matches whole, ahead of the segmentation model."""
    pipeline = IrTokenPipeline(specials=IrTuple("<s>"))
    tok = IrTokenizer.from_vocab("v", {"<s>": 0, "a": 1}, pipeline)
    assert tok.tokenize("<s>a") == [0, 1]


def test_build_refuses_a_special_that_is_not_in_the_vocab():
    """A special naming no vocab entry refuses at construction."""
    pipeline = IrTokenPipeline(specials=IrTuple("<missing>"))
    with pytest.raises(UnsupportedConstructError, match="<missing>"):
        IrTokenizer.from_vocab("v", {"a": 0}, pipeline)


def test_with_segmenter_returns_a_copy_carrying_the_new_model():
    """with_segmenter returns an independent copy; the original is unchanged."""
    tok = IrTokenizer.from_vocab("v", {"a": 0})
    swapped = tok.with_segmenter(IrRankedMerge())
    assert swapped.segmenter is IrRankedMerge()
    assert tok.segmenter is IrLongestMatch()  # the original is untouched


def test_carries_is_true_for_a_vocab_covered_character_false_otherwise():
    """carries() reports whether anything in the vocab can carry a spelling."""
    tok = IrTokenizer.from_vocab("v", {"a": 0})
    assert tok.carries("a")
    assert not tok.carries("z")


# ── _spelling / _identifier — exact-class carry ─────────────────────────────


class _StrSubclass(IrStr):
    """A local IrStr subclass — proves ``_spelling`` normalizes to exact
    ``IrStr`` rather than letting a subclass through."""


class _ChrSubclass(IrChr):
    """A local IrChr subclass — proves ``_identifier`` normalizes to exact
    ``IrChr`` rather than letting a subclass through."""


def test_spelling_carries_the_exact_irstr_object():
    """An exact ``IrStr`` in comes back as the SAME object — a regression
    that rebuilds it anyway would read as "the carry became a rebuild"."""
    value = IrStr("a")
    assert _spelling(value) is value


def test_spelling_rebuilds_a_plain_str_into_a_new_exact_irstr():
    """A plain ``str`` is not the leaf kind the vocab is keyed on — it has to
    be built, not merely claimed."""
    built = _spelling("a")
    assert built == "a"
    assert built.__class__ is IrStr


def test_spelling_never_lets_an_irstr_subclass_leak_through():
    """An ``IrStr`` SUBCLASS must be rebuilt to the exact class, not carried.

    ``IrScalar``'s type-aware equality makes a subclass instance compare
    UNEQUAL to a plain ``IrStr`` of the same text, so carrying one through
    would silently miss every plain-``IrStr`` vocab lookup — the failure
    mode is "a subclass leaked through", not a raised error.
    """
    subclass_value = _StrSubclass("a")
    built = _spelling(subclass_value)
    assert built is not subclass_value
    assert built.__class__ is IrStr
    assert built == "a"


def test_identifier_carries_the_exact_irchr_object():
    """An exact ``IrChr`` in comes back as the SAME object."""
    value = IrChr(60)
    assert _identifier(value) is value


def test_identifier_rebuilds_a_plain_int_into_a_new_exact_irchr():
    """A plain ``int`` is not the leaf kind ``decode`` is keyed on."""
    built = _identifier(60)
    assert int(built) == 60
    assert built.__class__ is IrChr


def test_identifier_never_lets_an_irchr_subclass_leak_through():
    """Same exactness requirement as ``_spelling``'s, on the id side."""
    subclass_value = _ChrSubclass(60)
    built = _identifier(subclass_value)
    assert built is not subclass_value
    assert built.__class__ is IrChr
    assert int(built) == 60


# ── the leaf-kind trap, pinned as behavior ──────────────────────────────────


def test_an_irmap_keyed_on_irchr_misses_an_irint_probe_of_the_same_ordinal():
    """Distinct leaf kinds never compare equal — ``IrScalar.__eq__`` is
    type-aware by design, so an ``IrChr`` key and an ``IrInt`` probe of the
    identical ordinal do not collide. This is the trap ``_identifier`` exists
    to close before a lookup ever runs."""
    table = IrMap(IrTuple(IrChr(40), IrStr("(")))
    assert table.get(IrInt(40)) is None
    assert table.get(IrChr(40)) == "("


def test_identifier_rebuilds_a_reducers_irint_id_so_spell_hits():
    """A reducer hands vocabulary ids over as ``IrInt``; ``decode`` and
    :meth:`IrTokenizer.spell` key on ``IrChr``. Building a tokenizer from a
    reducer-shaped vocab (``IrStr`` keys, ``IrInt`` ids — exactly what a
    reduced ``tokenizer.json`` document's ``vocab`` section carries) must
    still make every id resolvable: if ``_identifier`` ever stopped
    rebuilding an ``IrInt`` id, ``decode`` would be keyed on ``IrInt`` and
    ``spell()`` would silently fall through to its bracketed-id fallback
    instead of finding the token — a quiet lookup MISS, not a type error."""
    reduced_shaped = IrMap(IrTuple(IrStr("a"), IrInt(0)), IrTuple(IrStr("b"), IrInt(1)))
    tok = IrTokenizer.from_vocab("v", reduced_shaped)
    assert str(tok.spell(0)) == "a"
    assert str(tok.spell(1)) == "b"


# ── key-order stability ─────────────────────────────────────────────────────


def test_vocab_map_iterates_in_canonical_key_sorted_order_for_mixed_input():
    """``IrMap`` is key-ordered by design (key-repr-sorted) — the standing
    product property — so ``_vocab_map`` must not leak whatever order the
    input mapping happened to iterate in."""
    vocab = {"z": 0, "a": 1, "m": 2, "b": 3}
    built = _vocab_map(vocab)
    assert list(built.keys()) == sorted((IrStr(s) for s in vocab), key=repr)
