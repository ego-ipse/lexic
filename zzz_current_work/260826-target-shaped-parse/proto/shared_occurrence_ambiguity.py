"""Semantic ambiguity under a SHARED forest node, against an unrolled oracle.

`shared_forest_refold.py` exposes four real shapes whose derivation reuses one
subtree — duplicate slot, pending frame, sibling memo, transparent synthetic —
and shows the production fold executes a shared node's body a number of times
that depends on traversal order. It says nothing about MEANING. This module
puts semantic ambiguity under each shape and asks the question Prototype 15
left open: does the per-node exact relation
(`island_continuation.exact_meanings`) agree with a relation that gives every
grammatical OCCURRENCE its own family choice?

**Three lanes, deliberately different mechanisms.**

- The CANDIDATE is `island_continuation.exact_meanings` — one deduplicated
  meaning set per chart node, each consuming slot ranging over it.
- The ORACLE is :func:`unrolled_meanings`, written here: it re-resolves the
  chain at every occurrence, keys its results on the occurrence PATH rather
  than on the handle, never memoizes across occurrences, and compares values
  with the production `same_value` instead of the candidate's ``repr`` dedup.
  It calls no candidate function.
- The CONTROL being DISPROVED is :func:`key_correlated_meanings`: one family
  per arm-choice key across a whole derivation, through real `FastTree` builds.
  That is Prototype 15's own oracle, and six witnesses here show it answers a
  strictly smaller set than either lane above.

**What the three lanes establish.** A packed forest node is keyed by
``(item, end)``: it is a VALUE, and two grammatical occurrences of one rule can
reach it. The occurrence is named by ``(consuming handle, family index, slot)``.
That triple is DERIVABLE from what the forest already holds — nothing new need
be recorded during recognition — but no structure carries it:
`cyclic_meaning.Edge` is ``(parent, child, slot)`` with no family field, and
production's `forest/chart.py` has no parent-to-child edge at all. Materialising
it is real work, on the ambiguity path only.
The shared value's set is computed once; each consuming slot ranges over it
independently; and the consumer's own operation runs once per slot consumption.
Correlating the two occurrences — which a key-global assignment does — loses
meanings that the grammar derives.

Run directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product
from typing import NamedTuple

import cyclic_meaning as algebra
import island_alternate_seed as harness
import island_continuation as candidate

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import (
    IrArg,
    IrArgs,
    IrBuild,
    IrCompare,
    IrMap,
    IrNode,
    IrOp,
    IrRuleRef,
    IrSelf,
    IrStr,
    IrTuple,
    Reducer,
)
from lexic.ir.flavour import IrFlavour
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import (
    DERIVATIONS,
    ParseTree,
    PayloadLeaf,
)
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
    accept_node,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.normalize import normalize

FOCUS = IrStr("")
"""The focus every witness body receives; no witness action reads it."""

MARK_P = IrStr("P")
MARK_Q = IrStr("Q")
MARK_N = IrStr("N")

type Step = tuple[int, int, int]
"""One occurrence edge: ``(consuming handle, family index, kid slot)``."""

type Occurrence = tuple[Step, ...]
"""A root-down path of occurrence edges — what names an occurrence."""


# ── the shared reducer application ────────────────────────────────────────


def apply_body(reducer: Reducer, name: str, kids: Sequence[IrSelf]) -> IrSelf:
    """Run the rule's REAL authored action body over its argument channel."""
    return reducer.body(IrRuleRef(name)).eval(reducer, FOCUS, tuple(kids))


def add_unique(found: list[IrSelf], value: IrSelf) -> None:
    """Append ``value`` unless an observably equal meaning is already present.

    Deliberately NOT the candidate's ``repr``-keyed dedup: this is the
    production `same_value` relation, so the oracle and the candidate agree
    only if the composition is right rather than because they share a key.
    """
    for seen in found:
        if same_value(seen, value):
            return
    found.append(value)


def same_meaning_set(one: Sequence[IrSelf], other: Sequence[IrSelf]) -> bool:
    """Whether two meaning sets hold the same meanings, order aside."""
    if len(one) != len(other):
        return False
    return all(any(same_value(left, right) for right in other) for left in one)


# ── the independent occurrence-unrolled oracle ────────────────────────────


class UnrolledCounts:
    """What the oracle visited — its own lane, never compared to a set size."""

    __slots__ = ("occurrences", "applications", "resolves", "by_rule")

    def __init__(self) -> None:
        self.occurrences = 0
        self.applications = 0
        self.resolves = 0
        self.by_rule: dict[str, int] = {}

    def apply(self, rule: str) -> None:
        """Record one authored-body EXECUTION, attributed to the rule it ran for.

        Per-rule rather than a total, because "the effect executes per slot
        consumption" is a claim about how often one consumer's body RUNS — a
        meaning-set cardinality cannot establish it.
        """
        self.applications += 1
        self.by_rule[rule] = self.by_rule.get(rule, 0) + 1


def occurrence_families(
    kernel: Kernel, handle: int, counts: UnrolledCounts
) -> tuple[harness.Resolved, ...]:
    """Resolve one completion's families FRESH, at this occurrence.

    The oracle never reads a pre-built per-node family table: it re-resolves the
    binarised chain every time an occurrence reaches the handle, so two
    occurrences of one node cannot share a decision by construction.
    """
    counts.resolves += 1
    keys = algebra.local_choice_keys(kernel, handle)
    return tuple(
        algebra.selected_resolved(kernel, handle, assignment)
        for assignment in algebra.assignments(kernel, list(keys))
    )


def child_occurrences(
    resolved: harness.Resolved, handle: int, family: int, at: Occurrence
) -> list[tuple[int, Occurrence]]:
    """Each child handle of one family, with the occurrence path it stands at."""
    return [
        (child, at + ((handle, family, slot),))
        for slot, child in zip(algebra.child_slots(resolved), resolved.children)
    ]


def unrolled_meanings(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counts: UnrolledCounts,
    partial: frozenset[str] = frozenset(),
) -> tuple[IrSelf, ...]:
    """Every requested-root meaning, with a FAMILY CHOICE PER OCCURRENCE.

    Results are keyed on the occurrence path, so a node reached through two
    grammatical occurrences is expanded twice and the two expansions choose
    independently. Iterative, so a document-deep chart cannot overflow.

    :param kernel: The finished real Earley kernel.
    :param roots: Every accepting handle.
    :param options: Delegated-leaf option sets, by leaf identity.
    :param reducer: The real reducer whose authored bodies define meaning.
    :param counts: The oracle's own visit counters.
    :returns: The deduplicated requested-root meaning set.
    :raises UnsupportedConstructError: On a cyclic chart, which
        `cyclic_meaning.exact_meanings` owns.
    """
    results: dict[Occurrence, tuple[IrSelf, ...]] = {}
    stack: list[tuple[int, Occurrence, bool]] = [
        (root, ((root, 0, index),), False) for index, root in enumerate(roots)
    ]
    while stack:
        handle, at, expanded = stack.pop()
        _refuse_occurrence_cycle(kernel, handle, at)
        families = occurrence_families(kernel, handle, counts)
        if not expanded:
            counts.occurrences += 1
            stack.append((handle, at, True))
            stack.extend(_pending_children(families, handle, at, results))
            continue
        results[at] = _occurrence_set(
            kernel, handle, at, families, results, options, reducer, counts, partial
        )
    found: list[IrSelf] = []
    for index, root in enumerate(roots):
        for meaning in results[((root, 0, index),)]:
            add_unique(found, meaning)
    if not found:
        # The ONLY refusal. Every requested-root branch lost its meaning, so
        # the document has none; refusing here — and nowhere below — is what
        # keeps "an internal node has no image" from being confused with "this
        # document does not parse".
        raise UnsupportedConstructError(
            "shared occurrence: no complete requested-root meaning survives;"
            " every derivation's operations refused"
        )
    return tuple(found)


def _pending_children(
    families: Sequence[harness.Resolved],
    handle: int,
    at: Occurrence,
    results: dict[Occurrence, tuple[IrSelf, ...]],
) -> list[tuple[int, Occurrence, bool]]:
    """The child occurrences of one node that still need expanding."""
    out: list[tuple[int, Occurrence, bool]] = []
    for family, resolved in enumerate(families):
        for child, path in child_occurrences(resolved, handle, family, at):
            if path not in results:
                out.append((child, path, False))
    return out


def _refuse_occurrence_cycle(kernel: Kernel, handle: int, at: Occurrence) -> None:
    """A handle inside its own occurrence path is a cycle this lane refuses."""
    if any(step[0] == handle for step in at[:-1]):
        raise UnsupportedConstructError(
            "shared occurrence: this chart has a zero-width cycle at"
            f" {harness._name(kernel, handle)!r}; the exact relation there"
            " belongs to cyclic_meaning.exact_meanings, not to this module"
        )


def _occurrence_set(
    kernel: Kernel,
    handle: int,
    at: Occurrence,
    families: Sequence[harness.Resolved],
    results: dict[Occurrence, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counts: UnrolledCounts,
    partial: frozenset[str],
) -> tuple[IrSelf, ...]:
    """One occurrence's meanings, under BOTTOM semantics.

    Three rules, and no raise anywhere below the root. A family whose operation
    refuses contributes nothing. A family one of whose slot lanes is EMPTY —
    because the child occurrence has no meaning — contributes nothing, so an
    empty internal image eliminates exactly the parent families that consume
    it and leaves the parent's other families alone. An occurrence with no
    surviving family returns the empty set and lets its own consumers apply the
    same rule. Only the requested ROOT decides refusal, in
    :func:`unrolled_meanings`.

    `cyclic_meaning.node_set:657-661` already does this — an empty option lane
    is a `continue`, not an error — so bottom semantics is the production
    precedent rather than a new invention here.
    """
    name = harness._name(kernel, handle)
    found: list[IrSelf] = []
    for family, resolved in enumerate(families):
        lanes = _occurrence_lanes(resolved, handle, family, at, results, options)
        if lanes is None:
            continue
        for kids in product(*lanes):
            counts.apply(name)
            meaning = apply_or_none(reducer, name, kids, partial)
            if meaning is not None:
                add_unique(found, meaning)
    return tuple(found)


def apply_or_none(
    reducer: Reducer, name: str, kids: tuple[IrSelf, ...], partial: frozenset[str]
) -> IrSelf | None:
    """Run the authored body; a DECLARED partial operation that refuses has none.

    Bottom semantics, in the one place it is decided.
    `operation_slot_laws._prove_partial_operation` rules that an operation which
    refuses produces no value at all — the ``finite(0)`` bottom — so the family
    contributes nothing rather than contributing a marker.

    **The absorption is narrow by DECLARATION, not by exception type.** Only a
    rule the witness declares partial may swallow a refusal; every other
    `UnsupportedConstructError` propagates, because that type is also what an
    open `IrDispatch`/`IrTypeMap` raises for an undeclared construct and
    absorbing it would turn an engine failure into a silently dropped family.
    Production cannot use a declaration list: it needs a **distinct
    value-refusal exception**, raised by the operation itself and by nothing
    else. That signal does not exist today and is
    :func:`prove_the_required_production_signal`'s subject.
    """
    try:
        return apply_body(reducer, name, kids)
    except UnsupportedConstructError:
        if name in partial:
            return None
        raise


def _occurrence_lanes(
    resolved: harness.Resolved,
    handle: int,
    family: int,
    at: Occurrence,
    results: dict[Occurrence, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> list[tuple[IrSelf, ...]] | None:
    """One family's per-slot lanes, or ``None`` when a lane is EMPTY.

    ``None`` eliminates this one family and nothing else — the parent's other
    families are untouched. That is what "an empty internal image eliminates
    only the parent families consuming it" means operationally.
    """
    width = len(resolved.children) + len(resolved.leaves)
    paths = iter(child_occurrences(resolved, handle, family, at))
    lanes: list[tuple[IrSelf, ...]] = []
    for index in range(width):
        if index in resolved.slots:
            lane = options[id(resolved.leaves[resolved.slots.index(index)])]
        else:
            lane = results[next(paths)[1]]
        if not lane:
            return None
        lanes.append(lane)
    return lanes


# ── the control being disproved: one family per key, globally ─────────────


def key_correlated_meanings(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    partial: frozenset[str] = frozenset(),
) -> tuple[IrSelf, ...]:
    """Prototype 15's oracle: ONE family per arm-choice key per derivation.

    Kept only as the relation this round disproves. Where a chart node is
    reached by two occurrences and its own choice sits inside its own chain,
    fixing that key once forces both occurrences to the same arm — so the set
    it produces is a strict subset of the grammar's meanings.
    """
    points = _arm_points(kernel, roots)
    found: list[IrSelf] = []
    for root in roots:
        for assignment in algebra.assignments(kernel, points):
            tree = FastTree(kernel, dict(assignment)).build(root)
            if not isinstance(tree, ParseTree):
                continue
            for combo in _leaf_combos(options):
                meaning = _tree_meaning(tree, reducer, combo, partial)
                if meaning is not None:
                    add_unique(found, meaning)
    return tuple(found)


def _arm_points(kernel: Kernel, roots: tuple[int, ...]) -> list[int]:
    """Every authored arm-choice key reachable from any accepting item."""
    return candidate._arm_points(kernel, roots)


# ── the third lane: production's own trampolined enumeration ──────────────


class Enumerated(NamedTuple):
    """What production's forest enumeration produced on one witness.

    :ivar derivations: How many complete `ParseTree`s it emitted.
    :ivar meanings: Distinct meanings among the WELL-FORMED ones.
    :ivar malformed: Derivations holding a node whose rule needs kids and has
        none — the truncation signature.
    """

    derivations: int
    meanings: int
    malformed: int


def production_enumeration(parsed: Parsed) -> Enumerated:
    """Enumerate every derivation through the SHIPPED forest reader.

    `forest.DERIVATIONS` over `readout.to_chart` is the one enumerator in the
    tree built on genuinely independent machinery: it walks the decoded
    `Chart.links` through `PrefixSource`/`ChildDerivs` and never touches
    `predecessor_chain`, `local_choice_keys` or `selected_resolved`. It is
    also occurrence-unrolled BY CONSTRUCTION — a fresh `NodeDerivs` per
    consumption, no memo across occurrences — which is exactly what this round
    wants from an oracle.

    It cannot be used as one, and :func:`prove_production_enumeration_truncates`
    is why.
    """
    trees = DERIVATIONS.eval(
        parsed.reducer, accept_node(parsed.kernel), IrTuple(to_chart(parsed.kernel))
    )
    built = [tree for tree in trees if isinstance(tree, ParseTree)]
    malformed = sum(1 for tree in built if _has_starved_node(tree, parsed.reducer))
    found: list[IrSelf] = []
    for tree in built:
        if _has_starved_node(tree, parsed.reducer):
            continue
        meaning = _tree_meaning(tree, parsed.reducer, {})
        if meaning is not None:
            add_unique(found, meaning)
    return Enumerated(len(built), len(found), malformed)


def _has_starved_node(tree: ParseTree, reducer: Reducer) -> bool:
    """Whether any node has no kids while its authored body indexes a channel.

    The truncation signature: `ForestCtx.open` emits the single empty prefix
    for a handle it believes is cyclic, which builds a `ParseTree` with no kids
    under a rule that always has one. Detected structurally — a body reaching
    `IrArg` over an empty channel cannot be evaluated at all.
    """
    stack: list[ParseTree] = [tree]
    while stack:
        node = stack.pop()
        kids = [kid for kid in node.kids if isinstance(kid, (ParseTree, PayloadLeaf))]
        if not kids and _reads_a_slot(reducer.body(IrRuleRef(str(node.symbol)))):
            return True
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    return False


def _reads_a_slot(body: IrSelf) -> bool:
    """Whether one authored body indexes its argument channel positionally."""
    pending: list[IrSelf] = [body]
    while pending:
        node = pending.pop()
        if isinstance(node, IrArg):
            return True
        if isinstance(node, IrNode):
            pending.extend(node.children())
    return False


def _leaf_combos(
    options: dict[int, tuple[IrSelf, ...]],
) -> list[dict[int, IrSelf]]:
    """Every delegated-leaf option combination."""
    combos: list[dict[int, IrSelf]] = [{}]
    for leaf_id, lane in options.items():
        combos = [{**combo, leaf_id: value} for combo in combos for value in lane]
    return combos


def _tree_meaning(
    tree: ParseTree,
    reducer: Reducer,
    overrides: dict[int, IrSelf],
    partial: frozenset[str] = frozenset(),
) -> IrSelf | None:
    """One complete derivation's meaning, or ``None`` when it has none.

    A single derivation has one value or no value: if any node's operation
    refuses, the whole derivation contributes nothing. There is no set to
    narrow here, so bottom semantics is just propagation.
    """
    order: list[ParseTree] = []
    stack: list[ParseTree] = [tree]
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    values: dict[int, IrSelf] = {}
    for node in reversed(order):
        found = _node_value(node, reducer, overrides, values, partial)
        if found is None:
            return None
        values[id(node)] = found
    return values[id(tree)]


def _node_value(
    node: ParseTree,
    reducer: Reducer,
    overrides: dict[int, IrSelf],
    values: dict[int, IrSelf],
    partial: frozenset[str],
) -> IrSelf | None:
    """One derivation node's value, or ``None`` when its operation refuses."""
    kids: list[IrSelf] = []
    for kid in node.kids:
        if isinstance(kid, ParseTree):
            if id(kid) not in values:
                return None
            kids.append(values[id(kid)])
        elif isinstance(kid, PayloadLeaf):
            kids.append(overrides[id(kid)])
    return apply_or_none(reducer, str(node.symbol), tuple(kids), partial)


# ── the candidate lane, and the bottom-semantics lane beside it ───────────


def candidate_meanings(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counters: candidate.Counters,
) -> tuple[IrSelf, ...]:
    """The CANDIDATE per-node relation, exactly as it stands.

    Not wrapped and not corrected. Where a witness has no refusing operation
    this is the relation under test; where one does, it RAISES, and
    :func:`prove_partial_family_defect` pins that as the implementation task it
    is.
    """
    return candidate.exact_meanings(
        kernel, roots, options, reducer, counters, candidate.SETTLEMENT_LANE
    )


def bottom_meanings(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    partial: frozenset[str],
) -> tuple[IrSelf, ...]:
    """The candidate's per-node shape with empty lanes propagated CORRECTLY.

    The minimal correction, not a second architecture: same family-aware chart,
    same per-node set, same deduplication through `same_value`. The two
    differences are the two the round asks for — a refusing declared-partial
    operation contributes no meaning, and a family with an empty slot lane is
    skipped instead of raising, exactly as `cyclic_meaning.node_set` already
    does. Refusal happens once, at the requested root.

    :raises UnsupportedConstructError: When no complete requested-root meaning
        survives.
    """
    chart = algebra.build_chart(kernel, roots)
    candidate._refuse_cyclic(chart, kernel)
    sets: dict[int, tuple[IrSelf, ...]] = {}
    for handle in candidate._topological(chart, roots):
        sets[handle] = _bottom_node(
            kernel, handle, chart, sets, options, reducer, partial
        )
    found: list[IrSelf] = []
    for root in roots:
        for meaning in sets.get(root, ()):
            add_unique(found, meaning)
    if not found:
        raise UnsupportedConstructError(
            "shared occurrence: no complete requested-root meaning survives;"
            " every derivation's operations refused"
        )
    return tuple(found)


def _bottom_node(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    partial: frozenset[str],
) -> tuple[IrSelf, ...]:
    """One node's image; an empty one eliminates only its consuming families."""
    name = harness._name(kernel, handle)
    found: list[IrSelf] = []
    for resolved in chart.resolveds[handle]:
        lanes = _bottom_lanes(resolved, sets, options)
        if lanes is None:
            continue
        for kids in product(*lanes):
            meaning = apply_or_none(reducer, name, kids, partial)
            if meaning is not None:
                add_unique(found, meaning)
    return tuple(found)


def _bottom_lanes(
    resolved: harness.Resolved,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> list[tuple[IrSelf, ...]] | None:
    """One family's per-slot lanes, or ``None`` when one of them is empty."""
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


# ── the witnesses ─────────────────────────────────────────────────────────

DUP_SLOT = 'root ::= a a "x"\na ::= b\nb ::= p | q\np ::= "y"*\nq ::= "z"*\n'
DUP_SLOT_ABNF = 'root = a a "x"\r\na = b\r\nb = p / q\r\np = *"y"\r\nq = *"z"\r\n'
DUP_TWIN = (
    'root ::= a1 a2 "x"\n'
    'a1 ::= b1\nb1 ::= p1 | q1\np1 ::= "y"*\nq1 ::= "z"*\n'
    'a2 ::= b2\nb2 ::= p2 | q2\np2 ::= "y"*\nq2 ::= "z"*\n'
)
PENDING_FRAME = (
    'root ::= a b\nb ::= a "z"\na ::= c\nc ::= p | q\np ::= "y"*\nq ::= "w"*\n'
)
SIBLING_MEMO = (
    'root ::= b c\nb ::= a "u"\nc ::= a "w"\n'
    'a ::= d\nd ::= p | q\np ::= "y"*\nq ::= "z"*\n'
)
ARM_SHARED = (
    'root ::= "[" m "]"\nm ::= l | r\nl ::= s "z"\nr ::= s "z"\n'
    's ::= u\nu ::= p | q\np ::= "x"\nq ::= "x"\n'
)
SYNTHETIC_SHARED = (
    'root ::= (b | c) (b | c) "x"\nb ::= d\nd ::= p | q\nc ::= "k"+\n'
    'p ::= "y"*\nq ::= "z"*\n'
)
SYNTHETIC_NODE_SHARED = 'root ::= (p | q) (p | q) "x"\np ::= "y"*\nq ::= "z"*\n'
SYNTHETIC_INTER = (
    'root ::= "[" m "]"\nm ::= l | r\nl ::= b* "z"\nr ::= b* "z"\n'
    'b ::= c\nc ::= p | q\np ::= "y"\nq ::= "y"\n'
)
"""A genuinely shared SYNTHETIC node: one `__rep_1`, two occurrence edges.

Normalization DEDUPS identical generated rules, so the ``b*`` written in both
``l`` and ``r`` becomes one `__rep_1` referenced from two slots — and at
``[1,2)`` one chart node carries both occurrence edges. It is transparent
(no reducer action, so it takes the default) and result-less in
`ModelFold`'s sense, and the ambiguity of ``c`` sits beneath it.
"""
SYNTHETIC_INTRA = (
    'root ::= "y"? "y"? s "x"\ns ::= t\nt ::= p | q\np ::= "w"*\nq ::= "v"*\n'
)
"""The same dedup, INTRA-derivation: one `__rep_1` at two slots of one arm.

``"y"?`` written twice becomes one `__rep_1`, and at ``[0,0)`` both slots of the
single root family consume that one node. The ambiguity sits beside it in
``s``, so the transparent shared node has to compose correctly while a meaning
choice flows past it.
"""
"""Two hoisted `__grp` nodes CONSUMING one shared rule at two occurrences.

The nearest this round gets to the transparent-synthetic shape, and the limit
is reported rather than papered over — see
:func:`prove_no_synthetic_node_is_ever_shared`. A synthetic node is result-less
in the production fold's sense (`ModelFold._fold_node` returns early for a rule
with no config entry, `src/lexic/parsing/fold.py:498-500`), so the walk
re-folds it; the meaning relation has no result-less node, because every chart
node gets a set.
"""
MIXED = (
    'root ::= a a s\na ::= b\nb ::= p | q\np ::= "y"*\nq ::= "z"*\n'
    's ::= m | n\nm ::= "x"\nn ::= "x"\n'
)
SIBLING_ROOTS = (
    'root ::= one | two\none ::= a a "x"\ntwo ::= a a "x"\n'
    'a ::= b\nb ::= p | q\np ::= "y"*\nq ::= "z"*\n'
)
UNAMBIGUOUS_SHARED = 'root ::= a a "x"\na ::= b\nb ::= p\np ::= "y"*\n'

ISLAND_SHARED = (
    'root ::= "[" m "]"\nm ::= l | r\nl ::= s "z"\nr ::= s "z"\ns ::= t\n'
    't ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
)
ISLAND_INTERIOR = 't ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'

INTERNED_TWIN = 'root ::= b c\nb ::= a "u"\nc ::= a "w"\na ::= "y"?\n'
"""`shared_forest_refold.py`'s sibling-memo grammar — unambiguously nullable."""

LEAVES = (("p", MARK_P), ("q", MARK_Q))
PASS_THROUGH = (("a", IrArg(0)), ("b", IrArg(0)))

APPEND = IrBuild(IrTuple, IrTuple(IrArg(0), IrArg(1)))
INSERT = IrBuild(
    IrMap, IrTuple(IrTuple(IrStr("k0"), IrArg(0)), IrTuple(IrStr("k1"), IrArg(1)))
)
VERDICT = IrCompare(IrArgs(), IrOp("=="), IrTuple(MARK_Q, MARK_P))
DUPLICATE = IrBuild(
    IrMap, IrTuple(IrTuple(IrArg(0), IrStr("v")), IrTuple(IrArg(1), IrStr("w")))
)


class Witness(NamedTuple):
    """One shared-DAG shape carrying semantic ambiguity.

    :ivar name: The witness label.
    :ivar shape: Which `shared_forest_refold.py` shape it instantiates.
    :ivar grammar: The source, in ``flavour``'s spelling.
    :ivar text: The input.
    :ivar actions: The real authored reducer bodies.
    :ivar shared: The rule whose chart node is consumed more than once, or ``""``
        when this witness shares only a tree OBJECT.
    :ivar consumptions: How many occurrence edges reach that node.
    :ivar meanings: The exact requested-root meaning count.
    :ivar correlated: What the key-global control answers — lower where the
        occurrences are independently mixable.
    :ivar flavour: The surface the grammar is written in.
    :ivar partial: Rules whose authored operation is DECLARED partial — the
        only ones whose refusal may be read as "no meaning" rather than
        propagated. Production needs a distinct exception instead; see
        :func:`prove_the_required_production_signal`.
    """

    name: str
    shape: str
    grammar: str
    text: str
    actions: tuple[tuple[str, IrSelf], ...]
    shared: str
    consumptions: int
    meanings: int
    correlated: int
    flavour: IrFlavour = GBNF_FLAVOUR
    partial: frozenset[str] = frozenset()


WITNESSES = (
    Witness(
        "duplicate-slot",
        "duplicate slot",
        DUP_SLOT,
        "x",
        (("root", IrArgs()),) + PASS_THROUGH + LEAVES,
        "a",
        2,
        4,
        2,
    ),
    Witness(
        "duplicate-slot-abnf",
        "duplicate slot",
        DUP_SLOT_ABNF,
        "x",
        (("root", IrArgs()),) + PASS_THROUGH + LEAVES,
        "a",
        2,
        4,
        2,
        ABNF_FLAVOUR,
    ),
    Witness(
        "pending-frame",
        "pending frame",
        PENDING_FRAME,
        "z",
        (("root", IrArgs()), ("b", IrArgs()), ("a", IrArg(0)), ("c", IrArg(0)))
        + LEAVES,
        "a",
        2,
        4,
        2,
    ),
    Witness(
        "sibling-memo",
        "sibling memo",
        SIBLING_MEMO,
        "uw",
        (
            ("root", IrArgs()),
            ("b", IrArg(0)),
            ("c", IrArg(0)),
            ("a", IrArg(0)),
            ("d", IrArg(0)),
        )
        + LEAVES,
        "",
        0,
        4,
        4,
    ),
    Witness(
        "arm-shared",
        "sibling memo (chart-shared twin)",
        ARM_SHARED,
        "[xz]",
        (
            ("root", IrArg(0)),
            ("m", IrArg(0)),
            ("l", IrArg(0)),
            ("r", IrArg(0)),
            ("s", IrArg(0)),
            ("u", IrArg(0)),
        )
        + LEAVES,
        "s",
        2,
        2,
        2,
    ),
    Witness(
        "transparent-synthetic",
        "transparent synthetic",
        SYNTHETIC_SHARED,
        "x",
        (("root", IrArgs()), ("b", IrArg(0)), ("d", IrArg(0)), ("c", IrStr("C")))
        + LEAVES,
        "b",
        2,
        4,
        2,
    ),
    Witness(
        "synthetic-consumers",
        "transparent synthetic consumers over one shared rule",
        SYNTHETIC_NODE_SHARED,
        "x",
        (("root", IrArgs()),) + LEAVES,
        "p",
        2,
        4,
        4,
    ),
    Witness(
        "mixed-shared-and-not",
        "duplicate slot + an unshared choice",
        MIXED,
        "x",
        (
            ("root", IrCompare(IrArgs(), IrOp("=="), IrTuple(MARK_Q, MARK_P, MARK_N))),
            ("a", IrArg(0)),
            ("b", IrArg(0)),
            ("s", IrArg(0)),
            ("m", IrStr("M")),
            ("n", MARK_N),
        )
        + LEAVES,
        "a",
        2,
        2,
        1,
    ),
    Witness(
        "sibling-accepting-roots",
        "duplicate slot under two accepting items",
        SIBLING_ROOTS,
        "x",
        (
            ("root", IrArg(0)),
            ("one", IrBuild(IrTuple, IrTuple(IrStr("L"), IrArg(0), IrArg(1)))),
            ("two", IrBuild(IrTuple, IrTuple(IrStr("R"), IrArg(0), IrArg(1)))),
        )
        + PASS_THROUGH
        + LEAVES,
        "a",
        4,
        8,
        4,
    ),
    Witness(
        "unambiguous-shared",
        "duplicate slot, one family",
        UNAMBIGUOUS_SHARED,
        "x",
        (("root", IrArgs()),) + PASS_THROUGH + (("p", MARK_P),),
        "a",
        2,
        1,
        1,
    ),
)


EFFECTS = (
    ("append", APPEND, 4, 2, frozenset()),
    ("insert", INSERT, 4, 2, frozenset()),
    ("verdict", VERDICT, 2, 1, frozenset()),
    ("duplicate", DUPLICATE, 2, 0, frozenset({"root"})),
)
"""Occurrence-owned effects: label, root body, exact meanings, correlated ones.

``duplicate`` is the one whose correlated count is ZERO: forcing both slots to
the same arm makes every derivation insert one key twice, so the refusing
operation removes the whole image. Executing the effect per SLOT CONSUMPTION
keeps the two mixed derivations, which is the grammar's own answer.
"""


# ── running one witness ───────────────────────────────────────────────────


class Parsed(NamedTuple):
    """One recognized witness and everything three lanes read from it."""

    kernel: Kernel
    roots: tuple[int, ...]
    chart: algebra.Chart
    reducer: Reducer
    options: dict[int, tuple[IrSelf, ...]]


_GRAMMARS: dict[tuple[str, str], ParserTables] = {}


def tables_for(source: str, flavour: IrFlavour, size: int) -> ParserTables:
    """Real compiled tables for one witness grammar, built once."""
    key = (source, type(flavour).__name__)
    found = _GRAMMARS.get(key)
    if found is not None:
        return found
    built = compile_tables(
        normalize(canonical_grammar(source, flavour)), tier_for(size)
    )
    _GRAMMARS[key] = built
    return built


def recognize(
    source: str, flavour: IrFlavour, text: str, actions: tuple[tuple[str, IrSelf], ...]
) -> Parsed:
    """Recognize one witness document once through the real Earley kernel."""
    kernel = Kernel(tables_for(source, flavour, len(text)), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError(f"shared occurrence: {source!r} did not parse")
    roots = algebra.accepting_roots(kernel, accept_handle(kernel))
    return Parsed(
        kernel,
        roots,
        algebra.build_chart(kernel, roots),
        candidate.reducer_of(actions),
        {},
    )


def slot_consumptions(chart: algebra.Chart) -> dict[int, list[tuple[int, int]]]:
    """Every distinct ``(consuming handle, slot)`` edge reaching each chart node.

    The measure sharing has to be taken on: a node consumed twice by ONE parent
    has one distinct parent and two occurrences, so counting parents alone
    reports the duplicate-slot shape as unshared. The chart lists one edge per
    packed FAMILY, so the same slot appears once per family of its consumer and
    is counted once here — a grammatical occurrence, not a family of it.
    """
    out: dict[int, list[tuple[int, int]]] = {}
    for edge in chart.edges:
        found = out.setdefault(edge.child, [])
        if (edge.parent, edge.slot) not in found:
            found.append((edge.parent, edge.slot))
    return out


def shared_nodes(kernel: Kernel, chart: algebra.Chart, rule: str) -> tuple[int, ...]:
    """Every chart node of ``rule`` reached by more than one occurrence edge."""
    consumptions = slot_consumptions(chart)
    return tuple(
        node
        for node in chart.nodes
        if harness._name(kernel, node) == rule and len(consumptions.get(node, ())) > 1
    )


def all_shared_nodes(kernel: Kernel, chart: algebra.Chart) -> tuple[str, ...]:
    """Every rule whose chart node is reached by more than one occurrence edge.

    Asked WITHOUT a rule name, so a witness declaring no shared node is checked
    rather than trusted: filtering by a declared name would report ``0`` for a
    grammar that shares something else entirely.
    """
    consumptions = slot_consumptions(chart)
    return tuple(
        sorted(
            harness._name(kernel, node)
            for node in chart.nodes
            if len(consumptions.get(node, ())) > 1
        )
    )


def computed_once(chart: algebra.Chart, roots: tuple[int, ...]) -> bool:
    """Whether the candidate's own node order visits every handle exactly once.

    `island_continuation.exact_meanings` calls its per-node set function once
    per element of this order, so "each handle appears once" IS "each shared
    node's set is computed once" on the candidate's real code path.
    """
    order = candidate._topological(chart, roots)
    return len(order) == len(set(order))


def _exercise(witness: Witness) -> Parsed:
    """Run one witness through all three lanes and check every claim."""
    parsed = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    counters = candidate.Counters()
    exact = candidate_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, counters
    )
    counts = UnrolledCounts()
    oracle = unrolled_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, counts
    )
    correlated = key_correlated_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer
    )
    nodes = shared_nodes(parsed.kernel, parsed.chart, witness.shared)
    consumptions = slot_consumptions(parsed.chart)
    reached = sum(len(consumptions.get(node, ())) for node in nodes)
    every = all_shared_nodes(parsed.kernel, parsed.chart)
    assert same_meaning_set(exact, oracle), (witness.name, exact, oracle)
    assert len(exact) == witness.meanings, (witness.name, len(exact))
    assert len(correlated) == witness.correlated, (witness.name, len(correlated))
    assert reached == witness.consumptions, (witness.name, reached)
    # A witness declaring no shared node must have NO shared node at all, not
    # merely none under the name it declared.
    assert bool(every) == bool(witness.shared), (witness.name, every)
    assert computed_once(parsed.chart, parsed.roots), witness.name
    print(
        "shared-shape",
        witness.name,
        f"shape={witness.shape}",
        f"flavour={type(witness.flavour).__name__}",
        f"shared_node={witness.shared or '(tree object only)'}",
        f"occurrence_edges={reached}",
        f"chart_nodes={len(parsed.chart.nodes)}",
        f"exact_meanings={len(exact)}",
        f"unrolled_oracle_meanings={len(oracle)}",
        f"lanes_agree={same_meaning_set(exact, oracle)}",
        f"key_correlated_meanings={len(correlated)}"
        + ("  <-- LOSES MEANINGS" if len(correlated) < len(oracle) else ""),
        f"every_shared_rule={list(every)}",
        f"candidate_order_visits_each_handle_once="
        f"{computed_once(parsed.chart, parsed.roots)}",
        f"candidate_products={counters.executed_products}",
        f"candidate_dirty_nodes={counters.dirty_nodes}",
        f"oracle_occurrences={counts.occurrences}",
        f"oracle_applications={counts.applications}",
        f"oracle_chain_resolves={counts.resolves}",
        sep="\t",
    )
    return parsed


# ── the pins the round owes separately ────────────────────────────────────


def prove_correlation_is_disproved() -> None:
    """Name the witnesses where a key-global assignment answers a smaller set.

    This is the disproof the round exists for: the mixed occurrence choices are
    observable only JOINTLY, and a relation that fixes one family per key
    cannot express them.
    """
    losing: list[tuple[str, int, int]] = []
    for witness in WITNESSES:
        if witness.correlated < witness.meanings:
            losing.append((witness.name, witness.meanings, witness.correlated))
    assert len(losing) >= 3, losing
    print(
        "correlation-disproof",
        f"witnesses_where_the_key_global_control_loses_meanings={len(losing)}",
        f"rows={losing}",
        "a node reached by two occurrences whose own family choice sits inside"
        " its OWN chain is expanded once by a key-global assignment and twice"
        " by the grammar; the mixed derivations exist and mean something the"
        " correlated relation never produces",
        sep="\t",
    )


def prove_shared_value_is_computed_once() -> None:
    """The shared node's set is computed once — measured against an UNSHARED twin.

    The twin spells the same language with the two occurrences given their own
    rules, so nothing can be shared. Both lanes must answer the same meaning
    count while the twin pays for the second copy of the node's own set.
    """
    witness = WITNESSES[0]
    shared = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    twin_actions = (
        ("root", IrArgs()),
        ("a1", IrArg(0)),
        ("b1", IrArg(0)),
        ("a2", IrArg(0)),
        ("b2", IrArg(0)),
        ("p1", MARK_P),
        ("q1", MARK_Q),
        ("p2", MARK_P),
        ("q2", MARK_Q),
    )
    twin = recognize(DUP_TWIN, GBNF_FLAVOUR, "x", twin_actions)
    shared_counters, twin_counters = candidate.Counters(), candidate.Counters()
    shared_set = candidate_meanings(
        shared.kernel, shared.roots, shared.options, shared.reducer, shared_counters
    )
    twin_set = candidate_meanings(
        twin.kernel, twin.roots, twin.options, twin.reducer, twin_counters
    )
    node = shared_nodes(shared.kernel, shared.chart, witness.shared)[0]
    families = len(shared.chart.resolveds[node])
    gap = twin_counters.executed_products - shared_counters.executed_products
    assert same_meaning_set(shared_set, twin_set), (shared_set, twin_set)
    # The controlled statement: the twin's extra applications are EXACTLY the
    # second copy of the shared node's own set, not merely "more, because the
    # twin is bigger". A raw inequality would also pass on a twin that grew
    # for any other reason.
    assert gap == families, (gap, families)
    print(
        "shared-once-differential",
        f"shared_meanings={len(shared_set)}  twin_meanings={len(twin_set)}",
        f"shared_chart_nodes={shared_counters.chart_nodes}",
        f"twin_chart_nodes={twin_counters.chart_nodes}",
        f"shared_products={shared_counters.executed_products}",
        f"twin_products={twin_counters.executed_products}",
        f"extra_applications={gap}",
        f"shared_node_own_families={families}",
        f"extra_equals_one_more_copy_of_that_set={gap == families}",
        f"equal_meanings={same_meaning_set(shared_set, twin_set)}",
        "the unshared twin derives the same language and the same meanings and"
        " pays EXACTLY one more copy of the shared node's own set — the gap is"
        " that node's family count, not a size difference between the two"
        " charts, which is what makes this a control rather than an inequality",
        sep="\t",
    )


def prove_occurrence_owned_effects() -> None:
    """Append, insert, verdict and duplicate run per SLOT CONSUMPTION.

    Each row keeps the shared-node grammar and changes only the consumer's
    authored operation. The correlated control is what a per-shared-NODE
    execution would produce — it collapses the two occurrences into one value
    and answers a smaller image every time.
    """
    for label, root_body, exact_count, correlated_count, partial in EFFECTS:
        actions = (("root", root_body),) + PASS_THROUGH + LEAVES
        parsed = recognize(DUP_SLOT, GBNF_FLAVOUR, "x", actions)
        exact = bottom_meanings(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, partial
        )
        counts = UnrolledCounts()
        oracle = unrolled_meanings(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, counts, partial
        )
        live = key_correlated_meanings(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, partial
        )
        node = shared_nodes(parsed.kernel, parsed.chart, "a")[0]
        expansions = occurrence_paths_at(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, node
        )
        assert same_meaning_set(exact, oracle), (label, exact, oracle)
        assert len(exact) == exact_count, (label, len(exact))
        assert len(live) == correlated_count, (label, len(live))
        # The EXECUTION claim, not a cardinality: the consumer's body runs once
        # per slot-tuple it consumes (2 slots x 2 options = 4), while the
        # shared node it consumes is expanded at exactly its 2 occurrences.
        assert counts.by_rule["root"] == 4, (label, counts.by_rule)
        assert expansions == 2, (label, expansions)
        print(
            "occurrence-effect",
            label,
            f"operation={type(root_body).__name__}",
            f"declared_partial={sorted(partial)}",
            f"consumer_body_executions={counts.by_rule['root']}",
            f"shared_node_occurrence_expansions={expansions}",
            f"exact_meanings={len(exact)}",
            f"unrolled_oracle={len(oracle)}",
            f"per_shared_node_control={len(live)}",
            f"agree={same_meaning_set(exact, oracle)}",
            f"values={[repr(value) for value in exact]}",
            sep="\t",
        )
    print(
        "occurrence-effect",
        "conclusion",
        "the consumer's body runs FOUR times — once per (slot 0 option, slot 1"
        " option) tuple — while the shared node is expanded at its two"
        " occurrences and its own set is computed once; that is the execution"
        " property, measured, rather than inferred from a set size",
        sep="\t",
    )


ONE_REFUSES = 'root ::= a a "x"\na ::= b\nb ::= p | q\np ::= "y"*\nq ::= "z"*\n'
"""Witness (a): one requested-root branch refuses, another survives."""

ALL_REFUSE = IrBuild(
    IrMap, IrTuple(IrTuple(IrStr("k"), IrArg(0)), IrTuple(IrStr("k"), IrArg(1)))
)
"""A consumer that refuses on EVERY combination — a constant duplicate key."""


def prove_one_refusing_branch_beside_a_surviving_one() -> None:
    """Witness (a): a refusing family must not remove the surviving meaning.

    `DUPLICATE` inserts the two occurrence values as MAP KEYS, so the two mixed
    derivations succeed and the two matched ones refuse. Bottom semantics keeps
    exactly the survivors; anything that let a refusal stand as a value, or
    that raised on the refusing family, would answer differently.
    """
    actions = (("root", DUPLICATE),) + PASS_THROUGH + LEAVES
    parsed = recognize(DUP_SLOT, GBNF_FLAVOUR, "x", actions)
    partial = frozenset({"root"})
    bottom = bottom_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, partial
    )
    oracle = unrolled_meanings(
        parsed.kernel,
        parsed.roots,
        parsed.options,
        parsed.reducer,
        UnrolledCounts(),
        partial,
    )
    assert same_meaning_set(bottom, oracle) and len(bottom) == 2
    print(
        "partial-one-refusing-branch",
        f"surviving_meanings={len(bottom)}",
        f"unrolled_oracle={len(oracle)}",
        f"agree={same_meaning_set(bottom, oracle)}",
        f"values={[repr(value) for value in bottom]}",
        "two of the four combinations refuse (equal keys) and two survive; a"
        " refusing family removes itself and nothing else, so the document"
        " parses and means two things",
        sep="\t",
    )


def prove_every_root_branch_refusing() -> None:
    """Witness (b): when NO requested-root meaning survives, parsing refuses.

    The consumer inserts one constant key twice, so every combination refuses
    and no derivation has a value. This is the one place a refusal is correct,
    and it is the ROOT's decision — no internal node raised on the way here.
    """
    actions = (("root", ALL_REFUSE),) + PASS_THROUGH + LEAVES
    parsed = recognize(DUP_SLOT, GBNF_FLAVOUR, "x", actions)
    partial = frozenset({"root"})
    bottom_said = ""
    try:
        bottom_meanings(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, partial
        )
    except UnsupportedConstructError as error:
        bottom_said = str(error)
    oracle_said = ""
    try:
        unrolled_meanings(
            parsed.kernel,
            parsed.roots,
            parsed.options,
            parsed.reducer,
            UnrolledCounts(),
            partial,
        )
    except UnsupportedConstructError as error:
        oracle_said = str(error)
    assert bottom_said and oracle_said
    print(
        "partial-every-branch-refusing",
        f"bottom_lane_refuses={bool(bottom_said)}",
        f"unrolled_oracle_refuses={bool(oracle_said)}",
        f"same_refusal={bottom_said == oracle_said}",
        f"message={bottom_said}",
        "both lanes refuse, and only at the requested root: no internal node"
        " raised, because an empty internal image is a fact about that node"
        " rather than about the document",
        sep="\t",
    )


def prove_empty_image_eliminates_only_its_consumers() -> None:
    """An empty INTERNAL image must not take the parent's other families with it.

    The sharpest form of the rule. `inner` is consumed by one arm of `m` and
    refuses on every combination; the other arm of `m` does not consume it. If
    an empty image eliminated the whole parent the document would lose its
    meaning, and it does not.
    """
    source = (
        'root ::= m "z"\nm ::= viainner | direct\nviainner ::= inner\n'
        'inner ::= t t\ndirect ::= t t\nt ::= p | q\np ::= "y"\nq ::= "y"\n'
    )
    actions = (
        ("root", IrArg(0)),
        ("m", IrArg(0)),
        ("viainner", IrArg(0)),
        ("inner", ALL_REFUSE),
        ("direct", IrBuild(IrTuple, IrTuple(IrArg(0), IrArg(1)))),
        ("t", IrArg(0)),
    ) + LEAVES
    parsed = recognize(source, GBNF_FLAVOUR, "yyz", actions)
    partial = frozenset({"inner"})
    bottom = bottom_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, partial
    )
    oracle = unrolled_meanings(
        parsed.kernel,
        parsed.roots,
        parsed.options,
        parsed.reducer,
        UnrolledCounts(),
        partial,
    )
    assert same_meaning_set(bottom, oracle) and bottom
    print(
        "empty-image-scope",
        f"surviving_meanings={len(bottom)}",
        f"unrolled_oracle={len(oracle)}",
        f"agree={same_meaning_set(bottom, oracle)}",
        "the refusing rule's image is empty, which eliminates the parent"
        " families that CONSUME it and leaves the parent's other arm intact;"
        " the document still means something",
        sep="\t",
    )


def prove_partial_family_defect() -> None:
    """The candidate RAISES where bottom semantics eliminates a family.

    `island_continuation._slot_options` raises on an empty option lane, so the
    candidate cannot express "this family has no meaning" — it turns a local
    fact into a whole-parse refusal. `cyclic_meaning.node_set:657-661` already
    does it correctly with a `continue`, so this is a defect against an existing
    production precedent rather than an open question.
    """
    actions = (("root", DUPLICATE),) + PASS_THROUGH + LEAVES
    parsed = recognize(DUP_SLOT, GBNF_FLAVOUR, "x", actions)
    raised = ""
    try:
        candidate_meanings(
            parsed.kernel,
            parsed.roots,
            parsed.options,
            parsed.reducer,
            candidate.Counters(),
        )
    except UnsupportedConstructError as error:
        raised = str(error)
    bottom = bottom_meanings(
        parsed.kernel,
        parsed.roots,
        parsed.options,
        parsed.reducer,
        frozenset({"root"}),
    )
    assert raised and len(bottom) == 2
    print(
        "partial-family-defect",
        f"candidate_raises={raised}",
        f"bottom_lane_meanings={len(bottom)}",
        "the candidate propagates the operation's refusal and loses a document"
        " that means two things; the correction is the one cyclic_meaning"
        " already implements — skip the family, refuse only at the root",
        sep="\t",
    )
    prove_the_required_production_signal()


def prove_the_required_production_signal() -> None:
    """WHAT production needs before bottom semantics can land: a distinct type.

    The prototype absorbs a refusal only for rules a witness DECLARES partial,
    which production cannot do. Keying on the exception type instead is not
    available: `UnsupportedConstructError` is also what an open dispatch raises
    for an undeclared construct, so the two are indistinguishable, and
    absorbing the type would turn an engine failure into a silently dropped
    family. The row executes both raises to show they cannot be told apart.
    """
    value_refusal = ""
    undeclared = ""
    try:
        IrBuild(IrMap).eval(
            candidate.reducer_of(()),
            FOCUS,
            (IrTuple(MARK_P, MARK_P), IrTuple(MARK_P, MARK_Q)),
        )
    except UnsupportedConstructError as error:
        value_refusal = type(error).__name__
    try:
        algebra.slot_class("no-such-operation", 0)
    except UnsupportedConstructError as error:
        undeclared = type(error).__name__
    assert value_refusal == undeclared == "UnsupportedConstructError"
    print(
        "required-production-signal",
        f"value_refusal_type={value_refusal}",
        f"undeclared_construct_type={undeclared}",
        f"distinguishable_by_type={value_refusal != undeclared}",
        "REQUIRED: a distinct value-refusal exception raised by the operation"
        " itself and by nothing else — a partial operation reporting it has no"
        " value for these arguments. Until that exists, bottom semantics cannot"
        " be keyed on an exception type; the prototype substitutes an explicit"
        " per-rule declaration, which production must not",
        sep="\t",
    )


def prove_unambiguous_sharing_allocates_nothing() -> None:
    """Ordinary sharing with one family pays no ambiguity-only state at all."""
    witness = next(w for w in WITNESSES if w.name == "unambiguous-shared")
    parsed = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    counters = candidate.Counters()
    exact = candidate_meanings(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, counters
    )
    consumptions = slot_consumptions(parsed.chart)
    reached = max(len(edges) for edges in consumptions.values())
    assert len(exact) == 1 and counters.executed_products == 0
    assert counters.dirty_nodes == 0 and counters.multiplicity_nodes == 0
    print(
        "unambiguous-sharing",
        f"most_consumed_node_occurrences={reached}",
        f"chart_nodes={counters.chart_nodes}",
        f"dirty_nodes={counters.dirty_nodes}",
        f"set_applications={counters.executed_products}",
        f"multiplicity_nodes={counters.multiplicity_nodes}",
        f"baseline_products={counters.baseline_products}",
        "a shared node with one family is outside the dirty cone, so its set"
        " is its baseline and the ambiguity lane allocates nothing; the"
        " baseline fold beside it is the parse's own product",
        sep="\t",
    )


def prove_separate_accepting_roots() -> None:
    """Two accepting items over one shared node stay two complete meanings."""
    witness = next(w for w in WITNESSES if w.name == "sibling-accepting-roots")
    parsed = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    per_root: list[int] = []
    for root in parsed.roots:
        found = candidate_meanings(
            parsed.kernel,
            (root,),
            parsed.options,
            parsed.reducer,
            candidate.Counters(),
        )
        per_root.append(len(found))
    together = candidate_meanings(
        parsed.kernel,
        parsed.roots,
        parsed.options,
        parsed.reducer,
        candidate.Counters(),
    )
    assert len(parsed.roots) == 2 and per_root == [4, 4] and len(together) == 8
    print(
        "separate-accepting-roots",
        f"accepting_items={len(parsed.roots)}",
        f"meanings_per_root={per_root}",
        f"meanings_together={len(together)}",
        "each accepting item is its own complete meaning; the shared node"
        " below them is still expanded once per occurrence under each",
        sep="\t",
    )


def prove_delegated_option_under_a_shared_completion() -> None:
    """A delegated island's option set, consumed beneath a SHARED completion.

    The island interior is Earley-delegated through the real
    `Kernel(delegates=...)` seam, so the shared completion's children include a
    real `PayloadLeaf` carrying two published options rather than a subtree.
    """
    text = "[xz]"
    actions = (
        ("root", IrArg(0)),
        ("m", IrArg(0)),
        ("l", IrArgs()),
        ("r", IrArgs()),
        ("s", IrArg(0)),
        ("t", IrArg(0)),
        ("alpha", IrStr("one")),
        ("beta", IrStr("two")),
    )
    reducer = candidate.reducer_of(actions)
    canonical = canonical_grammar(ISLAND_SHARED, GBNF_FLAVOUR)
    normalized = normalize(canonical)
    artefact = candidate.compile_continuations(canonical, normalized, reducer, 0)
    counters = candidate.Counters()
    run = candidate.outer_run(
        compile_tables(normalized, tier_for(len(text))),
        tables_for(ISLAND_INTERIOR, GBNF_FLAVOUR, len(text)),
        text,
        "t",
        reducer,
        counters,
        artefact,
    )
    roots = algebra.accepting_roots(run.kernel, run.root)
    chart = algebra.build_chart(run.kernel, roots)
    options = _leaf_options(run.kernel)
    exact = candidate_meanings(run.kernel, roots, options, reducer, counters)
    oracle = unrolled_meanings(run.kernel, roots, options, reducer, UnrolledCounts())
    correlated = key_correlated_meanings(run.kernel, roots, options, reducer)
    shared = shared_nodes(run.kernel, chart, "s")
    assert shared and same_meaning_set(exact, oracle)
    print(
        "delegated-under-shared",
        f"shared_completions={len(shared)}",
        f"occurrence_edges={len(slot_consumptions(chart)[shared[0]])}",
        f"delegated_leaves={len(options)}",
        f"leaf_options={[len(lane) for lane in options.values()]}",
        f"exact_meanings={len(exact)}",
        f"unrolled_oracle={len(oracle)}",
        f"key_correlated_meanings={len(correlated)}",
        f"agree={same_meaning_set(exact, oracle)}",
        "an island option set is consumed beneath a node two derivations share;"
        " the option lane and the packed-family lane compose the same way. The"
        " correlated column agrees here and is reported for that reason: the"
        " two consumptions live in DIFFERENT derivations (m ::= l | r), so this"
        " row shows the delegated option composing, and does NOT discriminate"
        " the two relations — only the intra-derivation rows do, and per the"
        " zero-width argument a delegated island cannot take that shape",
        sep="\t",
    )


def _leaf_options(kernel: Kernel) -> dict[int, tuple[IrSelf, ...]]:
    """Every delegated occurrence's published option set, by leaf identity."""
    out: dict[int, tuple[IrSelf, ...]] = {}
    for leaf in kernel.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, candidate.IslandSeed):
            raise UnsupportedConstructError("shared occurrence: leaf carries no seed")
        out[id(leaf)] = (payload.baseline,) + payload.alternates
    return out


def prove_shared_transparent_synthetic() -> None:
    """The shape the gate requires: a GENUINELY shared transparent synthetic node.

    An earlier pass of this round claimed no synthetic node is ever shared, and
    argued it structurally: "normalization gives each alternative its own
    hoisted arm". That was WRONG. Normalization DEDUPS identical generated
    rules, so one `__rep_1` can be referenced from two slots and carry two
    occurrence edges on a single chart node. Both forms are witnessed here.

    **How a transparent, result-less synthetic composes.** It is result-less
    only in `ModelFold`'s sense: `_fold_node` returns early for a rule with no
    config entry (`src/lexic/parsing/fold.py:498-500`), so it never enters
    `results` and the walk re-folds it — which is
    `shared_forest_refold.py`'s finding. In the target-shaped meaning relation
    it is NOT special: it is an ordinary chart node, it takes the reducer's
    default action, its meaning set is computed ONCE per handle like any
    other, and each consuming slot ranges over that set independently.
    Transparency is a fold-configuration fact, not a meaning fact — so nothing
    in the relation needs a result-less case, and the two lanes agree.
    """
    for label, source, text, actions, shape in (
        (
            "inter-derivation",
            SYNTHETIC_INTER,
            "[yz]",
            (
                ("root", IrArg(0)),
                ("m", IrArg(0)),
                ("l", IrArg(0)),
                ("r", IrArg(0)),
                ("b", IrArg(0)),
                ("c", IrArg(0)),
            )
            + LEAVES,
            "two derivations share it; the ambiguity is BENEATH it",
        ),
        (
            "intra-derivation",
            SYNTHETIC_INTRA,
            "x",
            (
                ("root", IrArgs()),
                ("s", IrArg(0)),
                ("t", IrArg(0)),
            )
            + LEAVES,
            "two slots of ONE family share it; the ambiguity is BESIDE it",
        ),
    ):
        parsed = recognize(source, GBNF_FLAVOUR, text, actions)
        consumptions = slot_consumptions(parsed.chart)
        synthetic = [
            node
            for node in parsed.chart.nodes
            if harness._name(parsed.kernel, node).startswith("__")
            and len(consumptions.get(node, ())) > 1
        ]
        exact = bottom_meanings(
            parsed.kernel, parsed.roots, parsed.options, parsed.reducer, frozenset()
        )
        oracle = unrolled_meanings(
            parsed.kernel,
            parsed.roots,
            parsed.options,
            parsed.reducer,
            UnrolledCounts(),
        )
        assert synthetic, (label, all_shared_nodes(parsed.kernel, parsed.chart))
        assert same_meaning_set(exact, oracle), (label, exact, oracle)
        # Unconditional: a witness that carried no ambiguity would prove nothing
        # about composition, so neither form is allowed to pass vacuously.
        assert len(exact) > 1, (label, exact)
        print(
            "shared-transparent-synthetic",
            label,
            f"shared_synthetic_rule={harness._name(parsed.kernel, synthetic[0])}",
            f"occurrence_edges={len(consumptions[synthetic[0]])}",
            f"has_a_reducer_action={_has_action(parsed.reducer, synthetic[0], parsed.kernel)}",
            f"exact_meanings={len(exact)}",
            f"unrolled_oracle={len(oracle)}",
            f"agree={same_meaning_set(exact, oracle)}",
            shape,
            sep="\t",
        )
    print(
        "shared-transparent-synthetic",
        "composition",
        "a transparent synthetic node is result-less only to ModelFold, whose"
        " _fold_node returns early for a rule with no config entry so the node"
        " never enters `results` and the walk re-folds it. The meaning relation"
        " has no such case: the node is an ordinary chart node taking the"
        " reducer's DEFAULT action, its set is computed once per handle, and"
        " each consuming slot ranges over it independently — so transparency"
        " needs no special rule and the lanes agree",
        sep="\t",
    )


def _has_action(reducer: Reducer, handle: int, kernel: Kernel) -> bool:
    """Whether the reducer declares an explicit action for this node's rule."""
    return reducer.actions.get(IrRuleRef(harness._name(kernel, handle))) is not None


def prove_intra_derivation_sharing_is_zero_width() -> None:
    """WHY a node two slots of one derivation share is always zero-width.

    A chart node is keyed by its SPAN, and two slots of one arm occupy disjoint
    spans unless both are empty. So the duplicate-slot and pending-frame shapes
    are necessarily zero-width, and a delegated island — which must consume the
    text it recognizes — can only be shared ACROSS derivations, which is what
    :func:`prove_delegated_option_under_a_shared_completion` witnesses. The row
    executes the claim rather than asserting it: every intra-family repeated
    child in every witness is checked to be zero-width.
    """
    checked = 0
    spans: set[int] = set()
    for witness in WITNESSES:
        parsed = recognize(
            witness.grammar, witness.flavour, witness.text, witness.actions
        )
        for handle in _repeated_children(parsed.chart):
            checked += 1
            spans.add(_span_width(parsed.kernel, handle))
    assert checked and spans == {0}, (checked, spans)
    print(
        "intra-derivation-sharing",
        f"repeated_children_checked={checked}",
        f"distinct_span_widths={sorted(spans)}",
        "a node consumed twice inside ONE family is always zero-width, because"
        " a chart node is keyed by its span; sharing at a non-empty span is"
        " always ACROSS derivations, where each derivation consumes it once",
        sep="\t",
    )


def _repeated_children(chart: algebra.Chart) -> list[int]:
    """Child handles a single resolved family consumes more than once."""
    out: list[int] = []
    for resolveds in chart.resolveds.values():
        for resolved in resolveds:
            seen: dict[int, int] = {}
            for child in resolved.children:
                seen[child] = seen.get(child, 0) + 1
            out.extend(child for child, count in seen.items() if count > 1)
    return out


def _span_width(kernel: Kernel, handle: int) -> int:
    """How many characters one packed completion covers."""
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    return (handle & mask) - ((handle >> bits) & mask)


def prove_tree_identity_is_not_occurrence_identity() -> None:
    """The built `ParseTree` LOSES the occurrence the chart carries.

    Two independent causes, both executed. `FastTree` memoizes a built subtree
    by HANDLE, so a chart-shared node is one Python object in the tree; and
    `ParserTables.empty_tree` interns one derivation per unambiguously nullable
    rule, so even the sibling-memo shape — where the chart shares nothing,
    because the two spans differ — hands the fold one object at two positions.
    Production's `ModelFold.apply` keys its results on ``id(node)`` and
    `fold._tree_offsets` records one start per ``id``, so neither can tell the
    occurrences apart. The chart can DISTINGUISH them — the occurrence is the
    ``(consuming handle, family index, kid slot)`` triple — but it does not
    RECORD it: `cyclic_meaning.Edge` carries no family index and production's
    chart carries no parent-to-child edge, so the triple is derivable and
    unmaterialised.
    """
    witness = WITNESSES[0]
    parsed = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    tree = FastTree(parsed.kernel, {}).build(parsed.roots[0])
    assert isinstance(tree, ParseTree)
    memo_shared = sum(1 for count in _kid_object_counts(tree).values() if count > 1)
    edges = max(len(found) for found in slot_consumptions(parsed.chart).values())
    interned = tables_for(INTERNED_TWIN, GBNF_FLAVOUR, 2)
    twin = Kernel(interned, "uw", True).run()
    twin_tree = FastTree(twin, {}).build(accept_handle(twin))
    assert isinstance(twin_tree, ParseTree)
    twin_shared = sum(
        1 for count in _kid_object_counts(twin_tree).values() if count > 1
    )
    twin_chart = algebra.build_chart(twin, (accept_handle(twin),))
    print(
        "tree-versus-occurrence-identity",
        f"chart_shared_tree_objects_at_two_kid_slots={memo_shared}",
        f"chart_occurrence_edges_on_the_shared_node={edges}",
        "empty_tree_interns_one_derivation="
        f"{interned.empty_tree(_rule_id(interned, 'a')) is not None}",
        f"interned_twin_chart_shared_nodes={len(shared_nodes(twin, twin_chart, 'a'))}",
        f"interned_twin_tree_objects_at_two_kid_slots={twin_shared}",
        "the derivation tree keys a node by OBJECT and the production fold and"
        " offset pass both key on id(node), so an occurrence-owned effect run"
        " off the tree would execute once for two occurrences — and the twin"
        " shows the tree sharing a node the CHART does not share at all;"
        " (consuming handle, family, slot) is the identity the meaning relation"
        " must use; it is DERIVABLE from the forest and recorded by no structure"
        " — Edge has no family index and production's chart has no"
        " parent-to-child edge — so materialising it is production work",
        sep="\t",
    )
    assert memo_shared and edges == 2 and twin_shared


def _kid_object_counts(root: ParseTree) -> dict[int, int]:
    """How many kid slots reference each subtree OBJECT, by identity."""
    counts: dict[int, int] = {}
    seen: set[int] = set()
    stack: list[ParseTree] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                counts[id(kid)] = counts.get(id(kid), 0) + 1
                stack.append(kid)
    return counts


def _rule_id(tables: ParserTables, name: str) -> int:
    """The compiled rule id spelled ``name``."""
    for index, ref in enumerate(tables.decode.rule_refs):
        if str(ref) == name:
            return index
    raise UnsupportedConstructError(f"shared occurrence: no rule {name!r}")


def occurrence_paths_at(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    handle: int,
) -> int:
    """How many distinct occurrence PATHS the oracle expanded at one handle.

    The discriminating measure a bare "occurrences exceed nodes" count is not:
    a node with two families raises the path total with or without sharing, so
    only the paths ending at THIS handle say the shared node was expanded
    twice.
    """
    del options, reducer
    seen: set[tuple[int, Occurrence]] = set()
    stack: list[tuple[int, Occurrence]] = [
        (root, ((root, 0, index),)) for index, root in enumerate(roots)
    ]
    while stack:
        node, at = stack.pop()
        if (node, at) in seen:
            continue
        seen.add((node, at))
        for family, resolved in enumerate(
            occurrence_families(kernel, node, UnrolledCounts())
        ):
            stack.extend(child_occurrences(resolved, node, family, at))
    return sum(1 for node, _at in seen if node == handle)


def prove_oracle_is_independent() -> None:
    """State, executably, exactly what the oracle does and does NOT share.

    The honest boundary, because a reviewer is right to press on the word
    "independent". The oracle shares the chain-RESOLUTION primitives with the
    candidate — `cyclic_meaning.local_choice_keys` / `assignments` /
    `selected_resolved`, which is how any reader gets a family out of the
    binarised links — and it shares the real reducer, which it must, because
    the reducer IS the semantics both compute. What it does NOT share is the
    composition rule, the memo policy, or the dedup key: it keys results on the
    occurrence PATH rather than on the handle, never memoizes across
    occurrences, calls no candidate set function, and compares through the
    production `same_value` instead of the candidate's ``repr``.

    The lane that WOULD be independent in its family decomposition is
    production's own `DERIVATIONS` enumerator, and
    :func:`prove_production_enumeration_truncates` shows it is unsound on this
    round's shape and therefore unusable as an oracle. That is stated rather
    than hidden: no lane in the tree independently confirms the family
    enumeration, and this round does not claim one does.
    """
    witness = WITNESSES[0]
    parsed = recognize(witness.grammar, witness.flavour, witness.text, witness.actions)
    node = shared_nodes(parsed.kernel, parsed.chart, witness.shared)[0]
    at_shared = occurrence_paths_at(
        parsed.kernel, parsed.roots, parsed.options, parsed.reducer, node
    )
    edges = len(slot_consumptions(parsed.chart)[node])
    assert at_shared == edges == 2, (at_shared, edges)
    print(
        "oracle-independence",
        f"shared_handle_rule={harness._name(parsed.kernel, node)}",
        f"occurrence_paths_expanded_at_that_handle={at_shared}",
        f"chart_occurrence_edges_at_that_handle={edges}",
        "shares=[chain resolution primitives, the real reducer]",
        "does_not_share=[composition rule, memo policy, dedup key, traversal]",
        "the count is taken AT the shared handle, so it cannot be satisfied by"
        " a node with two families elsewhere; production's own DERIVATIONS"
        " enumerator is the only lane independent in its family decomposition"
        " and it is unsound here, which this round states rather than hides",
        sep="\t",
    )


def prove_production_enumeration_truncates() -> None:
    """The SHIPPED forest enumeration loses derivations on a shared occurrence.

    `forest.ForestCtx` guards re-entry on a handle whose prefixes are
    "mid-production", and its docstring says an EXHAUSTED handle may be
    re-entered legitimately because that is sharing. Under the trampolined
    lazy walk the distinction does not hold: a zero-width handle consumed at
    two slots of ONE derivation is still suspended — not exhausted — when the
    second consumption reaches it, so `PrefixSource` emits its single empty
    prefix and builds a `ParseTree` with no kids under a rule that always has
    one.

    The result is both fewer derivations than the grammar has and malformed
    ones among them. It is a shipped defect on exactly this round's shape, and
    it is why the one enumerator with an independent family decomposition
    cannot serve as this round's oracle.
    """
    for name in ("duplicate-slot", "pending-frame", "arm-shared"):
        witness = next(w for w in WITNESSES if w.name == name)
        parsed = recognize(
            witness.grammar, witness.flavour, witness.text, witness.actions
        )
        found = production_enumeration(parsed)
        oracle = unrolled_meanings(
            parsed.kernel,
            parsed.roots,
            parsed.options,
            parsed.reducer,
            UnrolledCounts(),
        )
        print(
            "production-enumeration",
            name,
            f"shipped_derivations={found.derivations}",
            f"shipped_wellformed_meanings={found.meanings}",
            f"shipped_malformed_derivations={found.malformed}",
            f"grammar_meanings={len(oracle)}",
            f"loses_meanings={found.meanings < len(oracle)}"
            + ("  <-- SHIPPED DEFECT" if found.malformed else ""),
            sep="\t",
        )
    duplicate = recognize(DUP_SLOT, GBNF_FLAVOUR, "x", WITNESSES[0].actions)
    assert production_enumeration(duplicate).malformed == 2
    print(
        "production-enumeration",
        "conclusion",
        "ForestCtx.open cannot tell a SUSPENDED shared handle from a cyclic"
        " one, so a zero-width node consumed at two slots of one derivation is"
        " truncated to the empty prefix; the enumeration then reports two"
        " derivations where the grammar derives four, and both carry a node"
        " with no kids under a rule that always has one",
        sep="\t",
    )


def main() -> None:
    """Run every shared shape, then the pins the round owes separately."""
    for witness in WITNESSES:
        _exercise(witness)
    prove_correlation_is_disproved()
    prove_oracle_is_independent()
    prove_production_enumeration_truncates()
    prove_shared_value_is_computed_once()
    prove_occurrence_owned_effects()
    prove_one_refusing_branch_beside_a_surviving_one()
    prove_every_root_branch_refusing()
    prove_empty_image_eliminates_only_its_consumers()
    prove_partial_family_defect()
    prove_unambiguous_sharing_allocates_nothing()
    prove_separate_accepting_roots()
    prove_delegated_option_under_a_shared_completion()
    prove_shared_transparent_synthetic()
    prove_intra_derivation_sharing_is_zero_width()
    prove_tree_identity_is_not_occurrence_identity()
    print(
        "invariant",
        "a packed forest node is a VALUE keyed by its span; a grammatical"
        " occurrence is the (consuming handle, family index, kid slot) triple"
        " that reaches"
        " it; that triple is DERIVABLE from the forest and recorded by no"
        " structure, so materialising it is production work. The shared"
        " value's meaning set is computed once and every consuming slot ranges"
        " over it independently, so occurrence-owned append, insert, verdict"
        " and duplicate effects execute per slot consumption; a relation that"
        " fixes one family per packed key correlates the occurrences and loses"
        " meanings the grammar derives. Ordinary unambiguous sharing stays"
        " outside the dirty cone and allocates nothing",
        sep="\t",
    )


if __name__ == "__main__":
    main()
