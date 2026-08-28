"""Decoded semantic route continuation across one following reference.

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
    """One finite route's predictive contextual destination."""

    route: int
    pda_clone: int


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
    """A producer completion controlling one following reference position."""

    producer_completion: int
    consumer_position: int
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


def decoded_route(table: RouteTable, key: str) -> int:
    """Collapse an arbitrary decoded key to one finite route."""
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
    position: int,
) -> int:
    """Select the contextual clone at the routed reference opcode."""
    if position != continuation.consumer_position:
        raise UnsupportedConstructError(
            "prototype continuation: routed reference position mismatch"
        )
    route = frame.routes[continuation.route_slot]
    if route == UNSET:
        raise UnsupportedConstructError(
            "prototype continuation: producer has not completed"
        )
    return _choice(routes.tables[continuation.table], route).pda_clone


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
                    RouteChoice(1, 101),
                    RouteChoice(2, 102),
                ),
            ),
        ),
        (RouteContinuation(names["string"], refs.index("value"), 0, 0),),
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

    model = decoded_route(routes.tables[0], _decoded_key('"model"'))
    escaped = decoded_route(routes.tables[0], _decoded_key('"m\\u006fdel"'))
    assert model == escaped == 1
    mark = frame.publish(continuation.route_slot, model)
    assert pda_child(routes, continuation, frame, 2) == 101
    frame.rollback(mark)
    assert frame.routes == [UNSET]

    extension = decoded_route(routes.tables[0], _decoded_key('"other"'))
    frame.publish(continuation.route_slot, extension)
    assert pda_child(routes, continuation, frame, 2) == 102


def prove_earley() -> None:
    """Encode route and occurrence in the existing packed successor code."""
    routes = _routes()
    continuation = routes.continuations[0]

    model = decoded_route(routes.tables[0], _decoded_key('"model"'))
    specialised = earley_successor(routes, continuation, 300, model)
    assert specialised == 301

    extension = decoded_route(routes.tables[0], _decoded_key('"other"'))
    generic = earley_successor(routes, continuation, 300, extension)
    assert generic == 302
    assert specialised != generic

    nested = earley_successor(routes, continuation, 400, model)
    assert nested == 401
    assert nested != specialised


def main() -> None:
    """Run both engine-shaped continuation proofs."""
    prove_pda()
    prove_earley()
    print("PASS: decoded route controls the following PDA/Earley child")


if __name__ == "__main__":
    main()
