"""``lexic.api.json_tokenizer`` — the ``tokenizer.json`` reader.

The two real-file suites (``test_real_tokenizer*.py``) pin that the loader
reproduces SmolLM2 and gemma reference-exactly. What they cannot cover is
everything the real files happen not to contain: the refusal paths, the
merges form each family does *not* use, and the fact that the json
formulation is a parameter rather than an assumption. That is this module.

Fixtures here are inline miniatures — small, but structurally the real schema.
"""

from __future__ import annotations

import json as _json

import pytest

from lexic.api.json_tokenizer import read, read_from_path, tokenizer_of
from lexic.api.pretokens import (
    QWEN_PATTERN,
    IrByteLevel,
    IrDigits,
    IrQwenSplit,
    IrSplitMerged,
)
from lexic.compile import compile_from_path, parse_reduced
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrChr, IrMap, IrReplace, IrStr, IrUnicodeForm
from tests.paths import GROUND_TRUTH


def json_str(text: str) -> str:
    """``text`` as a json string literal."""
    return _json.dumps(text)


_VOCAB = '{"h": 0, "e": 1, "l": 2, "o": 3, "he": 4, "ll": 5, "hell": 6}'


def _document(
    *,
    model_extra: str = "",
    vocab: str = _VOCAB,
    merges: str = '["h e", "l l", "he ll"]',
    **sections: str,
) -> str:
    """A miniature ``tokenizer.json`` with the given sections spliced in."""
    extra = "".join(f'"{key}": {value}, ' for key, value in sections.items())
    return (
        "{"
        f'{extra}"model": {{"type": "BPE", {model_extra}'
        f'"vocab": {vocab}, "merges": {merges}}}'
        "}"
    )


def _load(text: str):
    """Load a document through the json kit."""
    return read(text, JSON_GRAMMAR, JSON_REDUCER, name="t")


# --- the merges forms ------------------------------------------------------


def test_both_merges_forms_give_the_same_ranks() -> None:
    """``"l r"`` strings and ``[l, r]`` arrays are the same model.

    Each real family uses only one form, so nothing else pins that the two
    agree.
    """
    string_form = _load(_document())
    array_form = _load(_document(merges='[["h","e"], ["l","l"], ["he","ll"]]'))
    assert string_form.ranks == array_form.ranks
    assert string_form.tokenize("hello") == array_form.tokenize("hello") == [6, 3]


def test_array_merges_express_what_string_merges_cannot() -> None:
    """A merge part ending in a space is unambiguous only in the array form.

    ``["a ", "b"]`` spelled as a string is ``"a  b"``, which splits at the
    FIRST space into ``("a", " b")`` — the wrong dyad. That asymmetry is the
    reason to read both forms rather than normalise onto one.
    """
    vocab = '{"a": 0, " ": 1, "b": 2, "a ": 3, "a b": 4}'
    array = _load(_document(vocab=vocab, merges='[["a", " "], ["a ", "b"]]'))
    string = _load(_document(vocab=vocab, merges='["a  ", "a  b"]'))
    assert array.tokenize("a b") == [4]  # both merges fire
    assert string.tokenize("a b") == [3, 2]  # the second mis-splits, so it never fires


def test_a_merge_array_of_the_wrong_arity_refuses() -> None:
    """A three-part merge array is not a dyad."""
    with pytest.raises(UnsupportedConstructError, match="3 parts"):
        _load(_document(merges='[["h","e","l"]]'))


# --- what drives the pipeline ---------------------------------------------


def test_pretokenizer_sequence_is_flattened_in_order() -> None:
    """``Sequence`` nests, and the step order is the document's."""
    tok = _load(
        _document(
            pre_tokenizer='{"type": "Sequence", "pretokenizers": ['
            '{"type": "Digits", "individual_digits": false}, '
            '{"type": "ByteLevel"}]}'
        )
    )
    assert tok.pipeline.pretokens == (IrDigits(False), IrByteLevel())


def test_a_bytelevel_pretokenizer_selects_the_remap() -> None:
    """The byte → working-char remap follows from ByteLevel, not from a flag."""
    plain = _load(_document())
    byte_level = _load(_document(pre_tokenizer='{"type": "ByteLevel"}'))
    assert len(plain.pipeline.remap) == 0
    assert len(byte_level.pipeline.remap) == 256


def test_bytelevel_use_regex_false_contributes_no_split() -> None:
    """``use_regex`` is a real flag, not decoration — and it is READ HERE.

    Families that pre-split with their own pattern set it false and expect a
    byte-level step to contribute the byte MAPPING only; adding this pattern
    on top would corrupt their segmentation. The flag decides whether the
    reader EMITS a split spec at all, so it never reaches an IR node — the
    spine knows nothing of this format's field names. The mapping follows the
    step's presence, decided separately.
    """
    off = _load(_document(pre_tokenizer='{"type": "ByteLevel", "use_regex": false}'))
    on = _load(_document(pre_tokenizer='{"type": "ByteLevel"}'))
    assert off.pipeline.pretokens == ()  # mapping only, no split
    assert on.pipeline.pretokens == (IrByteLevel(),)  # absent ⇒ true
    assert len(off.pipeline.remap) == 256  # remap follows presence, not the flag


def test_a_replace_normalizer_becomes_an_ordered_dyad() -> None:
    """``Replace(pattern.String → content)`` is one replace pass."""
    tok = _load(
        _document(
            normalizer='{"type": "Replace", "pattern": {"String": " "}, "content": "_"}'
        )
    )
    assert tok.pipeline.normalize == (IrReplace(" ", "_"),)


def test_split_merged_with_previous_reads_its_pattern() -> None:
    """The supported ``Split`` behaviour carries the literal separator."""
    tok = _load(
        _document(
            pre_tokenizer='{"type": "Split", "pattern": {"String": "-"}, '
            '"behavior": "MergedWithPrevious"}'
        )
    )
    assert tok.pipeline.pretokens == (IrSplitMerged("-"),)


def test_byte_fallback_supplies_this_formats_byte_spelling() -> None:
    """The flag selects a SPELLING TABLE, not a boolean on the spine.

    How a vocabulary spells a byte token (``<0x41>`` here) is that format's
    convention, so the table is data this module writes and ``lexic.ir``
    merely consults — it must not know any format's spelling.
    """
    on = _load(_document(model_extra='"byte_fallback": true, ')).pipeline
    assert len(on.byte_fallback) == 256
    assert str(on.byte_fallback[IrChr(0x41)]) == "<0x41>"
    assert not _load(
        _document(model_extra='"byte_fallback": false, ')
    ).pipeline.byte_fallback
    assert not _load(_document()).pipeline.byte_fallback  # absent ⇒ off


def test_an_absent_or_null_section_is_simply_empty() -> None:
    """``"normalizer": null`` (smollm2's actual shape) is not a shape error."""
    tok = _load(_document(normalizer="null"))
    assert tok.pipeline.normalize == ()
    assert tok.pipeline.pretokens == ()


# --- added tokens ----------------------------------------------------------


def test_added_tokens_become_specials_and_extend_the_vocab() -> None:
    """An added token absent from ``vocab`` is added at its own id.

    gemma lists its specials only under ``added_tokens``; smollm2 lists them
    in both. Extending only what is missing serves both without a family flag.
    """
    tok = _load(_document(added_tokens='[{"id": 9, "content": "<|end|>"}]'))
    assert tok.pipeline.specials == (IrStr("<|end|>"),)
    assert tok.tokenize("hello<|end|>") == [6, 3, 9]


def test_an_added_token_already_in_the_vocab_keeps_its_vocab_id() -> None:
    """The vocab is authoritative where it covers the spelling."""
    tok = _load(_document(added_tokens='[{"id": 99, "content": "hell"}]'))
    assert tok.tokenize("hell") == [6]


# --- refusals --------------------------------------------------------------


def test_a_model_with_no_declared_type_is_accepted() -> None:
    """``model.type`` is the discriminator, but older files omit it entirely.

    GPT-2's real ``tokenizer.json`` has no ``type`` key at all. Absent means
    UNSPECIFIED, not "not BPE" — refusing it locked out a whole generation of
    real files (found by pointing the loader at a repo outside the fixtures).
    """
    tok = _load('{"model": {' + f'"vocab": {_VOCAB}, "merges": ["h e"]' + "}}")
    assert tok.tokenize("he") == [4]


def test_a_non_bpe_model_refuses() -> None:
    """Only BPE has a spec here; anything else is refused, not approximated."""
    with pytest.raises(UnsupportedConstructError, match="only BPE"):
        _load('{"model": {"type": "Unigram", "vocab": {}, "merges": []}}')


def test_the_cl100k_pattern_is_recognised_by_name() -> None:
    """A regex is never approximated — only patterns implemented by name pass.

    Documents spell this one as ``Split(Regex, Isolated)``; it is the
    pre-tokenizer of essentially every current reasoning model.
    """
    tok = _load(
        _document(
            pre_tokenizer='{"type": "Split", "pattern": {"Regex": '
            + json_str(QWEN_PATTERN)
            + '}, "behavior": "Isolated"}'
        )
    )
    assert tok.pipeline.pretokens == (IrQwenSplit(),)


def test_an_unimplemented_split_regex_refuses() -> None:
    """An unrecognised regex refuses rather than silently mis-segmenting."""
    with pytest.raises(UnsupportedConstructError, match="unimplemented Split regex"):
        _load(
            _document(
                pre_tokenizer='{"type": "Split", "pattern": {"Regex": "\\\\w+"}, '
                '"behavior": "Isolated"}'
            )
        )


def test_a_unicode_form_normalizer_is_read() -> None:
    """``NFC`` / ``NFD`` / ``NFKC`` / ``NFKD`` are normalization forms.

    Dropping one is a WRONG answer, not a partial read — it mis-tokenizes
    every decomposed character, invisible until someone feeds it combining
    marks.
    """
    tok = _load(_document(normalizer='{"type": "NFD"}'))
    assert tok.pipeline.normalize == (IrUnicodeForm("NFD"),)


@pytest.mark.parametrize(
    ("knob", "value"),
    [
        ("end_of_word_suffix", '"</w>"'),
        ("continuing_subword_prefix", '"##"'),
        ("ignore_merges", "true"),
    ],
)
def test_a_model_knob_this_reader_does_not_implement_refuses(knob, value) -> None:
    """Each of these changes the token stream, and each was read past.

    Measured divergences on minimal documents: ``end_of_word_suffix`` [6,7]
    vs [6,3]; ``continuing_subword_prefix`` [7,5,5,6] vs [0,1,2,2,3];
    ``ignore_merges`` [9] vs [6,3]. Every shipped fixture leaves all three at
    a default, which is why ignoring them stayed green.
    """
    with pytest.raises(UnsupportedConstructError, match="does not implement"):
        _load(_document(model_extra=f'"{knob}": {value}, '))


@pytest.mark.parametrize("unset", ["null", '""', "false"])
def test_the_four_spellings_of_unset_are_all_accepted(unset) -> None:
    """ "Not set" is written four ways ACROSS THE SHIPPED FILES, so all pass.

    ``ignore_merges`` is absent on one fixture and ``false`` on the rest; the
    two affix knobs are ``""`` on two and ``null`` on the others. A check
    written as ``is not None`` refuses three of the four real files — the
    exact failure this effort keeps producing: a rule correct in principle
    that rejects valid input.
    """
    tok = _load(_document(model_extra=f'"end_of_word_suffix": {unset}, '))
    assert tok.tokenize("hello") == [6, 3]
    assert _load(_document()).tokenize("hello") == [6, 3]  # absent, the fourth


def test_dropout_is_a_permanent_refusal() -> None:
    """Not a future feature: non-determinism cannot coexist with round-trip.

    It "refused" before only by accident — the json reducer has no float
    leaf, so ``0.5`` failed to parse. ``dropout: 0`` would have sailed
    through.
    """
    with pytest.raises(UnsupportedConstructError, match="does not implement"):
        _load(_document(model_extra='"dropout": 1, '))


@pytest.mark.parametrize("flag", ["lstrip", "rstrip"])
def test_an_added_token_that_moves_a_boundary_refuses(flag) -> None:
    """``lstrip``/``rstrip`` pull adjacent whitespace into the special's span."""
    with pytest.raises(UnsupportedConstructError, match="moves a token boundary"):
        _load(
            _document(added_tokens=f'[{{"id": 9, "content": "<e>", "{flag}": true}}]')
        )


def test_an_unimplemented_normalizer_refuses() -> None:
    """A normalizer with no spec refuses rather than being skipped."""
    with pytest.raises(UnsupportedConstructError, match="unimplemented normalizer"):
        _load(_document(normalizer='{"type": "Precompiled"}'))


def test_an_unsupported_pretokenizer_refuses() -> None:
    """A family with no split spec cannot be silently dropped."""
    with pytest.raises(UnsupportedConstructError, match="Whitespace"):
        _load(_document(pre_tokenizer='{"type": "Whitespace"}'))


def test_a_regex_pattern_refuses() -> None:
    """No spec matches a general regex, so reading it as a literal would lie."""
    with pytest.raises(UnsupportedConstructError, match="unimplemented Split regex"):
        _load(
            _document(
                pre_tokenizer='{"type": "Split", "pattern": {"Regex": "\\\\s+"}, '
                '"behavior": "MergedWithPrevious"}'
            )
        )


def test_an_unsupported_split_behaviour_refuses() -> None:
    """Only the backward-sticking behaviour has a spec."""
    with pytest.raises(UnsupportedConstructError, match="Isolated"):
        _load(
            _document(
                pre_tokenizer='{"type": "Split", "pattern": {"String": " "}, '
                '"behavior": "Isolated"}'
            )
        )


def test_a_document_that_is_not_a_map_refuses() -> None:
    """A valid json document of the wrong shape names what it reduced to."""
    with pytest.raises(UnsupportedConstructError, match="IrTuple, not IrMap"):
        _load("[1, 2, 3]")


def test_a_missing_required_field_names_itself() -> None:
    """The shape readers say which field, not just that something failed."""
    with pytest.raises(UnsupportedConstructError, match="'vocab'"):
        _load('{"model": {"type": "BPE", "merges": []}}')


# --- the formulation is a parameter ---------------------------------------


def test_the_same_document_loads_through_a_ground_truth_json_grammar() -> None:
    """Ruling: the shipped json kit is *a* formulation, never *the* one.

    The loader is handed the grammar+reducer, so a json definition compiled
    from a ground-truth ``.gbnf`` reads the identical document to the
    identical tokenizer — nothing in the loader knows how json is spelled.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    reduced = compiled.grammar
    text = _document(added_tokens='[{"id": 9, "content": "<|end|>"}]')
    theirs = read(text, reduced, JSON_REDUCER, name="t")
    assert theirs.ranks == _load(text).ranks
    assert theirs.tokenize("hello<|end|>") == [6, 3, 9]


def test_the_path_entry_defaults_the_name_to_the_file_stem(tmp_path) -> None:
    """``smollm2.tokenizer.json`` names its tokenizer ``smollm2``."""
    file = tmp_path / "smollm2.tokenizer.json"
    file.write_text(_document(), encoding="utf-8")
    assert str(read_from_path(file, JSON_GRAMMAR, JSON_REDUCER).name) == ("smollm2")


def test_tokenizer_of_needs_no_second_parse() -> None:
    """The seam that justifies a third entry point exists and is used.

    ``read`` parses and builds; ``tokenizer_of`` only builds. Without it a
    caller holding the reduction must re-parse, which for the real files
    costs seconds, not milliseconds. Pinned so the entry is not "simplified"
    away by a future reviewer counting names rather than callers.
    """
    doc = IrMap.ensure(parse_reduced(JSON_GRAMMAR, _document(), JSON_REDUCER))
    from_doc = tokenizer_of(doc, "t")
    from_text = read(_document(), JSON_GRAMMAR, JSON_REDUCER, name="t")
    assert from_doc == from_text
