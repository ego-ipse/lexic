"""Cyclic packed forests: the exact terminating meaning relation.

The rejected fallback enumerated every global family assignment (``2^k``) and
called one ``FastTree`` lap exact. This module replaces it.

The semantic question on a cyclic chart is NOT "enumerate the meanings": a
cyclic grammar derives one string in infinitely many ways, so the meaning
family can be infinite. The question the ambiguity contract asks is whether
the REQUESTED ROOT carries more than one distinct meaning. That is decidable
without enumeration, because a chart cycle is always a zero-width strongly
connected component (a child's span is contained in its parent's, so a cycle
forces equal spans), and the loop operations around such a component are
classified by the closed product-operation algebra:

- ``const``  — the operation ignores the cycle slot; the loop map is constant;
- ``ident``  — the operation returns the cycle slot unchanged; the loop map is
  the identity and adds nothing;
- ``finite`` — the operation's image is a declared finite domain, so the
  reachable value family is finite;
- ``grow``   — the operation embeds the cycle slot as a proper sub-value, so it
  is injective and strictly size-increasing: ``f^n(b)`` are pairwise distinct
  and the family is infinite.

A component terminates iff no cycle inside it carries a ``grow`` edge without a
``const``/``finite`` edge — decided in linear time by looking for a ``grow``
edge whose endpoints share a strongly connected component of the subgraph on
``ident``/``grow`` edges alone. Terminating components are solved by a monotone
Kleene fixpoint over exact deduplicated value sets; the classification supplies
the termination proof (a finite reachable value domain), and the iteration
asserts the monotonicity that proof rests on rather than guarding a lap cap.

A ``grow`` component that survives is answered by where its CARRIERS' value can
go — the carriers being the ``ident``/``grow`` upward closure of the growing
sub-cycle, never the whole component, because a ``const``/``finite`` member of
the same component never holds the unbounded family:

- an all-injective path to an accepting root makes the ROOT family infinite, so
  the exact verdict is "more than one meaning" — refuse the parse as ambiguous
  without attempting a bounded unrolling of that infinite family;
- no value-carrying path at all makes the carriers invisible, so they are
  frozen to one representative while every non-carrier member of the component
  is still evaluated exactly;
- otherwise the family reaches a bounded-image consumer and the exact relation
  is not finitely representable under this algebra: binding REFUSES with words.

The same classification runs on the normalized grammar alone
(:func:`grammar_verdict`), so the refusal is a binding-time property of the
composed (grammar, algebra) pair — no input, no rule-name special case, no
privileged formulation.

Run directly for the differential against an independent bounded-depth
exhaustive derivation oracle.
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Hashable, Mapping, Sequence
from itertools import product
from typing import NamedTuple

import island_alternate_seed as harness

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spine.spine import IrSelf
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import ambiguity_points
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain, tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, is_arm_choice
from lexic.parsing.earley.normalize import normalize

type Meaning = harness.Meaning
type MeaningSet = tuple[Meaning, ...]

MARKERS = frozenset({"two", "m2", "a"})
"""Decoded content that never appears in a default-family baseline."""

INJECTIVE = frozenset({"", "swap", "wrap"})
"""Operations that embed every child as a proper sub-value of their result."""

RING_SATURATION = 3
"""How many laps the ``ring`` operation counts before it saturates.

The witness needs a distinction that appears only DEEPER than the one-lap
relation can reach: that relation unrolls a cycle at most once per distinct
arm-choice key, which is a chart artefact, not a semantic bound.
"""

IMAGE_BOUND = {
    "drop": 1,
    "const": 1,
    "atmost1": 2,
    "atmost2": 2,
    "cond": 2,
    "dupkey": 2,
    "ring": RING_SATURATION + 1,
}
"""Declared image cardinality of every bounded-image operation."""

CONSTANT = frozenset({"drop", "const"})
"""Operations that ignore every child."""

CONST = "const"
IDENT = "ident"
FINITE = "finite"
GROW = "grow"

ACYCLIC = "acyclic"
CYCLIC_BOUNDED = "cyclic-bounded"
CYCLIC_INFINITE = "cyclic-infinite"
CYCLIC_OPAQUE = "cyclic-opaque"
CYCLIC_UNREPRESENTABLE = "cyclic-unrepresentable"


class CyclicRefusal(UnsupportedConstructError):
    """A cyclic component whose exact meaning relation is not representable."""


class Metrics:
    """What one verdict mechanism paid."""

    __slots__ = ("laps", "live", "max_live", "ops", "retained")

    def __init__(self) -> None:
        self.ops = 0
        self.retained = 0
        self.live = 0
        self.max_live = 0
        self.laps = 0

    def note(self, delta: int) -> None:
        """Track the peak count of concurrently stored meanings, in O(1)."""
        self.live += delta
        if self.live > self.max_live:
            self.max_live = self.live


def _flagged(meaning: Meaning) -> int:
    """Count marker atoms in one meaning — a pure decoded-content predicate."""
    if isinstance(meaning, str):
        return 1 if meaning in MARKERS else 0
    total = 0
    pending: list[Meaning] = [meaning]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            total += 1 if node in MARKERS else 0
        else:
            pending.extend(node)
    return total


def apply_policy(policy: str, name: str, kids: tuple[Meaning, ...]) -> Meaning:
    """One meaning operation — every shape the planned algebra declares."""
    if policy == "atom":
        raise UnsupportedConstructError(
            "cyclic meaning: the set lanes do not carry span text; span"
            " policies are island-internal in these witnesses"
        )
    if policy == "drop":
        return (name,)
    if policy == "const":
        return ("const", name)
    if policy == "pass":
        return kids[0] if kids else (name,)
    if policy == "swap":
        return (name,) + tuple(reversed(kids))
    if policy == "wrap":
        return (name, ("layer",) + kids)
    if policy in ("atmost1", "atmost2"):
        ceiling = 1 if policy == "atmost1" else 2
        count = sum(_flagged(kid) for kid in kids)
        return ("verdict", "ok" if count <= ceiling else "too-many")
    if policy == "cond":
        left = _flagged(kids[0]) > 0
        right = _flagged(kids[1]) > 0 if len(kids) > 1 else False
        return ("cond", "same" if left == right else "mixed")
    if policy == "dupkey":
        keys = ["K" if _flagged(kid) else f"k{index}" for index, kid in enumerate(kids)]
        duplicate = len(keys) != len(set(keys))
        return ("verdict", "dup" if duplicate else "ok")
    if policy == "ring":
        laps = sum(_flagged(kid) for kid in kids) + (1 if kids else 0)
        return ("ring",) + ("two",) * min(RING_SATURATION, laps)
    return (name,) + kids


def slot_class(policy: str, slot: int) -> str:
    """How ``policy``'s result depends on the child occupying ``slot``.

    :param policy: The lowered completion operation.
    :param slot: The child's kid index.
    :returns: One of :data:`CONST`, :data:`IDENT`, :data:`FINITE`, :data:`GROW`.
    :raises UnsupportedConstructError: On an operation with no declared class.
    """
    if policy in CONSTANT:
        return CONST
    if policy == "pass":
        return IDENT if slot == 0 else CONST
    if policy in IMAGE_BOUND:
        return FINITE
    if policy in INJECTIVE:
        return GROW
    raise UnsupportedConstructError(
        f"cyclic meaning: operation {policy!r} declares no slot class"
    )


class SetFolder(harness.Folder):
    """The harness meaning folder extended with the full policy algebra."""

    def _assemble(
        self,
        handle: int,
        resolved: harness.Resolved,
        memo: harness.Overlay,
        leaf_override: dict[int, Meaning],
    ) -> Meaning:
        """Apply the extended algebra; fall back to the harness for spans."""
        policy = self.program[harness._code(self.kernel, handle)]
        if policy in (
            "atmost1",
            "atmost2",
            "cond",
            "dupkey",
            "pass",
            "const",
            "ring",
        ):
            self._count()
            kids = self._kids(resolved, memo, leaf_override)
            return apply_policy(policy, harness._name(self.kernel, handle), kids)
        return super()._assemble(handle, resolved, memo, leaf_override)


def dedup(meanings: list[Meaning]) -> MeaningSet:
    """Semantic deduplication, first-seen order (meanings are value tuples)."""
    seen: set[Meaning] = set()
    out: list[Meaning] = []
    for meaning in meanings:
        if meaning not in seen:
            seen.add(meaning)
            out.append(meaning)
    return tuple(out)


def tables_for(grammar: str, size: int) -> ParserTables:
    """Real compiled tables for one witness grammar."""
    return compile_tables(
        normalize(canonical_grammar(grammar, GBNF_FLAVOUR)), tier_for(size)
    )


def selected_resolved(
    kernel: Kernel, handle: int, selected: dict[int, int]
) -> harness.Resolved:
    """``harness._resolved`` under a MULTI-key family selection."""
    bits = kernel.tables.packing.bits
    codes = kernel.tables.codes
    base = codes.arm_base[codes.code_arm[harness._code(kernel, handle)]]
    if handle in kernel.st.leo_links:
        expand_leo(kernel.st, kernel.tables, handle)
    chain = predecessor_chain(
        kernel.st.links,
        handle,
        ChainSpec(base, bits, kernel.tables.code_choice),
        # The chain walk CONSUMES entries from its choices dict (a flipped
        # point is spent at first visit), so every resolve gets a fresh copy.
        dict(selected),
    )
    if chain is None:
        start = (handle >> bits) & kernel.tables.packing.mask
        if start == (handle & kernel.tables.packing.mask):
            return harness.Resolved((), (), (), (handle,))
        raise UnsupportedConstructError("cyclic meaning: handle did not resolve")
    children: list[int] = []
    leaves: list[harness.PayloadLeaf] = []
    slots: list[int] = []
    slot = 0
    for _predecessor, _end, child in chain:
        if isinstance(child, harness.PayloadLeaf):
            leaves.append(child)
            slots.append(slot)
            slot += 1
        elif isinstance(child, int) and not isinstance(child, bool):
            children.append(child)
            slot += 1
    keys = (handle,) + tuple(
        (predecessor << bits) | end for predecessor, end, _child in chain
    )
    return harness.Resolved(tuple(children), tuple(leaves), tuple(slots), keys)


def assignments(kernel: Kernel, points: list[int]) -> list[dict[int, int]]:
    """Every family assignment over the given arm-choice keys."""
    combos: list[dict[int, int]] = [{}]
    for key in points:
        families = len(kernel.st.links[key])
        combos = [
            {**combo, key: family} for combo in combos for family in range(families)
        ]
    return combos


def local_choice_keys(kernel: Kernel, handle: int) -> tuple[int, ...]:
    """Every arm-choice packed key owned by THIS completion's chains.

    Family indices and even the key population are only stable at a census
    fixpoint under lazy Leo expansion, so the discovery iterates assignments
    until no new key appears.
    """
    bits = kernel.tables.packing.bits
    known: tuple[int, ...] = ()
    while True:
        found: set[int] = set(known)
        for assignment in assignments(kernel, list(known)):
            for key in selected_resolved(kernel, handle, assignment).keys:
                bucket = kernel.st.links.get(key)
                if (
                    bucket is not None
                    and len(bucket) > 1
                    and is_arm_choice(bucket, bits, kernel.tables.code_choice)
                ):
                    found.add(key)
        settled = tuple(sorted(found))
        if settled == known:
            return settled
        known = settled


def accepting_roots(kernel: Kernel, root: int) -> tuple[int, ...]:
    """EVERY accepting item at the document end — a many-production start
    symbol has no parent waiter, so its alternatives are sibling accepting
    ITEMS, invisible to the link table."""
    bits = kernel.tables.packing.bits
    mask = kernel.tables.packing.mask
    end = len(kernel.text)
    accepts = kernel.tables.codes.accept_codes
    roots = [
        (item << bits) | end
        for item in kernel.cols[end]
        if item >> bits in accepts and item & mask == 0
    ]
    if root not in roots:
        roots.insert(0, root)
    return tuple(roots)


class Edge(NamedTuple):
    """One family-aware parent→child dependency and its kid slot."""

    parent: int
    child: int
    slot: int


class Chart(NamedTuple):
    """The family-aware completed-node graph of one real parse."""

    nodes: tuple[int, ...]
    resolveds: dict[int, tuple[harness.Resolved, ...]]
    edges: tuple[Edge, ...]
    children: dict[int, tuple[int, ...]]


def child_slots(resolved: harness.Resolved) -> tuple[int, ...]:
    """The kid index of each child handle, delegated leaves interleaved."""
    width = len(resolved.children) + len(resolved.leaves)
    return tuple(index for index in range(width) if index not in resolved.slots)


def build_chart(kernel: Kernel, roots: tuple[int, ...]) -> Chart:
    """Resolve every reachable completion under every one of its families."""
    nodes: list[int] = []
    resolveds: dict[int, tuple[harness.Resolved, ...]] = {}
    edges: list[Edge] = []
    children: dict[int, tuple[int, ...]] = {}
    seen: set[int] = set()
    pending = list(roots)
    while pending:
        handle = pending.pop()
        if handle in seen:
            continue
        seen.add(handle)
        nodes.append(handle)
        keys = local_choice_keys(kernel, handle)
        found = tuple(
            selected_resolved(kernel, handle, assignment)
            for assignment in assignments(kernel, list(keys))
        )
        resolveds[handle] = found
        reached: list[int] = []
        for resolved in found:
            for slot, child in zip(child_slots(resolved), resolved.children):
                edges.append(Edge(handle, child, slot))
                reached.append(child)
                pending.append(child)
        children[handle] = tuple(dedup_ints(reached))
    return Chart(tuple(nodes), resolveds, tuple(edges), children)


def dedup_ints(values: list[int]) -> list[int]:
    """First-seen unique integers."""
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def components[Node: Hashable](
    nodes: Sequence[Node], adjacency: Mapping[Node, Sequence[Node]]
) -> list[tuple[Node, ...]]:
    """Tarjan strongly connected components, descendants emitted first.

    Iterative — a chart is as deep as its document.

    :param nodes: Every node, in discovery order.
    :param adjacency: Each node's successors.
    :returns: The components, each emitted after everything it can reach.
    """
    index: dict[Node, int] = {}
    low: dict[Node, int] = {}
    on_stack: set[Node] = set()
    stack: list[Node] = []
    order = 0
    found: list[tuple[Node, ...]] = []
    for start in nodes:
        if start in index:
            continue
        work: list[tuple[Node, int]] = [(start, 0)]
        while work:
            node, position = work[-1]
            if position == 0:
                index[node] = low[node] = order
                order += 1
                stack.append(node)
                on_stack.add(node)
            kids = adjacency.get(node, ())
            if position < len(kids):
                work[-1] = (node, position + 1)
                kid = kids[position]
                if kid not in index:
                    work.append((kid, 0))
                elif kid in on_stack:
                    low[node] = min(low[node], index[kid])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                group: list[Node] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                found.append(tuple(group))
    return found


class Classes(NamedTuple):
    """Per-edge slot classes plus the reachability lanes they induce."""

    edge_class: dict[Edge, str]
    visible: dict[int, bool]
    injective: dict[int, bool]


def classify_edges(
    kernel: Kernel, chart: Chart, program: tuple[str, ...], roots: tuple[int, ...]
) -> Classes:
    """Classify every edge, then propagate the value-carrying lanes."""
    edge_class = {
        edge: slot_class(program[harness._code(kernel, edge.parent)], edge.slot)
        for edge in chart.edges
    }
    outgoing: dict[int, list[Edge]] = {}
    for edge in chart.edges:
        outgoing.setdefault(edge.parent, []).append(edge)
    visible = _reach(chart, outgoing, edge_class, roots, frozenset({CONST}))
    injective = _reach(chart, outgoing, edge_class, roots, frozenset({CONST, FINITE}))
    return Classes(edge_class, visible, injective)


def _reach(
    chart: Chart,
    outgoing: dict[int, list[Edge]],
    edge_class: dict[Edge, str],
    roots: tuple[int, ...],
    blocked: frozenset[str],
) -> dict[int, bool]:
    """Nodes reachable from a root through edges whose class is not blocked."""
    marked = {node: False for node in chart.nodes}
    pending: list[int] = []
    for root in roots:
        if not marked.get(root, True):
            marked[root] = True
            pending.append(root)
    while pending:
        node = pending.pop()
        for edge in outgoing.get(node, ()):
            if edge_class[edge] in blocked or marked.get(edge.child, True):
                continue
            marked[edge.child] = True
            pending.append(edge.child)
    return marked


def _carriers[Node: Hashable](
    group: Sequence[Node],
    carrying: Sequence[tuple[Node, Node, str]],
) -> tuple[frozenset[Node], bool]:
    """Which nodes can hold an unbounded family, and whether one exists.

    The growing family originates on a cycle of the ``ident``/``grow``
    subgraph that carries at least one ``grow`` edge, and flows UPWARD from
    child to parent along those same edges. Only those carriers may be asked
    where the family can go: a ``const``/``finite`` member of the same
    strongly connected component never holds it, and testing the whole
    component instead misclassifies exactly the charts where a dropping
    consumer sits inside the cycle's component.

    :param group: The component's nodes.
    :param carrying: Its internal ``(parent, child, class)`` edges restricted
        to the ``ident``/``grow`` classes.
    :returns: The carrier set and whether the component grows at all.
    """
    adjacency: dict[Node, tuple[Node, ...]] = {node: () for node in group}
    for parent, child, _kind in carrying:
        adjacency[parent] = adjacency[parent] + (child,)
    place = {
        node: position
        for position, part in enumerate(components(group, adjacency))
        for node in part
    }
    growing = {
        place[parent]
        for parent, child, kind in carrying
        if kind == GROW and place[parent] == place[child]
    }
    if not growing:
        return frozenset(), False
    reach = {node for node in group if place[node] in growing}
    changed = True
    while changed:
        changed = False
        for parent, child, _kind in carrying:
            if child in reach and parent not in reach:
                reach.add(parent)
                changed = True
    return frozenset(reach), True


def _growing_kind[Node: Hashable](
    carriers: frozenset[Node],
    injective: dict[Node, bool],
    visible: dict[Node, bool],
) -> str:
    """Where a growing component's unbounded family can reach."""
    if any(injective.get(node, False) for node in carriers):
        return CYCLIC_INFINITE
    if not any(visible.get(node, False) for node in carriers):
        return CYCLIC_OPAQUE
    return CYCLIC_UNREPRESENTABLE


class ComponentClass(NamedTuple):
    """One component's classification and which of its nodes grow."""

    kind: str
    carriers: frozenset[int]


def component_kind(
    group: tuple[int, ...], internal: list[Edge], classes: Classes
) -> ComponentClass:
    """Whether one component is acyclic, terminating, infinite, or refused.

    :param group: The component's nodes.
    :param internal: Exactly the edges with both endpoints inside it, bucketed
        once by the caller — scanning every chart edge per component is what
        made this quadratic on a long document.
    :param classes: Edge classes plus the value-carrying reachability lanes.
    :returns: The classification and the component's carrier set.
    """
    if len(group) == 1 and not any(edge.parent == edge.child for edge in internal):
        return ComponentClass(ACYCLIC, frozenset())
    carrying = [
        (edge.parent, edge.child, classes.edge_class[edge])
        for edge in internal
        if classes.edge_class[edge] in (IDENT, GROW)
    ]
    carriers, growing = _carriers(group, carrying)
    if not growing:
        return ComponentClass(CYCLIC_BOUNDED, frozenset())
    return ComponentClass(
        _growing_kind(carriers, classes.injective, classes.visible), carriers
    )


def _slot_options(
    resolved: harness.Resolved,
    sets: dict[int, MeaningSet],
    leaf_options: dict[int, MeaningSet],
) -> list[MeaningSet] | None:
    """One family's per-kid option sets, or ``None`` when a lane is empty."""
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    out: list[MeaningSet] = []
    for index in range(width):
        if index in resolved.slots:
            leaf = resolved.leaves[resolved.slots.index(index)]
            options = leaf_options[id(leaf)]
        else:
            options = sets.get(next(ints), ())
        if not options:
            return None
        out.append(options)
    return out


def node_set(
    kernel: Kernel,
    handle: int,
    program: tuple[str, ...],
    chart: Chart,
    sets: dict[int, MeaningSet],
    leaf_options: dict[int, MeaningSet],
    metrics: Metrics,
) -> MeaningSet:
    """One node's exact set: its OWN packed families × child/leaf option sets."""
    policy = program[harness._code(kernel, handle)]
    name = harness._name(kernel, handle)
    meanings: list[Meaning] = []
    for resolved in chart.resolveds[handle]:
        options = _slot_options(resolved, sets, leaf_options)
        if options is None:
            continue
        for kids in product(*options):
            metrics.ops += 1
            meanings.append(apply_policy(policy, name, kids))
    return dedup(meanings)


def _solve_component(
    group: tuple[int, ...],
    verdict: ComponentClass,
    kernel: Kernel,
    program: tuple[str, ...],
    chart: Chart,
    sets: dict[int, MeaningSet],
    leaf_options: dict[int, MeaningSet],
    metrics: Metrics,
    injective: dict[int, bool] | None = None,
) -> None:
    """Fill ``sets`` for one component under its classification.

    Termination comes from the classification, not from a lap count: a
    component only reaches the fixpoint below when every cycle inside it is
    identity-preserving or passes through a bounded-image operation, so the
    reachable value domain is finite and a MONOTONE Kleene iteration over it
    must stop. The loop therefore checks monotonicity — the one property the
    termination argument rests on — instead of guarding an unproved cap.

    An OPAQUE component freezes only its CARRIERS to a sentinel; its
    non-carrier members are exact, because a member that does not carry the
    unbounded family reaches it only through an operation constant in that
    slot.
    """
    pending = group
    if verdict.kind == CYCLIC_OPAQUE:
        for node in verdict.carriers:
            sets[node] = (("opaque", harness._name(kernel, node)),)
            metrics.note(1)
        pending = tuple(node for node in group if node not in verdict.carriers)
    for node in pending:
        sets.setdefault(node, ())
    while True:
        metrics.laps += 1
        changed = False
        for node in pending:
            found = node_set(kernel, node, program, chart, sets, leaf_options, metrics)
            if found != sets[node]:
                if not set(sets[node]) <= set(found):
                    raise CyclicRefusal(
                        "cyclic meaning: the value-set iteration was not"
                        f" monotone at {harness._name(kernel, node)!r} — the"
                        " termination argument does not hold"
                    )
                metrics.note(len(found) - len(sets[node]))
                sets[node] = found
                changed = True
            if injective is not None and len(found) > 1 and injective[node]:
                # An injective path to an accepting root turns this node's own
                # multiplicity into root multiplicity, whatever the siblings
                # and whatever the ancestors' own arm choices are: fix that
                # path's families and vary only this node's subderivation.
                raise _EarlyRefusal
        if not changed:
            return


class Outcome(NamedTuple):
    """The exact verdict plus every structural count it paid."""

    differs: bool
    meanings: MeaningSet
    kind: str
    components: int
    cyclic_components: int
    laps: int
    ops: int
    retained: int
    max_live: int
    early: bool


class _EarlyRefusal(Exception):
    """A node under an injective sky already holds two meanings."""


def exact_meanings(
    kernel: Kernel,
    root: int,
    policies: dict[str, str],
    occurrences: dict[int, Meaning],
    seeds: dict[int, harness.IslandSeed],
    metrics: Metrics,
    early_exit: bool = False,
) -> Outcome:
    """The exact requested-root meaning relation, cyclic charts included.

    :param kernel: The finished real Earley kernel.
    :param root: The accepting handle the caller requested.
    :param policies: The rule-name → completion-operation program.
    :param occurrences: Delegated-leaf baseline meanings by leaf id.
    :param seeds: Island seeds by leaf id, supplying their option sets.
    :param metrics: The counter record this run fills.
    :param early_exit: Stop as soon as a node under an injective path to an
        accepting root holds two meanings; the verdict is then decided and the
        meaning set is deliberately not completed.
    :returns: The verdict, the root meanings, and the component census.
    :raises CyclicRefusal: When a component's exact relation is not finitely
        representable under the declared algebra.
    """
    roots = accepting_roots(kernel, root)
    chart = build_chart(kernel, roots)
    folder = SetFolder(kernel, policies, occurrences, harness.Counters(), "oracle")
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (meaning,) for leaf_id, meaning in occurrences.items()
    }
    for leaf_id, seed in seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    classes = classify_edges(kernel, chart, folder.program, roots)
    sets: dict[int, MeaningSet] = {}
    kinds: list[str] = []
    early = False
    early_kind = ACYCLIC
    lane = classes.injective if early_exit else None
    groups = components(chart.nodes, chart.children)
    for group, internal in zip(groups, _bucket_edges(groups, chart)):
        verdict = component_kind(group, internal, classes)
        kind = verdict.kind
        kinds.append(kind)
        if kind == CYCLIC_UNREPRESENTABLE:
            raise CyclicRefusal(
                "cyclic meaning: a zero-width cycle builds an unbounded meaning"
                f" family consumed by a bounded-image operation at"
                f" {harness._name(kernel, group[0])!r}; the exact relation is"
                " not finitely representable"
            )
        if kind == CYCLIC_INFINITE:
            # The classification alone decides: an infinite family under an
            # injective path makes the root family infinite. No bounded
            # unrolling is needed to manufacture a witness pair.
            early = True
            early_kind = CYCLIC_INFINITE
            break
        try:
            _solve_component(
                group,
                verdict,
                kernel,
                folder.program,
                chart,
                sets,
                leaf_options,
                metrics,
                lane,
            )
        except _EarlyRefusal:
            early = True
            early_kind = _dominant(kinds)
            break
    metrics.retained = sum(len(values) for values in sets.values())
    cyclic = sum(1 for kind in kinds if kind != ACYCLIC)
    if early:
        return Outcome(
            True,
            (),
            early_kind,
            len(kinds),
            cyclic,
            metrics.laps,
            metrics.ops,
            metrics.retained,
            metrics.max_live,
            True,
        )
    union = dedup([meaning for node in roots for meaning in sets.get(node, ())])
    return Outcome(
        len(union) > 1,
        union,
        _dominant(kinds),
        len(kinds),
        cyclic,
        metrics.laps,
        metrics.ops,
        metrics.retained,
        metrics.max_live,
        False,
    )


def _bucket_edges(groups: list[tuple[int, ...]], chart: Chart) -> list[list[Edge]]:
    """Each component's internal edges, assigned in one pass over the chart."""
    place = {node: index for index, group in enumerate(groups) for node in group}
    buckets: list[list[Edge]] = [[] for _ in groups]
    for edge in chart.edges:
        if place[edge.parent] == place[edge.child]:
            buckets[place[edge.parent]].append(edge)
    return buckets


def _dominant(kinds: list[str]) -> str:
    """The strongest component classification present."""
    for kind in (CYCLIC_OPAQUE, CYCLIC_BOUNDED):
        if kind in kinds:
            return kind
    return ACYCLIC


def one_lap_meanings(
    kernel: Kernel,
    root: int,
    policies: dict[str, str],
    occurrences: dict[int, Meaning],
    seeds: dict[int, harness.IslandSeed],
) -> MeaningSet:
    """The REJECTED one-lap relation, kept only as the comparison lane.

    Builds every global family assignment through ``FastTree``, whose choices
    dict is consumed at first visit, so each key unrolls at most once. Priced
    at ``2^k`` in reachable arm points and NOT the relation this module
    computes.
    """
    roots = accepting_roots(kernel, root)
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (meaning,) for leaf_id, meaning in occurrences.items()
    }
    for leaf_id, seed in seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    points = _all_points(kernel, roots)
    meanings: list[Meaning] = []
    for accepting in roots:
        for assignment in assignments(kernel, points):
            tree = FastTree(kernel, dict(assignment)).build(accepting)
            if not isinstance(tree, ParseTree):
                continue
            for overrides in _leaf_combos(leaf_options):
                meanings.append(tree_meaning(tree, policies, overrides))
    if not meanings:
        raise UnsupportedConstructError("cyclic meaning: no derivation built")
    return dedup(meanings)


def _all_points(kernel: Kernel, roots: tuple[int, ...]) -> list[int]:
    """Every arm-choice key reachable from any accepting root."""
    bits = kernel.tables.packing.bits
    found: list[int] = []
    seen: set[int] = set()
    for root in roots:
        for key in ambiguity_points(kernel, root):
            bucket = kernel.st.links.get(key)
            if key in seen or bucket is None:
                continue
            seen.add(key)
            if is_arm_choice(bucket, bits, kernel.tables.code_choice):
                found.append(key)
    return sorted(found)


def _leaf_combos(leaf_sets: dict[int, MeaningSet]) -> list[dict[int, Meaning]]:
    """Every override combination over delegated leaves."""
    combos: list[dict[int, Meaning]] = [{}]
    for leaf_id, options in leaf_sets.items():
        combos = [{**combo, leaf_id: option} for combo in combos for option in options]
    return combos


def tree_meaning(
    tree: ParseTree, policies: dict[str, str], overrides: dict[int, Meaning]
) -> Meaning:
    """Fold one real derivation under the policy algebra, iteratively."""
    values: list[Meaning] = []
    stack: list[tuple[ParseTree, bool]] = [(tree, False)]
    while stack:
        node, expanded = stack.pop()
        subtrees = [kid for kid in node.kids if isinstance(kid, ParseTree)]
        if not expanded:
            stack.append((node, True))
            for kid in reversed(subtrees):
                stack.append((kid, False))
            continue
        taken = values[len(values) - len(subtrees) :] if subtrees else []
        del values[len(values) - len(subtrees) :]
        kids: list[Meaning] = []
        position = 0
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                kids.append(taken[position])
                position += 1
            elif isinstance(kid, harness.PayloadLeaf):
                kids.append(overrides[id(kid)])
        values.append(
            apply_policy(
                policies.get(str(node.symbol), ""), str(node.symbol), tuple(kids)
            )
        )
    return values[0]


class OracleReport(NamedTuple):
    """The bounded-depth oracle's answer and the full depth ladder it walked."""

    meanings: MeaningSet
    stabilized_at: int
    ceiling: int
    ladder: tuple[int, ...]

    @property
    def stable(self) -> bool:
        """Whether the set survived :data:`QUIET_DEPTHS` unchanged steps."""
        return self.stabilized_at <= self.ceiling - QUIET_DEPTHS

    @property
    def unbounded(self) -> bool:
        """Whether the ladder was STILL growing over its last quiet window.

        A cycle whose arm keys step every second depth grows in plateaus, so
        strict per-rung growth is the wrong test; growth across the window
        that a finite family would have to be flat over is the right one.
        """
        rising = all(
            later >= earlier for earlier, later in zip(self.ladder, self.ladder[1:])
        )
        return rising and self.ladder[-1] > self.ladder[-QUIET_DEPTHS]


QUIET_DEPTHS = 3
"""Consecutive unchanged depths a bounded-depth answer must survive.

One is not enough and the ``ring`` witness proves it: its set is unchanged
from depth 0 to depth 1 and then GROWS at depth 2, which is exactly the
phenomenon that makes the one-lap relation wrong.
"""


def bounded_depth_meanings(
    kernel: Kernel,
    root: int,
    policies: dict[str, str],
    occurrences: dict[int, Meaning],
    seeds: dict[int, harness.IslandSeed],
    ceiling: int = 7,
) -> OracleReport:
    """Independent oracle: enumerate derivations by explicit cycle unrolling.

    No component analysis, no classification, no ``FastTree`` — every family
    assignment is expanded per node, and a handle already on the current DFS
    path may be re-entered at most ``depth`` more times. The depth rises to
    ``ceiling`` and the answer must be unchanged over the last
    :data:`QUIET_DEPTHS` steps.

    :param ceiling: How far the ladder is walked; a stabilization check on the
        ORACLE, never a cap on the mechanism it checks.
    :returns: The stabilized set, where it settled, and the size ladder.
    :raises UnsupportedConstructError: When the set never stabilizes.
    """
    roots = accepting_roots(kernel, root)
    program = SetFolder(
        kernel, policies, occurrences, harness.Counters(), "oracle"
    ).program
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (meaning,) for leaf_id, meaning in occurrences.items()
    }
    for leaf_id, seed in seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    rungs: list[MeaningSet] = []
    for depth in range(ceiling):
        found: list[Meaning] = []
        for accepting in roots:
            found.extend(_unrolled(kernel, accepting, program, leaf_options, depth, ()))
        rungs.append(dedup(found))
    settled = max(
        (
            depth
            for depth in range(ceiling)
            if depth == 0 or rungs[depth] != rungs[depth - 1]
        ),
        default=0,
    )
    return OracleReport(rungs[-1], settled, ceiling, tuple(len(rung) for rung in rungs))


def _unrolled(
    kernel: Kernel,
    handle: int,
    program: tuple[str, ...],
    leaf_options: dict[int, MeaningSet],
    budget: int,
    path: tuple[int, ...],
) -> list[Meaning]:
    """Every meaning of ``handle`` under at most ``budget`` cycle re-entries."""
    if handle in path:
        if budget <= 0:
            return []
        budget -= 1
    policy = program[harness._code(kernel, handle)]
    name = harness._name(kernel, handle)
    deeper = path + (handle,)
    meanings: list[Meaning] = []
    keys = local_choice_keys(kernel, handle)
    for assignment in assignments(kernel, list(keys)):
        resolved = selected_resolved(kernel, handle, assignment)
        options = _oracle_options(
            kernel, resolved, program, leaf_options, budget, deeper
        )
        if options is None:
            continue
        for kids in product(*options):
            meanings.append(apply_policy(policy, name, kids))
    return meanings


def _oracle_options(
    kernel: Kernel,
    resolved: harness.Resolved,
    program: tuple[str, ...],
    leaf_options: dict[int, MeaningSet],
    budget: int,
    path: tuple[int, ...],
) -> list[MeaningSet] | None:
    """The oracle's per-kid option sets for one family, or ``None`` if dead."""
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    out: list[MeaningSet] = []
    for index in range(width):
        if index in resolved.slots:
            options = leaf_options[id(resolved.leaves[resolved.slots.index(index)])]
        else:
            options = dedup(
                _unrolled(kernel, next(ints), program, leaf_options, budget, path)
            )
        if not options:
            return None
        out.append(options)
    return out


class RuleEdge(NamedTuple):
    """One binding-time carrier edge: a rule that can cover its parent's span."""

    parent: str
    child: str
    slot: int


class GrammarVerdict(NamedTuple):
    """The binding-time cyclic classification of one grammar × algebra pair."""

    refused: bool
    components: tuple[tuple[str, ...], ...]
    kinds: tuple[str, ...]
    message: str


def _rules(ast: IrAst) -> tuple[IrRule, ...]:
    """Every rule of a normalized AST."""
    return tuple(part for part in ast[0] if isinstance(part, IrRule))


def _arms(rule: IrRule) -> tuple[IrSequence, ...]:
    """The rule's alternative sequences."""
    body = rule.body
    if isinstance(body, IrAlternation):
        return tuple(arm for arm in body if isinstance(arm, IrSequence))
    if isinstance(body, IrSequence):
        return (body,)
    raise UnsupportedConstructError(
        f"cyclic meaning: rule {str(rule.name)!r} has an unexpected body"
    )


def _nullable(rules: tuple[IrRule, ...]) -> set[str]:
    """The rules that derive the empty string."""
    empty: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in rules:
            name = str(rule.name)
            if name in empty:
                continue
            if any(
                all(_item_nullable(item, empty) for item in arm) for arm in _arms(rule)
            ):
                empty.add(name)
                changed = True
    return empty


def _item_nullable(item: IrSelf, empty: set[str]) -> bool:
    """Whether one normalized item can match no characters."""
    if not isinstance(item, IrItem):
        return False
    atom = item[0]
    if isinstance(atom, IrRuleRef):
        return str(atom) in empty
    if isinstance(atom, IrLiteral):
        return len(str(atom)) == 0
    return False


def carrier_edges(ast: IrAst) -> tuple[RuleEdge, ...]:
    """Every edge where a child rule can cover its parent's entire span."""
    rules = _rules(ast)
    empty = _nullable(rules)
    edges: list[RuleEdge] = []
    for rule in rules:
        for arm in _arms(rule):
            items = [item for item in arm if isinstance(item, IrItem)]
            refs = [
                position
                for position, item in enumerate(items)
                if isinstance(item[0], IrRuleRef)
            ]
            for slot, position in enumerate(refs):
                others = [item for index, item in enumerate(items) if index != position]
                if all(_item_nullable(other, empty) for other in others):
                    child = items[position][0]
                    edges.append(RuleEdge(str(rule.name), str(child), slot))
    return tuple(edges)


def child_edges(ast: IrAst) -> tuple[RuleEdge, ...]:
    """Every value-carrying parent→child edge, cycle-capable or not.

    Visibility and injectivity are questions about where a value can FLOW, so
    they read this graph; only cycle detection reads the narrower
    :func:`carrier_edges`.
    """
    edges: list[RuleEdge] = []
    for rule in _rules(ast):
        for arm in _arms(rule):
            items = [item for item in arm if isinstance(item, IrItem)]
            refs = [item[0] for item in items if isinstance(item[0], IrRuleRef)]
            for slot, child in enumerate(refs):
                edges.append(RuleEdge(str(rule.name), str(child), slot))
    return tuple(edges)


def grammar_verdict(grammar: str, policies: dict[str, str]) -> GrammarVerdict:
    """Classify a grammar × algebra pair before any input is seen.

    :param grammar: The authored GBNF source.
    :param policies: The rule-name → completion-operation program.
    :returns: The binding-time verdict and its component census.
    """
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    start = "".join(str(part) for part in ast[1])
    names = tuple(str(rule.name) for rule in _rules(ast))
    edges = carrier_edges(ast)
    flow = child_edges(ast)
    classified = {
        edge: slot_class(policies.get(edge.parent, ""), edge.slot)
        for edge in edges + flow
    }
    adjacency: dict[str, tuple[str, ...]] = {name: () for name in names}
    for edge in edges:
        adjacency[edge.parent] = adjacency[edge.parent] + (edge.child,)
    visible = _rule_reach(names, flow, classified, start, frozenset({CONST}))
    injective = _rule_reach(names, flow, classified, start, frozenset({CONST, FINITE}))
    groups = components(names, adjacency)
    kinds: list[str] = []
    refused: list[str] = []
    for group in groups:
        kind = _rule_component_kind(group, edges, classified, visible, injective)
        kinds.append(kind)
        if kind == CYCLIC_UNREPRESENTABLE:
            refused.append(group[0])
    message = (
        "binding refuses: "
        + ", ".join(sorted(refused))
        + " carry a value-growing zero-width cycle consumed by a bounded-image"
        " operation"
        if refused
        else "binding accepts"
    )
    return GrammarVerdict(bool(refused), tuple(groups), tuple(kinds), message)


def _rule_reach(
    names: tuple[str, ...],
    edges: tuple[RuleEdge, ...],
    classified: dict[RuleEdge, str],
    start: str,
    blocked: frozenset[str],
) -> dict[str, bool]:
    """Rules reachable from the start rule through unblocked carrier edges."""
    outgoing: dict[str, list[RuleEdge]] = {}
    for edge in edges:
        outgoing.setdefault(edge.parent, []).append(edge)
    marked = {name: False for name in names}
    marked[start] = True
    pending = [start]
    while pending:
        name = pending.pop()
        for edge in outgoing.get(name, ()):
            if classified[edge] in blocked or marked.get(edge.child, True):
                continue
            marked[edge.child] = True
            pending.append(edge.child)
    return marked


def _rule_component_kind(
    group: tuple[str, ...],
    edges: tuple[RuleEdge, ...],
    classified: dict[RuleEdge, str],
    visible: dict[str, bool],
    injective: dict[str, bool],
) -> str:
    """The binding-time classification of one rule-graph component."""
    members = set(group)
    internal = [
        edge for edge in edges if edge.parent in members and edge.child in members
    ]
    if len(group) == 1 and not any(edge.parent == edge.child for edge in internal):
        return ACYCLIC
    carrying = [
        (edge.parent, edge.child, classified[edge])
        for edge in internal
        if classified[edge] in (IDENT, GROW)
    ]
    carriers, growing = _carriers(group, carrying)
    if not growing:
        return CYCLIC_BOUNDED
    return _growing_kind(carriers, injective, visible)


class Case(NamedTuple):
    """One cyclic witness and the verdict every mechanism must agree on."""

    name: str
    grammar: str
    text: str
    policies: dict[str, str]
    differs: bool
    kind: str
    one_lap_differs: bool
    oracle_ceiling: int = 7


RING = 'root ::= s\ns ::= t | "x"\nt ::= s\n'
UNIT = 'root ::= a\na ::= b | "x"\nb ::= a\n'
NULLABLE_STAR = (
    'root ::= pad list\nlist ::= gap*\ngap ::= item?\nitem ::= "a"\npad ::= "x"\n'
)
TWO_KEY = 'root ::= s\ns ::= t | "x"\nt ::= u\nu ::= s | "y"\n'
ACYCLIC_TWIN = 'root ::= s\ns ::= "x"\n'
ISLAND_CYCLE = "root ::= c\nc ::= d | t\nd ::= c\n" + harness.ISLAND
SIBLING_CYCLE = 'root ::= p | q\np ::= c\nq ::= c\nc ::= d | "x"\nd ::= c\n'
MIXED_SCC = 'root ::= e\ne ::= a\na ::= e | b | "x"\nb ::= a\n'
DEEP_CYCLE = 'root ::= c list\nc ::= d | "x"\nd ::= c\nlist ::= item*\nitem ::= [ab]\n'

CASES = (
    Case(
        "ring-depth3-one-lap-misses",
        RING,
        "x",
        {"root": "atmost2", "s": "ring", "t": "pass"},
        True,
        CYCLIC_BOUNDED,
        False,
    ),
    Case(
        "ring-depth1-one-lap-agrees",
        RING,
        "x",
        {"root": "atmost1", "s": "ring", "t": "pass"},
        True,
        CYCLIC_BOUNDED,
        True,
    ),
    Case(
        "ring-dropped-root",
        RING,
        "x",
        {"root": "drop", "s": "ring", "t": "pass"},
        False,
        CYCLIC_BOUNDED,
        False,
    ),
    Case("unit-cycle-growing", UNIT, "x", {}, True, CYCLIC_INFINITE, True, 5),
    Case(
        "unit-cycle-dropped-root",
        UNIT,
        "x",
        {"root": "drop"},
        False,
        CYCLIC_OPAQUE,
        False,
    ),
    Case(
        "identity-cycle",
        UNIT,
        "x",
        {"a": "pass", "b": "pass"},
        False,
        CYCLIC_BOUNDED,
        False,
    ),
    Case(
        "two-key-cycle-bounded",
        TWO_KEY,
        "x",
        {"root": "atmost2", "s": "ring", "t": "pass", "u": "pass"},
        True,
        CYCLIC_BOUNDED,
        False,
        12,
    ),
    Case("two-key-cycle-growing", TWO_KEY, "x", {}, True, CYCLIC_INFINITE, True, 4),
    Case(
        "acyclic-twin-of-ring",
        ACYCLIC_TWIN,
        "x",
        {"root": "atmost1"},
        False,
        ACYCLIC,
        False,
    ),
    Case(
        "nullable-star-consuming-item",
        NULLABLE_STAR,
        "xa",
        {},
        False,
        ACYCLIC,
        False,
    ),
    Case(
        "sibling-roots-over-cycle",
        SIBLING_CYCLE,
        "x",
        {},
        True,
        CYCLIC_INFINITE,
        True,
        4,
    ),
    # A dropping/bounded consumer INSIDE the growing cycle's own component:
    # the reachability lanes must be read on the carriers, not on the whole
    # strongly connected component, or these misclassify.
    Case(
        "mixed-scc-dropping-consumer",
        MIXED_SCC,
        "x",
        {"root": "pass", "e": "drop", "b": "pass"},
        False,
        CYCLIC_OPAQUE,
        False,
    ),
    Case(
        "mixed-scc-bounded-consumer",
        MIXED_SCC,
        "x",
        {"root": "atmost1", "e": "drop", "b": "pass"},
        False,
        CYCLIC_OPAQUE,
        False,
    ),
    Case(
        "sibling-roots-over-cycle-dropped",
        SIBLING_CYCLE,
        "x",
        {"root": "drop", "p": "drop", "q": "drop"},
        False,
        CYCLIC_OPAQUE,
        False,
    ),
)

REFUSED = Case(
    "growing-cycle-under-bounded-consumer",
    RING,
    "x",
    {"root": "atmost1", "s": "", "t": "pass"},
    True,
    CYCLIC_UNREPRESENTABLE,
    True,
)


def _run_case(case: Case) -> tuple[Outcome, OracleReport, MeaningSet, float]:
    """Run one witness through the mechanism, the oracle, and the one-lap lane."""
    kernel = Kernel(tables_for(case.grammar, len(case.text)), case.text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError(f"cyclic meaning: {case.name} did not parse")
    root = harness.accept_handle(kernel)
    metrics = Metrics()
    started = time.process_time()
    outcome = exact_meanings(kernel, root, case.policies, {}, {}, metrics)
    elapsed = time.process_time() - started
    oracle = bounded_depth_meanings(
        kernel, root, case.policies, {}, {}, case.oracle_ceiling
    )
    one_lap = one_lap_meanings(kernel, root, case.policies, {}, {})
    return outcome, oracle, one_lap, elapsed


def _early_lane(case: Case) -> Outcome:
    """The same mechanism with the injective-sky early exit switched on."""
    kernel = Kernel(tables_for(case.grammar, len(case.text)), case.text, True).run()
    root = harness.accept_handle(kernel)
    return exact_meanings(
        kernel, root, case.policies, {}, {}, Metrics(), early_exit=True
    )


def _check_oracle(case: Case, outcome: Outcome, oracle: OracleReport) -> None:
    """Hold the mechanism against the independent bounded-depth enumeration."""
    if case.kind == CYCLIC_INFINITE:
        # An infinite family cannot stabilize; the oracle's evidence is that
        # every deeper rung still adds meanings.
        assert oracle.unbounded, (case.name, oracle.ladder)
        assert len(oracle.meanings) > 1, case.name
        return
    assert oracle.stable, (case.name, oracle.ladder)
    assert (len(oracle.meanings) > 1) == case.differs, (case.name, oracle.meanings)
    assert set(outcome.meanings) == set(oracle.meanings), (
        case.name,
        outcome.meanings,
        oracle.meanings,
    )


def _check_case(case: Case) -> None:
    """Assert the mechanism, the oracle, and the declared verdict all agree."""
    tracemalloc.start()
    outcome, oracle, one_lap, elapsed = _run_case(case)
    allocated, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert outcome.differs == case.differs, case.name
    assert outcome.kind == case.kind, (case.name, outcome.kind)
    _check_oracle(case, outcome, oracle)
    binding = grammar_verdict(case.grammar, case.policies)
    assert binding.refused is False, case.name
    # Soundness direction: every chart cycle must appear in the binding-time
    # carrier graph. The converse does not hold — canonicalisation can remove
    # a potential cycle before the chart is built, so binding over-approximates.
    if outcome.kind != ACYCLIC:
        assert case.kind in binding.kinds, (case.name, binding.kinds)
    one_lap_differs = len(one_lap) > 1
    assert one_lap_differs == case.one_lap_differs, (case.name, one_lap)
    early = _early_lane(case)
    assert early.differs == case.differs, (case.name, early)
    print(
        "cyclic-case",
        case.name,
        f"kind={outcome.kind}",
        f"differs={outcome.differs}",
        f"oracle_differs={len(oracle.meanings) > 1}",
        f"oracle_stable_from={oracle.stabilized_at}/{oracle.ceiling}",
        f"oracle_ladder={list(oracle.ladder)}",
        f"one_lap_differs={one_lap_differs}"
        + ("  <-- ONE-LAP UNSOUND" if one_lap_differs != case.differs else ""),
        f"one_lap_set={len(one_lap)}",
        f"exact_set={len(outcome.meanings)}"
        + ("  (classification decides)" if outcome.kind == CYCLIC_INFINITE else ""),
        f"components={outcome.components}",
        f"cyclic_components={outcome.cyclic_components}",
        f"laps={outcome.laps}",
        f"ops={outcome.ops}",
        f"retained={outcome.retained}",
        f"max_live={outcome.max_live}",
        f"early_ops={early.ops}",
        f"early_exit={early.early}",
        f"alloc_bytes={allocated}",
        f"cpu={elapsed:.6f}",
        sep="\t",
    )


def prove_binding_refusal() -> None:
    """The one refused class refuses at BINDING, before any input."""
    binding = grammar_verdict(REFUSED.grammar, REFUSED.policies)
    assert binding.refused, binding
    assert CYCLIC_UNREPRESENTABLE in binding.kinds
    kernel = Kernel(
        tables_for(REFUSED.grammar, len(REFUSED.text)), REFUSED.text, True
    ).run()
    root = harness.accept_handle(kernel)
    try:
        exact_meanings(kernel, root, REFUSED.policies, {}, {}, Metrics())
    except CyclicRefusal as error:
        message = str(error)
    else:
        raise AssertionError("the unrepresentable component was not refused")
    print(
        "binding-refusal",
        f"refused_at_binding={binding.refused}",
        f"parse_refusal={message.split(';')[0]}",
        "the parse-time refusal is redundant: binding already declined",
        sep="\t",
    )


def prove_formulation_independence() -> None:
    """The verdict follows the composed grammar and algebra, nothing else."""
    renamed = 'alpha ::= beta\nbeta ::= gamma | "x"\ngamma ::= beta\n'
    renamed_policies = {"alpha": "atmost1", "beta": "", "gamma": "pass"}
    assert grammar_verdict(renamed, renamed_policies).refused
    assert (
        grammar_verdict(renamed, renamed_policies).kinds
        == grammar_verdict(REFUSED.grammar, REFUSED.policies).kinds
    )
    spaced = RING.replace("::=", " ::= ").replace("\n", "\n\n")
    assert (
        grammar_verdict(spaced, CASES[0].policies).kinds
        == grammar_verdict(RING, CASES[0].policies).kinds
    )
    assert not grammar_verdict(ACYCLIC_TWIN, {"root": "atmost1"}).refused
    hoisted = 'root ::= (s)\ns ::= (t) | "x"\nt ::= (s)\n'
    assert grammar_verdict(hoisted, CASES[0].policies).refused is False
    print(
        "formulation-independence",
        "renaming every rule preserves the refusal and its component census;"
        " respelling and group-hoisting the same formulation preserve the"
        " verdict; an ACYCLIC formulation of the same language binds — the"
        " refused property is the value-growing zero-width cycle itself,"
        " derived generically from the normalized grammar plus the declared"
        " operation classes, with no input, rule-name case, or privileged"
        " formulation",
        sep="\t",
    )


def prove_island_cycle() -> None:
    """A cyclic chart carrying delegated island leaf options stays exact."""
    text = "xy"
    island = tables_for(harness.ISLAND, len(text))
    outer = tables_for(ISLAND_CYCLE, len(text))
    metrics = Metrics()
    run = harness.outer_run(outer, island, text, "t", {}, harness.Counters())
    outcome = exact_meanings(
        run.kernel, run.root, {}, run.occurrences, run.seeds, metrics
    )
    oracle = bounded_depth_meanings(
        run.kernel, run.root, {}, run.occurrences, run.seeds
    )
    assert outcome.differs and len(oracle.meanings) > 1
    print(
        "island-cycle",
        f"kind={outcome.kind}",
        f"differs={outcome.differs}",
        f"seeds={len(run.seeds)}",
        f"leaf_options={sum(1 + len(s.alternates) for s in run.seeds.values())}",
        f"oracle_differs={len(oracle.meanings) > 1}",
        f"ops={outcome.ops}",
        sep="\t",
    )


def prove_deep_cycles() -> None:
    """A cyclic component under an ordinary-depth document stays stack-safe."""
    for pad in (2_000, 8_000, 32_000):
        text = "x" + "a" * pad
        kernel = Kernel(tables_for(DEEP_CYCLE, len(text)), text, True).run()
        if accept_item(kernel) < 0:
            raise UnsupportedConstructError("cyclic meaning: deep parse failed")
        root = harness.accept_handle(kernel)
        metrics = Metrics()
        started_cpu = time.process_time()
        started_wall = time.perf_counter()
        outcome = exact_meanings(kernel, root, {}, {}, {}, metrics, early_exit=True)
        cpu = time.process_time() - started_cpu
        wall = time.perf_counter() - started_wall
        assert outcome.differs and outcome.kind == CYCLIC_INFINITE
        assert outcome.early
        print(
            "deep-cycle",
            f"chars={len(text)}",
            f"kind={outcome.kind}",
            f"differs={outcome.differs}",
            f"early_exit={outcome.early}",
            f"ops={outcome.ops}",
            f"components={outcome.components}",
            f"cpu={cpu:.6f}",
            f"wall={wall:.6f}",
            sep="\t",
        )


def prove_nested_island_cycle() -> None:
    """A cyclic chart above NESTED delegated islands stays exact."""
    text = "xy"
    nested = tables_for(harness.INNER, len(text))
    island = tables_for(harness.ISLAND_NESTED, len(text))
    outer = tables_for(
        "root ::= c\nc ::= d | t\nd ::= c\n" + harness.ISLAND_NESTED, len(text)
    )
    run = harness.outer_run(
        outer, island, text, "t", {}, harness.Counters(), nested, "inner"
    )
    metrics = Metrics()
    outcome = exact_meanings(
        run.kernel, run.root, {}, run.occurrences, run.seeds, metrics
    )
    oracle = bounded_depth_meanings(
        run.kernel, run.root, {}, run.occurrences, run.seeds, 4
    )
    assert outcome.differs and len(oracle.meanings) > 1
    print(
        "nested-island-cycle",
        f"kind={outcome.kind}",
        f"differs={outcome.differs}",
        f"seeds={len(run.seeds)}",
        f"leaf_options={sum(1 + len(s.alternates) for s in run.seeds.values())}",
        f"oracle_ladder={list(oracle.ladder)}",
        f"ops={outcome.ops}",
        sep="\t",
    )


def prove_scaling() -> None:
    """The mechanism is linear in chart nodes where the fallback was 2^k."""
    for points in (1, 2, 3, 4, 6):
        extra = "".join(
            f's{index} ::= p{index} | q{index}\np{index} ::= "y"\nq{index} ::= "y"\n'
            for index in range(points - 1)
        )
        body = " ".join(f"s{index}" for index in range(points - 1))
        grammar = (
            (f"root ::= c {body}\n" if body else "root ::= c\n")
            + 'c ::= d | "x"\nd ::= c\n'
            + extra
        )
        text = "x" + "y" * (points - 1)
        kernel = Kernel(tables_for(grammar, len(text)), text, True).run()
        root = harness.accept_handle(kernel)
        metrics = Metrics()
        started = time.process_time()
        outcome = exact_meanings(kernel, root, {}, {}, {}, metrics)
        elapsed = time.process_time() - started
        early_metrics = Metrics()
        early_started = time.process_time()
        early = exact_meanings(kernel, root, {}, {}, {}, early_metrics, early_exit=True)
        early_elapsed = time.process_time() - early_started
        assert early.differs == outcome.differs
        lap = one_lap_meanings(kernel, root, {}, {}, {})
        print(
            "scaling",
            f"arm_points={points}",
            f"kind={outcome.kind}",
            f"chart_nodes={len(build_chart(kernel, accepting_roots(kernel, root)).nodes)}",
            f"full_ops={outcome.ops}",
            f"full_retained={outcome.retained}",
            f"full_max_live={outcome.max_live}",
            f"early_ops={early.ops}",
            f"early_exit={early.early}",
            f"one_lap_assignments={2**points}",
            f"one_lap_folds={len(lap)}",
            f"full_cpu={elapsed:.6f}",
            f"early_cpu={early_elapsed:.6f}",
            sep="\t",
        )


def main() -> None:
    """Differential the exact mechanism against the bounded-depth oracle."""
    for case in CASES:
        _check_case(case)
    prove_binding_refusal()
    prove_formulation_independence()
    prove_island_cycle()
    prove_nested_island_cycle()
    prove_deep_cycles()
    prove_scaling()
    print(
        "invariant",
        "a chart cycle is a zero-width SCC; the component terminates iff no"
        " grow edge lies on a cycle carrying no const/finite edge; terminating"
        " components are solved by a monotone Kleene fixpoint over exact"
        " deduplicated value sets, whose termination follows from the"
        " classification's finite value domain and whose monotonicity is"
        " asserted every lap; a surviving grow component is judged on its"
        " CARRIERS — the ident/grow upward closure of the growing sub-cycle,"
        " never the whole component — and is INFINITE under an injective path"
        " to an accepting root (classification decides), OPAQUE when no"
        " carrier is value-visible (carriers frozen to a representative, every"
        " non-carrier member still exact), and otherwise refused at BINDING"
        " with words; the one-lap relation is neither the exact set nor a"
        " sound refusal test",
        sep="\t",
    )


if __name__ == "__main__":
    main()
