"""Divided regions bound to stitch plans."""

from __future__ import annotations

from lexic.ir import IrAst
from lexic.parsing.parallel.discovery.partition import Division
from lexic.parsing.parallel.discovery.regions import Region
from lexic.parsing.parallel.stitch.merge import MergeRequest, assign_witnesses
from lexic.parsing.parallel.stitch.plan import (
    RegionPlan,
    RegionWork,
    bracket_rule,
    derive_plan,
)
from lexic.parsing.parallel.stitch.safety import owner_excludes, terminates_once


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
        rule = bracket_rule(grammar, region.rule, text[region.opener])
        plan = derive_plan(grammar, request.binding, rule)
        if plan is None or not safe_leads(analysis, plan):
            continue
        if all(text[mark] in plan.separators for mark in region.marks):
            works.append(RegionWork(region, cuts, plan))
    return works


def safe_leads(analysis: IrAst, plan: RegionPlan) -> bool:
    """Whether every mark of the plan's lead set is a boundary of its run.

    Per owner and per character: the head cannot spell any lead where the scan
    reads it (:func:`~...stitch.safety.owner_excludes`) — for a terminated run,
    every visible terminator in the unit is its last character
    (:func:`~...stitch.safety.terminates_once`) — and nothing else in
    the bracket arm can emit one (:attr:`RegionPlan.around`, ANY where it
    cannot be read), so a lead at the region's depth stands between two items.
    """
    proof = terminates_once if plan.ends else owner_excludes
    return not any(plan.around.has(lead) for lead in plan.separators) and all(
        proof(analysis, plan.head_rule, lead, region_scan=True)
        for lead in plan.separators
    )
