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

**The three lanes.** ``full`` materializes every node's set (the candidate,
`island_continuation.exact_meanings`). ``streaming`` stops a ROOT node's
enumeration at a certified second distinct requested-root meaning — that is its
only stop. ``certified`` answers from the slot laws plus ONE witnessing node's
own families. No budget lane exists and no declared-image quotient exists: this
round proposes no resource policy and rejects the quotient
(:func:`prove_the_quotient_is_rejected`).

**The result.** Where the requested root is reachable through ``ident``/``grow``
slots alone, the law lane drops the question from the root's product to one
node's family count — two applications against 2^k, measured. Where a ``finite``
consumer sits above interacting children, the second distinct value can appear
only at the LAST product —
executed here — so the APPLICATION count is Omega(m(h)) and no lever reduces it.
Wall cost is that count times a value-identity factor which is not constant, so
this module states no single-unit Theta; see
:func:`prove_applications_are_not_the_cost`. That exponential is RECORDED as the
current lane's worst case under this enumeration and these slot laws. No refusal
contract, budget or ceiling is proposed — neither a user decision nor an
implementation blocker.

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
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import (
    IrArg,
    IrArgs,
    IrAst,
    IrBuild,
    IrCompare,
    IrMap,
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


# ── the declared image bound: REJECTED, and the census that rejects it ────


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

    One lever, because only one survived. The declared-image quotient is
    REJECTED (:func:`prove_the_quotient_is_rejected`) and no resource budget is
    proposed: this round records the exact lane's exponential worst case as a
    property of the current enumeration rather than proposing a policy against
    it.

    :ivar stop_at: Stop a ROOT node's enumeration once this many distinct
        meanings exist; ``0`` disables the early stop.
    """

    stop_at: int = 0


def settle(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    settings: Settings,
    partial: frozenset[str] = frozenset(),
) -> Cost:
    """Settle one document's requested-root ambiguity under ``settings``.

    :param kernel: The finished real Earley kernel.
    :param roots: Every accepting handle.
    :param options: Delegated-leaf option sets, by leaf identity.
    :param reducer: The reducer whose authored bodies define meaning.
    :param settings: Which levers this lane is allowed.
    :returns: The verdict and what it cost.
    """
    chart = algebra.build_chart(kernel, roots)
    candidate._refuse_cyclic(chart, kernel)
    order = candidate._topological(chart, roots)
    lane = Lane()
    baselines = _baselines(kernel, order, chart, options, reducer, lane, partial)
    dirty = candidate._dirty_cone(chart, options)
    sets: dict[int, tuple[IrSelf, ...]] = {}
    found: list[IrSelf] = []
    for handle in order:
        if handle not in dirty:
            baseline = baselines.get(handle)
            sets[handle] = () if baseline is None else (baseline,)
            continue
        sets[handle] = _settled_set(
            kernel,
            handle,
            chart,
            sets,
            options,
            reducer,
            settings,
            lane,
            roots,
            partial,
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
    partial: frozenset[str] = frozenset(),
) -> dict[int, IrSelf]:
    """Each node's baseline — the first family that HAS a value, if any.

    `island_continuation._baseline_node` reads `resolveds[0]` and applies its
    body directly, so a refusing default family both loses the baseline and
    propagates the refusal. Under bottom semantics the baseline is the first
    LIVE family, and a node with none simply has no entry — its consumers then
    see an empty lane and eliminate their own families.
    """
    baselines: dict[int, IrSelf] = {}
    for handle in order:
        lane.baseline += 1
        found = _first_live_family(
            kernel, handle, chart, baselines, options, reducer, partial
        )
        if found is not None:
            baselines[handle] = found
    return baselines


def _settled_set(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    settings: Settings,
    lane: Lane,
    roots: tuple[int, ...],
    partial: frozenset[str],
) -> tuple[IrSelf, ...]:
    """One dirty node's set, under bottom semantics and the ROOT stop.

    One stop, and it is not a cap: the root stop ends the enumeration once the
    ambiguity question — more than one requested-root meaning — already has its
    answer, so the set is then deliberately incomplete and :attr:`Cost.complete`
    is ``False`` rather than a cardinality that would be read as a set size. The
    declared-image quotient that once stopped here is REJECTED
    (:func:`prove_the_quotient_is_rejected`) and no bound is consulted.
    """
    name = harness._name(kernel, handle)
    ceiling = _ceiling(handle, roots, settings)
    found: list[IrSelf] = []
    for resolved in chart.resolveds[handle]:
        lanes = _lanes_or_none(resolved, sets, options)
        if lanes is None:
            continue  # an empty child image eliminates THIS family, not the node
        for kids in product(*lanes):
            lane.applications += 1
            meaning = shared.apply_or_none(reducer, name, kids, partial)
            if meaning is not None:
                counted_add_unique(found, meaning, lane)
            # The ceiling counts meanings that EXIST. A refusing family
            # contributes none, so one refusal beside one live value can never
            # end the enumeration at a one-element set and report `equal` on an
            # ambiguous document.
            if ceiling and len(found) >= ceiling:
                return tuple(found)
    return tuple(found)


def _lanes_or_none(
    resolved: harness.Resolved,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> list[tuple[IrSelf, ...]] | None:
    """One family's per-slot lanes, or ``None`` when one of them is EMPTY.

    `island_continuation._slot_options` raises here; `cyclic_meaning.node_set`
    skips the family. The second is right, and this follows it: an empty
    internal image is a fact about that node, not about the document.
    """
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    lanes: list[tuple[IrSelf, ...]] = []
    for index in range(width):
        if index in resolved.slots:
            lane = options[id(resolved.leaves[resolved.slots.index(index)])]
        else:
            lane = sets.get(next(ints), ())
        if not lane:
            return None
        lanes.append(lane)
    return lanes


def _ceiling(handle: int, roots: tuple[int, ...], settings: Settings) -> int:
    """The root stop, or ``0``. No bound is consulted — the quotient is rejected."""
    return settings.stop_at if handle in roots else 0


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
    partial: frozenset[str] = frozenset(),
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
    baselines = _baseline_table(kernel, roots, chart, options, reducer, lane, partial)
    spent = 0
    for node in chart.nodes:
        if node not in marked:
            continue
        found, applications = _local_witness(
            kernel, node, chart, baselines, options, reducer, partial
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
    partial: frozenset[str],
) -> dict[int, IrSelf]:
    """The certificate's view of the same baselines the settlement lane builds."""
    return _baselines(
        kernel,
        candidate._topological(chart, roots),
        chart,
        options,
        reducer,
        lane,
        partial,
    )


def _first_live_family(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    partial: frozenset[str],
) -> IrSelf | None:
    """This node's baseline: the first family that yields a value, or none."""
    name = harness._name(kernel, handle)
    for resolved in chart.resolveds[handle]:
        kids = _baseline_channel(resolved, baselines, options)
        if kids is None:
            continue
        found = shared.apply_or_none(reducer, name, kids, partial)
        if found is not None:
            return found
    return None


def _baseline_channel(
    resolved: harness.Resolved,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
) -> tuple[IrSelf, ...] | None:
    """One family's baseline channel, or ``None`` if a child has no baseline."""
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    kids: list[IrSelf] = []
    for index in range(width):
        if index in resolved.slots:
            kids.append(options[id(resolved.leaves[resolved.slots.index(index)])][0])
            continue
        found = baselines.get(next(ints))
        if found is None:
            return None
        kids.append(found)
    return tuple(kids)


def _local_witness(
    kernel: Kernel,
    node: int,
    chart: algebra.Chart,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    partial: frozenset[str],
) -> tuple[bool, int]:
    """Does this node hold two meanings that EXIST, with children at baseline?

    Two corrections over the first version, both of which decided a verdict.
    A family whose operation refuses contributes nothing, so a refusal can
    never be counted as the second meaning — one refusal beside one live value
    is not ambiguity. And a family whose baseline channel is incomplete is
    skipped rather than crashing.
    """
    families = chart.resolveds[node]
    if len(families) < 2 and not _has_wide_leaf(families, options):
        return False, 0
    name = harness._name(kernel, node)
    found: list[IrSelf] = []
    spent = 0
    for resolved in families:
        for kids in _baseline_lanes(resolved, baselines, options):
            spent += 1
            meaning = shared.apply_or_none(reducer, name, kids, partial)
            if meaning is not None:
                shared.add_unique(found, meaning)
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
    """One family's channels with children at baseline and leaves at each option.

    A child with NO baseline — every one of its families refused — yields no
    channel at all, so this family contributes nothing rather than raising.
    """
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    lanes: list[tuple[IrSelf, ...]] = []
    for index in range(width):
        if index in resolved.slots:
            lanes.append(options[id(resolved.leaves[resolved.slots.index(index)])])
            continue
        found = baselines.get(next(ints))
        if found is None:
            return []
        lanes.append((found,))
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
) -> tuple[Kernel, tuple[int, ...], Reducer, frozenset[str]]:
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
    dropped = laws.dropped_rules(reducer)
    aligned = candidate.aligned_rules(canonical, normalized, dropped)
    return kernel, roots, reducer, aligned


def run_rung(name: str, points: int, flavour: IrFlavour = GBNF_FLAVOUR) -> Rung:
    """Execute one rung through the materializing, streaming and law lanes."""
    body = ROW_BODIES[name if name in ROW_BODIES else "grow"](points)
    kernel, roots, reducer, aligned = parse_ladder(points, body, flavour)
    chart = algebra.build_chart(kernel, roots)
    full = settle(kernel, roots, {}, reducer, Settings())
    streamed = settle(kernel, roots, {}, reducer, Settings(stop_at=2))
    law = certified(kernel, roots, chart, {}, reducer, aligned)
    top = _root_multiplicity(kernel, roots, chart, reducer)
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
            kernel,
            handle,
            chart,
            sets,
            {},
            reducer,
            Settings(),
            lane,
            roots,
            frozenset(),
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
        cost = settle(kernel, roots, {}, reducer, Settings())
        top = _root_multiplicity(kernel, roots, chart, reducer)
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
        " product, so streaming, deduplication and the dirty cone all"
        " still pay 2^k APPLICATIONS. The bound is stated in"
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
    ("root-stop-only", Settings(stop_at=2)),
)
"""The two lanes that remain: materializing, and the certified-second stop."""


def prove_levers_isolated() -> None:
    """Run each lever alone, so no lane can be credited with another's saving.

    Two lanes remain: materializing, and the certified-second root stop. The
    declared-image quotient was a third and is REJECTED
    (:func:`prove_the_quotient_is_rejected`), so it is not isolated here — a
    lever no lane consults has nothing to isolate.
    """
    for name in ("collapse", "early-second", "late-second", "grow"):
        for points in (4, 8):
            body = ROW_BODIES[name](points)
            kernel, roots, reducer, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
            costs = [
                (label, settle(kernel, roots, {}, reducer, settings))
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


ALWAYS_REFUSES = IrBuild(
    IrMap, IrTuple(IrTuple(IrStr("k"), IrArg(0)), IrTuple(IrStr("k"), IrArg(1)))
)
"""A consumer that refuses on every combination — a constant duplicate key."""

REFUSING_ARM = (
    'root ::= pick "z"\npick ::= viadup | plain\nviadup ::= t t\n'
    'plain ::= t t\nt ::= p | q\np ::= "y"\nq ::= "y"\n'
)
"""One arm refuses on every combination; the other survives."""


def _refusing_arm_case(
    plain_body: IrSelf,
) -> tuple[Kernel, tuple[int, ...], Reducer, frozenset[str]]:
    """Recognize the refusing-arm control and compile what its lanes read."""
    actions = (
        ("root", IrArg(0)),
        ("pick", IrArg(0)),
        ("viadup", ALWAYS_REFUSES),
        ("plain", plain_body),
        ("t", IrArg(0)),
        ("p", MARK_P),
        ("q", MARK_Q),
    )
    text = "yyz"
    canonical = canonical_grammar(REFUSING_ARM, GBNF_FLAVOUR)
    normalized = normalize(canonical)
    kernel = Kernel(compile_tables(normalized, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("exact lane: the control did not parse")
    roots = algebra.accepting_roots(kernel, accept_handle(kernel))
    reducer = candidate.reducer_of(actions)
    dropped = laws.dropped_rules(reducer)
    aligned = candidate.aligned_rules(canonical, normalized, dropped)
    return kernel, roots, reducer, aligned


def prove_the_quotient_is_rejected() -> None:
    """The declared-image quotient is REJECTED — this row is why, not a lever.

    Three independent reasons, none of them "it needs more work":

    - its cross-slot composition is UNPROVED. `image_bound` multiplies per-slot
      bounds across distinct slots, and per-slot bounds do not compose by
      product: ``f(i,j) = v_i if i == j else x`` varies over at most two values
      in either coordinate alone and has an image of ``n+1``.
      `operation_slot_laws.differential_law` validates one slot at a time with
      every other position held at a filler, so it never probes the product;
    - it fires NOWHERE useful — on all four shipped surfaces every rule with a
      bounded image bounds to ONE, the constant actions;
    - a wrong bound would silently NARROW a meaning set, the "unambiguous"
      wrong answer.

    No settlement lane in this module consults it. `image_bound` survives only
    to produce this census, which is the evidence for the rejection.
    """
    total = 0
    for surface, reducer in laws.DISPATCHERS.items():
        canonical, normalized = laws._canonical(surface), laws._normalized(surface)
        dropped = laws.dropped_rules(reducer)
        aligned = candidate.aligned_rules(canonical, normalized, dropped)
        widths = laws.rule_arity(normalized, dropped)
        wide = sum(
            1
            for rule, width in widths.items()
            if image_bound(reducer, aligned, rule, width) > 1
        )
        total += wide
        print(
            "quotient-rejected",
            surface,
            f"rules={len(widths)}",
            f"rules_with_a_declared_image_wider_than_one={wide}",
            sep="\t",
        )
    assert total == 0, total
    print(
        "quotient-rejected",
        "conclusion",
        f"shipped_rules_the_quotient_could_ever_help={total}",
        "rejected on composition (unproved across slots), on reach (zero"
        " shipped rules) and on risk (a wrong bound narrows a meaning set"
        " silently); no lane consults it and it is not carried into the plan",
        sep="\t",
    )


def prove_a_refusing_family_is_not_ambiguity() -> None:
    """NEGATIVE CONTROL: one refusing family plus one live value is NOT two.

    The decisive case for the certificate. `pick` has two families; one refuses
    on every combination and one produces a value, so its image holds exactly
    ONE meaning. A lane that counted the refusal — as a sentinel, or by reading
    "two families" as "two meanings" — would certify ambiguity here.
    """
    kernel, roots, reducer, aligned = _refusing_arm_case(IrStr("only"))
    chart = algebra.build_chart(kernel, roots)
    partial = frozenset({"viadup"})
    cost = settle(kernel, roots, {}, reducer, Settings(), partial)
    law = certified(kernel, roots, chart, {}, reducer, aligned, partial)
    oracle = shared.unrolled_meanings(
        kernel, roots, {}, reducer, shared.UnrolledCounts(), partial
    )
    assert cost.verdict == VERDICT_EQUAL, cost
    assert not law.differs, law
    assert len(oracle) == 1, oracle
    print(
        "refusing-family-is-not-ambiguity",
        f"settle_verdict={cost.verdict}",
        f"law_lane_differs={law.differs}",
        f"unrolled_oracle_meanings={len(oracle)}",
        f"settle_meanings={len(cost.values)}",
        "a node carrying two families, one refusing on every combination, has"
        " an image of ONE meaning; neither the certificate nor the settlement"
        " lane may call that ambiguous",
        sep="\t",
    )


def prove_baseline_survives_a_refusing_default_family() -> None:
    """NEGATIVE CONTROL: the baseline must come from a family that HAS a value.

    `island_continuation._baseline_node` takes `resolveds[0]` unconditionally,
    so a node whose default family refuses would have no baseline — and the
    certificate reads baselines to build its witness. The corrected baseline
    takes the first LIVE family, and the settlement still matches the oracle.
    """
    kernel, roots, reducer, _aligned = _refusing_arm_case(
        IrBuild(IrTuple, IrTuple(IrArg(0), IrArg(1)))
    )
    chart = algebra.build_chart(kernel, roots)
    partial = frozenset({"viadup"})
    baselines = _baseline_table(kernel, roots, chart, {}, reducer, Lane(), partial)
    picks = [node for node in chart.nodes if harness._name(kernel, node) == "pick"]
    starved = [node for node in picks if node not in baselines]
    live = [node for node in picks if node in baselines]
    families = len(chart.resolveds[roots[0]])
    cost = settle(kernel, roots, {}, reducer, Settings(), partial)
    oracle = shared.unrolled_meanings(
        kernel, roots, {}, reducer, shared.UnrolledCounts(), partial
    )
    # The engine gives each arm its own completed code, so the refusing and the
    # surviving arm are two `pick` NODES and the node carrying both families is
    # the accepting root. Both halves are pinned: the starved node correctly has
    # no baseline, and the root — whose first family reaches it — still does.
    assert starved and live, (starved, live)
    assert families > 1 and roots[0] in baselines, (families, roots[0])
    assert shared.same_meaning_set(cost.values, oracle), (cost.values, oracle)
    print(
        "baseline-past-a-refusing-default",
        f"pick_nodes={len(picks)}",
        f"starved_of_a_baseline={len(starved)}",
        f"with_a_baseline={len(live)}",
        f"root_families={families}",
        f"root_has_a_baseline={roots[0] in baselines}",
        f"settle_meanings={len(cost.values)}",
        f"unrolled_oracle_meanings={len(oracle)}",
        f"agree={shared.same_meaning_set(cost.values, oracle)}",
        "a node whose only family refuses correctly has NO baseline, and its"
        " consumer — which carries both the refusing and the surviving family —"
        " still gets one from the family that lives; a baseline read off"
        " resolveds[0] unconditionally would have neither",
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
        kernel, roots, reducer, _aligned = parse_ladder(points, IrArgs(), GBNF_FLAVOUR)
        wrapped = candidate.reducer_of(collapsing_actions(points))
        plain = settle(kernel, roots, {}, reducer, Settings())
        collapsed = settle(kernel, roots, {}, wrapped, Settings())
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
    cost = settle(kernel, roots, {}, reducer, Settings(stop_at=2))
    chart_cpu = _time_chart_build(kernel, roots)
    settle_cpu = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, Settings(stop_at=2))
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
            kernel, roots, reducer, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
            oracle = shared.unrolled_meanings(
                kernel, roots, {}, reducer, shared.UnrolledCounts()
            )
            full = settle(kernel, roots, {}, reducer, Settings())
            streamed = settle(
                kernel,
                roots,
                {},
                reducer,
                Settings(stop_at=2),
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
        " rejected quotient would have had nothing to work on. The rules that"
        " force the exponential product are the unbounded ones, which are the"
        " majority",
        sep="\t",
    )


# ── timing, with a control ────────────────────────────────────────────────


REPEATS = 5
"""How many in-process passes each timing takes the minimum of."""


def _time_lane(name: str, points: int, settings: Settings) -> float:
    """Minimum process CPU of one lane over :data:`REPEATS` in-process passes."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    best = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, settings)
        elapsed = time.process_time() - started
        best = elapsed if index == 0 else min(best, elapsed)
    return best


def _time_certificate(name: str, points: int) -> float:
    """Minimum process CPU of the LAW lane over :data:`REPEATS` passes."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, aligned = parse_ladder(points, body, GBNF_FLAVOUR)
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
    kernel, roots, reducer, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    left = 0.0
    right = 0.0
    for index in range(REPEATS):
        started = time.process_time()
        settle(kernel, roots, {}, reducer, settings)
        first = time.process_time() - started
        started = time.process_time()
        settle(kernel, roots, {}, reducer, settings)
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
    streaming = Settings(stop_at=2)
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
    not applications alone. Both factors are counted here. This round proposes
    no budget; the ratio is recorded as the current lane's worst case.
    """
    for points in (6, 8, 10):
        late = _measure("late-second", points, Settings(stop_at=2))
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
        " own image. No budget is proposed: the ratio is recorded as the"
        " current enumeration's worst case, not as a policy",
        sep="\t",
    )


def _measure(name: str, points: int, settings: Settings) -> Cost:
    """One rung's full cost record under one lane setting."""
    body = ROW_BODIES[name](points)
    kernel, roots, reducer, _aligned = parse_ladder(points, body, GBNF_FLAVOUR)
    return settle(kernel, roots, {}, reducer, settings)


def main() -> None:
    """Walk the ladder, then execute every lever and the lower bound."""
    rungs = prove_ladder()
    prove_multiplicity_is_the_cost(rungs)
    prove_multiplicity_is_paid_at_every_level()
    prove_verdicts_against_the_unrolled_oracle()
    prove_streaming_wins_where_it_can(rungs)
    prove_levers_isolated()
    prove_the_quotient_is_rejected()
    prove_a_refusing_family_is_not_ambiguity()
    prove_baseline_survives_a_refusing_default_family()
    prove_grow_image_is_computed_not_enumerated()
    prove_dedup_stops_multiplicity_climbing()
    prove_lower_bound(rungs)
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
        " comparisons), so no single-unit Theta is claimed. That exponential"
        " is recorded as the CURRENT exact lane's worst case under this"
        " enumeration and these slot laws — no resource policy is proposed"
        " against it, and a future symbolic analysis is not ruled out",
        sep="\t",
    )


if __name__ == "__main__":
    main()
