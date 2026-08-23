"""Tests for lexic.ir.text.pipeline — normalizers, pretokens, and their order.

Real-tokenizer coverage of the assembled pipeline lives in
``tests/integration/lexic/tokens/``; this file targets the pipeline's own
pieces: ``identity_meta``, ``IrReplace``, and ``IrUnicodeForm``.
"""

from __future__ import annotations

import unicodedata

from lexic.ir.text.pipeline import (
    IrReplace,
    IrTokenPipeline,
    IrUnicodeForm,
    IrUnknown,
    identity_meta,
)


def test_identity_meta_gives_every_char_its_own_aligned_span():
    """No pipeline: each char is its own one-wide, self-starting span."""
    assert identity_meta(0, 3) == [(0, 1, True), (1, 2, True), (2, 3, True)]


def test_identity_meta_offsets_by_the_given_base():
    """A non-zero base shifts every span by that amount."""
    assert identity_meta(5, 2) == [(5, 6, True), (6, 7, True)]


def test_ir_replace_rewrites_every_occurrence():
    """Every match of ``src`` becomes ``dst``, spans included."""
    text, meta = IrReplace("ab", "X").apply("abcab", identity_meta(0, 5))
    assert text == "XcX"
    assert len(meta) == 3


def test_ir_replace_shares_the_matched_span_across_a_multi_char_replacement():
    """Every output char from one match shares that match's source span, with
    only the first one flagged as the span's start."""
    text, meta = IrReplace("a", "xyz").apply("a", identity_meta(0, 1))
    assert text == "xyz"
    assert meta == [(0, 1, True), (0, 1, False), (0, 1, False)]


def test_ir_replace_leaves_unmatched_text_untouched():
    """Text and meta pass through unchanged when the source never matches."""
    text, meta = IrReplace("z", "X").apply("abc", identity_meta(0, 3))
    assert text == "abc"
    assert meta == identity_meta(0, 3)


def test_ir_unicode_form_composes_a_starter_and_combining_mark():
    """NFC composes ``e`` + combining acute into the single precomposed
    character, per the module's own normalization contract."""
    decomposed = "é"  # 'e' + combining acute accent
    text, meta = IrUnicodeForm("NFC").apply(decomposed, identity_meta(0, 2))
    assert text == unicodedata.normalize("NFC", decomposed)
    assert len(meta) == len(text)


def test_ir_unicode_form_defaults_to_nfc():
    """``IrUnicodeForm()``'s default form is NFC."""
    assert IrUnicodeForm().form == "NFC"


def test_ir_unknown_defaults_to_no_fallback_and_no_fusion():
    """A default IrUnknown has no fallback spelling and never fuses."""
    unknown = IrUnknown()
    assert unknown.spelling == ""
    assert unknown.fuse is False


def test_ir_token_pipeline_defaults_are_all_empty():
    """A default IrTokenPipeline is plain text in, ranked-merge-free out."""
    pipeline = IrTokenPipeline()
    assert not pipeline.specials
    assert not pipeline.normalize
    assert not pipeline.pretokens
    assert pipeline.unknown == IrUnknown()
