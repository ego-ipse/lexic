"""Encoding family — the codec that gives a char class's ordinals meaning."""

from __future__ import annotations

from lexic.ir.base import IrAtom, IrNode, IrNone, IrStr, IrTuple
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
