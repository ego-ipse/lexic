"""The forced Earley seat reads exactly what the pre-factoring recorder stored.

**Why this test exists, and why the ones beside it could not catch what it
catches.** Roster dump identity parses through the PUBLIC entry, and almost no
roster row reaches the Earley kernel that way — the PDA answers first. The
parity suite compares the two engines' ANSWERS, and an answer can come out the
same while the families behind it differ: an extra family is an extra
candidate reading at a decision point, and a misordered bucket changes which
family is FIRST — what the fast path and the ambiguity walk take — without
changing the tree a given document happens to produce.

The oracle is :func:`tests.earley_families.paired`: the same recognition,
recorded one family per waiter per completion as the kernel did before
factoring. Everything here is compared against it on the forced
`lexic-earley` route — complete ordered buckets, and then what every consumer
of those buckets computes from them.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import DEFAULT_CONFIG, ParseConfig, derivations
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import ambiguity_points
from lexic.parsing.earley.kernel.forest.support.readout import accept_items, to_chart
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST
from lexic.parsing.earley.kernel.tables.splits import canonical_indices, spec_for
from lexic.parsing.products import _model_product, earley_model
from tests.earley_families import (
    baseline_recorder,
    before_group,
    bucket_differences,
    paired,
)
from tools.benchmark.cases import corpora
from tools.benchmark.cases.grammars import BENCHES

SEATS = (
    ("split-nullable", corpora.split_nullable_corpus, 20),
    ("split-nullable", corpora.split_nullable_corpus, 60),
    ("csv", corpora.csv_corpus, 40),
    ("json", corpora.json_corpus, 40),
    ("gbnf-meta", lambda n: corpora.meta_corpus("json.gbnf", n), 1),
)
"""Split-nullable first: its keys promote, so without it the suite would pass on
charts that never exercise the read-back path."""

OPERATORS = 'root ::= e\ne ::= e "+" e | e "*" e | "n"\n'
"""Keys at one ``(rule, end)`` promote at different times — the late-promotion
shape that once served a key's families in promotion order, not filing order —
and every document is an ARM ambiguity, so the refusal and resolver paths run."""


def seat(name: str):
    """The bench's own `lexic-earley` product, as `bench.py` builds it."""
    bench = next(one for one in BENCHES if one.name == name)
    return bench, _model_product(bench.compiled.codegen_grammar, bench.compiled.product)


def operators():
    """The operator grammar's compiled artefact and its `lexic-earley` product."""
    compiled = compile_text(OPERATORS)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def handles(kern) -> list[int]:
    """The accepting handles of a finished kernel."""
    bits = kern.tables.packing.bits
    return [(it << bits) | len(kern.text) for it in accept_items(kern)]


def consumers(kern) -> dict[str, object]:
    """What every reader of the family table computes on this chart.

    The fast-path tree per accepting handle; a family-index PIN at each
    ambiguity point, per family index; each point's canonical carvings; the
    ambiguity points themselves; and the decoded chart.
    """
    reader = kern.family_reader()
    codes, bits = kern.tables.codes, kern.tables.packing.bits
    out: dict[str, object] = {}
    for handle in handles(kern):
        out[f"tree {handle}"] = FastTree(kern, {}, LEFTMOST_LONGEST).build(handle)
        points = ambiguity_points(kern, handle)
        out[f"points {handle}"] = points
        for point in points:
            bucket = reader[point]
            spec = spec_for(codes, bits, kern.tables.code_choice, point)
            out[f"canonical {point}"] = canonical_indices(reader, bucket, spec)
            for index in range(min(len(bucket), 3)):
                out[f"pin {point}={index}"] = FastTree(
                    kern, {point: index}, LEFTMOST_LONGEST
                ).build(handle)
    out["chart"] = [(key, list(fams)) for key, fams in to_chart(kern).links.items()]
    return out


@pytest.mark.parametrize(("name", "build", "size"), SEATS)
def test_the_seat_serves_the_recorders_buckets_complete_and_in_order(name, build, size):
    """Every key, every family, in order — after every Leo chain is expanded."""
    _bench, product = seat(name)
    base, kern = paired(product.tables, build(size))
    assert base.st.links, f"{name}/{size} files nothing — it proves nothing"
    differences = bucket_differences(base, kern)
    assert not differences, f"{name}/{size}: {differences[:2]}"


def test_the_late_promotion_shape_serves_the_recorders_buckets():
    """The shape whose first families were once served out of order."""
    _compiled, product = operators()
    base, kern = paired(product.tables, "n+n*n+n*n+n*n*n+n")
    assert before_group(kern), "no first family predates its group — nothing tested"
    assert not bucket_differences(base, kern)


@pytest.mark.parametrize(
    ("label", "text"),
    [("split-nullable", corpora.split_nullable_corpus(8)), ("operators", "n+n*n+n*n")],
)
def test_every_consumer_computes_what_it_computed_from_the_recorders_table(label, text):
    """Trees, pinned builds, canonical carvings, ambiguity points, decoded chart.

    Run on both kernels of one pair: the baseline's reader is its plain dict,
    so this is the consumer code as it ran before factoring, on the same chart.
    """
    tables = (seat(label)[1] if label == "split-nullable" else operators()[1]).tables
    base, kern = paired(tables, text)
    assert kern.st.groups, f"{label}: nothing promoted — the factored reader never ran"
    want, got = consumers(base), consumers(kern)
    assert any(key.startswith("pin ") for key in want), f"{label}: no ambiguity point"
    assert want.keys() == got.keys()
    for key, value in want.items():
        assert got[key] == value, f"{label}: {key}"


def _earley(
    compiled, product, text: str, resolve=None
) -> tuple[tuple[str, object], list]:
    """One forced-Earley model parse: its value or refusal, and the resolver's calls."""
    calls: list = []

    def recording(first, other):
        """Keep the first derivation, and remember what was asked."""
        calls.append((first, other))
        return first

    try:
        value = earley_model(
            product.instance_grammar,
            text,
            compiled.product,
            product.tables,
            ParseConfig(resolve=recording) if resolve else DEFAULT_CONFIG,
        )
    except UnsupportedConstructError as refusal:
        return ("refused", str(refusal)), calls
    return ("model", value.dump()), calls


@pytest.mark.parametrize("resolve", [False, True])
def test_refusals_and_resolver_calls_match_the_recorders(resolve):
    """An ARM ambiguity refuses without a resolver and asks it the same
    questions, in the same order, with one."""
    compiled, product = operators()
    with baseline_recorder():
        want = _earley(compiled, product, "n+n*n+n*n", resolve)
    got = _earley(compiled, product, "n+n*n+n*n", resolve)
    assert want[0][0] == ("model" if resolve else "refused")
    assert got == want
    if resolve:
        assert want[1], "the resolver was never asked — nothing compared"


@pytest.mark.parametrize(
    ("label", "source", "text"),
    [
        ("operators", OPERATORS, "n+n*n+n"),
        ("split-nullable", None, corpora.split_nullable_corpus(2)),
    ],
)
def test_finite_derivations_match_the_recorders(label, source, text):
    """Every derivation, in the order the forest enumerates them."""
    grammar = (operators()[1] if source else seat("split-nullable")[1]).instance_grammar
    with baseline_recorder():
        want = list(derivations(grammar, text))
    got = list(derivations(grammar, text))
    assert len(want) > 1, f"{label}: one derivation — nothing to order"
    assert got == want
