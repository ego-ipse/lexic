"""Qwen3 through the json reducer + the full pipeline — the SLOW lane.

The third real family, and the one that exercises the pipeline shapes the
other two do not: the **Qwen** pre-token pattern (spelled as
``Split(Regex, Isolated)``), a **Unicode-form normalizer** (``NFC``), and a
``ByteLevel`` step declaring ``use_regex: false`` — i.e. "byte mapping only,
no split of my own", because the pattern already did the splitting.

Each of those was a silent defect before this file existed: the regex Split
refused outright, the ``NFC`` step was dropped (mis-tokenizing every
decomposed character), and the ``use_regex`` flag was ignored.

The ~11 MB reduce takes ~30 s, so this is opt-in: set ``LEXIC_SLOW=1`` and
fetch the fixture (``uv run python -m ext.API.hf``). The pattern's own
matching logic is pinned fast and fixture-free in
``tests/unit/lexic/api/test_pretokens.py``; this module pins that the whole
read is reference-exact.
"""

from __future__ import annotations

import os
import unicodedata

import pytest

from ext.API import cache
from lexic.api.json_tokenizer import read_from_path
from lexic.api.pretokens import IrQwenSplit
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.encoding import IrTokenizer, IrUnicodeForm
from tests.integration.tokenizer_corpus import SHARED_CORPUS

QWEN = cache.path("qwen3")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("LEXIC_SLOW") and cache.cached("qwen3")),
    reason="slow lane — set LEXIC_SLOW=1 and run 'uv run python -m ext.API.hf'",
)

_DECOMPOSED = (
    "éclair",
    "Å",
    unicodedata.normalize("NFD", "éàü café"),
    unicodedata.normalize("NFD", "q̇ụ"),
)
"""Inputs whose tokenization differs if the NFC normalizer is skipped — the
cases that were silently wrong while the step was being dropped."""

_CORPUS = SHARED_CORPUS + _DECOMPOSED + ("<think>reason</think>answer", "3.14*r**2")


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer() -> IrTokenizer:
    """The Qwen3 tokenizer off one whole-file reduce."""
    return read_from_path(QWEN, JSON_GRAMMAR, JSON_REDUCER)


@pytest.fixture(scope="module", name="reference")
def _reference():
    """The ``tokenizers`` reference oracle over the same file."""
    lib = pytest.importorskip("tokenizers")
    return lib.Tokenizer.from_file(str(QWEN))


def test_pipeline_is_derived_from_the_documents_sections(
    tokenizer: IrTokenizer,
) -> None:
    """The loader READ this family's pipeline — a third distinct shape.

    Qwen pre-split, NFC normalize, and a byte remap that is on despite the
    ByteLevel step contributing no split of its own. Nothing here overlaps
    smollm2's or gemma's shape, which is what makes the derivation general
    rather than fitted.
    """
    assert tokenizer.pipeline.pretokens == (IrQwenSplit(),)
    assert tokenizer.pipeline.normalize == (IrUnicodeForm("NFC"),)
    assert len(tokenizer.pipeline.remap) == 256  # ByteLevel present ⇒ remap on
    assert not tokenizer.pipeline.byte_fallback


def test_the_think_tokens_are_single_tokens(tokenizer: IrTokenizer) -> None:
    """``<think>`` / ``</think>`` are one id each — what ``think.gbnf`` needs.

    Neither smollm2, gpt2 nor gemma carries them; a token grammar over them
    is only demonstrable against a vocabulary like this one.
    """
    assert len(tokenizer.tokenize("<think>")) == 1
    assert len(tokenizer.tokenize("</think>")) == 1


def test_real_model_sizes(tokenizer: IrTokenizer) -> None:
    """The extraction carries Qwen3's real vocab / merges / specials counts."""
    assert (len(tokenizer.encode), len(tokenizer.ranks), len(tokenizer.specials)) == (
        151669,
        151387,
        26,
    )


def test_decomposed_text_is_reference_exact(tokenizer, reference) -> None:
    """The NFC normalizer is honoured — the headline regression guard.

    Dropping it produced confident, wrong ids (``éclair`` → 3 tokens instead
    of 2) rather than an error, so this is the case that must never silently
    pass again.
    """
    for case in _DECOMPOSED:
        assert tokenizer.tokenize(case) == reference.encode(case).ids, repr(case)


def test_curated_corpus_is_reference_exact(tokenizer, reference) -> None:
    """Every curated case tokenizes reference-exact (the headline gate)."""
    for case in _CORPUS:
        assert tokenizer.tokenize(case) == reference.encode(case).ids, repr(case)
