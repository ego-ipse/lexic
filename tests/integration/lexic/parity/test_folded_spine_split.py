"""A depth-growing model assembled by a stitch — the repo's only such coverage.

Fifteen of the roster's splitting rows build models of CONSTANT depth, and the
four whose depth grows with the document all run on one worker. The two sets do
not intersect, so until the folded source there was no row anywhere in which a
stitch reassembled a model that gets deeper as the input gets longer. There is
no prior art and no regression net beyond this file.

That is why identity is asked at several widths rather than one. A join that
rebuilds one level too few is off by the number of CUTS, not by a constant: at
a single width the error reads as an off-by-one anyone would look for in the
test, and only varying the width shows it tracking the division.

**Depth convention, stated once and kept:** depth 1 is the start-rule model
itself, and every nested :class:`~lexic.model.GrammarModel` adds one. A reading
that starts at the start rule's CHILD is one lower throughout; the growth rate
is the same and is what carries the argument.

Deep models are compared by :meth:`~lexic.model.GrammarModel.dump`, never by
``==``. A left-nested model is as deep as its document and ``==`` recurses one
C frame per level, so a long one raises ``RecursionError`` on the COMPARISON
while the parse and the model are both fine.
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.compile import CompiledGrammar, compile_text
from lexic.model import GrammarModel
from lexic.parsing.parallel.plan.folded import folded_plan
from lexic.parsing.parallel.planner import split_plan
from tests.split_helpers import engages
from tools.benchmark.cases.corpora import island_corpus
from tools.benchmark.cases.grammars import BENCHES

WORKERS = (2, 4, 8, 16)
"""Worker counts identity is asked at — several, so no answer rests on one."""

SEPARATED = (
    'root ::= expr\nexpr ::= term step*\nstep ::= op term\nterm ::= [a-z]\nop ::= "+"\n'
)
"""Witness A — the same language, stated as a repetition.

Splits today, and its model's depth does not grow: the run is a tuple field,
not a nesting. It is the rung below B, and the only difference between them is
which formulation the grammar uses.
"""

RECURSIVE = 'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]\nop ::= "+"\n'
"""Witness B — the same language, left-recursive.

Had no plan of any kind before the folded source, and its model's depth is the
term count. B is what the ladder exists to reach; A is what proves the rung
below it was already sound.
"""


def document(terms: int) -> str:
    """A ``terms``-long chain under either witness."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "+".join(letters[index % 26] for index in range(terms))


def depth(model: GrammarModel) -> int:
    """The model's longest chain of nested models, counting the root as 1.

    Iterative on purpose. The recursive reading of this walk raises
    ``RecursionError`` on exactly the models it exists to measure, which is
    how a real spine gets mistaken for a broken instrument.
    """
    best, stack = 0, [(model, 1)]
    while stack:
        node, at = stack.pop()
        best = max(best, at)
        for child in node.children():
            if isinstance(child, GrammarModel):
                stack.append((child, at + 1))
            elif child.__class__ is tuple:
                parts = cast(tuple[object, ...], child)
                stack.extend(
                    (part, at + 1) for part in parts if isinstance(part, GrammarModel)
                )
    return best


def witness(source: str, key: str):
    """One witness's artefact, compiled once per key."""
    return compile_text(source, cache_key=f"folded-spine-{key}")


# ── the ladder: two formulations of one language ──────────────────────────


def test_the_separated_witness_splits_and_its_depth_is_flat() -> None:
    """A already split, and its model does not get deeper. The rung below B."""
    compiled = witness(SEPARATED, "separated")
    assert split_plan(compiled.codegen_grammar) is not None
    assert folded_plan(compiled.codegen_grammar) is None
    depths = {depth(compiled.parse(document(n), cores=1)) for n in (2, 4, 8, 16)}
    assert len(depths) == 1, f"witness A stopped being constant-depth: {depths}"


def test_the_recursive_witness_gains_a_plan_it_did_not_have() -> None:
    """B had no plan of any kind; the folded source is what it gains."""
    compiled = witness(RECURSIVE, "recursive")
    assert split_plan(compiled.codegen_grammar) is None
    plan = folded_plan(compiled.codegen_grammar)
    assert plan is not None
    assert (plan.rule, plan.lead, plan.marks) == ("expr", "op", ("+",))


@pytest.mark.parametrize("terms", (2, 4, 8, 16))
def test_the_recursive_witness_is_as_deep_as_its_document(terms: int) -> None:
    """B's depth grows one per term — the property with no other coverage."""
    compiled = witness(RECURSIVE, "recursive")
    assert depth(compiled.parse(document(terms), cores=1)) == terms + 1


@pytest.mark.parametrize("workers", WORKERS)
def test_the_stitched_spine_is_the_sequential_spine(workers: int) -> None:
    """B, split and folded back, is the model a sequential parse builds.

    Depth is asserted BESIDE the dump, not instead of it: a dump comparison
    would already catch a missing level, and stating the depth is what makes a
    failure legible as "one level per cut" rather than a diff of two long
    strings.
    """
    compiled = witness(RECURSIVE, "recursive")
    text = document(6000)
    assert engages(compiled, text, cores=workers)
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=workers)
    assert type(parallel) is type(sequential)
    assert parallel.to_text() == text
    assert depth(parallel) == depth(sequential) == 6001
    assert parallel.dump() == sequential.dump()


# ── island-earley, the row the order was given for ────────────────────────


def island() -> tuple[CompiledGrammar, str]:
    """The roster's island-earley artefact and its full sample."""
    bench = next(one for one in BENCHES if one.name == "island-earley")
    return bench.compiled, bench.full


def test_island_earley_has_a_folded_plan_by_name() -> None:
    """The rule, the step rule and both marks, spelled out.

    By NAME rather than by count: a plan that found a different rule or a
    different separator would still be "a plan", and would split the wrong
    thing.
    """
    compiled, _text = island()
    plan = folded_plan(compiled.codegen_grammar)
    assert plan is not None
    assert (plan.rule, plan.step, plan.lead) == ("expr", "expr-arm1", "addop")
    assert plan.marks == (" + ", " - ")
    assert plan.owners == ("term",)
    assert (plan.before, plan.after) == ("", "\n")


@pytest.mark.parametrize("workers", WORKERS)
def test_island_earley_engages_and_answers_identically(workers: int) -> None:
    """The row splits, and every worker count gives the sequential model."""
    compiled, text = island()
    assert engages(compiled, text, cores=workers)
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=workers)
    assert parallel.to_text() == text
    assert depth(parallel) == depth(sequential)
    assert parallel.dump() == sequential.dump()


@pytest.mark.parametrize("terms", (32, 64, 128, 256, 512))
def test_island_earley_is_identical_at_five_widths(terms: int) -> None:
    """Five widths, because a per-cut error is invisible at one.

    A join short by one level is short by the number of CUTS, so it scales
    with the division rather than sitting at a constant. Only varying the
    width tells the two apart.
    """
    compiled, _full = island()
    text = island_corpus(terms)
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=4)
    assert parallel.to_text() == text
    assert depth(parallel) == depth(sequential)
    assert parallel.dump() == sequential.dump()


# ── nothing else on the roster moved ──────────────────────────────────────


def test_dense_earley_keeps_its_terminated_plan() -> None:
    """The other fold row is untouched, and says so by owner and mark.

    Precedence is by CONSTRUCTION here, twice over. ``root ::= line+`` yields
    a terminated plan, which the plan cascade's ``or`` prefers; and the folded
    source declines the shape outright, because a piece cannot wear a
    repetition's text. Both are asserted, since either alone would let the
    other rot.
    """
    bench = next(one for one in BENCHES if one.name == "dense-earley")
    plan = split_plan(bench.compiled.codegen_grammar)
    assert plan is not None
    assert plan.terminated
    assert plan.owner == "line"
    assert plan.mark == frozenset({"\n"})
    assert folded_plan(bench.compiled.codegen_grammar) is None
    assert engages(bench.compiled, bench.full, cores=4)


def test_only_island_earley_gains_a_folded_plan() -> None:
    """Exactly one roster row reaches the new source.

    Both halves matter. A second row quietly gaining one would be a change to
    a measured grammar nobody asked for; ZERO rows gaining one would make
    every identity assertion above a test of the sequential path against
    itself.
    """
    reached = {
        bench.name
        for bench in BENCHES
        if folded_plan(bench.compiled.codegen_grammar) is not None
    }
    assert reached == {"island-earley"}


@pytest.mark.parametrize("bench", BENCHES, ids=lambda one: one.name)
def test_every_bench_grammar_still_answers_as_it_did(bench) -> None:
    """Every row's model at four workers is its sequential model."""
    sequential = bench.compiled.parse(bench.full, cores=1)
    parallel = bench.compiled.parse(bench.full, cores=4)
    assert parallel.to_text() == bench.full
    assert parallel.dump() == sequential.dump()
