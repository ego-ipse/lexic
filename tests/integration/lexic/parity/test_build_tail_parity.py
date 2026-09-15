"""PDA/Earley parity, pinned specifically to the composed build tail.

`test_pda_parity.py` already holds both engines to raw model equality across
the whole ground-truth corpus (`test_both_engines_build_the_same_model_not_
just_the_same_meaning`) — this module does not widen that bar. It exists as a
narrow, fast regression directly tied to the record build tail
(`lexic.parsing.pda.compiler.program.lowering`): every sequence record either engine
builds from these three grammars now passes through `shape_build`'s composed
callable rather than the generic per-field dispatcher it replaced, so a wrong
bind on any field mode reaches here on the very first mismatching sample.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_from_path
from lexic.generate import generate
from lexic.parsing import parse_model
from lexic.parsing.parallel import split_model, split_plan
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail, pda_model
from tests.integration.lexic.parity.pda_parity_helpers import forced_engine, grammar_for
from tests.paths import GROUND_TRUTH
from tests.split_helpers import assert_parallel_matches_sequential
from tests.unit.lexic.parsing.parsing_helpers import prod

STEMS: tuple[str, ...] = ("arithmetic.gbnf", "json.gbnf", "markdown.gbnf")
N_SEEDS = 30
MAX_DEPTH = 4


@pytest.mark.parametrize("stem", STEMS)
def test_build_tail_records_agree_with_the_engine_and_round_trip(stem: str) -> None:
    """Raw model equality plus a `to_text()` round-trip, both engines, three
    ground-truth grammars — checked count asserted so a vacuous run fails."""
    cg, specs, start = grammar_for(stem)
    checked = 0
    for seed in range(N_SEEDS):
        text = generate(start, specs, rng=random.Random(seed), max_depth=MAX_DEPTH)
        if not text:
            continue
        want = forced_engine(cg, text)
        try:
            got = pda_model(prod(cg).pda, text, cg.executor)
        except PdaFail:
            continue
        checked += 1
        assert repr(got) == repr(want), f"{stem} seed={seed} text={text!r}"
        assert got.to_text() == want.to_text() == text
    assert checked >= N_SEEDS // 2, f"{stem}: too few samples actually checked"


# ── the MT path builds through the same tail, per worker ──────────────────


def _markdown_document(blocks: int) -> str:
    """A markdown document of repeated headings/bullets/paragraphs, well
    over the 2 KiB per-worker split floor at the block counts used below."""
    lines = []
    for i in range(blocks):
        lines.append(f"# heading {i} with `code{i}` and *em{i}*\n")
        lines.append(f"- bullet {i} plain text\n")
        lines.append(f"paragraph {i} plain *emphasis{i}* more `code{i}` text\n")
        lines.append("\n")
    return "".join(lines)


@pytest.mark.parametrize("workers", (2, 8, 16))
def test_split_records_equal_the_sequential_parse_on_a_ground_truth_grammar(
    workers: int,
) -> None:
    """A split parse over the 2 KiB floor builds byte-identical records to
    the sequential parse — every worker's records pass through the same
    composed build tail, so a per-worker clone specialised wrong diverges
    here rather than only in a synthetic single-shape document."""
    compiled = compile_from_path(GROUND_TRUTH / "markdown.gbnf")
    text = _markdown_document(400)
    assert len(text) >= 16 * 1024
    assert split_plan(compiled.codegen_grammar) is not None, (
        "markdown must be splittable"
    )
    grammar, binding = compiled.codegen_grammar, compiled.product
    calls: list[str] = []

    def recording_parse(g, source, fold, resolve=None):
        calls.append(source)
        return parse_model(g, source, fold, resolve)

    split = split_model(recording_parse, grammar, Request(text, binding), workers)
    assert split is not None, "the split must actually have run, not declined"
    assert len(calls) >= 2, "the split must have divided the document"

    sequential = assert_parallel_matches_sequential(compiled, text, workers)
    assert split == sequential
