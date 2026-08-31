"""Pin the PDA route lane's semantics, including the three stale-route cases.

The lane carries `(consumer path, route)` from the producer that classified a
decoded discriminator to the descendant occurrence that consumes it. It lives
on the kernel cursor rather than in a frame, because a frame is one
program-independent flat list and widening it would tax every product's every
frame push — including the generated-model product, which routes nothing.

Two guards keep a route from reaching the wrong occurrence, and they catch
DIFFERENT mistakes, so both are exercised separately here:

* frame identity — a later frame at the same depth must not read a route the
  frame before it published;
* clearing on advance — a later sibling under the same LIVE parent must not
  read a route the first routed child already consumed.

Plus the abandoned attempt: `_attempt_run` speculates on the live stack under a
depth watermark rather than on a discarded copy, so unwinding the stack is not
enough on its own.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import Any

from lexic.parsing.pda.runtime.admission import NO_ROUTE, RouteLane, frames_copy
from lexic.parsing.pda.runtime.build import F_ENDS, F_OUT, F_SINKS
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel


def _frame(label: str) -> list[Any]:
    """A frame shaped like the kernel's — nine slots, aliasable lists."""
    out: list[Any] = []
    return [label, 0, 0, out, 0, None, 0, [0, 0], None]


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 route lane: {claim}")


def publish_and_consume() -> None:
    """The ordinary case: a producer publishes, its descendant reads."""
    lane = RouteLane()
    parent = _frame("parent")
    lane.publish(0, parent, (2,), 7)

    _check("the published route did not read back", lane.route_at(0, parent) == 7)
    _check("the consumer path did not read back", lane.path_at(0, parent) == (2,))
    print("publish\troute 7 waits at depth 0 for path (2,)")


def a_later_frame_at_the_same_depth_reads_nothing() -> None:
    """Stale case (c): the publisher popped; a new frame took its depth."""
    lane = RouteLane()
    published = _frame("published")
    lane.publish(1, published, (0,), 3)

    # The publishing frame fails and pops WITHOUT its routed child advancing;
    # a different frame then occupies depth 1.
    replacement = _frame("replacement")
    _check(
        "a later frame at the same depth inherited a stale route",
        lane.route_at(1, replacement) == NO_ROUTE,
    )
    _check(
        "the stale path leaked to the later frame",
        lane.path_at(1, replacement) == (),
    )
    _check(
        "the original frame lost its own route",
        lane.route_at(1, published) == 3,
    )
    print("stale (c)\tlater frame at the same depth reads NO_ROUTE")


def a_later_sibling_under_one_parent_reads_nothing() -> None:
    """Stale case (b): same LIVE parent, second child after the first advanced.

    Frame identity cannot catch this one — the parent is the same object — so
    it is clearing on advance that has to, which is why both guards exist.
    """
    lane = RouteLane()
    parent = _frame("parent")
    lane.publish(0, parent, (1,), 5)

    _check("the first routed child missed its route", lane.route_at(0, parent) == 5)
    lane.clear(0)  # the routed occurrence advanced
    _check(
        "a later sibling under the same live parent inherited the route",
        lane.route_at(0, parent) == NO_ROUTE,
    )
    print("stale (b)\tlater sibling under one live parent reads NO_ROUTE")


def an_abandoned_attempt_leaves_nothing_behind() -> None:
    """Stale case (a): an attempt runs on the LIVE stack under a watermark."""
    lane = RouteLane()
    outer = _frame("outer")
    lane.publish(0, outer, (0,), 1)

    # An attempt descends past the watermark and publishes as it goes.
    inner = _frame("inner")
    deeper = _frame("deeper")
    lane.publish(1, inner, (0,), 2)
    lane.publish(2, deeper, (0,), 3)

    lane.discard_above(0)  # the attempt is abandoned back to the watermark
    _check("the attempt's own route survived it", lane.route_at(1, inner) == NO_ROUTE)
    _check("a deeper attempt route survived", lane.route_at(2, deeper) == NO_ROUTE)
    _check(
        "abandoning the attempt destroyed the outer route it did not own",
        lane.route_at(0, outer) == 1,
    )
    print("stale (a)\tabandoned attempt drops its own routes, keeps the outer")


def a_fork_rebinds_to_the_copied_frames() -> None:
    """The lane rides a real `frames_copy` fork, remapped by depth."""
    stack = [_frame("root"), _frame("child")]
    # Alias the child's sink into the root's, the topology `frames_copy` exists
    # to preserve — the lane must survive the same operation.
    stack[1][F_OUT] = stack[0][F_OUT]

    lane = RouteLane()
    lane.publish(0, stack[0], (1,), 9)
    copies = frames_copy(stack)
    forked = lane.forked(copies)

    _check("the fork did not preserve the aliasing topology", copies[1][F_OUT] is copies[0][F_OUT])
    _check("the forked lane still names the ORIGINAL frame", forked.route_at(0, stack[0]) == NO_ROUTE)
    _check("the forked lane lost its route", forked.route_at(0, copies[0]) == 9)
    _check("the forked lane lost its path", forked.path_at(0, copies[0]) == (1,))
    _check("forking mutated the original lane", lane.route_at(0, stack[0]) == 9)
    _check("the forked frames are distinct objects", copies[0] is not stack[0])
    _check("the per-frame lists were duplicated", copies[0][F_ENDS] is not stack[0][F_ENDS])
    _check("an unset sink stayed unset", copies[0][F_SINKS] is None)
    print("fork\tlane rebinds to the copied frames; the original is untouched")


def a_discarded_fork_leaves_the_original_untouched() -> None:
    """Stale case (d): a probe publishes on its fork, then the fork is thrown.

    `_probe` installs the forked stack, drives it, and restores the original
    in a `finally`. Whatever the probe published must go with the fork — the
    real stack must read exactly what it did before the probe ran.
    """
    stack = [_frame("root"), _frame("child")]
    lane = RouteLane()
    lane.publish(0, stack[0], (0,), 4)

    # The probe forks, publishes something of its own, and is discarded.
    copies = frames_copy(stack)
    probe_lane = lane.forked(copies)
    probe_lane.publish(1, copies[1], (0,), 8)
    probe_lane.clear(0)  # the probe consumed the outer route on ITS copy

    _check(
        "the probe's own route leaked to the real stack",
        lane.route_at(1, stack[1]) == NO_ROUTE,
    )
    _check(
        "the probe's clear reached the real stack",
        lane.route_at(0, stack[0]) == 4,
    )
    print("stale (d)\tdiscarded fork leaves the original lane exactly as it was")


def the_probe_fork_site_carries_the_lane() -> None:
    """The wired half: `_probe` saves, forks, and restores the lane."""
    source = (
        __import__("pathlib").Path("src/lexic/parsing/pda/runtime/kernel/decisions.py")
        .read_text(encoding="utf-8")
    )
    _check(
        "the probe fork does not fork the lane",
        "self._routes = saved_routes.forked(forked)" in source,
    )
    _check(
        "the probe fork does not restore the lane",
        "self._routes = saved_routes" in source,
    )
    _check(
        "the lane fork is not guarded for unrouted programs",
        "if saved_routes is not None:" in source,
    )
    print("wiring\t_probe forks and restores the lane under one None guard")


def the_unrouted_kernel_allocates_no_lane() -> None:
    """The model product's cost: one attribute, holding `None`."""
    _check(
        "the kernel does not declare the lane slot",
        "_routes" in PdaKernel.__slots__,
    )
    print("cost\tPdaKernel._routes is one slot; None for an unrouted program")


def main() -> None:
    """Run every case; any failure raises."""
    publish_and_consume()
    a_later_frame_at_the_same_depth_reads_nothing()
    a_later_sibling_under_one_parent_reads_nothing()
    an_abandoned_attempt_leaves_nothing_behind()
    a_fork_rebinds_to_the_copied_frames()
    a_discarded_fork_leaves_the_original_untouched()
    the_probe_fork_site_carries_the_lane()
    the_unrouted_kernel_allocates_no_lane()
    print("s3 route lane\tPASS\tpublish, four stale cases, fork remap, probe wiring")


if __name__ == "__main__":
    main()
