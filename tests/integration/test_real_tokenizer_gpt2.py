"""GPT-2 through the json reducer + IrTokenizer — the fourth real family.

Small (1.3 MB, ~8 s), so this one runs in the DEFAULT lane rather than
behind ``LEXIC_SLOW``. It carries three properties no other fixture has, each
of which is load-bearing somewhere:

- **no ``model.type``.** Older documents omit the discriminator entirely.
  Refusing an absent one locked out a whole generation of real files.
- **a bare ``ByteLevel`` pre-tokenizer**, with no ``Digits`` beside it —
  smollm2 pairs the two, so this is the only file that pins ByteLevel alone.
- **``normalized: true`` on an added token, with a NULL normalizer.** That
  combination is the reason the added-token rule must be conditional: an
  unconditional refusal of ``normalized`` would reject this file, while the
  flag is inert here because there is nothing to normalize.

It was verified by hand when the reader was written and then left ungated,
while "four vocabularies stay reference-exact" was asserted in commit
messages and a plan's regression gate. This file is that claim's gate.
"""

from __future__ import annotations

import json as stdlib_json

import pytest

from ext.API import cache
from lexic.api.json_tokenizer import read_from_path
from lexic.api.pretokens import IrByteLevel
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.encoding import IrTokenizer
from tests.integration.tokenizer_corpus import SHARED_CORPUS

GPT2 = cache.path("gpt2")

pytestmark = pytest.mark.skipif(
    cache.cached("gpt2") is None,
    reason="fixture absent — run 'uv run python -m ext.API.hf'",
)

_CORPUS = SHARED_CORPUS + (
    "Hello",
    "def f(x): return x",
    "3.14 * r**2",
    "line1\n\nline2",
    "CamelCase snake_case",
    'quote "inside" it',
)


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer() -> IrTokenizer:
    """The GPT-2 tokenizer off one whole-file reduce."""
    return read_from_path(GPT2, JSON_GRAMMAR, JSON_REDUCER)


@pytest.fixture(scope="module", name="reference")
def _reference():
    """The ``tokenizers`` reference oracle over the same file."""
    lib = pytest.importorskip("tokenizers")
    return lib.Tokenizer.from_file(str(GPT2))


def test_the_document_declares_no_model_type() -> None:
    """The property this fixture exists to pin — verified on the FILE.

    ``model.type`` is the discriminator, and this document omits it. Reading
    it as "not BPE" refused every file of this generation; absent means
    UNSPECIFIED. stdlib json is the oracle for the document's own shape.
    """
    document = stdlib_json.loads(GPT2.read_text(encoding="utf-8"))
    assert "type" not in document["model"]
    assert document.get("normalizer") is None
    assert any(t.get("normalized") for t in document.get("added_tokens", []))


def test_pipeline_is_derived_from_the_documents_sections(
    tokenizer: IrTokenizer,
) -> None:
    """A bare ByteLevel — the only fixture that pins it without ``Digits``."""
    assert tokenizer.pipeline.pretokens == (IrByteLevel(),)
    assert len(tokenizer.pipeline.remap) == 256
    assert tokenizer.pipeline.normalize == ()
    assert not tokenizer.pipeline.byte_fallback


def test_real_model_sizes(tokenizer: IrTokenizer) -> None:
    """The extraction carries GPT-2's real vocab / merges / specials counts."""
    assert (len(tokenizer.encode), len(tokenizer.ranks), len(tokenizer.specials)) == (
        50257,
        50000,
        1,
    )


def test_curated_corpus_is_reference_exact(tokenizer, reference) -> None:
    """Every curated case tokenizes reference-exact (the headline gate)."""
    for case in _CORPUS:
        assert tokenizer.tokenize(case) == reference.encode(case).ids, repr(case)
