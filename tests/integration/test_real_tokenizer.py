"""The real SmolLM2 ``tokenizer.json`` through the json reducer + IrTokenizer.

The whole ~2 MB file parses with ``parse_reduced(JSON_GRAMMAR, text,
JSON_REDUCER)`` — the engine's reduce product over the grammar's own kit —
and the typed values feed :class:`~lexic.ir.encoding.IrTokenizer` directly.
stdlib ``json`` appears only as the test-side oracle; the ``tokenizers`` lib
is the reference tokenize oracle. Fixtures are FETCHED, never committed
(``tools/fetch_tokenizers.py``); every test skips when the file is absent.
"""

from __future__ import annotations

import json as stdlib_json  # oracle only — never in src
from pathlib import Path

import pytest

from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.base import IrInt, IrNone, IrStr, IrTuple
from lexic.ir.encoding import (
    BYTE_LEVEL_REMAP,
    IrByteLevel,
    IrDigits,
    IrTokenizer,
    IrTokenPipeline,
)
from lexic.ir.mapping import IrMap
from lexic.parsing import parse_reduced
from tests.integration.tokenizer_corpus import SHARED_CORPUS

SMOLLM2 = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "tokenizers"
    / "smollm2.tokenizer.json"
)

pytestmark = pytest.mark.skipif(
    not SMOLLM2.is_file(),
    reason="real tokenizer fixture absent — run tools/fetch_tokenizers.py",
)


def _de_ir(v: object) -> object:
    """The oracle shim — reduce values to stdlib-json shapes (type-faithful)."""
    if v is IrNone:
        return None
    if isinstance(v, IrMap):
        return {str(k): _de_ir(x) for k, x in v.items()}
    if isinstance(v, tuple) and not isinstance(v, str):
        return [_de_ir(x) for x in v]
    if isinstance(v, IrInt):
        return int(v)
    return str(v)


@pytest.fixture(scope="module", name="text")
def _text() -> str:
    """The raw tokenizer.json document."""
    return SMOLLM2.read_text(encoding="utf-8")


@pytest.fixture(scope="module", name="document")
def _document(text: str) -> IrMap:
    """One reduce of the whole real file."""
    doc = parse_reduced(JSON_GRAMMAR, text, JSON_REDUCER)
    assert isinstance(doc, IrMap)
    return doc


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer(document: IrMap) -> IrTokenizer:
    """The IrTokenizer built straight off the reduction's typed values."""
    model = document[IrStr("model")]
    assert isinstance(model, IrMap)
    merges: list[tuple[str, str]] = []
    for entry in model[IrStr("merges")]:
        left, _, right = str(entry).partition(" ")
        merges.append((left, right))
    specials = [str(t[IrStr("content")]) for t in document[IrStr("added_tokens")]]
    pipeline = IrTokenPipeline(
        IrTuple(*(IrStr(s) for s in specials)),
        BYTE_LEVEL_REMAP,
        IrTuple(),
        IrTuple(IrDigits(True), IrByteLevel()),
        False,
    )
    return IrTokenizer.from_merges(
        "smollm2", model[IrStr("vocab")], merges, pipeline=pipeline
    )


@pytest.fixture(scope="module", name="reference")
def _reference():
    """The ``tokenizers`` reference oracle over the same file."""
    lib = pytest.importorskip("tokenizers")
    return lib.Tokenizer.from_file(str(SMOLLM2))


def test_reducer_matches_stdlib_on_whole_file(document: IrMap, text: str) -> None:
    """The json reducer equals stdlib json on the ENTIRE real document."""
    assert _de_ir(document) == stdlib_json.loads(text)


def test_model_type_is_bpe(document: IrMap) -> None:
    """The reduction reads model.type directly."""
    model = document[IrStr("model")]
    assert isinstance(model, IrMap)
    assert str(model[IrStr("type")]) == "BPE"


def test_real_model_sizes(tokenizer: IrTokenizer) -> None:
    """The extraction carries the real vocab / merges / specials counts."""
    assert (len(tokenizer.encode), len(tokenizer.ranks), len(tokenizer.specials)) == (
        49152,
        48900,
        17,
    )


def test_space_free_bpe_matches_reference(tokenizer, reference) -> None:
    """Space-free BPE content tokenizes reference-exact."""
    assert tokenizer.tokenize("Hello") == reference.encode("Hello").ids


def test_specials_path_matches_reference(tokenizer, reference) -> None:
    """A special amid content is one atomic token, reference-exact."""
    text = "<|im_start|>hi"
    assert tokenizer.tokenize(text) == reference.encode(text).ids


def test_byte_level_matches_reference(tokenizer, reference) -> None:
    """The full pipeline closes the byte-level gap — spacey text is exact."""
    text = "Hello world"
    assert tokenizer.tokenize(text) == reference.encode(text).ids


_CORPUS = SHARED_CORPUS + (
    "Hello",
    "line1\n\nline2",
    "CamelCase snake_case",
    "3.14 * r**2",
    "",
    " ",
    "\n",
    'quote "inside" it',
)


def test_curated_corpus_is_reference_exact(tokenizer, reference) -> None:
    """Every curated case tokenizes reference-exact (the headline gate)."""
    for case in _CORPUS:
        assert tokenizer.tokenize(case) == reference.encode(case).ids, repr(case)
