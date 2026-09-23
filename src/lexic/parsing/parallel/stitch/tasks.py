"""Divided regions bound to stitch plans, and their units flattened to tasks."""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.discovery.partition import Division, Unit
from lexic.parsing.parallel.stitch.merge import MergeRequest, assign_witnesses
from lexic.parsing.parallel.stitch.plan import RegionWork, derive_plan
from lexic.parsing.parallel.stitch.safety import owner_excludes


def region_works[M](
    request: MergeRequest[M],
    grammar: IrAst,
    divided: list[Division[Region]],
    analysis: IrAst,
) -> list[RegionWork]:
    """Bind divided regions to safe, exact model-stitch plans.

    The cuts are the ones :func:`~lexic.parsing.parallel.discovery.partition.partition`
    made — never re-derived here, where another count would aim at other
    marks and the stitch would rebuild separators the pieces never lost. A
    region without a safe plan is left undivided: its text stays with
    whatever holds it, and the others still divide.

    :returns: The regions that divide; empty when none does.
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
    return assign_witnesses(request, works)


def region_tasks(
    grammar: IrAst, works: list[RegionWork], plan: list[Unit]
) -> list[tuple[IrAst, str]]:
    """One ``(grammar, text)`` task per unit: a piece under its region's rooted
    grammar, the shell under the document's.

    The parse VIEW is deliberately not chosen here: it belongs to the worker
    thread that ends up running the task, not to the task's position in this
    list — see :func:`~lexic.parsing.parallel.replicas.worker_parse`.
    """
    return [
        (works[unit.owner].plan.root if unit.owner >= 0 else grammar, unit.text)
        for unit in plan
    ]
