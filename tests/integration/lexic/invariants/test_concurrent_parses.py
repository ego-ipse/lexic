"""A shared ``CompiledGrammar`` is safe under concurrent parses.

Document-level parallelism — N threads, N documents, one artefact — relies on
the engine's per-parse state (kernel scratch, the intern cache) being
constructed per call, never shared. On a GIL build threads interleave; on a
free-threaded build they genuinely race. The invariant is the same either
way: every concurrently parsed model equals its sequential reference, and
every round-trip is exact.
"""

from __future__ import annotations

import threading

from lexic.compile import compile_text
from lexic.model import GrammarModel

GRAMMAR = """\
root ::= "[" row ("," row)* "]"
row ::= "{" [a-z]+ ":" [0-9]+ "}"
"""

THREADS = 8


def _doc(seed: int, rows: int = 200) -> str:
    key = "key" + "x" * (1 + seed % 3)
    body = ",".join(f"{{{key}:{seed}{k:03d}}}" for k in range(rows))
    return "[" + body + "]"


def _parse_all(texts: list[str]) -> tuple[list[GrammarModel], list[GrammarModel]]:
    """Parse ``texts`` sequentially, then concurrently off one barrier."""
    compiled = compile_text(GRAMMAR)
    reference = [compiled.parse(text) for text in texts]
    out: list[GrammarModel | None] = [None] * len(texts)
    barrier = threading.Barrier(len(texts))

    def run(index: int) -> None:
        barrier.wait()
        out[index] = compiled.parse(texts[index])

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(texts))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(model is not None for model in out)
    return reference, [
        GrammarModel.ensure(model, "test: parsed model") for model in out
    ]


def test_concurrent_distinct_documents_match_sequential():
    """N threads × N distinct documents: models equal, round-trips exact."""
    texts = [_doc(seed) for seed in range(THREADS)]
    reference, concurrent = _parse_all(texts)
    assert concurrent == reference
    for model, text in zip(concurrent, texts):
        assert model.to_text() == text


def test_concurrent_same_document_builds_identical_models():
    """All threads parsing ONE text agree with each other and the reference."""
    texts = [_doc(0)] * THREADS
    reference, concurrent = _parse_all(texts)
    assert all(model == reference[0] for model in concurrent)
