"""A bracket arm that captures a value between its delimiters and its run.

The merged node is a stand-in's with the region's items overlaid. An arm like
``"(" [ ]* list [ ]* ")"`` captures its spaces in slots of its own, so the plan
lays them back as edges: the spaces before the run from the first piece and
those after it from the last, whose text there is the document's. That needs
the capture to be able to vanish (a middle piece has none) and its alphabet to
miss the run's; a capture failing either declines, and the parse is the
sequential one at every worker count.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.stitch.plan import derive_plan
from tests.split_helpers import assert_parallel_matches_sequential, engages

LIST = 'list ::= item ("," item)*\nitem ::= [a-z]+\n'
SPACED = 'root ::= "(" [ ]* list [ ]* ")"\n' + LIST
DIRECT = 'root ::= "(" [ ]* item ("," item)* [ ]* ")"\nitem ::= [a-z]+\n'
"""The run held by the bracket arm itself, its captures beside it."""
BEFORE = 'root ::= "(" [ ]* list ")"\n' + LIST
AFTER = 'root ::= "(" list [ ]* ")"\n' + LIST
HELD = 'root ::= "{" block ("," block)* "}"\nblock ::= "(" [ ]* list [ ]* ")"\n' + LIST
"""Captured regions inside a holder's run: each laid back into its stand-in."""
_CORES = (2, 8, 16)


def _items(rng: random.Random, n: int) -> str:
    return ",".join("abcdefgh"[: rng.randrange(1, 9)] for _ in range(n))


def _group(rng: random.Random, n: int, before: int, after: int) -> str:
    return "(" + " " * before + _items(rng, n) + " " * after + ")"


def _documents() -> list[tuple[str, str, str]]:
    """``(id, grammar, document)``: item lengths drawn so the cuts land at
    different items, and every pair of 0, 1 and 3 spaces either side."""
    rng, out = random.Random(2202), []
    for before, after in ((0, 0), (1, 3), (3, 1), (3, 0), (0, 1)):
        tag = f"{before}{after}"
        out.append((f"spaced-{tag}", SPACED, _group(rng, 8000, before, after)))
        out.append((f"direct-{tag}", DIRECT, _group(rng, 8000, before, after)))
        out.append((f"before-{tag}", BEFORE, _group(rng, 8000, before, 0)))
        out.append((f"after-{tag}", AFTER, _group(rng, 8000, 0, after)))
        blocks = ",".join(_group(rng, 2000, before, after) for _ in range(4))
        out.append((f"held-{tag}", HELD, "{" + blocks + "}"))
    return out


DOCUMENTS = _documents()


@pytest.mark.parametrize("cores", _CORES)
@pytest.mark.parametrize(
    ("source", "text"), [d[1:] for d in DOCUMENTS], ids=[d[0] for d in DOCUMENTS]
)
def test_captured_spaces_survive_a_parallel_parse(
    source: str, text: str, cores: int
) -> None:
    """The region divides, and the spaces it captures are the document's."""
    compiled = compile_text(source, cache_key=f"captured-{hash(source)}")
    assert engages(compiled, text, cores), f"at {cores}: the region declined"
    assert_parallel_matches_sequential(compiled, text, cores)


def test_the_plan_lays_each_capture_back_from_its_side() -> None:
    """Slot 0, before the list, from the first piece; slot 2 from the last."""
    compiled = compile_text(SPACED, cache_key="captured-edges")
    plan = derive_plan(compiled.codegen_grammar, compiled.product, "root")
    assert plan is not None and plan.edges == ((0, True), (2, False))


REFUSED = {
    "required": 'root ::= "(" [ ]+ list [ ]* ")"\n' + LIST,
    "shares-the-run": 'root ::= "(" [ ,]* list ")"\n' + LIST,
}
"""A capture a middle piece cannot do without, and one spelling a character the
run spells, so a piece's shorter text could carve them apart differently."""


@pytest.mark.parametrize("shape", sorted(REFUSED))
def test_a_capture_the_pieces_cannot_restore_declines(shape: str) -> None:
    """No plan binds, and the parse is the sequential one at every count."""
    compiled = compile_text(REFUSED[shape], cache_key=f"refused-{shape}")
    assert derive_plan(compiled.codegen_grammar, compiled.product, "root") is None
    text = "( ," + _items(random.Random(7), 8000) + ")"
    if shape == "required":
        text = "( " + text[3:]
    for cores in _CORES:
        assert not engages(compiled, text, cores)
        assert_parallel_matches_sequential(compiled, text, cores)
