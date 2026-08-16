"""The transpile crossing: both documents addressed, and the map between them.

`Transpiler.run` used to return a bare string, discarding the source→built
correspondence the walk had in hand. `cross()` keeps it — always-on, in the
export-gate tradition — and `run` is now that, keeping only the text.

What the product can honestly claim is the point of these gates.
`IrBottomUp` transforms a shared object ONCE and splices the result
everywhere it appeared, so the walk knows an OBJECT correspondence, never an
occurrence one. The crossing therefore emits one `IrOrigin` per
``(built occurrence, source occurrence)`` pair the object map licenses: one
entry where the source value stands in one place, several where it stands in
several. The set IS the answer; nothing is picked from it.
"""

from __future__ import annotations

from collections import Counter

import pytest

from getting_started import ex16_transpile_json_yaml as ex16
from lexic.compile import compile_from_path, compile_text, transpile
from lexic.compile.transpile import Crossing, Transpiler
from lexic.exceptions import UnsupportedConstructError
from lexic.model import GrammarModel


def walker() -> Transpiler:
    """The shipped json→yaml transform, baked (both compiles are memoised)."""
    return transpile(
        compile_from_path(ex16.JSON_GRAMMAR),
        compile_text(ex16.YAML_GRAMMAR, cache_key="test-crossing"),
        ex16.RULES,
    )


def crossed() -> tuple[Crossing, GrammarModel, GrammarModel]:
    """The shipped example, crossed — plus the source and product models.

    A plain function rather than a fixture: a module-level fixture name and
    the parameter that receives it are the same name, which is a shadowing
    the linter refuses, and the build is memoised anyway.
    """
    walk = walker()
    model = walk.source.parse(ex16.DOC)
    return walk.cross(ex16.DOC), model, walk.apply(model)


def test_run_is_cross_keeping_only_the_text() -> None:
    """One path, two products — ``run`` cannot drift from ``cross``."""
    cross, _model, _product = crossed()
    assert walker().run(ex16.DOC) == cross.product.text


def test_both_sides_carry_their_own_addressed_emission() -> None:
    """Each document is addressed in its OWN coordinates, not the other's."""
    cross, model, product = crossed()
    assert cross.source.text == model.to_text() == ex16.DOC
    assert cross.product.text == product.to_text()
    assert len(cross.source.extents) > len(cross.product.extents) > 0


def test_the_source_side_really_does_share_objects() -> None:
    """The premise: this is why the correspondence is object-level.

    If the source ever stopped sharing, the shared-case gates below would
    stop testing anything, so the premise is asserted rather than assumed.
    """
    _cross, model, _product = crossed()
    seen: Counter[int] = Counter()
    stack: list[object] = [model]
    while stack:
        node = stack.pop()
        if isinstance(node, GrammarModel):
            seen[id(node)] += 1
            stack.extend(k for k in node.children() if k is not None)
        elif isinstance(node, tuple):
            stack.extend(node)
    assert max(seen.values()) > 1, "the source no longer shares any object"


def test_every_walk_built_occurrence_resolves_to_a_source() -> None:
    """The gate: a built occurrence the WALK produced names where it came from.

    Not every built model is a walk result: a table body may build models
    inside itself (``Make("entry", IrTuple(Make("key", …), …))``) and the
    chain-grower mints the item models of a hoisted list. Those are the
    table's own construction, not a transformed source node, and the crossing
    says so with an empty set rather than attributing them to a neighbour.
    """
    cross, _model, product = crossed()
    built = [
        extent.address
        for extent in cross.product.extents
        if isinstance(product.occurrence(extent.address), GrammarModel)
    ]
    resolved = [address for address in built if cross.sources_of(address)]
    assert resolved, "no built occurrence resolved at all"
    introduced = {
        type(product.occurrence(address)).__name__
        for address in built
        if not cross.sources_of(address)
    }
    assert introduced <= {"Entry", "Key", "AvalsItem", "FentsItem"}, introduced


def test_a_unique_pair_round_trips_as_one_origin() -> None:
    """Where the source value stands in ONE place, the answer is one address.

    And it resolves: the address names a real occurrence of the source model.
    """
    cross, model, product = crossed()
    unique = [
        address
        for address in (e.address for e in cross.product.extents)
        if len(cross.sources_of(address)) == 1
    ]
    assert unique
    for address in unique:
        source_at = cross.sources_of(address)[0]
        assert isinstance(model.occurrence(source_at), GrammarModel)
        assert isinstance(product.occurrence(address), GrammarModel)


def test_a_shared_source_is_drawn_as_a_set_never_picked_from() -> None:
    """Where one source value stands in several places, ALL of them appear.

    This is the identity doctrine: one value, many occurrences, wash them
    all. A product that named one of them would be making a choice the walk
    never made.
    """
    cross, model, _product = crossed()
    everywhere: dict[int, set[tuple]] = {}
    for extent in cross.source.extents:
        occurrence = model.occurrence(extent.address)
        if isinstance(occurrence, GrammarModel):
            everywhere.setdefault(id(occurrence), set()).add(tuple(extent.address))

    shared = [
        address
        for address in (e.address for e in cross.product.extents)
        if len(cross.sources_of(address)) > 1
    ]
    assert shared, "expected at least one shared source in the example"
    for address in shared:
        sources = cross.sources_of(address)
        assert len(set(sources)) == len(sources), "a source address repeated"
        # The no-pick invariant: for every source value the set names, EVERY
        # place that value stands is in the set. A product that had chosen
        # would carry a proper subset. (Two distinct source values may both
        # produce one built object — the fold interns by spelling — so the
        # set is their union, not necessarily one value's occurrences.)
        named = {tuple(at) for at in sources}
        for at in sources:
            assert everywhere[id(model.occurrence(at))] <= named, (
                "the crossing named some occurrences of a source value and "
                "not others — that is a pick"
            )


def test_every_origin_address_resolves_on_its_own_side() -> None:
    """No origin names an address its document does not have."""
    cross, model, product = crossed()
    for origin in cross.origins:
        assert product.occurrence(origin.address) is not None
        assert model.occurrence(origin.source) is not None


def test_the_crossing_is_built_only_after_the_gates_pass() -> None:
    """A refused run yields no crossing — the gates still come first."""
    with pytest.raises(UnsupportedConstructError):
        walker().cross("[1, 2, 3]")
