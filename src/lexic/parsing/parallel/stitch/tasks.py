"""Region pieces flattened onto distinct model-parse worker views."""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.fold import ModelFold
from lexic.parsing.parallel.discovery.regions import Region, piece_marks
from lexic.parsing.parallel.replicas import worker_replicas
from lexic.parsing.parallel.stitch.model import RegionWork, derive_plan
from lexic.parsing.parallel.stitch.safety import owner_excludes


def region_works[M](
    grammar: IrAst,
    fold: ModelFold[M],
    text: str,
    divided: list[tuple[Region, list[str]]],
    analysis: IrAst,
) -> list[RegionWork] | None:
    """Bind discovered regions to safe, exact model-stitch plans."""
    works: list[RegionWork] = []
    for region, parts in divided:
        plan = derive_plan(grammar, fold, region.rule)
        cuts = piece_marks(region, len(parts))
        safe = plan is not None and owner_excludes(
            analysis, plan.head_rule, plan.separator, region_scan=True
        )
        marks_match = plan is not None and all(
            text[mark] == plan.separator for mark in region.marks
        )
        if not safe or not marks_match or len(parts) != len(cuts) + 1:
            return None
        assert plan is not None
        works.append(RegionWork(region, parts, cuts, plan))
    return works or None


def region_tasks[M](
    works: list[RegionWork], fold: ModelFold[M]
) -> tuple[list[tuple[IrAst, ModelFold, str]], list[int]]:
    """Flatten pieces with one distinct parse view and owner per task.

    :param works: Chosen regions with their piece texts and model plans.
    :param fold: The model fold whose generated classes every view preserves.
    :returns: Parse inputs and the owning-region index for each input.
    """
    counts: dict[str, int] = {}
    for work in works:
        counts[work.region.rule] = counts.get(work.region.rule, 0) + len(work.parts)
    views = {
        work.region.rule: worker_replicas(
            work.plan.root, fold, counts[work.region.rule]
        )
        for work in works
    }
    used: dict[str, int] = {}
    tasks: list[tuple[IrAst, ModelFold, str]] = []
    owners: list[int] = []
    for owner, work in enumerate(works):
        for part in work.parts:
            at = used.get(work.region.rule, 0)
            used[work.region.rule] = at + 1
            grammar, view = views[work.region.rule][at]
            tasks.append((grammar, view, part))
            owners.append(owner)
    return tasks, owners
