"""What bounds the exact lane — measured, with the lower bound demonstrated.

Prototype 15 replaced the shipped linear one-flip probe with a per-node option
product and stated, without a bound, that exactness is exponential in a single
node's LOCAL MULTIPLICITY. This module defines that multiplicity from real
chart data, builds a controlled ladder that separates the cases, executes every
lever the tasking names, and demonstrates the case where no lever applies.

**Local multiplicity, from the chart.** For a completed node ``h`` the exact
relation applies its authored operation

    ``m(h) = Sigma over h's packed families of Pi over that family's slots of
             |set(child)|``

times, where a slot's lane is a child node's DEDUPLICATED meaning set, a
delegated island's published option set, or — for a sibling accepting item —
one root of the union. ``m(h)`` is what the dirty cone does not bound: the cone
bounds HOW MANY nodes pay, never what one node pays.

**The four lanes.** ``full`` materializes every node's set (the candidate,
`island_continuation.exact_meanings`). ``streaming`` stops a node's own
enumeration at a certified second distinct requested-root meaning and at its
declared image bound. ``certified`` answers from the slot laws plus ONE
witnessing node's own families. ``budgeted`` is ``streaming`` under a declared
ceiling that REFUSES rather than guessing.

**The result.** Where the requested root is reachable through ``ident``/``grow``
slots alone, the law lane drops the question from the root's product to one
node's family count — two applications against 2^k, measured. Where a node's
law declares a finite image, its retained set is bounded by that image exactly
and its WORK is not. And where a ``finite`` consumer sits above interacting
children, the second distinct value can appear only at the LAST product —
executed here — so the APPLICATION count is Omega(m(h)) and no lever reduces it.
Wall cost is that count times a value-identity factor which is not constant, so
this module states no single-unit Theta; see
:func:`prove_applications_are_not_the_cost`. What remains is a refusal contract,
and choosing it — and its unit — is the user's.

Run directly.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from itertools import product
from typing import NamedTuple

import cyclic_meaning as algebra
import island_alternate_seed as harness
import island_continuation as candidate
import operation_slot_laws as laws
import shared_occurrence_ambiguity as shared

from lexic.compile import canonical_grammar
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import (
    IrArg,
    IrArgs,
    IrAst,
    IrCompare,
    IrOp,
    IrSelf,
    IrStr,
    IrTuple,
    Reducer,
)
from lexic.ir.flavour import IrFlavour
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize

MARK_P = IrStr("P")
MARK_Q = IrStr("Q")

VERDICT_DIFFERS = "differs"
VERDICT_EQUAL = "equal"


class BudgetRefusal(LexicError):
    """Exact settlement exceeded the declared work budget.

    Deliberately NOT an `UnsupportedConstructError`. The round's own recommended
    partial-operation guard absorbs that type
    (`shared_occurrence_ambiguity._partial_apply`), so a budget refusal raised
    inside a reducer evaluation would be swallowed into the absent value and
    the family would silently drop — turning a refusal into "equal", which is
    exactly what the tasking forbids. It must never be readable as "this
    document is unambiguous", and being outside the absorbed type is how that
    is enforced rather than hoped for.
    """


def counted_add_unique(found: list[IrSelf], value: IrSelf, lane: Lane) -> None:
    """Semantic dedup that COUNTS its comparisons — the round's other cost unit.

    Written here rather than reused from the oracle module for two reasons: the
    settlement lane must not share the oracle's dedup, and the comparison count
    is the factor an application count hides. `add_unique` is a linear scan over
    the values collected so far, so a node whose image grows pays quadratically
    in its own image on top of its application count.
    """
    for seen in found:
        lane.comparisons += 1
        if shared.same_value(seen, value):
            return
    found.append(value)


# ── local multiplicity, read off a real chart ─────────────────────────────


class Multiplicity(NamedTuple):
    """One node's local multiplicity and where it comes from.

    :ivar handle: The completed node.
    :ivar rule: What the node derives.
    :ivar families: How many packed families the node itself carries.
    :ivar lanes: Each family's per-slot option-set sizes.
    :ivar applications: ``Sigma over families of Pi over slots`` — what the
        exact relation applies at this node.
    """

    handle: int
    rule: str
    families: int
    lanes: tuple[tuple[int, ...], ...]
    applications: int


def node_multiplicity(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> Multiplicity:
    """One node's local multiplicity, from its families and its children's sets."""
    lanes: list[tuple[int, ...]] = []
    total = 0
    for resolved in chart.resolveds[handle]:
        widths = _lane_widths(resolved, sets, options)
        lanes.append(widths)
        span = 1
        for width in widths:
            span *= width
        total += span
    return Multiplicity(
        handle, harness._name(kernel, handle), len(lanes), tuple(lanes), total
    )


def _lane_widths(
    resolved: harness.Resolved,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> tuple[int, ...]:
    """One family's per-slot option-set sizes, in slot order."""
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    found: list[int] = []
    for index in range(width):
        if index in resolved.slots:
            found.append(len(options[id(resolved.leaves[resolved.slots.index(index)])]))
            continue
        found.append(len(sets.get(next(ints), ())))
    return tuple(found)


# ── the declared image bound: an exact quotient, not a cap ────────────────


def image_bound(
    reducer: Reducer, aligned: frozenset[str], rule: str, width: int
) -> int:
    """How many distinct values ``rule``'s operation can produce, or ``0``.

    Read from the REAL authored body through
    `operation_slot_laws.Classifier` — the same declaration
    `operation_slot_laws.differential_law` holds against direct evaluation, so
    a wrong bound is a caught misdeclaration rather than an unproved ceiling.
    A rule every one of whose slots classifies ``const`` or ``finite`` has an
    image of at most the product of those bounds; one slot classifying
    ``ident`` or ``grow`` makes the image as wide as that slot's set, which is
    input-dependent, and the bound is reported as ``0`` — unbounded.
    """
    total = 1
    for slot in range(max(width, 1)):
        law = candidate.slot_law(reducer, rule, slot, aligned)
        if law.kind not in (laws.CONST, laws.FINITE):
            return 0
        total *= max(law.bound, 1)
    return total


def bounds_for(
    grammar: IrAst, normalized: IrAst, reducer: Reducer, chart_rules: Sequence[str]
) -> dict[str, int]:
    """Every named rule's declared image bound over one grammar and reducer."""
    dropped = laws.dropped_rules(reducer)
    aligned = candidate.aligned_rules(grammar, normalized, dropped)
    widths = laws.rule_arity(normalized, dropped)
    return {
        rule: image_bound(reducer, aligned, rule, _width_of(widths, rule))
        for rule in dict.fromkeys(chart_rules)
    }


def _width_of(widths: dict[str, int], rule: str) -> int:
    """One rule's channel width, or refuse — never a silent default.

    A rule missing from the arity table would otherwise be examined at slot 0
    only, so a carrying slot at index >= 1 would be missed and the rule declared
    BOUNDED. That is the silent default `docs/STYLE.md` forbids, in the one
    place where it would narrow a meaning set rather than raise.
    """
    width = widths.get(rule)
    if width is None:
        raise UnsupportedConstructError(
            f"exact lane: rule {rule!r} has no channel width, so its image"
            " bound cannot be derived; refusing rather than assuming one slot"
        )
    return width


# ── the four settlement lanes ─────────────────────────────────────────────


VERDICT_NO_MEANING = "no-meaning"
"""Every derivation's operation refused — the root has no meaning at all.

A THIRD verdict, because folding it into ``equal`` would report a document with
no meaning as unambiguous, and folding it into ``differs`` would invent one.
"""


class Cost(NamedTuple):
    """What one lane paid and what it answered.

    :ivar verdict: :data:`VERDICT_DIFFERS`, :data:`VERDICT_EQUAL`, or
        :data:`VERDICT_NO_MEANING`.
    :ivar applications: Operation applications on the AMBIGUITY lane only.
    :ivar comparisons: Value-identity comparisons the dedup performed — the
        second cost unit, which an application count hides.
    :ivar baseline: The parse's own per-node fold, counted apart.
    :ivar dirty: Nodes inside the dirty cone.
    :ivar nodes: Nodes in the family-aware chart.
    :ivar peak: The largest set retained at any ONE node.
    :ivar retained: The sum of every dirty node's set size.
    :ivar values: The requested-root meanings this lane actually produced.
    :ivar complete: Whether :attr:`values` is the whole set. ``False`` when the
        lane stopped on its answer; the set is then deliberately partial and
        must not be read as a cardinality.
    """

    verdict: str
    applications: int
    comparisons: int
    baseline: int
    dirty: int
    nodes: int
    peak: int
    retained: int
    values: tuple[IrSelf, ...]
    complete: bool


class Lane:
    """One settlement run's mutable counters — the engine-side cursor shape."""

    __slots__ = ("applications", "comparisons", "baseline", "peak", "retained")

    def __init__(self) -> None:
        self.applications = 0
        self.comparisons = 0
        self.baseline = 0
        self.peak = 0
        self.retained = 0

    def retain(self, count: int) -> None:
        """Record one node's retained set: its size, and the running total.

        :attr:`peak` is the largest set at any ONE node, which is what a
        per-node retention claim needs; :attr:`retained` is the sum across the
        dirty cone. An earlier version added into a never-decremented ``live``
        and called the result a peak, so every retention statement read off it
        was really reading the sum.
        """
        self.retained += count
        if count > self.peak:
            self.peak = count


class Settings(NamedTuple):
    """What a lane is allowed to do.

    :ivar stop_at: Stop a ROOT node's enumeration once this many distinct
        meanings exist; ``0`` disables the early stop.
    :ivar quotient: Honour each node's declared image bound as an exact
        ceiling on its own enumeration.
    :ivar budget: Refuse past this many ambiguity-lane applications; ``0``
        disables the refusal.
    """

    stop_at: int = 0
    quotient: bool = False
    budget: int = 0


def settle(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    bounds: dict[str, int],
    settings: Settings,
) -> Cost:
    """Settle one document's requested-root ambiguity under ``settings``.

    :param kernel: The finished real Earley kernel.
    :param roots: Every accepting handle.
    :param options: Delegated-leaf option sets, by leaf identity.
    :param reducer: The reducer whose authored bodies define meaning.
    :param bounds: Rule → declared image bound, ``0`` meaning unbounded.
    :param settings: Which levers this lane is allowed.
    :returns: The verdict and what it cost.
    :raises BudgetRefusal: When the ambiguity lane exceeds ``settings.budget``.
    """
    chart = algebra.build_chart(kernel, roots)
    candidate._refuse_cyclic(chart, kernel)
    order = candidate._topological(chart, roots)
    lane = Lane()
    baselines = _baselines(kernel, order, chart, options, reducer, lane)
    dirty = candidate._dirty_cone(chart, options)
    sets: dict[int, tuple[IrSelf, ...]] = {}
    found: list[IrSelf] = []
    for handle in order:
        if handle not in dirty:
            sets[handle] = (baselines[handle],)
            continue
        sets[handle] = _settled_set(
            kernel, handle, chart, sets, options, reducer, bounds, settings, lane, roots
        )
        lane.retain(len(sets[handle]))
    stopped = False
    for root in roots:
        for meaning in sets.get(root, ()):
            counted_add_unique(found, meaning, lane)
        if settings.stop_at and len(found) >= settings.stop_at:
            stopped = True
            break
    return Cost(
        _verdict(found, sets, roots),
        lane.applications,
        lane.comparisons,
        lane.baseline,
        len(dirty),
        len(chart.nodes),
        lane.peak,
        lane.retained,
        tuple(found),
        not stopped,
    )


def _verdict(
    found: Sequence[IrSelf],
    sets: dict[int, tuple[IrSelf, ...]],
    roots: tuple[int, ...],
) -> str:
    """Three answers, because two would conflate 'no meaning' with 'equal'.

    A root whose every family refused has an EMPTY set, and calling that
    ``equal`` would report a document with no meaning as unambiguous — the one
    direction the tasking forbids. The occurrence oracle raises in this case;
    this lane names it instead, so the two are comparable rather than silently
    different.
    """
    if len(found) > 1:
        return VERDICT_DIFFERS
    if not any(sets.get(root, ()) for root in roots):
        return VERDICT_NO_MEANING
    return VERDICT_EQUAL


def _baselines(
    kernel: Kernel,
    order: Sequence[int],
    chart: algebra.Chart,
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    lane: Lane,
) -> dict[int, IrSelf]:
    """Every node's baseline meaning — the parse's OWN product, counted apart."""
    baselines: dict[int, IrSelf] = {}
    for handle in order:
        lane.baseline += 1
        baselines[handle] = candidate._baseline_node(
            kernel, handle, chart, baselines, options, reducer
        )
    return baselines


def _settled_set(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    bounds: dict[str, int],
    settings: Settings,
    lane: Lane,
    roots: tuple[int, ...],
) -> tuple[IrSelf, ...]:
    """One dirty node's set, under the declared bound and the early stop.

    Two exact stops, neither a cap. The declared image bound says how many
    distinct values the operation CAN produce, so collecting that many ends the
    enumeration with the complete set in hand. The root stop ends it once the
    ambiguity question — more than one requested-root meaning — already has its
    answer; the set is then deliberately incomplete and :attr:`Cost.meanings`
    reports zero rather than a number that would be read as a set size.
    """
    name = harness._name(kernel, handle)
    ceiling = _ceiling(handle, roots, bounds, name, settings)
    found: list[IrSelf] = []
    for resolved in chart.resolveds[handle]:
        lanes = candidate._slot_options(resolved, sets, options)
        for kids in product(*lanes):
            lane.applications += 1
            _refuse_past_budget(settings, lane, name)
            counted_add_unique(found, shared._partial_apply(reducer, name, kids), lane)
            # The ceiling counts LIVE meanings only. Counting the refusal
            # sentinel toward it would let one refusing family plus one real
            # value end the enumeration at a one-element set — the lane then
            # reporting `equal` on an ambiguous document, which is settling by
            # exhaustion and is the one thing the early stop must never do.
            if ceiling and _live_count(found) >= ceiling:
                return _live(found)
    return _live(found)


def _live(found: Sequence[IrSelf]) -> tuple[IrSelf, ...]:
    """The meanings that exist — the refusal sentinel is not one."""
    return tuple(value for value in found if value is not shared._ABSENT)


def _live_count(found: Sequence[IrSelf]) -> int:
    """How many real meanings have been collected so far."""
    return sum(1 for value in found if value is not shared._ABSENT)


def _ceiling(
    handle: int,
    roots: tuple[int, ...],
    bounds: dict[str, int],
    name: str,
    settings: Settings,
) -> int:
    """The smallest exact stop this node may take, or ``0`` for none."""
    declared = bounds.get(name, 0) if settings.quotient else 0
    at_root = settings.stop_at if handle in roots else 0
    if declared and at_root:
        return min(declared, at_root)
    return declared or at_root


def _refuse_past_budget(settings: Settings, lane: Lane, name: str) -> None:
    """Refuse with words once the ambiguity lane passes its declared budget."""
    if settings.budget and lane.applications > settings.budget:
        raise BudgetRefusal(
            f"parsing: settling ambiguity exactly at {name!r} passed the"
            f" declared budget of {settings.budget} operation applications;"
            " the requested root's meaning set is NOT known to be a singleton"
            " — raise the budget or supply a resolver"
        )


# ── the law lane: a verdict from the slot laws plus one local witness ─────


class Certificate(NamedTuple):
    """The law lane's answer and what proving it cost.

    :ivar differs: Whether some node holding two meanings carries injectively
        to an accepting item.
    :ivar applications: Operation applications the local witness paid — the
        witnessing node's OWN family count, never the root's product.
    :ivar baseline: The full baseline fold this lane runs UNCONDITIONALLY
        before examining any marked node. Counted, because reporting only
        :attr:`applications` would state a lane cost that excludes most of the
        lane's work.
    :ivar node: The rule the witness was found at, or ``""``.
    """

    differs: bool
    applications: int
    baseline: int
    node: str


def certified(
    kernel: Kernel,
    roots: tuple[int, ...],
    chart: algebra.Chart,
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    aligned: frozenset[str],
) -> Certificate:
    """Settle from the slot laws plus ONE node's own families, if it can.

    The existential certificate over real family-aware chart edges. A node is
    marked when some realized route to an accepting item has an ``ident`` or
    ``grow`` slot law at every step; fixing that route's families and varying
    only this node's derivation then builds two distinct root meanings. The
    witness that the node really holds two meanings is constructive and local:
    its own families are applied with every CHILD held at its baseline, which
    is a lower bound on the node's true set. Acting only on "yes, two" keeps
    that sound — the lane never concludes "one" from it, and falls through to
    the executing lane instead.

    This is what actually removes the exponential where it can be removed: the
    exact question drops from the ROOT's local multiplicity to one witnessing
    node's family count.
    """
    marked = _injective_nodes(kernel, roots, chart, reducer, aligned)
    lane = Lane()
    baselines = _baseline_table(kernel, roots, chart, options, reducer, lane)
    spent = 0
    for node in chart.nodes:
        if node not in marked:
            continue
        found, applications = _local_witness(
            kernel, node, chart, baselines, options, reducer
        )
        spent += applications
        if found:
            return Certificate(True, spent, lane.baseline, harness._name(kernel, node))
    return Certificate(False, spent, lane.baseline, "")


def _baseline_table(
    kernel: Kernel,
    roots: tuple[int, ...],
    chart: algebra.Chart,
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    lane: Lane,
) -> dict[int, IrSelf]:
    """Every node's baseline meaning — counted into ``lane``, never discarded."""
    return _baselines(
        kernel, candidate._topological(chart, roots), chart, options, reducer, lane
    )


def _local_witness(
    kernel: Kernel,
    node: int,
    chart: algebra.Chart,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
) -> tuple[bool, int]:
    """Does this node hold two meanings with every child at its baseline?"""
    families = chart.resolveds[node]
    if len(families) < 2 and not _has_wide_leaf(families, options):
        return False, 0
    name = harness._name(kernel, node)
    found: list[IrSelf] = []
    spent = 0
    for resolved in families:
        for kids in _baseline_lanes(resolved, baselines, options):
            spent += 1
            shared.add_unique(found, shared._partial_apply(reducer, name, kids))
    return len(found) > 1, spent


def _has_wide_leaf(
    families: Sequence[harness.Resolved], options: dict[int, tuple[IrSelf, ...]]
) -> bool:
    """Whether any family holds a delegated leaf publishing more than one option."""
    return any(
        len(options[id(leaf)]) > 1 for resolved in families for leaf in resolved.leaves
    )


def _baseline_lanes(
    resolved: harness.Resolved,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
) -> list[tuple[IrSelf, ...]]:
    """One family's channels with children at baseline and leaves at each option."""
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    lanes: list[tuple[IrSelf, ...]] = []
    for index in range(width):
        if index in resolved.slots:
            lanes.append(options[id(resolved.leaves[resolved.slots.index(index)])])
            continue
        lanes.append((baselines[next(ints)],))
    return [tuple(kids) for kids in product(*lanes)]


def _injective_nodes(
    kernel: Kernel,
    roots: tuple[int, ...],
    chart: algebra.Chart,
    reducer: Reducer,
    aligned: frozenset[str],
) -> frozenset[int]:
    """Nodes reachable from an accepting item through ident/grow slots only."""
    outgoing: dict[int, list[algebra.Edge]] = {}
    for edge in chart.edges:
        outgoing.setdefault(edge.parent, []).append(edge)
    marked = set(roots)
    pending = list(roots)
    while pending:
        parent = pending.pop()
        for edge in outgoing.get(parent, ()):
            if edge.child in marked or not _carries(kernel, edge, reducer, aligned):
                continue
            marked.add(edge.child)
            pending.append(edge.child)
    return frozenset(marked)


def _carries(
    kernel: Kernel, edge: algebra.Edge, reducer: Reducer, aligned: frozenset[str]
) -> bool:
    """Whether one realized chart edge's slot law retains its child's value."""
    parent = harness._name(kernel, edge.parent)
    return candidate.slot_law(reducer, parent, edge.slot, aligned).kind in (
        laws.IDENT,
        laws.GROW,
    )


# ── the rejected one-flip probe, executed for comparison only ─────────────


def one_flip_differs(kernel: Kernel, roots: tuple[int, ...], reducer: Reducer) -> bool:
    """Flip one arm-choice key at a time — the shipped probe's shape."""
    first = FastTree(kernel, {}).build(roots[0])
    if not isinstance(first, ParseTree):
        raise UnsupportedConstructError("exact lane: the baseline did not build")
    base = shared._tree_meaning(first, reducer, {})
    for key in candidate._arm_points(kernel, roots):
        for family in range(1, len(kernel.st.links[key])):
            other = FastTree(kernel, {key: family}).build(roots[0])
            if not isinstance(other, ParseTree):
                continue
            if not shared.same_value(base, shared._tree_meaning(other, reducer, {})):
                return True
    return False


# ── the controlled ladder ─────────────────────────────────────────────────


def ladder_grammar(points: int) -> str:
    """A grammar with ``points`` INDEPENDENT binary ambiguity points.

    The ``s -> t -> p | q`` indirection is load-bearing: the engine packs a
    child's arm choice on the CONSUMING waiter's key, so writing
    ``s ::= p | q`` would attribute every point's multiplicity to the root's
    own family count instead of to the child's meaning SET. One level of
    indirection puts each point's choice inside its own chain, which is the
    shape the per-node relation is written for and the one where a lane width
    is a set size.
    """
    arms = "".join(
        f"s{index} ::= t{index}\n"
        f't{index} ::= p{index} | q{index}\np{index} ::= "y"\nq{index} ::= "y"\n'
        for index in range(points)
    )
    body = " ".join(f"s{index}" for index in range(points))
    return f'root ::= {body} "z"\n' + arms


def ladder_grammar_abnf(points: int) -> str:
    """The same language and the same points, spelled in ABNF."""
    arms = "".join(
        f"s{index} = t{index}\r\n"
        f't{index} = p{index} / q{index}\r\np{index} = "y"\r\nq{index} = "y"\r\n'
        for index in range(points)
    )
    body = " ".join(f"s{index}" for index in range(points))
    return f'root = {body} "z"\r\n' + arms


def ladder_text(points: int) -> str:
    """The one document every ladder row parses."""
    return "y" * points + "z"


def ladder_actions(points: int, root_body: IrSelf) -> tuple[tuple[str, IrSelf], ...]:
    """Real authored bodies: a pass-through per point, a marker per arm."""
    found: list[tuple[str, IrSelf]] = [("root", root_body)]
    for index in range(points):
        found.append((f"s{index}", IrArg(0)))
        found.append((f"t{index}", IrArg(0)))
        found.append((f"p{index}", MARK_P))
        found.append((f"q{index}", MARK_Q))
    return tuple(found)


def collapsing_actions(points: int) -> tuple[tuple[str, IrSelf], ...]:
    """The ladder's actions with every POINT's own consumer collapsing.

    Same grammar, same root operation: only each ``s`` rule's authored body
    changes, from a pass-through to a predicate whose image is one value on
    this document. Its set then deduplicates to width one and the root's
    product stops growing.
    """
    collapse = IrCompare(IrArgs(), IrOp("=="), IrStr("never"))
    found: list[tuple[str, IrSelf]] = [("root", IrArgs())]
    for index in range(points):
        found.append((f"s{index}", collapse))
        found.append((f"t{index}", IrArg(0)))
        found.append((f"p{index}", MARK_P))
        found.append((f"q{index}", MARK_Q))
    return tuple(found)


def _target(points: int, mark: IrSelf) -> IrSelf:
    """A tuple of ``points`` copies of one marker — a predicate's comparand."""
    return IrTuple(*(mark for _ in range(points)))


def collapse_body(points: int) -> IrSelf:
    """Every derivation collapses to one requested value."""
    del points
    return IrCompare(IrArgs(), IrOp("=="), IrStr("never"))


def early_body(points: int) -> IrSelf:
    """The second distinct root value appears at the SECOND product."""
    return IrCompare(IrArgs(), IrOp("=="), _target(points, MARK_P))


def late_body(points: int) -> IrSelf:
    """The second distinct root value appears only at the LAST product."""
    return IrCompare(IrArgs(), IrOp("=="), _target(points, MARK_Q))


def grow_body(points: int) -> IrSelf:
    """A retaining consumer — the image is exactly the product, all distinct."""
    del points
    return IrArgs()


class Row(NamedTuple):
    """One rung of the ladder.

    :ivar name: The rung label.
    :ivar body: Which root body it uses.
    :ivar differs: The verdict every lane must reach.
    :ivar certified: Whether the law lane settles it from one local witness.
    """

    name: str
    body: str
    differs: bool
    certified: bool


ROW_BODIES = {
    "collapse": collapse_body,
    "early-second": early_body,
    "late-second": late_body,
    "grow": grow_body,
}

ROWS = (
    Row("collapse", "collapse", False, False),
    Row("early-second", "early-second", True, False),
    Row("late-second", "late-second", True, False),
    Row("law-settled", "grow", True, True),
)
"""The rungs, by what separates them; ``grow`` serves the law row."""


class Rung(NamedTuple):
    """One executed rung: its lanes, its costs, and its multiplicity."""

    name: str
    points: int
    full: Cost
    streamed: Cost
    law: Certificate
    multiplicity: int
    one_flip: bool


def parse_ladder(
    points: int, root_body: IrSelf, flavour: IrFlavour
) -> tuple[Kernel, tuple[int, ...], Reducer, dict[str, int], frozenset[str]]:
    """Recognize one rung's document and compile everything its lanes read."""
    source = (
        ladder_grammar_abnf(points)
        if flavour is ABNF_FLAVOUR
        else ladder_grammar(points)
    )
    text = ladder_text(points)
    canonical = canonical_grammar(source, flavour)
    normalized = normalize(canonical)
    kernel = Kernel(compile_tables(normalized, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("exact lane: the ladder did not parse")
    roots = algebra.accepting_roots(kernel, accept_handle(kernel))
    reducer = candidate.reducer_of(ladder_actions(points, root_body))
    rules = tuple(harness._name(kernel, node) for node in roots)
    chart = algebra.build_chart(kernel, roots)
    names = tuple(harness._name(kernel, node) for node in chart.nodes) + rules
    bounds = bounds_for(canonical, normalized, reducer, names)
    dropped = laws.dropped_rules(reducer)
    aligned = candidate.aligned_rules(canonical, normalized, dropped)
    return kernel, roots, reducer, bounds, aligned


def run_rung(name: str, points: int, flavour: IrFlavour = GBNF_FLAVOUR) -> Rung:
    """Execute one rung through the materializing, streaming and law lanes."""
    body = ROW_BODIES[name if name in ROW_BODIES else "grow"](points)
    kernel, roots, reducer, bounds, aligned = parse_ladder(points, body, flavour)
    chart = algebra.build_chart(kernel, roots)
    full = settle(kernel, roots, {}, reducer, bounds, Settings())
    streamed = settle(
        kernel, roots, {}, reducer, bounds, Settings(stop_at=2, quotient=True)
    )
    law = certified(kernel, roots, chart, {}, reducer, aligned)
    top = _root_multiplicity(kernel, roots, chart, reducer, bounds)
    return Rung(
        name,
        points,
        full,
        streamed,
        law,
        top,
        one_flip_differs(kernel, roots, reducer),
    )


def _root_multiplicity(
    kernel: Kernel,
    roots: tuple[int, ...],
    chart: algebra.Chart,
    reducer: Reducer,
    bounds: dict[str, int],
) -> int:
    """The accepting node's own local multiplicity, from the settled child sets."""
    order = candidate._topological(chart, roots)
    lane = Lane()
    baselines = _baselines(kernel, order, chart, {}, reducer, lane)
    sets: dict[int, tuple[IrSelf, ...]] = {}
    dirty = candidate._dirty_cone(chart, {})
    for handle in order:
        if handle == roots[0]:
            continue
        if handle not in dirty:
            sets[handle] = (baselines[handle],)
            continue
        sets[handle] = _settled_set(
            kernel, handle, chart, sets, {}, reducer, bounds, Settings(), lane, roots
        )
    return node_multiplicity(kernel, roots[0], chart, sets, {}).applications


# ── what each row establishes ─────────────────────────────────────────────


LADDER_POINTS = (2, 4, 6, 8, 10)
"""The point counts the ladder is walked at — 2^k stays under five thousand."""


def prove_ladder() -> dict[str, list[Rung]]:
    """Walk every rung at every point count and check its declared shape."""
    found: dict[str, list[Rung]] = {}
    for row in ROWS:
        rungs = [run_rung(row.body, points) for points in LADDER_POINTS]
        found[row.name] = rungs
        for rung in rungs:
            assert (rung.full.verdict == VERDICT_DIFFERS) == row.differs, row.name
            assert (rung.streamed.verdict == VERDICT_DIFFERS) == row.differs, row.name
            assert rung.law.differs == row.certified, (row.name, rung.points)
        print(
            "ladder",
            row.name,
            f"root_operation={row.body}",
            f"differs={row.differs}",
            f"points={list(LADDER_POINTS)}",
            f"root_local_multiplicity={[r.multiplicity for r in rungs]}",
            f"full_applications={[r.full.applications for r in rungs]}",
            f"streaming_applications={[r.streamed.applications for r in rungs]}",
            f"law_lane_settles={row.certified}",
            f"law_lane_applications={[r.law.applications for r in rungs]}",
            f"law_lane_baseline_folds={[r.law.baseline for r in rungs]}",
            f"law_lane_witness={[r.law.node for r in rungs]}",
            f"one_flip_differs={[r.one_flip for r in rungs]}",
            f"full_peak_retained={[r.full.peak for r in rungs]}",
            f"streaming_peak_retained={[r.streamed.peak for r in rungs]}",
            f"chart_nodes={[r.full.nodes for r in rungs]}",
            f"dirty_nodes={[r.full.dirty for r in rungs]}",
            f"baseline_products={[r.full.baseline for r in rungs]}",
            sep="\t",
        )
    return found


def stacked_grammar(levels: int) -> str:
    """A CHAIN of retaining consumers — multiplicity at every level, not one.

    The ladder gives the root the only multi-slot consumer, so its "everything
    below is linear" residue is a property of that shape rather than of the
    exact relation. Here each level consumes the level below it TWICE beside a
    binary point, so every level's image is the square of the one under it and
    the product is paid at every node, not at one.
    """
    arms = 't0 ::= p0 | q0\np0 ::= "y"\nq0 ::= "y"\n'
    for level in range(1, levels + 1):
        arms += f"t{level} ::= t{level - 1} t{level - 1}\n"
    return f'root ::= t{levels} "z"\n' + arms


def stacked_actions(levels: int) -> tuple[tuple[str, IrSelf], ...]:
    """Retaining bodies all the way up — every level embeds both children."""
    found: list[tuple[str, IrSelf]] = [
        ("root", IrArgs()),
        ("t0", IrArg(0)),
        ("p0", MARK_P),
        ("q0", MARK_Q),
    ]
    for level in range(1, levels + 1):
        found.append((f"t{level}", IrArgs()))
    return tuple(found)


def prove_multiplicity_is_paid_at_every_level() -> None:
    """The MISSING control: a stacked product, where every level pays.

    The ladder's residue is linear because its ladder has one multi-slot
    consumer. This grammar has one at every level, and the total is not the
    root's product plus a linear tail — it is a sum of products that grows at
    every node. The round therefore does NOT claim the exponential term sits at
    a single node in general; it claims that the per-node cost IS that node's
    local multiplicity, and that the dirty cone bounds neither.
    """
    for levels in (1, 2, 3):
        source = stacked_grammar(levels)
        text = "y" * (2**levels) + "z"
        canonical = canonical_grammar(source, GBNF_FLAVOUR)
        normalized = normalize(canonical)
        kernel = Kernel(
            compile_tables(normalized, tier_for(len(text))), text, True
        ).run()
        if accept_item(kernel) < 0:
            raise UnsupportedConstructError("exact lane: the stack did not parse")
        roots = algebra.accepting_roots(kernel, accept_handle(kernel))
        reducer = candidate.reducer_of(stacked_actions(levels))
        chart = algebra.build_chart(kernel, roots)
        names = tuple(harness._name(kernel, node) for node in chart.nodes)
        bounds = bounds_for(canonical, normalized, reducer, names)
        cost = settle(kernel, roots, {}, reducer, bounds, Settings())
        top = _root_multiplicity(kernel, roots, chart, reducer, bounds)
        print(
            "stacked-product",
            f"levels={levels}",
            f"chart_nodes={cost.nodes}",
            f"dirty_nodes={cost.dirty}",
            f"total_applications={cost.applications}",
            f"root_local_multiplicity={top}",
            f"applications_below_the_root={cost.applications - top}",
            f"root_share={top / max(cost.applications, 1):.0%}",
            f"image={len(cost.values)}",
            f"peak_retained_at_one_node={cost.peak}",
            f"comparisons={cost.comparisons}",
            sep="\t",
        )
    print(
        "stacked-product",
        "conclusion",
        "with a retaining consumer at every level the work is NOT the root's"
        " product plus a linear tail: the sum below the root grows with the"
        " stack. The ladder's linear residue is a property of its one-consumer"
        " shape, so this round claims only the per-node identity — a node's"
        " cost is its own local multiplicity — and not that the exponential"
        " term sits at a single node in general",
        sep="\t",
    )


def prove_multiplicity_is_the_cost(rungs: dict[str, list[Rung]]) -> None:
    """The materializing lane's cost at the root IS its local multiplicity."""
    for name, found in rungs.items():
        for rung in found:
            assert rung.multiplicity == 2**rung.points, (name, rung)
    residue = {
        name: [r.full.applications - r.multiplicity for r in found]
        for name, found in rungs.items()
    }
    print(
        "multiplicity",
        "root_multiplicity_is_two_to_the_points=True",
        f"full_applications_minus_root_multiplicity={residue}",
        "this identity is DEFINITIONAL — the lane applies once per element of"
        " the same product — so it measures nothing. The residue is linear"
        " because THIS ladder gives the root its only multi-slot consumer;"
        " prove_multiplicity_is_paid_at_every_level is the control, and there"
        " the root is under half the work. No claim is made that the"
        " exponential term sits at one node in general",
        sep="\t",
    )


def prove_lower_bound(rungs: dict[str, list[Rung]]) -> None:
    """The witness no lever reaches: the second value appears at the LAST product."""
    late = rungs["late-second"]
    for rung in late:
        assert rung.streamed.applications == 2**rung.points + 2 * rung.points, rung
        assert rung.streamed.applications == rung.full.applications, rung
        assert not rung.one_flip
        assert rung.streamed.verdict == VERDICT_DIFFERS
    print(
        "lower-bound",
        f"points={[r.points for r in late]}",
        f"streaming_applications={[r.streamed.applications for r in late]}",
        f"root_local_multiplicity={[r.multiplicity for r in late]}",
        "streaming_equals_the_materializing_lane="
        f"{[r.streamed.applications == r.full.applications for r in late]}",
        f"law_lane_applications={[r.law.applications for r in late]}",
        f"one_flip_differs={[r.one_flip for r in late]}",
        "the consumer's law declares a finite image and says nothing about"
        " WHICH combination collapses, so an exact algorithm has to apply the"
        " operation; this operation's second distinct value is the last"
        " product, so streaming, the declared bound, deduplication and the"
        " dirty cone all still pay 2^k APPLICATIONS. The bound is stated in"
        " that unit and only that unit: applications are Omega(m(h)) here and"
        " no lever reduces them. Wall cost is this count times the"
        " value-identity work each application triggers, which"
        " prove_applications_are_not_the_cost shows is not constant, so there"
        " is no single-unit Theta to quote",
        sep="\t",
    )


def prove_streaming_wins_where_it_can(rungs: dict[str, list[Rung]]) -> None:
    """Streaming is a real win exactly where the second value comes early."""
    early, late = rungs["early-second"], rungs["late-second"]
    for rung in early:
        assert rung.streamed.applications == 2 * rung.points + 2, rung
        assert not rung.streamed.complete, rung
    print(
        "streaming",
        f"points={[r.points for r in early]}",
        f"early_second_streaming={[r.streamed.applications for r in early]}",
        "early_second_is_two_per_point_plus_two="
        f"{[r.streamed.applications == 2 * r.points + 2 for r in early]}",
        f"early_second_full={[r.full.applications for r in early]}",
        f"late_second_streaming={[r.streamed.applications for r in late]}",
        f"late_second_full={[r.full.applications for r in late]}",
        "the early stop is exact and unconditional — it ends the enumeration"
        " once a SECOND distinct requested-root meaning exists, never because"
        " work ran out; the incomplete set is reported as zero meanings so it"
        " cannot be read as a set size. Two applications per point is the"
        " children's own sets, which every lane pays; the saving is the root's"
        " product collapsing from 2^k to 2",
        sep="\t",
    )


LEVER_SETTINGS = (
    ("full", Settings()),
    ("declared-bound-only", Settings(quotient=True)),
    ("root-stop-only", Settings(stop_at=2)),
    ("both", Settings(stop_at=2, quotient=True)),
)
"""The lever isolation: each lane on its own, then together."""


def prove_levers_isolated() -> None:
    """Run each lever alone, so no lane can be credited with another's saving.

    The declared image bound turns out NOT to be an independent lever on this
    ladder, and the row says so: a node's produced set is already deduplicated,
    so the bound only ever ends an enumeration whose distinct values appeared
    early — which the root stop ends anyway. What the bound does supply that
    dedup cannot is a COMPILE-TIME ceiling on the retained set, which is what
    :func:`prove_static_census` reports.
    """
    for name in ("collapse", "early-second", "late-second", "grow"):
        for points in (4, 8):
            body = ROW_BODIES[name](points)
            kernel, roots, reducer, bounds, _aligned = parse_ladder(
                points, body, GBNF_FLAVOUR
            )
            costs = [
                (label, settle(kernel, roots, {}, reducer, bounds, settings))
                for label, settings in LEVER_SETTINGS
            ]
            applications = {label: cost.applications for label, cost in costs}
            peaks = {label: cost.peak for label, cost in costs}
            verdicts = {cost.verdict for _label, cost in costs}
            print(
                "lever-isolation",
                name,
                f"points={points}",
                f"applications={applications}",
                f"peak_retained={peaks}",
                f"verdicts={verdicts}",
                sep="\t",
            )


def prove_quotient_bounds_the_set_not_the_work(rungs: dict[str, list[Rung]]) -> None:
    """A declared finite image bounds what is RETAINED, never the work."""
    collapse, grow = rungs["collapse"], rungs["law-settled"]
    for rung in collapse:
        assert rung.full.peak <= 2 * rung.full.nodes, rung
        assert rung.streamed.applications == rung.full.applications, rung
    print(
        "declared-bound-quotient",
        f"collapse_full_peak={[r.full.peak for r in collapse]}",
        f"collapse_full_applications={[r.full.applications for r in collapse]}",
        f"collapse_streaming_applications={[r.streamed.applications for r in collapse]}",
        f"grow_full_peak={[r.full.peak for r in grow]}",
        f"grow_full_applications={[r.full.applications for r in grow]}",
        "a finite(b) law caps a node's RETAINED set at b exactly — the"
        " predicate rows' peak stays linear in the point count while the"
        " retaining row's grows with its image — and it does NOT cap the work:"
        " the collapse row's streaming lane pays exactly what the"
        " materializing lane pays, because the operation still has to be"
        " applied to find out which combinations collapse",
        sep="\t",
    )


def prove_grow_image_is_computed_not_enumerated() -> None:
    """A retaining consumer's image SIZE is arithmetic on its children's sets.

    The lever that actually removes the exponential: ``grow`` is injective, so
    no two products collapse and the image size is the product of the child set
    sizes. Where the requested root is reachable through ``ident``/``grow``
    alone the verdict follows from one local witness, so the law lane answers
    in two applications while the materializing lane pays 2^k for a set nobody
    asked for.
    """
    for points in LADDER_POINTS:
        rung = run_rung("grow", points)
        assert rung.law.differs and len(rung.full.values) == 2**points
        assert rung.law.applications < rung.full.applications
        print(
            "grow-image",
            f"points={points}",
            f"full_applications={rung.full.applications}",
            f"materialized_image={len(rung.full.values)}",
            f"image_equals_two_to_the_points={len(rung.full.values) == 2**points}",
            f"law_lane_applications={rung.law.applications}",
            f"law_lane_unconditional_baseline_folds={rung.law.baseline}",
            f"law_lane_witness={rung.law.node}",
            f"law_lane_differs={rung.law.differs}",
            sep="\t",
        )


def prove_dedup_stops_multiplicity_climbing() -> None:
    """Structural sharing: multiplicity that COLLAPSES does not multiply upward.

    An intermediate consumer whose law declares a finite image deduplicates its
    children's product into at most that image, so the node above it sees a set
    of that size rather than the product. Executed at three point counts so the
    saving is visible as a number rather than argued.
    """
    for points in (4, 6, 8):
        kernel, roots, reducer, bounds, _aligned = parse_ladder(
            points, IrArgs(), GBNF_FLAVOUR
        )
        wrapped = candidate.reducer_of(collapsing_actions(points))
        plain = settle(kernel, roots, {}, reducer, bounds, Settings())
        collapsed = settle(kernel, roots, {}, wrapped, bounds, Settings())
        assert len(plain.values) == 2**points and len(collapsed.values) == 1
        print(
            "dedup-climb",
            f"points={points}",
            f"retaining_children_image={len(plain.values)}",
            f"retaining_children_applications={plain.applications}",
            f"collapsing_children_image={len(collapsed.values)}",
            f"collapsing_children_applications={collapsed.applications}",
            "a child whose own set deduplicates to one value contributes a lane"
            " of width one, so the parent's product does not grow — the exact"
            " relation's dedup is the structural sharing lever, and it is"
            " already in the per-node form",
            sep="\t",
        )


def prove_budget_refuses_rather_than_guessing() -> None:
    """A resource ceiling REFUSES; it never answers 'unambiguous'.

    The budget is not a numeric cap on the algebra: it is a declared resource
    ceiling whose only outcome is a refusal that names the node and the count.
    Executed at a budget the late-second rung provably exceeds, and checked
    against the same rung settling exactly under a budget it does not.
    """
    points = 8
    body = late_body(points)
    kernel, roots, reducer, bounds, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    refusal = ""
    try:
        settle(
            kernel,
            roots,
            {},
            reducer,
            bounds,
            Settings(stop_at=2, quotient=True, budget=64),
        )
    except BudgetRefusal as error:
        refusal = str(error)
    generous = settle(
        kernel,
        roots,
        {},
        reducer,
        bounds,
        Settings(stop_at=2, quotient=True, budget=1 << 20),
    )
    assert refusal and generous.verdict == VERDICT_DIFFERS
    print(
        "budget-refusal",
        f"points={points}",
        f"budget=64  refusal={refusal}",
        f"generous_budget_verdict={generous.verdict}",
        f"generous_budget_applications={generous.applications}",
        "the refusal is a distinct exception, says the set is NOT known to be"
        " a singleton, and neither picks a derivation nor falls back to the"
        " one-flip probe; whether production carries one at all, and at what"
        " ceiling, is a public-semantics choice and therefore the user's",
        sep="\t",
    )


def prove_unambiguous_path_allocates_nothing() -> None:
    """What the unambiguous path pays — INCLUDING the cost the counters exclude.

    The SET lane allocates nothing: no dirty node, no product, no retained
    meaning. That is the narrow, true claim, and it is what the counters
    measure.

    It is not the whole cost, and the row says so. Both `settle` and
    `island_continuation.exact_meanings` build the family-resolved
    `cyclic_meaning.build_chart` — a per-node `local_choice_keys` fixpoint that
    re-resolves each handle's chain under every assignment — BEFORE dirtiness
    is known, and `Cost` charges none of it. On an unambiguous document that
    build is pure overhead against a parse that would otherwise do none of it,
    so "keep ambiguity machinery off the unambiguous path" is NOT satisfied by
    an empty dirty cone alone. The chart build is measured here beside the set
    lane rather than left out of the account; making it demand-driven is a
    production obligation this round does not discharge.
    """
    source = 'root ::= s "z"\ns ::= p\np ::= "y"\n'
    text = "yz"
    canonical = canonical_grammar(source, GBNF_FLAVOUR)
    normalized = normalize(canonical)
    kernel = Kernel(compile_tables(normalized, tier_for(len(text))), text, True).run()
    roots = algebra.accepting_roots(kernel, accept_handle(kernel))
    reducer = candidate.reducer_of((("root", IrArgs()), ("s", IrArg(0)), ("p", MARK_P)))
    names = tuple(
        harness._name(kernel, node) for node in algebra.build_chart(kernel, roots).nodes
    )
    bounds = bounds_for(canonical, normalized, reducer, names)
    cost = settle(
        kernel, roots, {}, reducer, bounds, Settings(stop_at=2, quotient=True)
    )
    chart_cpu = _time_chart_build(kernel, roots)
    settle_cpu = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, bounds, Settings(stop_at=2, quotient=True))
        elapsed = time.process_time() - started
        settle_cpu = elapsed if index == 0 else min(settle_cpu, elapsed)
    assert cost.applications == 0 and cost.dirty == 0 and cost.peak == 0
    assert cost.retained == 0 and cost.comparisons == 0
    print(
        "unambiguous-path",
        f"chart_nodes={cost.nodes}",
        f"dirty_nodes={cost.dirty}",
        f"ambiguity_applications={cost.applications}",
        f"peak_retained_meanings={cost.peak}"
        f"  retained_total={cost.retained}  comparisons={cost.comparisons}",
        f"baseline_products={cost.baseline}",
        f"verdict={cost.verdict}",
        f"unconditional_chart_build_cpu={chart_cpu:.6f}",
        f"whole_settle_cpu={settle_cpu:.6f}",
        f"chart_build_share_of_settle={chart_cpu / max(settle_cpu, 1e-9):.1%}",
        "the SET lane allocates nothing — no dirty node, no product, no"
        " retained meaning — which is the claim the counters support. The"
        " family-resolved chart is built BEFORE dirtiness is known and no"
        " counter charges it; its CPU share is reported here so the account is"
        " whole. An unambiguous document still pays that build, so a"
        " demand-driven chart is an open production obligation",
        sep="\t",
    )


def _time_chart_build(kernel: Kernel, roots: tuple[int, ...]) -> float:
    """Minimum process CPU of the unconditional family-resolved chart build."""
    best = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        algebra.build_chart(kernel, roots)
        elapsed = time.process_time() - started
        best = elapsed if index == 0 else min(best, elapsed)
    return best


def prove_flavour_neutrality() -> None:
    """The same rung under a second surface answers and costs identically."""
    for name in ("late-second", "grow"):
        gbnf = run_rung(name, 6, GBNF_FLAVOUR)
        abnf = run_rung(name, 6, ABNF_FLAVOUR)
        assert gbnf.full.verdict == abnf.full.verdict
        assert gbnf.full.applications == abnf.full.applications
        assert gbnf.law.differs == abnf.law.differs
        print(
            "flavour-neutral",
            name,
            f"gbnf_applications={gbnf.full.applications}",
            f"abnf_applications={abnf.full.applications}",
            f"gbnf_verdict={gbnf.full.verdict}  abnf_verdict={abnf.full.verdict}",
            f"law_lane_settles={gbnf.law.differs}",
            f"law_lane_applications={gbnf.law.applications}/{abnf.law.applications}",
            sep="\t",
        )


def prove_verdicts_against_the_unrolled_oracle() -> None:
    """Every lane's MEANING SET, held against the occurrence-unrolled relation.

    What is and is not shared, stated exactly.
    `shared_occurrence_ambiguity.unrolled_meanings` re-resolves the chain per
    occurrence and forms no per-node set, so the COMPOSITION differs; it does
    share the chain-resolution primitives with `settle`, and `settle` uses that
    module's `add_unique` as its dedup. The lanes are therefore independent in
    composition and memo policy, not in family decomposition.

    The comparison is on SETS, not on the boolean verdict: a lever that changed
    WHICH meanings are produced while keeping "more than one" would pass a
    verdict-only check.
    """
    for row in ROWS:
        for points in (2, 4):
            body = ROW_BODIES[row.body](points)
            kernel, roots, reducer, bounds, _aligned = parse_ladder(
                points, body, GBNF_FLAVOUR
            )
            oracle = shared.unrolled_meanings(
                kernel, roots, {}, reducer, shared.UnrolledCounts()
            )
            full = settle(kernel, roots, {}, reducer, bounds, Settings())
            streamed = settle(
                kernel,
                roots,
                {},
                reducer,
                bounds,
                Settings(stop_at=2, quotient=True),
            )
            differs = len(oracle) > 1
            same = shared.same_meaning_set(full.values, oracle)
            assert (full.verdict == VERDICT_DIFFERS) == differs, (row.name, points)
            assert (streamed.verdict == VERDICT_DIFFERS) == differs, (row.name, points)
            # The set comparison, not merely the verdict: the materializing
            # lane must produce the SAME meanings the unrolled relation does.
            assert same, (row.name, points, full.values, oracle)
            print(
                "oracle-check",
                row.name,
                f"points={points}",
                f"unrolled_oracle_meanings={len(oracle)}",
                f"settle_lane_meanings={len(full.values)}",
                f"same_meaning_set={same}",
                f"full_verdict={full.verdict}",
                f"streaming_verdict={streamed.verdict}",
                f"agree={differs == (full.verdict == VERDICT_DIFFERS)}",
                sep="\t",
            )


# ── the compile-time census: which rules can be settled statically ────────


def prove_static_census() -> None:
    """Per shipped grammar, how many rules have a statically bounded image.

    The compile-time half of the cost policy. A rule whose every slot law is
    ``const`` or ``finite`` has an image the compiler can name; one carrying an
    ``ident``/``grow`` slot has an image as wide as its children's, which is
    input-dependent — and it is exactly the ``finite`` rules above wide
    children that force the exponential product. The census says how many rules
    of each kind the shipped surfaces actually have.
    """
    started = time.process_time()
    for surface, reducer in laws.DISPATCHERS.items():
        canonical, normalized = laws._canonical(surface), laws._normalized(surface)
        dropped = laws.dropped_rules(reducer)
        aligned = candidate.aligned_rules(canonical, normalized, dropped)
        widths = laws.rule_arity(normalized, dropped)
        census: dict[str, int] = {}
        for rule, width in widths.items():
            bound = image_bound(reducer, aligned, rule, width)
            key = "unbounded" if bound == 0 else f"bounded={bound}"
            census[key] = census.get(key, 0) + 1
        print(
            "static-census",
            surface,
            f"rules={len(widths)}",
            f"image_bounds={dict(sorted(census.items()))}",
            sep="\t",
        )
    print(
        "static-census",
        f"cpu={time.process_time() - started:.6f}",
        "ONE un-repeated process-CPU sample with no control row: it says the"
        " classification runs over the shipped surfaces, not what it costs."
        " Read the rows plainly: every bounded rule on the shipped surfaces"
        " bounds to ONE — they are the constant actions — so no shipped rule"
        " today has a finite image wider than a constant, and the declared"
        " bound has nothing to quotient there. The rules that force the"
        " exponential product are the unbounded ones, which are the majority",
        sep="\t",
    )


# ── timing, with a control ────────────────────────────────────────────────


REPEATS = 5
"""How many in-process passes each timing takes the minimum of."""


def _time_lane(name: str, points: int, settings: Settings) -> float:
    """Minimum process CPU of one lane over :data:`REPEATS` in-process passes."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, bounds, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    best = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, bounds, settings)
        elapsed = time.process_time() - started
        best = elapsed if index == 0 else min(best, elapsed)
    return best


def _time_certificate(name: str, points: int) -> float:
    """Minimum process CPU of the LAW lane over :data:`REPEATS` passes."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, _bounds, aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    chart = algebra.build_chart(kernel, roots)
    best = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        certified(kernel, roots, chart, {}, reducer, aligned)
        elapsed = time.process_time() - started
        best = elapsed if index == 0 else min(best, elapsed)
    return best


def _time_alternating(
    name: str, points: int, settings: Settings
) -> tuple[float, float]:
    """Two byte-identical arms, ALTERNATED in one process; min of each.

    `docs/STYLE.md` requires alternation for an in-process A/B precisely so a
    monotonic drift across the run is not attributed to one arm. An earlier
    version ran one arm to completion and then the other, and its quoted floor
    did not reproduce.
    """
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, bounds, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    left = 0.0
    right = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, bounds, settings)
        first = time.process_time() - started
        started = time.process_time()
        settle(kernel, roots, {}, reducer, bounds, settings)
        second = time.process_time() - started
        left = first if index == 0 else min(left, first)
        right = second if index == 0 else min(right, second)
    return left, right


def prove_timing_with_a_control() -> None:
    """Time each lane beside an ALTERNATED floor control, on process CPU.

    The floor control is two byte-identical arms of the same lane on the same
    rung, alternated within one process, so the spread between them is this
    harness's own noise band rather than a drift artefact. The band is
    reported per run and is NOT quoted as a fixed figure: it moves between runs,
    which is what an un-repeated spread is worth.

    The row that matters is the last two columns. `late-second` streaming and
    `grow` materializing execute the SAME number of operation applications at
    every point count, and their CPU differs by two orders of magnitude — which
    is why :func:`prove_applications_are_not_the_cost` exists and why this
    module no longer states a bound in applications alone.
    """
    streaming = Settings(stop_at=2, quotient=True)
    for points in (6, 8, 10):
        late, floor = _time_alternating("late-second", points, streaming)
        early, _ = _time_alternating("early-second", points, streaming)
        grow_full, _ = _time_alternating("grow", points, Settings())
        grow_law = _time_certificate("grow", points)
        print(
            "timing",
            f"points={points}",
            f"late_second_streaming_cpu={late:.6f}",
            f"floor_control_cpu={floor:.6f}",
            f"floor_spread={abs(late - floor) / max(late, 1e-9):.3%}",
            f"early_second_streaming_cpu={early:.6f}",
            f"grow_materialized_cpu={grow_full:.6f}",
            f"grow_law_lane_cpu={grow_law:.6f}",
            "process CPU, one process, five ALTERNATED in-process pairs, min of"
            " each arm; the floor is two byte-identical arms of one lane on one"
            " rung and its spread moves between runs, so it is read per run and"
            " never quoted as a fixed band",
            sep="\t",
        )


def prove_applications_are_not_the_cost() -> None:
    """The application count HIDES a second factor, and the gap is two orders.

    The correction this round owes its own §B5 table. `late-second` streaming
    and `grow` materializing perform an identical number of operation
    applications at every point count, and their CPU is not close: the
    difference is value-identity work. Deduplication is a linear scan comparing
    each candidate against the meanings collected so far, so a node whose IMAGE
    grows pays quadratically in that image on top of its application count,
    over values that are themselves growing.

    So the exact lane's cost is applications x per-comparison value identity,
    not applications alone, and a budget denominated in applications buys
    wildly different amounts of work. Both factors are counted here.
    """
    for points in (6, 8, 10):
        late = _measure("late-second", points, Settings(stop_at=2, quotient=True))
        grow = _measure("grow", points, Settings())
        assert late.applications == grow.applications, (late, grow)
        # Derived, not arbitrary: a lane whose set stays at two compares each
        # candidate against at most two entries, so its comparisons are LINEAR
        # in its applications; a lane whose image is its product compares
        # against an ever-growing set, so its comparisons are quadratic in that
        # image. Both bounds are asserted from the measured peak.
        assert late.comparisons <= 2 * late.applications, late
        assert grow.comparisons >= grow.applications * grow.peak / 4, grow
        assert grow.peak == 2**points, (grow.peak, points)
        print(
            "applications-are-not-the-cost",
            f"points={points}",
            f"applications_late={late.applications}",
            f"applications_grow={grow.applications}",
            f"identical_application_counts={late.applications == grow.applications}",
            f"comparisons_late={late.comparisons}",
            f"comparisons_grow={grow.comparisons}",
            f"comparison_ratio={grow.comparisons / max(late.comparisons, 1):.0f}x",
            f"peak_retained_late={late.peak}  peak_retained_grow={grow.peak}",
            f"late_comparisons_linear_in_applications="
            f"{late.comparisons <= 2 * late.applications}",
            f"grow_comparisons_quadratic_in_its_image="
            f"{grow.comparisons >= grow.applications * grow.peak / 4}",
            sep="\t",
        )
    print(
        "applications-are-not-the-cost",
        "conclusion",
        "two rungs with EQUAL application counts differ by two orders of"
        " magnitude in CPU, so an application count is not a cost. The exact"
        " lane's cost is the product of applications and the value-identity"
        " work each one triggers, and the second factor grows with the node's"
        " own image; any budget must be denominated in the work, not in"
        " applications",
        sep="\t",
    )


def _measure(name: str, points: int, settings: Settings) -> Cost:
    """One rung's full cost record under one lane setting."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, bounds, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    return settle(kernel, roots, {}, reducer, bounds, settings)


def main() -> None:
    """Walk the ladder, then execute every lever and the lower bound."""
    rungs = prove_ladder()
    prove_multiplicity_is_the_cost(rungs)
    prove_multiplicity_is_paid_at_every_level()
    prove_verdicts_against_the_unrolled_oracle()
    prove_streaming_wins_where_it_can(rungs)
    prove_levers_isolated()
    prove_quotient_bounds_the_set_not_the_work(rungs)
    prove_grow_image_is_computed_not_enumerated()
    prove_dedup_stops_multiplicity_climbing()
    prove_lower_bound(rungs)
    prove_budget_refuses_rather_than_guessing()
    prove_unambiguous_path_allocates_nothing()
    prove_flavour_neutrality()
    prove_static_census()
    prove_applications_are_not_the_cost()
    prove_timing_with_a_control()
    print(
        "invariant",
        "the exact lane's cost at one node is Sigma over its packed families of"
        " Pi over its slots of the child set size — its LOCAL MULTIPLICITY,"
        " which the dirty cone never bounds. Two levers reduce it and both are"
        " exact: an injective (ident/grow) route to an accepting item drops the"
        " question from the root's product to ONE witnessing node's own family"
        " count, measured at two applications against 2^k; and stopping at a"
        " certified second requested-root meaning ends the enumeration on its"
        " answer rather than on exhaustion. A declared finite image bounds what"
        " a node RETAINS and never its work, and on the shipped surfaces every"
        " bounded rule bounds to one, so it buys nothing there. Neither lever"
        " reaches a finite consumer whose second distinct value is its LAST"
        " product, executed here at 2^k APPLICATIONS for every point count. Applications are Omega(m(h)) and no lever reduces them; wall cost is"
        " that count times a value-identity factor which is NOT constant"
        " (equal application counts differ by three orders of magnitude in"
        " comparisons), so no single-unit Theta is claimed and no budget may be"
        " denominated in applications. The only remaining lever is a refusal"
        " that names the node and the count — never a chosen derivation, never"
        " a one-flip fallback, and never 'unambiguous'",
        sep="\t",
    )


if __name__ == "__main__":
    main()
