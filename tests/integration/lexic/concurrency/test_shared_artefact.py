"""One artefact, many threads — and many artefacts, many threads.

Document-level parallelism relies on the engine's per-parse state (kernel
scratch, the intern cache, every cursor) being constructed per call and never
shared. On a GIL build threads interleave; on a free-threaded build they
genuinely race. The invariant is the same either way: every concurrently
parsed model equals its sequential reference field for field, and every
round-trip is exact.

Each thread's document encodes its own index, so a leak between threads is
detectable BY VALUE rather than by count — a torn model is a wrong string,
not merely a wrong length. Two grammars are used deliberately. The first never
splits, so it tests the sequential path under thread pressure. The second
does, so each already-concurrent thread takes a pool lease of its own and the
contention on the warm-pool cache is real rather than hypothetical.
"""

from __future__ import annotations

from functools import partial

import pytest

from lexic.compile import CompiledGrammar, compile_text
from lexic.model import GrammarModel
from tests.integration.lexic.concurrency.concurrency import clean, parallel
from tests.integration.lexic.concurrency.fixtures import (
    FLAT,
    SPLITTING,
    engages,
    flat_doc,
    split_doc,
)

WIDTHS = (2, 4, 8, 16)
"""Thread counts every sweep runs at — two is the smallest race, sixteen is
this machine's worker ceiling, so the pool cache is contended at the top."""


def _parse(
    index: int, compiled: CompiledGrammar, texts: list[str], cores: int
) -> GrammarModel:
    """Parse this worker's own document off the shared artefact."""
    return compiled.parse(texts[index], cores=cores)


def _compile_and_parse(index: int, source: str) -> str:
    """Compile a per-worker grammar and parse a per-worker document with it.

    Each worker gets its own ``cache_key``, so the artefact is genuinely
    distinct rather than a memo hit — which is what makes this a test of
    concurrent INSERTION into the identity memos.
    """
    compiled = compile_text(source, cache_key=f"concurrency-distinct-{index}")
    text = flat_doc(index)
    return compiled.parse(text).to_text()


@pytest.mark.parametrize("width", WIDTHS)
def test_concurrent_distinct_documents_match_sequential(width: int) -> None:
    """N threads × N distinct documents: models equal, round-trips exact."""
    compiled = compile_text(FLAT, cache_key="concurrency-flat")
    texts = [flat_doc(seed) for seed in range(width)]
    reference = [compiled.parse(text) for text in texts]
    models = clean(
        parallel(partial(_parse, compiled=compiled, texts=texts, cores=1), width)
    )
    assert models == reference
    for model, text in zip(models, texts):
        assert model.to_text() == text


@pytest.mark.parametrize("width", WIDTHS)
def test_concurrent_parses_of_one_document_agree_with_each_other(width: int) -> None:
    """All threads parsing ONE text agree with each other and the reference."""
    compiled = compile_text(FLAT, cache_key="concurrency-flat")
    texts = [flat_doc(0)] * width
    reference = compiled.parse(texts[0])
    models = clean(
        parallel(partial(_parse, compiled=compiled, texts=texts, cores=1), width)
    )
    assert all(model == reference for model in models)


def test_concurrent_parses_of_one_document_round_trip_byte_identical() -> None:
    """Two threads racing the SAME ``str`` object still round-trip exactly.

    The engine's per-thread document copy (the product entries' private
    ``_owned_text``) is what makes a shared document safe under free
    threading. If it ever degraded to one of the no-op idioms CPython
    shortcuts for an exact ``str`` — pinned directly in
    ``tests/unit/lexic/parsing/test_products.py`` — this is the behavioural
    surface where a torn parse would show up: not a wrong model, but a
    ``to_text()`` that no longer equals the input.
    """
    compiled = compile_text(FLAT, cache_key="concurrency-flat")
    text = flat_doc(0)
    reference = compiled.parse(text)
    models = clean(
        parallel(partial(_parse, compiled=compiled, texts=[text, text], cores=1), 2)
    )
    assert all(model == reference for model in models)
    assert all(model.to_text() == text for model in models)


def test_concurrent_split_parses_on_one_artefact_stay_exact() -> None:
    """Threads whose own parses split: pool leases contended, models exact.

    The outer threads race for warm pools while the inner split threads do the
    parsing, which is the shape a service under load actually runs.
    """
    width = 4
    compiled = compile_text(SPLITTING, cache_key="concurrency-nested")
    texts = [split_doc(seed) for seed in range(width)]
    assert engages(compiled, texts[0]), "the split declined — this proves nothing"
    reference = [compiled.parse(text, cores=1) for text in texts]
    models = clean(
        parallel(partial(_parse, compiled=compiled, texts=texts, cores=4), width)
    )
    assert models == reference
    for model, text in zip(models, texts):
        assert model.to_text() == text


@pytest.mark.parametrize("width", (4, 16))
def test_threads_compiling_distinct_grammars_do_not_interfere(width: int) -> None:
    """Concurrent COMPILATION as well as parsing — distinct memo keys.

    Every worker mints its own artefact, so the identity memos take concurrent
    insertions under keys that never collide. A lost write shows up as a wrong
    round-trip, not as a cache miss.
    """
    texts = clean(parallel(partial(_compile_and_parse, source=FLAT), width))
    assert texts == [flat_doc(index) for index in range(width)]
