"""The real SmolLM2 ``tokenizer.json`` through the json reducer + IrTokenizer.

The whole ~2 MB file parses with ``parse_reduced(JSON_GRAMMAR, text,
JSON_REDUCER)`` — the engine's reduce product over the grammar's own kit —
and the typed values feed :class:`~lexic.ir.encoding.IrTokenizer` directly.
stdlib ``json`` appears only as the test-side oracle; the ``tokenizers`` lib
is the reference tokenize oracle. Fixtures are FETCHED, never committed
(``uv run python -m ext.API.hf``); every test skips when the file is absent.
"""

from __future__ import annotations

import json as stdlib_json  # oracle only — never in src

import pytest

from ext.API import cache
from lexic.api.json_tokenizer import tokenizer_of
from lexic.api.pretokens import IrByteLevel, IrDigits
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrInt, IrMap, IrNone, IrStr, IrTokenizer
from lexic.parsing import parse_reduced
from tests.integration.tokenizer_corpus import SHARED_CORPUS

SMOLLM2 = cache.path("smollm2")

pytestmark = pytest.mark.skipif(
    cache.cached("smollm2") is None,
    reason="real tokenizer fixture absent — run 'uv run python -m ext.API.hf'",
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
    """The IrTokenizer the document describes, built by the HF loader."""
    return tokenizer_of(document, "smollm2")


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


def test_pipeline_is_derived_from_the_documents_sections(
    tokenizer: IrTokenizer,
) -> None:
    """The loader READ smollm2's pipeline; nothing here was hand-supplied.

    ``pre_tokenizer`` is ``Sequence[Digits(individual), ByteLevel]`` and
    ``normalizer`` is null, so a correct read gives exactly these two split
    specs in order, the byte-level remap on, no replaces, and no byte
    fallback — a mis-read of any section moves one of them.
    """
    assert tokenizer.pipeline.pretokens == (IrDigits(True), IrByteLevel())
    assert len(tokenizer.pipeline.remap) == 256  # ByteLevel ⇒ the remap is on
    assert tokenizer.pipeline.normalize == ()
    assert not tokenizer.pipeline.byte_fallback


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


@pytest.fixture(scope="module", name="uncovered")
def _uncovered(tokenizer: IrTokenizer) -> tuple[str, ...]:
    """Source characters whose byte this vocabulary has no token for.

    Derived rather than listed, so the cases below follow the fixture. Only
    the ASCII range: a byte above ``0x7F`` never stands alone in utf-8, so no
    single source character produces one.
    """
    return tuple(
        chr(int(byte))
        for byte, working in tokenizer.pipeline.remap.items()
        if int(byte) < 0x80 and IrStr(str(working)) not in tokenizer.encode
    )


def test_this_vocabulary_really_does_lack_some_bytes(uncovered) -> None:
    """Guard the guard: the two cases below are vacuous on a total vocabulary.

    A byte-level vocabulary is not obliged to carry all 256 working
    characters, and this one does not — which is what makes it the fixture
    that exercises the uncovered-symbol path at all.
    """
    assert uncovered


def test_an_uncovered_byte_is_reference_exact(tokenizer, reference, uncovered) -> None:
    """A byte the vocabulary cannot carry still tokenizes exactly.

    Refusing here would reject input the reference accepts; emitting a token
    for it would invent one. The reference drops it, so this must too.
    """
    for char in uncovered:
        for template in ("%s", "a%sb", "%s!", " %s ", "!%s’"):
            text = template % char
            assert tokenizer.tokenize(text) == reference.encode(text).ids, repr(text)


def test_an_uncovered_byte_lets_its_neighbours_merge(
    tokenizer, reference, uncovered
) -> None:
    """Dropping a symbol must leave its neighbours ADJACENT, not merely apart.

    Seeding the merge from what the vocabulary can carry makes ``!`` and
    ``’`` neighbours, so they merge exactly as they would with nothing
    between them. Seeding that keeps the gap open leaves two tokens where the
    reference has one — the same wrong answer as dropping the symbol after
    the merge instead of before it.
    """
    for char in uncovered:
        text = f"!{char}’"
        assert tokenizer.tokenize(text) == tokenizer.tokenize("!’"), repr(text)
        assert tokenizer.tokenize(text) == reference.encode(text).ids, repr(text)
