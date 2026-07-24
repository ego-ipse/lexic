"""gemma-4 through the json reducer + the full pipeline — the SLOW lane.

The 31 MB ``tokenizer.json`` reduce takes ~75 s, so this module is opt-in:
set ``LEXIC_SLOW=1`` (and fetch the fixture — ``tools/fetch_tokenizers.sh``).
It pins the second real family end to end: arrays-form merges, the
``Replace`` normalizer, ``Split(MergedWithPrevious)``, ``byte_fallback``,
added-token vocab extension — reference-exact against the ``tokenizers``
oracle (``add_special_tokens=False``; the ``<bos>`` template is
post-processing, outside segmentation).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.encoding import IrSplitMerged, IrTokenizer, IrTokenPipeline
from lexic.ir.mapping import IrMap
from lexic.parsing import parse_reduced
from tests.integration.tokenizer_corpus import SHARED_CORPUS

GEMMA = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "tokenizers"
    / "gemma4.tokenizer.json"
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("LEXIC_SLOW") and GEMMA.is_file()),
    reason="slow lane — set LEXIC_SLOW=1 and run tools/fetch_tokenizers.sh",
)

_CORPUS = SHARED_CORPUS + ("\x07bell",)


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer() -> IrTokenizer:
    """The gemma tokenizer off one whole-file reduce."""
    doc = parse_reduced(JSON_GRAMMAR, GEMMA.read_text(encoding="utf-8"), JSON_REDUCER)
    assert isinstance(doc, IrMap)
    model = doc[IrStr("model")]
    assert isinstance(model, IrMap)
    vocab = {str(k): int(v) for k, v in model[IrStr("vocab")].items()}
    for token in doc[IrStr("added_tokens")]:
        content = str(token[IrStr("content")])
        if content not in vocab:
            vocab[content] = int(token[IrStr("id")])
    merges: list[tuple[str, str]] = []
    for entry in model[IrStr("merges")]:
        if isinstance(entry, tuple) and not isinstance(entry, str):
            merges.append((str(entry[0]), str(entry[1])))
        else:
            left, _, right = str(entry).partition(" ")
            merges.append((left, right))
    pipeline = IrTokenPipeline(
        IrTuple(*(t[IrStr("content")] for t in doc[IrStr("added_tokens")])),
        IrMap(),
        IrTuple(IrTuple(IrStr(" "), IrStr("▁"))),
        IrTuple(IrSplitMerged(" ")),
        True,
    )
    return IrTokenizer.from_merges("gemma4", vocab, merges, pipeline=pipeline)


@pytest.fixture(scope="module", name="reference")
def _reference():
    """The ``tokenizers`` reference oracle over the same file."""
    lib = pytest.importorskip("tokenizers")
    return lib.Tokenizer.from_file(str(GEMMA))


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
