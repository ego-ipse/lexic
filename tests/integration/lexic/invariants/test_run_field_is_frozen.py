"""A model's repeated field is a plain `tuple`, whichever path built it.

Stored raw, a sink list would alias per-parse state and make the record
unhashable — and a record built with one compares UNEQUAL to the same record
built from a tuple, so two parses of one document would not be one value.

`model.py`'s checked constructor says that in its own words. The freeze is not
in one place, though, and that is what this pins — with each route's evidence
named for what it is, because they are not equally strong:

* the **fused PDA** build and **Earley** are exercised end to end below;
* the **parallel stitch** family needs `cores > 1`, which these witnesses do
  not reach; it rebuilds through `IrNamedTuple.rebuild` into the checked
  constructor, and is covered by `test_interior.py`'s split tests and the
  owner pins;
* the **validated keyword** path is pinned DIRECTLY against the constructor it
  calls, never through a document, because no shipped grammar reaches it with
  a run. Measured over every clone of the benchmark roster AND the
  ground-truth corpus: not one has captures without a composed build — the
  fast licence is granted universally, so the keyword path is reached only by
  an empty alternate arm, which carries no captures at all. That is weaker evidence of
  real-world relevance and it is said rather than dressed up, following
  `test_fold_refusals.py`'s precedent for the same situation.
"""

from __future__ import annotations

import pytest

from lexic.model import GrammarModel
from lexic.parsing.products import _model_product, earley_model, pda_model
from tools.benchmark.cases.grammars import BENCHES

WITNESSES = ("csv", "nested")
"""Two shapes with repeated fields — flat runs, and nested ones."""


def runs_of(model: object) -> list[object]:
    """Every repeated field held anywhere in a built model."""
    found: list[object] = []
    seen: set[int] = set()
    stack: list[object] = [model]
    while stack:
        node = stack.pop()
        if not isinstance(node, GrammarModel) or id(node) in seen:
            continue
        seen.add(id(node))
        for field in node:
            if isinstance(field, tuple) and not isinstance(field, GrammarModel):
                found.append(field)
                stack.extend(field)
            elif isinstance(field, GrammarModel):
                stack.append(field)
    return found


@pytest.mark.parametrize("name", WITNESSES)
def test_the_fused_pda_build_freezes_its_runs(name: str) -> None:
    """`_read_models` returns `tuple(...)` — "the item's whole run, frozen"."""
    bench = next(one for one in BENCHES if one.name == name)
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)

    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)

    runs = runs_of(model)
    assert runs, f"{name} has no repeated field to freeze"
    assert all(run.__class__ is tuple for run in runs)
    hash(model)


@pytest.mark.parametrize("name", WITNESSES)
def test_the_earley_build_freezes_them_too(name: str) -> None:
    """`CaptureMode.MANY` hands a LIST to the checked constructor, which
    coerces it — a different mechanism reaching the same shape."""
    bench = next(one for one in BENCHES if one.name == name)
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)

    model = earley_model(
        product.instance_grammar,
        bench.corpus,
        bench.compiled.product,
        product.tables,
    )

    assert all(run.__class__ is tuple for run in runs_of(model))
    hash(model)


@pytest.mark.parametrize("name", WITNESSES)
def test_both_engines_build_the_same_value(name: str) -> None:
    """Equal AND equally hashable — the property the freeze exists for.

    A list-held run would make these unequal while both still round-tripped,
    so the comparison is the assertion and the round-trip is not enough.
    """
    bench = next(one for one in BENCHES if one.name == name)
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)

    fused = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)
    gated = earley_model(
        product.instance_grammar,
        bench.corpus,
        bench.compiled.product,
        product.tables,
    )

    assert fused == gated
    assert hash(fused) == hash(gated)


def test_the_validated_paths_own_constructor_coerces_a_list() -> None:
    """The keyword path's final call, pinned against the constructor.

    `build_validated` puts the raw sink LIST into kwargs and calls
    `clone.ctor(**kwargs)` — the checked constructor, which coerces. No
    document reaches this with a run (see the module docstring), so the
    function is pinned where the behaviour lives.
    """
    bench = next(one for one in BENCHES if one.name == "csv")
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)
    cls, names = type(model), type(model)._fields

    built = cls(**dict(zip(names, [model[0], list(model[1])])))

    assert built[1].__class__ is tuple, "the keyword path did not freeze it"
    assert built == model
    assert hash(built) == hash(model)


def test_a_list_held_run_is_unhashable_and_unequal() -> None:
    """The negative control — the hazard the freeze prevents, demonstrated.

    Built through the UNCHECKED constructor, which bypasses the coercion. If
    this ever stops raising, the tests above are asserting a property that
    nothing could violate.
    """
    bench = next(one for one in BENCHES if one.name == "csv")
    product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
    model = pda_model(product.pda, bench.corpus, bench.compiled.product.executor)

    # The UNCHECKED constructor is the SUBJECT of this test; reaching it any
    # other way would not be reaching it.
    # pylint: disable-next=protected-access
    raw = type(model)._from_values([model[0], list(model[1])])

    assert raw[1].__class__ is list
    with pytest.raises(TypeError):
        hash(raw)
    assert raw != model, "the twin built through a parse is a DIFFERENT value"
