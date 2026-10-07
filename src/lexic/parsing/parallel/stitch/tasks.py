"""Divided regions bound to stitch plans."""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.partition import Division
from lexic.parsing.parallel.stitch.merge import MergeRequest, assign_witnesses
from lexic.parsing.parallel.stitch.plan import RegionWork, derive_plan
from lexic.parsing.parallel.stitch.safety import owner_excludes


def region_works[M](
    request: MergeRequest[M],
    grammar: IrAst,
    divided: list[Division[Region]],
    analysis: IrAst,
) -> list[RegionWork]:
    """:func:`bound_works`, each given its stand-in (:func:`assign_witnesses`).

    :returns: The regions that divide; empty when none does.
    """
    return assign_witnesses(request, bound_works(request, grammar, divided, analysis))


def bound_works[M](
    request: MergeRequest[M],
    grammar: IrAst,
    divided: list[Division[Region]],
    analysis: IrAst,
) -> list[RegionWork]:
    """Bind divided regions to safe, exact model-stitch plans — no stand-ins
    yet, so the pieces that need none can be parsed while they are chosen.

    The cuts are the ones :func:`~lexic.parsing.parallel.discovery.partition.partition`
    made — never re-derived here, where another count would aim at other
    marks and the stitch would rebuild separators the pieces never lost. A
    region without a safe plan is left undivided: its text stays with
    whatever holds it, and the others still divide.

    :returns: The regions with a safe plan, in document order.
    """
    text, works = request.text, []
    for region, cuts in divided:
        plan = derive_plan(grammar, request.binding, region.rule)
        if plan is None or not owner_excludes(
            analysis, plan.head_rule, plan.separator, region_scan=True
        ):
            continue
        if all(text[mark] == plan.separator for mark in region.marks):
            works.append(RegionWork(region, cuts, plan))
    return works
