"""The forced Earley seat serves exactly the families the producer filed.

**Why this test exists, and why the ones beside it could not catch what it
catches.** Roster dump identity parses through the PUBLIC entry, and almost no
roster row reaches the Earley kernel that way — the PDA answers first. The
parity suite compares the two engines' ANSWERS. Neither looks at the family
relation on the forced `lexic-earley` route, and a reader that serves
derivations the parse never built can pass both while changing what
:class:`FastTree` returns.

That is not hypothetical: a reader that rebuilt a promoted key's families by
walking ``cols[end]`` served 8,991 families where the producer filed 8,947,
and turned a `ParseTree` into a decline on the split-ambiguous witness. Both
gates passed.

The oracle is :func:`tests.earley_families.filed_families`, built from a
different structure than the reader's own record so a bug in that record
cannot hide behind it.
"""

from __future__ import annotations

import pytest

from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_items
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.products import _model_product
from tests.earley_families import filed_families
from tools.benchmark.cases import corpora
from tools.benchmark.cases.grammars import BENCHES

WITNESSES = (
    ("split-nullable", corpora.split_nullable_corpus, (20, 60)),
    ("csv", corpora.csv_corpus, (40,)),
    ("json", corpora.json_corpus, (40,)),
    ("gbnf-meta", lambda n: corpora.meta_corpus("json.gbnf", n), (1,)),
)
"""Split-nullable first: it is the only one whose keys promote at all, so a
witness list without it would pass on charts that never exercise the path."""


def seat(name: str):
    """The bench's own `lexic-earley` tables, as `bench.py` builds them."""
    bench = next(one for one in BENCHES if one.name == name)
    return _model_product(bench.compiled.codegen_grammar, bench.compiled.product)


@pytest.mark.parametrize(
    ("name", "size"),
    [(name, size) for name, _, sizes in WITNESSES for size in sizes],
)
def test_the_seat_serves_exactly_the_families_the_producer_filed(name, size):
    """Membership AND order, per key, on the forced Earley route."""
    build = next(one for label, one, _ in WITNESSES if label == name)
    text = build(size)
    kern = Kernel(seat(name).tables, text, True).run()
    table = kern.families
    oracle = filed_families(kern)
    assert oracle, f"{name}/{size} files no ordinary family — it proves nothing"
    for key, want in oracle.items():
        served = table.get(key)
        assert served is not None, f"{name}/{size}: key {key} serves nothing"
        assert served[: len(want)] == want, f"{name}/{size}: key {key}"
    extra = {
        key: [one for one in (table.get(key) or ()) if one not in oracle.get(key, ())]
        for key in table.keys()
    }
    invented = {
        key: got
        for key, got in extra.items()
        if got and not any(one in kern.st.links.get(key, ()) for one in got)
    }
    assert not invented, (
        f"{name}/{size}: the seat serves families no producer filed: "
        f"{list(invented.items())[:2]}"
    )


@pytest.mark.parametrize("size", [20, 60])
def test_the_split_ambiguous_witness_still_builds_a_tree(size):
    """`FastTree` must decide the same way it always did.

    The symptom the family divergence produced: a key packing more families
    than the producer filed made the fast path decline, and a decline is
    cheap, so the regression read as a large speedup.
    """
    text = corpora.split_nullable_corpus(size)
    kern = Kernel(seat("split-nullable").tables, text, True).run()
    bits = kern.tables.packing.bits
    accepting = list(accept_items(kern))
    assert accepting, "the witness does not parse — the test proves nothing"
    for it in accepting:
        built = FastTree(kern, {}).build((it << bits) | len(text))
        assert built is not None and type(built).__name__ == "ParseTree", (
            f"the fast path declined at {size} paragraphs where it builds a "
            f"tree: got {type(built).__name__}"
        )


def test_a_promoting_witness_is_present():
    """The suite would pass on charts that never promote — so one must."""
    kern = Kernel(
        seat("split-nullable").tables, corpora.split_nullable_corpus(20), True
    )
    kern.run()
    promoted = sum(
        1 for bucket in kern.st.links.values() if bucket and bucket[0][0] < 0
    )
    assert promoted, "no key promoted — the read-back path is never exercised"
