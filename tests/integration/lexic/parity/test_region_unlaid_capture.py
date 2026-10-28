"""A bracket arm that captures a value the region stitch never lays back.

The merged node is a stand-in's with the region's items overlaid, and only the
wrapper references beside the run take their values from the pieces. An arm
like ``"(" [ ]* list [ ]* ")"`` captures its spaces in slots of its own: divided,
the result kept the stand-in's (none) and lost the document's. Such a plan
declines, so the parse is the sequential one at every worker count.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.stitch.plan import derive_plan
from tests.split_helpers import assert_parallel_matches_sequential

SPACED = 'root ::= "(" [ ]* list [ ]* ")"\nlist ::= item ("," item)*\nitem ::= [a-z]+\n'


def _document(spaces: int) -> str:
    items = ",".join("abcdefgh"[: k % 8 + 1] for k in range(8000))
    return "(" + " " * spaces + items + " " * spaces + ")"


@pytest.mark.parametrize("cores", (2, 8, 16))
@pytest.mark.parametrize("spaces", (0, 1, 3))
def test_captured_wrapper_spaces_survive_a_parallel_parse(
    spaces: int, cores: int
) -> None:
    """The spaces the arm captures are the document's, at every worker count."""
    compiled = compile_text(SPACED, cache_key="unlaid-spaces")
    assert_parallel_matches_sequential(compiled, _document(spaces), cores)


def test_a_plan_with_an_unlaid_capture_declines() -> None:
    """No region plan binds an arm whose captures the stitch cannot restore."""
    compiled = compile_text(SPACED, cache_key="unlaid-plan")
    assert derive_plan(compiled.codegen_grammar, compiled.product, "root") is None
