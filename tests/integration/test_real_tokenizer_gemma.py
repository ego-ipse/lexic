"""gemma-4 through the json reducer + the full pipeline — the SLOW lane.

The 31 MB ``tokenizer.json`` reduce takes ~75 s, so this module is opt-in:
set ``LEXIC_SLOW=1`` (and fetch the fixture — ``uv run python -m ext.API.hf``).
It pins the second real family end to end: arrays-form merges, the
``Replace`` normalizer, ``Split(MergedWithPrevious)``, ``byte_fallback``,
added-token vocab extension — reference-exact against the ``tokenizers``
oracle (``add_special_tokens=False``; the ``<bos>`` template is
post-processing, outside segmentation).
"""

from __future__ import annotations

import os

import pytest

from ext.API import cache
from lexic.api.json_tokenizer import read_from_path
from lexic.api.pretokens import IrSplitMerged
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.encoding import IrReplace, IrTokenizer
from tests.integration.tokenizer_corpus import SHARED_CORPUS

GEMMA = cache.path("gemma4")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("LEXIC_SLOW") and cache.cached("gemma4")),
    reason="slow lane — set LEXIC_SLOW=1 and run 'uv run python -m ext.API.hf'",
)

_CORPUS = SHARED_CORPUS + ("\x07bell",)


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer() -> IrTokenizer:
    """The gemma tokenizer off one whole-file reduce, read from the document."""
    return read_from_path(GEMMA, JSON_GRAMMAR, JSON_REDUCER)


@pytest.fixture(scope="module", name="reference")
def _reference():
    """The ``tokenizers`` reference oracle over the same file."""
    lib = pytest.importorskip("tokenizers")
    return lib.Tokenizer.from_file(str(GEMMA))


def test_pipeline_is_derived_from_the_documents_sections(
    tokenizer: IrTokenizer,
) -> None:
    """The loader READ gemma's pipeline — a shape disjoint from smollm2's.

    ``normalizer`` is ``Replace(" " → "▁")``, ``pre_tokenizer`` is
    ``Split(" ", MergedWithPrevious)``, ``model.byte_fallback`` is true, and
    there is no ByteLevel anywhere — so every field lands opposite to the
    other family's. Two disjoint reads off the same code is what makes the
    derivation real rather than a fit to one file.
    """
    assert tokenizer.pipeline.normalize == (IrReplace(" ", "▁"),)
    assert tokenizer.pipeline.pretokens == (IrSplitMerged(" "),)
    assert tokenizer.pipeline.byte_fallback
    assert len(tokenizer.pipeline.remap) == 0  # no ByteLevel ⇒ no remap


def test_real_model_sizes(tokenizer: IrTokenizer) -> None:
    """The extraction carries gemma's real vocab / merges / specials counts."""
    assert (len(tokenizer.encode), len(tokenizer.ranks), len(tokenizer.specials)) == (
        262145,
        514906,
        6415,
    )


def test_curated_corpus_is_reference_exact(tokenizer, reference) -> None:
    """Every curated case tokenizes reference-exact (byte_fallback included)."""
    for case in _CORPUS:
        ours = tokenizer.tokenize(case)
        theirs = reference.encode(case, add_special_tokens=False).ids
        assert ours == theirs, repr(case)
