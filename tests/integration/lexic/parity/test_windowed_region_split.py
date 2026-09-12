"""The orchestrator's windowed find round-trips exactly.

``_split_regions`` (``orchestrate.py``) calls ``par_find``, not the serial
``find``, so a document over the split floor divides through the windowed
walk end to end. The public seam is ``compiled.parse``, and the only
acceptable evidence is :func:`assert_parallel_matches_sequential` — the split
answer IS the sequential one, byte for byte.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.policy import MIN_CHUNK
from tests.split_helpers import assert_parallel_matches_sequential, engages

SOURCE = 'root ::= arr\narr ::= "[" item ("," item)* "]"\nitem ::= [a-z0-9]+\n'
"""A flat, skip-free bracket grammar — no opaque interior, so the split
takes the windowed find rather than the serial fallback."""


def _document(count: int) -> str:
    """One long array, comfortably clearing the split floor."""
    return "[" + ",".join(f"item{i:05d}" for i in range(count)) + "]"


DOCUMENT = _document(2000)


def test_a_windowed_split_matches_the_sequential_parse() -> None:
    """Over the floor, several worker counts, exact model and round-tripped text."""
    compiled = compile_text(SOURCE, cache_key="test-windowed-orchestrator-roundtrip")
    assert len(DOCUMENT) > 2 * MIN_CHUNK, "the fixture must clear the split floor"
    assert engages(compiled, DOCUMENT), "the split must actually engage, not decline"
    for workers in (2, 4, 8):
        assert_parallel_matches_sequential(compiled, DOCUMENT, workers)
