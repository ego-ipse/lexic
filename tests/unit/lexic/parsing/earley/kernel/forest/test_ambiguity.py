"""A decided split is not an ambiguity — the refusal is for the ARM class only."""

from __future__ import annotations

import random

from lexic.compile import compile_from_path
from lexic.generate import generate
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    another_meaning,
)
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.products import _model_product
from tests.paths import GROUND_TRUTH


def test_a_decided_nullable_split_is_not_reported_as_ambiguity():
    """json's ambiguity is ALL split class, and splits now have one answer.

    Two adjacent nullable slots carve a gap two ways; the first slot owns the
    text, decided on the chain. Once that is decided the engine must neither
    refuse it nor fall back for it — refusing would refuse a question it can
    now answer, and RFC 8259's own shape is ambiguous, so lexic must parse it.

    The ARM class — one span through two DIFFERENT productions — keeps the
    refusal, because a length rule has no standing over which production the
    grammar meant.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    product = _model_product(compiled.codegen_grammar, compiled.product)
    rules = {r.name: r for r in compiled.grammar.rules}
    with_points = flagged = 0
    for seed in range(200):
        text = generate(
            compiled.grammar.start, rules, rng=random.Random(seed), max_depth=12
        )
        if not text:
            continue
        kernel = Kernel(product.tables, text, True).run()
        if accept_item(kernel) < 0:
            continue
        handle = (accept_item(kernel) << kernel.tables.packing.bits) | len(text)
        tree = FastTree(kernel, {}).build(handle)
        if not isinstance(tree, ParseTree):
            continue
        if ambiguity_points(kernel, handle):
            with_points += 1
        if (
            another_meaning(kernel, handle, compiled.product.executor.build, tree)
            is not None
        ):
            flagged += 1
    assert with_points, "no ambiguous json input generated — the test proves nothing"
    assert not flagged, (
        f"{flagged} of {with_points} split-ambiguous json inputs were reported as "
        "meaning two things; a decided split is not an ambiguity"
    )
