"""Region pieces flattened onto one parse task and owner each."""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.regions import Division
from lexic.parsing.parallel.stitch.merge import MergeRequest, assign_witnesses
from lexic.parsing.parallel.stitch.plan import RegionWork, derive_plan
from lexic.parsing.parallel.stitch.safety import owner_excludes


def region_works[M](
    request: MergeRequest[M],
    grammar: IrAst,
    divided: list[Division],
    analysis: IrAst,
) -> list[RegionWork] | None:
    """Bind discovered regions to safe, exact model-stitch plans.

    The cuts are the ones :func:`~lexic.parsing.parallel.discovery.regions.choose`
    cut the pieces at — never re-derived here, where another count would aim at
    other marks and the stitch would rebuild separators the pieces never lost.
    """
    text, works = request.text, []
    for region, parts, cuts in divided:
        plan = derive_plan(grammar, request.binding, region.rule)
        safe = plan is not None and owner_excludes(
            analysis, plan.head_rule, plan.separator, region_scan=True
        )
        marks_match = plan is not None and all(
            text[mark] == plan.separator for mark in region.marks
        )
        if not safe or not marks_match:
            return None
        assert plan is not None
        works.append(RegionWork(region, parts, cuts, plan))
    return assign_witnesses(request, works) if works else None


def region_tasks(works: list[RegionWork]) -> tuple[list[tuple[IrAst, str]], list[int]]:
    """Flatten pieces to one ``(grammar, text)`` task and owner each.

    The parse VIEW is deliberately not chosen here: it belongs to the worker
    thread that ends up running the task, not to the task's position in this
    list — see :func:`~lexic.parsing.parallel.replicas.worker_parse`.

    :param works: Chosen regions with their piece texts and model plans.
    :returns: Parse inputs and the owning-region index for each input.
    """
    tasks: list[tuple[IrAst, str]] = []
    owners: list[int] = []
    for owner, work in enumerate(works):
        for part in work.parts:
            tasks.append((work.plan.root, part))
            owners.append(owner)
    return tasks, owners
