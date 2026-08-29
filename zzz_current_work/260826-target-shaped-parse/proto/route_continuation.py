"""Semantic or raw route continuation across one following reference.

The witness is JSON ``member`` shape, but every runtime record contains only
integer completion/item positions and finite routes.  Grammar and target names
exist only in the prototype assertion which stands in for compile lowering.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import compile_ast
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrRuleRef, IrSequence, IrStr

UNSET = -1


class RouteChoice(NamedTuple):
    """One finite route's contextual clone chain."""

    route: int
    pda_clones: tuple[int, ...]


class EarleyRouteAdvance(NamedTuple):
    """One sparse routed waiter advance into an existing successor code."""

    waiter_code: int
    route: int
    successor_code: int


class RouteTable(NamedTuple):
    """Decoded spellings collapsed to finite semantic routes."""

    known: tuple[tuple[str, int], ...]
    extension: int
    choices: tuple[RouteChoice, ...]


class RouteContinuation(NamedTuple):
    """A producer completion controlling one descendant reference path."""

    producer_completion: int
    consumer_positions: tuple[int, ...]
    route_slot: int
    table: int


class ProductRoutes(NamedTuple):
    """Immutable route data shared by PDA and Earley."""

    tables: tuple[RouteTable, ...]
    continuations: tuple[RouteContinuation, ...]
    earley_advances: tuple[EarleyRouteAdvance, ...]


class RouteMark(NamedTuple):
    """One reversible route-lane write."""

    slot: int
    prior: int


class PdaRouteFrame:
    """Predictive frame's dedicated finite-route lane."""

    __slots__ = ("routes",)

    def __init__(self, count: int) -> None:
        self.routes = [UNSET] * count

    def publish(self, slot: int, route: int) -> RouteMark:
        """Commit one successful producer and return its rollback entry."""
        mark = RouteMark(slot, self.routes[slot])
        self.routes[slot] = route
        return mark

    def rollback(self, mark: RouteMark) -> None:
        """Restore one failed continuation attempt in constant time."""
        self.routes[mark.slot] = mark.prior


def route_for(table: RouteTable, key: str) -> int:
    """Collapse one already-spelled semantic or raw key to a finite route."""
    for spelling, route in table.known:
        if spelling == key:
            return route
    return table.extension


def _choice(table: RouteTable, route: int) -> RouteChoice:
    """Return one compiled destination, refusing an invalid route id."""
    for choice in table.choices:
        if choice.route == route:
            return choice
    raise UnsupportedConstructError(
        f"prototype continuation: route {route} has no destination"
    )


def pda_child(
    routes: ProductRoutes,
    continuation: RouteContinuation,
    frame: PdaRouteFrame,
    positions: tuple[int, ...],
) -> int:
    """Select the first contextual clone for a routed descendant path."""
    if positions != continuation.consumer_positions:
        raise UnsupportedConstructError(
            "prototype continuation: routed reference path mismatch"
        )
    route = frame.routes[continuation.route_slot]
    if route == UNSET:
        raise UnsupportedConstructError(
            "prototype continuation: producer has not completed"
        )
    return _choice(routes.tables[continuation.table], route).pda_clones[0]


def pda_descendant(choice: RouteChoice, depth: int) -> int:
    """Read the child already baked into a route-specialized clone."""
    if depth < 1 or depth >= len(choice.pda_clones):
        raise UnsupportedConstructError(
            "prototype continuation: contextual clone depth mismatch"
        )
    return choice.pda_clones[depth]


def earley_successor(
    routes: ProductRoutes,
    continuation: RouteContinuation,
    waiter_code: int,
    route: int,
) -> int:
    """Advance only one routed waiter to its route-specific packed code."""
    _choice(routes.tables[continuation.table], route)
    for advance in routes.earley_advances:
        if advance.waiter_code == waiter_code and advance.route == route:
            return advance.successor_code
    raise UnsupportedConstructError(
        "prototype continuation: routed waiter has no successor code"
    )


def _decoded_key(text: str) -> str:
    """Decode one key through the real JSON grammar and reducer."""
    value = compile_ast(JSON_GRAMMAR).reduce(text, JSON_REDUCER, cores=1)
    if not isinstance(value, IrStr):
        raise UnsupportedConstructError(
            "prototype continuation: JSON key did not reduce to text"
        )
    return str(value)


def _routes() -> ProductRoutes:
    """Stand in for lower-signature × upper-schema compile output."""
    names = {str(rule.name): index for index, rule in enumerate(JSON_GRAMMAR.rules)}
    member = next(rule for rule in JSON_GRAMMAR.rules if str(rule.name) == "member")
    sequence = member.body[0]
    if not isinstance(sequence, IrSequence):
        raise UnsupportedConstructError(
            "prototype continuation: JSON member is not one sequence"
        )
    refs: list[str] = []
    for item in sequence:
        if not isinstance(item.atom, IrRuleRef):
            raise UnsupportedConstructError(
                "prototype continuation: JSON member item is not a reference"
            )
        refs.append(str(item.atom))
    if refs != ["string", "name-separator", "value"]:
        raise UnsupportedConstructError(
            f"prototype continuation: unexpected JSON member shape {refs!r}"
        )
    return ProductRoutes(
        (
            RouteTable(
                (("model", 1),),
                2,
                (
                    RouteChoice(1, (101,)),
                    RouteChoice(2, (102,)),
                ),
            ),
        ),
        (RouteContinuation(names["string"], (refs.index("value"),), 0, 0),),
        (
            EarleyRouteAdvance(300, 1, 301),
            EarleyRouteAdvance(300, 2, 302),
            EarleyRouteAdvance(400, 1, 401),
            EarleyRouteAdvance(400, 2, 402),
        ),
    )


def prove_pda() -> None:
    """Route the following value clone and restore it on failed speculation."""
    routes = _routes()
    continuation = routes.continuations[0]
    frame = PdaRouteFrame(1)

    model = route_for(routes.tables[0], _decoded_key('"model"'))
    escaped = route_for(routes.tables[0], _decoded_key('"m\\u006fdel"'))
    assert model == escaped == 1
    mark = frame.publish(continuation.route_slot, model)
    assert pda_child(routes, continuation, frame, (2,)) == 101
    frame.rollback(mark)
    assert frame.routes == [UNSET]

    extension = route_for(routes.tables[0], _decoded_key('"other"'))
    frame.publish(continuation.route_slot, extension)
    assert pda_child(routes, continuation, frame, (2,)) == 102


def prove_earley() -> None:
    """Encode route and occurrence in the existing packed successor code."""
    routes = _routes()
    continuation = routes.continuations[0]

    model = route_for(routes.tables[0], _decoded_key('"model"'))
    specialised = earley_successor(routes, continuation, 300, model)
    assert specialised == 301

    extension = route_for(routes.tables[0], _decoded_key('"other"'))
    generic = earley_successor(routes, continuation, 300, extension)
    assert generic == 302
    assert specialised != generic

    nested = earley_successor(routes, continuation, 400, model)
    assert nested == 401
    assert nested != specialised


def prove_raw() -> None:
    """Route raw spellings without adding a competing grammar arm."""
    routes = _routes()
    decoded = routes.tables[0]
    raw = RouteTable(
        (('"model"', 1),),
        decoded.extension,
        decoded.choices,
    )
    continuation = routes.continuations[0]
    frame = PdaRouteFrame(1)

    exact = route_for(raw, '"model"')
    escaped = route_for(raw, '"m\\u006fdel"')
    if exact != 1 or escaped != raw.extension:
        raise AssertionError("raw route collapsed distinct surface spellings")
    frame.publish(continuation.route_slot, exact)
    if pda_child(routes, continuation, frame, (2,)) != 101:
        raise AssertionError("raw route lost its predictive destination")
    if earley_successor(routes, continuation, 300, exact) != 301:
        raise AssertionError("raw route lost its Earley successor")


def prove_non_sibling() -> None:
    """Carry one route through an intervening contextual clone."""
    base = _routes()
    table = RouteTable(
        base.tables[0].known,
        base.tables[0].extension,
        (
            RouteChoice(1, (201, 211)),
            RouteChoice(2, (202, 212)),
        ),
    )
    continuation = RouteContinuation(10, (1, 1), 0, 0)
    routes = ProductRoutes(
        (table,),
        (continuation,),
        (
            EarleyRouteAdvance(500, 1, 501),
            EarleyRouteAdvance(500, 2, 502),
            EarleyRouteAdvance(501, 1, 511),
            EarleyRouteAdvance(502, 2, 512),
        ),
    )
    frame = PdaRouteFrame(1)
    route = route_for(table, "model")
    frame.publish(continuation.route_slot, route)
    outer = pda_child(routes, continuation, frame, (1, 1))
    choice = _choice(table, route)
    inner = pda_descendant(choice, 1)
    if (outer, inner) != (201, 211):
        raise AssertionError("PDA route did not survive the contextual clone")
    tail = earley_successor(routes, continuation, 500, route)
    value = earley_successor(routes, continuation, tail, route)
    if (tail, value) != (501, 511):
        raise AssertionError("Earley route did not survive the contextual code")


def main() -> None:
    """Run both engine-shaped continuation proofs."""
    prove_pda()
    prove_earley()
    prove_raw()
    prove_non_sibling()
    print(
        "PASS: decoded/raw routes cross PDA/Earley descendants; grammar_arm_additions=0"
    )


if __name__ == "__main__":
    main()
