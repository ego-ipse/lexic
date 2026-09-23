"""Which split plans a grammar admits, and which a safety proof licenses.

Derivation reads the grammar's shape: a terminated repetition, a separated
one, an envelope container, or, last and only by proposal, a repetition whose
openings the text must confirm. Certification asks each plan the proof its
shape owes over the caller's view. Both are per grammar and memoised; nothing
here reads a document, which is :mod:`~lexic.parsing.parallel.orchestrate`'s.
"""

from __future__ import annotations

from lexic.ir import (
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.discovery.shapes import UNIT, unbounded
from lexic.parsing.parallel.plan.cuts import sole_mark
from lexic.parsing.parallel.plan.envelope import envelope_plans
from lexic.parsing.parallel.plan.speculation import speculative_openings
from lexic.parsing.parallel.plan.split import SplitPlan, lead_skip, spellings
from lexic.parsing.parallel.roles import Roles, Separator, Terminator, roles
from lexic.parsing.parallel.stitch.safety import (
    bounds_units,
    mark_interiors,
    mark_overlap,
    owner_excludes,
    scan_agrees,
    terminates_once,
    unit_boundary,
)


def _unit_ref(item: IrItem) -> str | None:
    """The unit rule an item references, when it is a plain unit reference."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and item.quantifier == UNIT:
        return str(atom)
    return None


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The rule's only arm, when it has exactly one."""
    arms = tuple(rule.body)
    return tuple(arms[0]) if len(arms) == 1 else None


def _item_shape(rule: IrRule, sep: Separator, unit: str) -> bool:
    """Whether the repeated rule is ``lead unit`` for this separator."""
    items = _single_arm(rule)
    if items is None or len(items) != 2 or _unit_ref(items[1]) != unit:
        return False
    lead_atom = items[0].atom
    if sep.lead:
        return _unit_ref(items[0]) == sep.lead
    return isinstance(lead_atom, IrLiteral) and str(lead_atom) == sep.mark


def _wrapper_chain(
    rule_map: dict[str, IrRule], start: str, target: str
) -> tuple[str, ...] | None:
    """Head-reference route from ``start`` through empty-capable tails."""
    wrappers: list[str] = []
    seen: set[str] = set()
    current = start
    while current != target:
        rule = rule_map.get(current)
        items = _single_arm(rule) if rule is not None else None
        child = _unit_ref(items[0]) if items else None
        empty_tails = items is not None and all(
            unbounded(item) and item.quantifier.lo == 0 for item in items[1:]
        )
        if child is None or not empty_tails or current in seen:
            return None
        seen.add(current)
        wrappers.append(current)
        current = child
    return tuple(wrappers)


def _plan_for(
    grammar: IrAst, sep: Separator, rule_map: dict[str, IrRule]
) -> SplitPlan | None:
    """The plan one separator record admits, or ``None`` on a shape miss."""
    container = rule_map.get(sep.container)
    item_rule = rule_map.get(sep.item)
    if container is None or item_rule is None:
        return None
    wrappers = _wrapper_chain(rule_map, str(grammar.start), sep.container)
    if wrappers is None:
        return None
    items = _single_arm(container)
    if items is None or len(items) != 2:
        return None
    unit = _unit_ref(items[0])
    repeated = items[1].atom
    repeats = isinstance(repeated, IrRuleRef) and str(repeated) == sep.item
    if unit is None or not repeats or not _item_shape(item_rule, sep, unit):
        return None
    if sep.lead:
        lead_grammar, literal = IrAst(grammar.rules, sep.lead), ""
        skip = lead_skip(_single_arm(rule_map[sep.lead]), rule_map, sep.mark)
    else:
        lead_grammar, literal = None, sep.mark
        skip = frozenset()
    return SplitPlan(
        grammar,
        Scanner(roles(grammar)),
        frozenset({sep.mark}),
        spellings(frozenset({sep.mark})),
        unit,
        wrappers,
        sep,
        lead_grammar,
        literal,
        skip,
    )


def _terminated_plans(
    grammar: IrAst, rule_map: dict[str, IrRule]
) -> tuple[SplitPlan, ...]:
    """The plans a ``start ::= unit+`` terminated repetition admits.

    The start rule's only arm must be one unbounded reference to a unit that
    ends with an agreed anchor mark. Cuts land after the terminator, so each
    chunk holds whole units and parses under the start rule unchanged.
    Terminators a certified delimited region hides go to the scanner instead.

    One plan per agreed spelling, narrowest first: which of them a grammar can
    prove is the safety cascade's question, not this one's.
    """
    start = rule_map.get(str(grammar.start))
    if start is None:
        return ()
    items = _single_arm(start)
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return ()
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return ()
    derived = roles(grammar)
    unit = str(target)
    return tuple(
        SplitPlan(
            grammar,
            Scanner(derived, mark_interiors(grammar, unit, record.mark)),
            record.mark,
            spellings(record.mark),
            unit,
            (),
            None,
            None,
            "",
            frozenset(),
        )
        for record in derived.terminators
        if record.unit == unit and record.container == str(grammar.start)
    )


def _speculative_plans(
    grammar: IrAst, rule_map: dict[str, IrRule]
) -> tuple[SplitPlan, ...]:
    """The plan a ``start ::= unit+`` repetition admits by PROPOSAL.

    Read last, and only where every other route declined: this is the one plan
    whose cuts are candidates rather than boundaries, and it pays a piece parse
    to find out. The precondition it rests on is
    :func:`~...plan.speculation.speculative_openings`; an empty answer is the
    ordinary decline.

    The scan needs no new machinery — it sweeps a set of spellings already, so
    the unit's opening alphabet goes in where a terminator's would.
    """
    start = rule_map.get(str(grammar.start))
    items = _single_arm(start) if start is not None else None
    if items is None or len(items) != 1 or not unbounded(items[0]):
        return ()
    target = items[0].atom
    if not isinstance(target, IrRuleRef):
        return ()
    unit = str(target)
    openings = speculative_openings(grammar, unit)
    if not openings:
        return ()
    derived = roles(grammar)
    proposals = Roles(
        derived.pairs, (), (Terminator(openings, str(grammar.start), unit),)
    )
    return (
        SplitPlan(
            grammar,
            Scanner(proposals),
            openings,
            spellings(openings),
            unit,
            (),
            None,
            None,
            "",
            frozenset(),
            opening=True,
        ),
    )


_PLANS: dict[int, tuple[IrAst, tuple[SplitPlan, ...]]] = memo({})
"""Plan memo — id(grammar) → (grammar, plans). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def split_plans(grammar: IrAst) -> tuple[SplitPlan, ...]:
    """Every exact start-reachable plan, memoised per grammar identity."""
    entry = _PLANS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        terminated = _terminated_plans(grammar, rule_map)
        separated = tuple(
            plan
            for sep in roles(grammar).records
            if sep.item and (plan := _plan_for(grammar, sep, rule_map)) is not None
        )
        wrapped = _envelope_split_plan(grammar)
        proposed = _speculative_plans(grammar, rule_map)
        # Proposals are APPENDED, never an alternative: a derived plan that
        # then fails certification must not shadow them, and a certified one
        # must still be tried first — a proposal pays a piece parse to learn
        # what a proof already knows.
        plans = (terminated or separated or wrapped) + proposed
        entry = (grammar, plans)
        _PLANS[id(grammar)] = entry
    return entry[1]


def split_plan(grammar: IrAst) -> SplitPlan | None:
    """The grammar's split plan, memoised per identity; ``None`` = sequential.

    :param grammar: The codegen grammar (repetitions hoisted to rules).
    :returns: A plan when the START rule is a separated repetition whose
        shape the stitch supports; ``None`` otherwise.
    """
    plans = split_plans(grammar)
    return plans[0] if plans else None


def _certified(plan: SplitPlan, view: IrAst) -> SplitPlan | None:
    """The plan a safety proof licenses over ``view``, or ``None`` to drop it.

    Each shape owes a different proof, and a TERMINATED plan owes either of
    two. The first is that its unit emits the mark ONLY as its own final edge
    (``terminates_once``), which makes every mark a boundary and needs no
    filter. Failing that, the unit may still ANNOUNCE itself — the boundary
    proof — and the plan carries that prefix so :func:`_cut_offsets` can admit
    the marks that begin a unit and refuse the ones that do not. A unit with
    neither is what it always was: not splittable on this mark.
    """
    if plan.opening:
        # A proposal owes no boundary proof — the piece parse settles whether
        # it was right — but it owes the same AGREEMENT ``scan_agrees`` owes:
        # the precondition is derived on the grammar the pieces parse under,
        # and a caller-supplied view that licenses a different opening
        # alphabet is describing a different language, not a stricter one.
        return plan if speculative_openings(view, plan.owner) == plan.mark else None
    mark = sole_mark(plan)
    if plan.envelope is not None:
        return plan if unit_boundary(view, plan.owner, mark) is not None else None
    if plan.sep is None:
        return _certified_terminated(plan, view, mark)
    if not owner_excludes(view, plan.owner, mark):
        return None
    overlap = mark_overlap(view, plan.owner, mark)
    return plan._replace(trailing=overlap.trailing) if overlap.decided else None


def _certified_terminated(plan: SplitPlan, view: IrAst, mark: str) -> SplitPlan | None:
    """The three routes a terminated plan may be licensed by, in order.

    The agreed terminator first — every mark is a boundary and no filter is
    needed. Then the unit's whole ending alphabet, where the arms close
    differently and no ending character stands anywhere but at an end. Failing
    both, the unit may still ANNOUNCE itself, and the plan carries that prefix
    so the cut selection can admit the marks that begin a unit.
    """
    if (
        mark
        and terminates_once(view, plan.owner, mark)
        and scan_agrees(view, plan.grammar, plan.owner, plan.mark)
    ):
        return plan
    if bounds_units(view, plan.owner, plan.mark):
        return plan
    bound = unit_boundary(view, plan.owner, mark) if mark else None
    return None if bound is None else plan._replace(bound=bound)


def safe_plans(plans: tuple[SplitPlan, ...], view: IrAst) -> tuple[SplitPlan, ...]:
    """Every plan a safety proof licenses over ``view``, in cascade order."""
    return tuple(
        certified for plan in plans if (certified := _certified(plan, view)) is not None
    )


def _envelope_split_plan(grammar: IrAst) -> tuple[SplitPlan, ...]:
    """The plans an envelope container with a noise-run separator admits.

    Read last: a grammar whose start rule is a plain repetition is already
    served, and this shape costs a boundary proof to certify. One plan per
    PROVABLE mark — which of them a document actually carries is the
    orchestrator's question, settled by the first that yields cuts.
    """
    derived = roles(grammar)
    return tuple(
        SplitPlan(
            grammar,
            Scanner(derived),
            frozenset({found.mark}),
            spellings(frozenset({found.mark})),
            found.shape.unit,
            (),
            None,
            found.run.target,
            "",
            frozenset(),
            found,
        )
        for found in envelope_plans(grammar, str(grammar.start))
    )
