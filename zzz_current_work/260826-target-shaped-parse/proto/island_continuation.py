"""One cached island→requested-root continuation per contextual occurrence.

The mechanisms this composes already exist separately: `route_continuation.py`
lowers a producer completion to a contextual child, `island_alternate_seed.py`
publishes a cold alternate seed from a REAL delegated island, `operation_slot_laws.py`
classifies the REAL authored reducer operations into the ``const``/``ident``/
``finite``/``grow`` slot algebra, `ambiguity_interaction.py` disproves one-flip
separability, `root_meaning_incremental.py` replays an ancestor cone, and
`resolver_pair.py` builds the resolver's derivation pair by occurrence-addressed
splicing. Nothing here invents a second architecture; this module compiles the
one artefact that joins them and executes the six cases the composition needs.

**The compiled artefact.** For one bound product (grammar identity × reducer
identity × requested root) the table holds one immutable row per
``(consumer rule, channel slot)`` — the contextual occurrence a clone chain
names. A row carries only ints and declaration strings: the slot's law under
the real operation algebra, and the two grammar-level reachability lanes.
No parse value, no kernel, no tree, no callable.

**The certificate, stated exactly.** Write ``law(P, s)`` for the class the real
authored body of rule ``P`` declares for its channel slot ``s``, and let the
flow graph be every ``(parent, channel slot, child)`` reference edge.

- DROP (universal). The value at ``(P, s)`` is unobservable at the requested
  root when ``law(P, s) == const`` OR no path from the root down to ``P``
  exists whose every edge is non-``const``. Both are quantified over EVERY
  path in the grammar's flow graph, which over-approximates the chart's
  realizable paths, so a grammar-level "no path" implies "no realizable path".
  Every derivation therefore maps every value in that slot to one root
  meaning, whatever the other families do. This is not one-flip reasoning: it
  never inspects a baseline.
- INEQUALITY (existential, chart-verified). When ``law(P, s)`` is ``ident`` or
  ``grow`` and SOME path from the root to ``P`` has only ``ident``/``grow``
  edges, the composed map from that slot to the root is injective along that
  path — but a grammar path need not be realized in this parse, so the
  existential half is verified against the actual chart before it is used:
  the realized route to THIS occurrence is enumerated and its own laws are
  composed. Fixing that route's families and varying only the occurrence's
  value then constructs two distinct root meanings, so the exact root meaning
  set holds at least two elements. Unrelated dropping parents cannot
  invalidate a constructive witness.
- EXECUTE. Otherwise the cached row settles nothing and the exact relation
  runs: per-node meaning sets over the node's OWN families × its children's
  DEDUPLICATED option sets. Global family assignments are never enumerated.

Interacting occurrences compose through that per-node product, so two choices
that are individually invisible are still jointly visible; the one-flip lane is
executed beside it only to show that it is not.

Run directly.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from functools import partial
from itertools import product
from typing import NamedTuple

import cyclic_meaning as algebra
import island_alternate_seed as harness
import operation_slot_laws as laws
import resolver_pair as pairs

from lexic.compile import canonical_grammar, compile_text
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import (
    IrArg,
    IrArgs,
    IrAst,
    IrBuild,
    IrCompare,
    IrMap,
    IrOp,
    IrRuleRef,
    IrSelf,
    IrStr,
    IrTuple,
    Reducer,
)
from lexic.ir.flavour import IrFlavour
from lexic.ir.reduction import DROP
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    same_value,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Delegate, Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.earley.normalize import normalize

type Flat = int | str | tuple["Flat", ...]
"""What a compiled continuation row is allowed to be made of, exhaustively."""

DROP_VERDICT = "drop"
INJECTIVE_VERDICT = "injective"
EXECUTE_VERDICT = "execute"

FOCUS = IrStr("")
"""The focus every witness body receives.

No witness action reads the focus — :func:`prove_no_witness_reads_the_focus`
checks that structurally — so the drop-aware text view `YIELD` needs is not
part of this composition. That obligation stays exactly where Prototype 14 put
it.
"""


class Counters:
    """Every structural count one witness reports, attributed by LANE.

    Every derivation this module builds goes through :func:`build_tree` and
    every whole-document recognition through :func:`run_document`, so a count
    of zero is a fact about the code path rather than a counter nobody
    increments. The lanes are kept apart because they answer different
    questions: what the SETTLEMENT costs, what publishing the island's seed
    costs, what the rejected one-flip lane costs, what the ORACLE costs, and
    what an invoked resolver costs.
    """

    __slots__ = (
        "baseline_products",
        "seed_baseline_products",
        "chart_nodes",
        "descent_steps",
        "dirty_nodes",
        "seed_chart_nodes",
        "seed_dirty_nodes",
        "document_recognitions",
        "dropped_alternates",
        "executed_products",
        "injective_settlements",
        "island_runs",
        "lookups",
        "multiplicity_nodes",
        "seed_multiplicity_nodes",
        "one_flip_trees",
        "oracle_trees",
        "resolver_calls",
        "resolver_trees",
        "retained_island_kernels",
        "seed_products",
        "seed_trees",
        "settlement_trees",
        "skipped_enumerations",
    )

    def __init__(self) -> None:
        self.island_runs = 0
        self.document_recognitions = 0
        self.lookups = 0
        self.descent_steps = 0
        self.dropped_alternates = 0
        self.skipped_enumerations = 0
        self.injective_settlements = 0
        self.chart_nodes = 0
        self.dirty_nodes = 0
        self.seed_chart_nodes = 0
        self.seed_dirty_nodes = 0
        self.multiplicity_nodes = 0
        self.seed_multiplicity_nodes = 0
        self.baseline_products = 0
        self.seed_baseline_products = 0
        self.executed_products = 0
        self.seed_products = 0
        self.retained_island_kernels = 0
        self.settlement_trees = 0
        self.seed_trees = 0
        self.one_flip_trees = 0
        self.oracle_trees = 0
        self.resolver_trees = 0
        self.resolver_calls = 0

    def chart(self, lane: str, nodes: int, dirty: int) -> None:
        """Attribute one chart walk's node and dirty-cone counts to its lane."""
        if lane == SEED_LANE:
            self.seed_chart_nodes += nodes
            self.seed_dirty_nodes += dirty
            return
        self.chart_nodes += nodes
        self.dirty_nodes += dirty

    def baseline(self, lane: str) -> None:
        """Attribute one baseline node fold — the parse's own product — to a lane."""
        if lane == SEED_LANE:
            self.seed_baseline_products += 1
        else:
            self.baseline_products += 1

    def multiple(self, lane: str) -> None:
        """Attribute one node that holds more than one meaning to its lane."""
        if lane == SEED_LANE:
            self.seed_multiplicity_nodes += 1
        else:
            self.multiplicity_nodes += 1

    def product(self, lane: str) -> None:
        """Attribute one meaning-operation application to its lane."""
        if lane == SEED_LANE:
            self.seed_products += 1
        else:
            self.executed_products += 1

    def tree(self, lane: str) -> None:
        """Attribute one derivation build to its lane."""
        if lane == SEED_LANE:
            self.seed_trees += 1
        elif lane == ORACLE_LANE:
            self.oracle_trees += 1
        elif lane == FLIP_LANE:
            self.one_flip_trees += 1
        elif lane == RESOLVER_LANE:
            self.resolver_trees += 1
        else:
            self.settlement_trees += 1


SEED_LANE = "seed"
ORACLE_LANE = "oracle"
FLIP_LANE = "one-flip"
RESOLVER_LANE = "resolver"
SETTLEMENT_LANE = "settlement"


def build_tree(
    kernel: Kernel,
    handle: int,
    choices: dict[int, int],
    counters: Counters,
    lane: str,
) -> ParseTree:
    """THE derivation constructor — every `FastTree` in this module goes here.

    Routing every build through one function is what makes a zero count
    falsifiable: a lane that built a tree would report it, because there is no
    other way to build one.
    """
    counters.tree(lane)
    tree = FastTree(kernel, dict(choices)).build(handle)
    if not isinstance(tree, ParseTree):
        raise UnsupportedConstructError("island continuation: derivation did not build")
    return tree


def run_document(
    tables: ParserTables, text: str, delegates: dict[int, Delegate], counters: Counters
) -> Kernel:
    """THE whole-document recognition — the only `Kernel(...).run()` here."""
    counters.document_recognitions += 1
    kernel = Kernel(tables, text, True, delegates=delegates).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("island continuation: outer parse failed")
    return kernel


# ── the compiled continuation artefact ────────────────────────────────────


class ContinuationKey(NamedTuple):
    """The four things one continuation is owned by.

    :ivar clone: The consuming contextual clone. Today's engine names a
        contextual identity by its COMPLETED CODE, and
        ``codes.arm_rule[codes.code_arm[code]]`` resolves that code to the rule
        this field spells; with contextual clones two clones of one rule take
        two codes and therefore two rows, without changing the table's shape.
    :ivar slot: The consumed child's channel slot — the occurrence within the
        clone. WHICH occurrence at parse time is the delegated leaf object
        (`resolver_pair.payload_leaves`), one per delegated occurrence.
    :ivar root: The requested root.
    :ivar product: The bound product's identity.
    """

    clone: str
    slot: int
    root: str
    product: int


class Continuation(NamedTuple):
    """One immutable row: flat law and route data, never a value or a callback.

    :ivar key: The occurrence this row is compiled for.
    :ivar child: The rule standing in that slot.
    :ivar slot_kind: The class the real authored body declares for the slot.
    :ivar slot_bound: That class's declared image bound.
    :ivar observable: Whether ANY flow path carries this slot to the root.
    :ivar injective: Whether SOME flow path carries it injectively.
    :ivar verdict: :data:`DROP_VERDICT`, :data:`INJECTIVE_VERDICT`, or
        :data:`EXECUTE_VERDICT`.
    """

    key: ContinuationKey
    child: str
    slot_kind: str
    slot_bound: int
    observable: bool
    injective: bool
    verdict: str


class ContinuationArtefact(NamedTuple):
    """Every occurrence row of one bound product."""

    product: int
    root: str
    rows: tuple[Continuation, ...]


class _Entry(NamedTuple):
    """One registry entry — and the PIN that makes its identity key correct."""

    grammar: IrAst
    reducer: Reducer
    artefact: ContinuationArtefact


_REGISTRY: dict[tuple[int, int], _Entry] = {}
"""Bound product identity → its compiled table.

**The pin is deliberate and it is not free.** `parsing/caches.py` states the
rule this registry obeys: a bare ``dict`` keyed on ``id(...)`` must PIN its key
objects to stay correct against address reuse, and a pinned key is an immortal
key. So the entry holds the grammar and the reducer strongly and every hit
re-checks identity; an entry lives until :func:`release_continuations` drops
it. That is correct and mortal-by-request, which is what a prototype can show.

It is NOT the production protocol. `lexic.parsing.caches`' ``memo``/``track``
makes the entry die with a weak-referenceable OWNER — and IR values are not
weak-referenceable (`IrAst` and `Reducer` both refuse `weakref.ref`), so
production's owner is the `CompiledGrammar` artefact, exactly as
`cache_lifetime.py` already proved. Production adopts the continuation table
into that protocol; this module does not re-derive it and does not claim to.
"""

_NEXT_PRODUCT = [1]


def flow_edges(ast: IrAst, dropped: frozenset[str]) -> tuple[algebra.RuleEdge, ...]:
    """Every ``(parent, channel slot, child)`` reference edge of one grammar.

    Channel coordinates, not reference coordinates: a child the reducer DROPS
    never reaches the argument channel, so it has no slot and contributes
    nothing — which is the same answer as classifying it ``const``.
    `operation_slot_laws.prove_slot_alignment` is where the two coordinate
    systems are held against each other.
    """
    edges: list[algebra.RuleEdge] = []
    for rule in algebra._rules(ast):
        for arm in algebra._arms(rule):
            items = [part for part in arm if isinstance(part, laws.IrItem)]
            kept = laws.contributing(arm, dropped)
            for slot, position in enumerate(kept):
                child = items[position][0]
                edges.append(algebra.RuleEdge(str(rule.name), str(child), slot))
    return tuple(edges)


def _ref_names(ast: IrAst, dropped: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """Each rule's contributing reference names, per arm, flattened in order."""
    out: dict[str, tuple[str, ...]] = {}
    for rule in algebra._rules(ast):
        found: list[str] = []
        for arm in algebra._arms(rule):
            items = [part for part in arm if isinstance(part, laws.IrItem)]
            found.append("|")
            found.extend(str(items[at][0]) for at in laws.contributing(arm, dropped))
        out[str(rule.name)] = tuple(found)
    return out


def aligned_rules(
    canonical: IrAst, normalized: IrAst, dropped: frozenset[str]
) -> frozenset[str]:
    """The rules whose CHART slot index is the AUTHORED body's channel index.

    This is the coordinate join the whole certificate rests on, and it is not
    free. The chart's chain slot counts child completions of the NORMALIZED
    arm; the authored body's ``IrArg(k)`` indexes the binding view's
    ``fields_of``, which additionally splices a hoisted group's interior and a
    quantified repeat's elements into the parent channel
    (`compile/reduce/fold.py::contribute`), so the real width is
    input-dependent there. `PROTOTYPE_14.md` §4 carries reading the real
    channel as an open obligation and this module does not close it.

    What it does instead is REFUSE the rules where the two can disagree: a
    rule keeps a law only when its canonical and normalized contributing
    reference sequences are identical, arm for arm. Anything normalization
    rewrote — every hoisted group, every quantified ref — loses its law and
    falls to the exact executed relation, which is the conservative direction.
    """
    left, right = _ref_names(canonical, dropped), _ref_names(normalized, dropped)
    return frozenset(
        name for name, refs in right.items() if left.get(name, ("",)) == refs
    )


FOCUS_MAPPING = ("IrEach", "IrChildren", "IrRebuild", "IrAt")
"""Operations whose ``grow`` comes from RETAINING a mapped focus.

`operation_slot_laws._rule_each` classifies ``IrEach(IrArg(k))`` ``grow``
because the body carries the slot — but over an EMPTY focus the result is the
empty tuple for every slot value, so it is not injective, and
`differential_law`'s probe domain always supplies a non-empty focus and cannot
catch it. Prototype 14 used ``grow`` for a census; this module uses it for a
REFUSAL, so the premise has to be narrower: a body reaching one of these gets
no law at all.
"""


def _reads_positional(body: IrSelf) -> bool:
    """Whether a body indexes its channel — the only way splicing can bite."""
    pending: list[IrSelf] = [body]
    while pending:
        node = pending.pop()
        if isinstance(node, IrArg):
            return True
        if isinstance(node, laws.IrNode):
            pending.extend(node.children())
    return False


def slot_law(
    reducer: Reducer, parent: str, slot: int, aligned: frozenset[str]
) -> laws.SlotLaw:
    """The class the REAL authored body of ``parent`` declares for ``slot``.

    Refuses — :data:`laws.UNKNOWN_LAW`, which forces the exact executed
    relation — when the body indexes a channel whose coordinates the analysis
    cannot join (:func:`aligned_rules`), or when it reaches a focus-mapping
    operation whose ``grow`` is not injective over an empty focus
    (:data:`FOCUS_MAPPING`). A body that never indexes its channel is
    splice-invariant: a splat, a constant and a predicate classify the same
    whatever the width, so alignment is not required of them.
    """
    body = reducer.actions.get(IrRuleRef(parent))
    if body is None:
        body = reducer.default
    names = _node_type_names(body)
    if names & set(FOCUS_MAPPING):
        return laws.UNKNOWN_LAW
    if _reads_positional(body) and parent not in aligned:
        return laws.UNKNOWN_LAW
    width = max(laws._width(body), slot + 1)
    classifier = laws.Classifier(laws.OPERATION_LAWS, laws.CONSTRUCTOR_LAWS)
    try:
        return classifier.law(body, laws.Env(slot, width, laws.CONST_LAW))
    except laws.SlotRefusal:
        return laws.UNKNOWN_LAW


def compile_continuations(
    canonical: IrAst, normalized: IrAst, reducer: Reducer, product: int
) -> ContinuationArtefact:
    """Compile one immutable row per contextual occurrence of the grammar.

    Both lanes are `cyclic_meaning._rule_reach` — the same reachability the
    cyclic classification runs — driven by the real operation classes rather
    than a toy policy table. ``UNKNOWN`` (a slot whose law refused, or one the
    coordinate join cannot reach) blocks the injective lane and does NOT block
    the observable lane, which is the conservative direction on both.
    """
    start = "".join(str(part) for part in normalized[1])
    names = tuple(str(rule.name) for rule in algebra._rules(normalized))
    dropped = laws.dropped_rules(reducer)
    edges = flow_edges(normalized, dropped)
    aligned = aligned_rules(canonical, normalized, dropped)
    classified = {
        edge: slot_law(reducer, edge.parent, edge.slot, aligned) for edge in edges
    }
    kinds = {edge: law.kind for edge, law in classified.items()}
    visible = algebra._rule_reach(names, edges, kinds, start, frozenset({laws.CONST}))
    injective = algebra._rule_reach(
        names, edges, kinds, start, frozenset({laws.CONST, laws.FINITE, laws.UNKNOWN})
    )
    rows = tuple(
        _row(edge, classified[edge], visible, injective, start, product)
        for edge in edges
    )
    return ContinuationArtefact(product, start, rows)


def _row(
    edge: algebra.RuleEdge,
    law: laws.SlotLaw,
    visible: dict[str, bool],
    injective: dict[str, bool],
    start: str,
    product: int,
) -> Continuation:
    """One occurrence row and its verdict under the stated certificate."""
    observable = law.kind != laws.CONST and visible.get(edge.parent, False)
    carries = law.kind in (laws.IDENT, laws.GROW) and injective.get(edge.parent, False)
    verdict = EXECUTE_VERDICT
    if not observable:
        verdict = DROP_VERDICT
    elif carries:
        verdict = INJECTIVE_VERDICT
    return Continuation(
        ContinuationKey(edge.parent, edge.slot, start, product),
        edge.child,
        law.kind,
        law.bound,
        observable,
        carries,
        verdict,
    )


def bind_continuations(
    canonical: IrAst, normalized: IrAst, reducer: Reducer
) -> ContinuationArtefact:
    """The bound product's table, compiled once and shared by every parse."""
    key = (id(normalized), id(reducer))
    found = _REGISTRY.get(key)
    if found is not None:
        if found.grammar is not normalized or found.reducer is not reducer:
            raise UnsupportedConstructError(
                "island continuation: registry identity collision — the pin"
                " that prevents address reuse was not held"
            )
        return found.artefact
    product = _NEXT_PRODUCT[0]
    _NEXT_PRODUCT[0] = product + 1
    built = compile_continuations(canonical, normalized, reducer, product)
    _REGISTRY[key] = _Entry(normalized, reducer, built)
    return built


def release_continuations(normalized: IrAst, reducer: Reducer) -> bool:
    """Drop one bound product's table — residency only, never semantics."""
    return _REGISTRY.pop((id(normalized), id(reducer)), None) is not None


def row_for(artefact: ContinuationArtefact, clone: str, slot: int) -> Continuation:
    """The row owning one contextual occurrence."""
    for row in artefact.rows:
        if row.key.clone == clone and row.key.slot == slot:
            return row
    raise UnsupportedConstructError(
        f"island continuation: no compiled row for {clone!r} slot {slot}"
    )


# ── the real reducer, executed as the completion operation ────────────────


def meaning_of(reducer: Reducer, name: str, kids: Sequence[IrSelf]) -> IrSelf:
    """Run the rule's REAL authored action body over its argument channel."""
    return reducer.body(IrRuleRef(name)).eval(reducer, FOCUS, tuple(kids))


def tree_meaning(
    tree: ParseTree, reducer: Reducer, overrides: dict[int, IrSelf]
) -> IrSelf:
    """Fold one complete Earley derivation with the real reducer, iteratively.

    The oracle's traversal and the island enumerator's: it reads a real
    `ParseTree`, where the mechanism reads packed chart handles, so the two
    agree only if the composition is right.
    """
    order: list[ParseTree] = []
    stack: list[ParseTree] = [tree]
    while stack:
        node = stack.pop()
        order.append(node)
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                stack.append(kid)
    values: dict[int, IrSelf] = {}
    for node in reversed(order):
        kids: list[IrSelf] = []
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                kids.append(values[id(kid)])
            elif isinstance(kid, PayloadLeaf):
                kids.append(overrides[id(kid)])
        values[id(node)] = meaning_of(reducer, str(node.symbol), kids)
    return values[id(tree)]


def same_set(one: Sequence[IrSelf], other: Sequence[IrSelf]) -> bool:
    """Whether two meaning sets hold the same meanings, order aside."""
    return sorted(repr(value) for value in one) == sorted(
        repr(value) for value in other
    )


def dedup(meanings: Sequence[IrSelf]) -> tuple[IrSelf, ...]:
    """Semantic deduplication of IR values, first-seen order.

    Keyed on ``repr``, which for IR values is constructor-shaped, so a leaf and
    its bare payload cannot collapse into one entry the way ``==`` would.
    """
    seen: set[str] = set()
    out: list[IrSelf] = []
    for meaning in meanings:
        key = repr(meaning)
        if key not in seen:
            seen.add(key)
            out.append(meaning)
    return tuple(out)


# ── the delegated run, with exact island meaning sets ─────────────────────


class IslandSeed(NamedTuple):
    """One island occurrence's baseline meaning, its cold alternates, and — only
    while it HAS alternates — the island kernel a resolver would need.

    `island_alternate_seed.IslandSeed` is the same record over that module's
    ``str | tuple`` meaning type; this one carries real IR values.

    :ivar kernel: The island's own finished kernel, retained ONLY when this
        occurrence published an alternate. That retention is the deferred
        per-occurrence state `PROTOTYPE_14.md` §2 says a document-rooted pair
        needs — made concrete rather than described. An unambiguous island
        retains ``None``, so the cost falls exactly on the occurrences that
        might reach a resolver. Without it a resolver has to RE-RECOGNIZE the
        island, because `islands.island_parse` lets its kernel die.
    :ivar root: That kernel's accepting handle.
    """

    baseline: IrSelf
    alternates: tuple[IrSelf, ...]
    kernel: Kernel | None
    root: int


class OuterRun(NamedTuple):
    """One delegated whole-document run and the seeds its occurrences published."""

    kernel: Kernel
    root: int
    seeds: dict[int, IslandSeed]


def unobservable_rule(artefact: ContinuationArtefact, rule: str) -> bool:
    """Whether NO consuming occurrence of ``rule`` can reach the requested root.

    The rule-level half of the DROP certificate, and the half a delegate can
    read before it does any work: if every compiled row into ``rule`` is
    unobservable, no derivation of it can change the requested root, so its
    alternates need never be enumerated at all. A rule with no row into it is
    the requested root itself and is trivially observable.
    """
    rows = tuple(row for row in artefact.rows if row.child == rule)
    return bool(rows) and not any(row.observable for row in rows)


def island_meanings(
    tables: ParserTables,
    window: str,
    pos: int,
    reducer: Reducer,
    counters: Counters,
    delegates: dict[int, Delegate] | None,
    artefact: ContinuationArtefact,
    rule: str,
) -> tuple[int, IslandSeed] | None:
    """One real windowed island, published as baseline plus cold alternates.

    **The compiled table is consulted FIRST.** When every occurrence of this
    island rule is unobservable at the requested root, the island publishes its
    baseline and stops: no set is formed, no alternate is built. That is the
    shortcut the design claims — the alternates are never PAID FOR. Note the
    scope: this is the RULE-WIDE half of the DROP certificate, the only half a
    delegate can read, because an Earley delegate is not told which occurrence
    invoked it. The per-occurrence half is read later, in :func:`settle`.

    Otherwise the island's own exact set comes from the SAME per-node lane the
    document uses (:func:`exact_meanings`) — not from a global assignment
    enumeration. One derivation is built, the engine's own, which is what
    `islands.island_parse` builds today and what fixes the pair's first
    element; the set is read off the chart.
    """
    counters.island_runs += 1
    kern, best = harness.island_run(tables, window[pos : pos + 256], delegates)
    if best is None:
        return None
    item, end = best
    root = (item << kern.tables.packing.bits) | end
    leaf_options: dict[int, tuple[IrSelf, ...]] = {}
    for leaf in kern.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, IslandSeed):
            raise UnsupportedConstructError("island continuation: leaf carries no seed")
        leaf_options[id(leaf)] = _seed_options(payload)
    baseline = _derivation_meaning(
        kern, root, {}, reducer, leaf_options, counters, SEED_LANE
    )
    if unobservable_rule(artefact, rule):
        counters.skipped_enumerations += 1
        return pos + end, IslandSeed(baseline, (), None, root)
    roots = (root,) + harness._sibling_accepts(kern, root)
    found = exact_meanings(kern, roots, leaf_options, reducer, counters, SEED_LANE)
    if not any(same_value(baseline, value) for value in found):
        raise UnsupportedConstructError(
            "island continuation: the engine's own island derivation is not in"
            " the island's exact meaning set"
        )
    alternates = tuple(value for value in found if not same_value(baseline, value))
    counters.retained_island_kernels += 1 if alternates else 0
    return pos + end, IslandSeed(
        baseline, alternates, kern if alternates else None, root
    )


def _seed_options(seed: IslandSeed) -> tuple[IrSelf, ...]:
    """One occurrence's option set — baseline first, then its alternates."""
    return (seed.baseline,) + seed.alternates


def _arm_points(kern: Kernel, roots: tuple[int, ...]) -> list[int]:
    """Every authored arm-choice key reachable from any accepting item."""
    bits = kern.tables.packing.bits
    found: list[int] = []
    seen: set[int] = set()
    for root in roots:
        for key in ambiguity_points(kern, root):
            bucket = kern.st.links.get(key)
            if key in seen or bucket is None:
                continue
            seen.add(key)
            if is_arm_choice(bucket, bits, kern.tables.code_choice):
                found.append(key)
    return sorted(found)


def _all_leaf_meanings(
    kern: Kernel,
    accepting: int,
    assignment: dict[int, int],
    reducer: Reducer,
    leaf_options: dict[int, tuple[IrSelf, ...]],
    counters: Counters,
    lane: str,
) -> list[IrSelf]:
    """One derivation's meanings over every nested-leaf option combination."""
    tree = build_tree(kern, accepting, assignment, counters, lane)
    out: list[IrSelf] = []
    names = tuple(leaf_options)
    for combo in product(*(leaf_options[name] for name in names)):
        out.append(tree_meaning(tree, reducer, dict(zip(names, combo, strict=True))))
    return out


def _derivation_meaning(
    kern: Kernel,
    root: int,
    assignment: dict[int, int],
    reducer: Reducer,
    leaf_options: dict[int, tuple[IrSelf, ...]],
    counters: Counters,
    lane: str,
) -> IrSelf:
    """The meaning of the engine's OWN derivation — the pair's first element."""
    tree = build_tree(kern, root, assignment, counters, lane)
    baselines = {name: options[0] for name, options in leaf_options.items()}
    return tree_meaning(tree, reducer, baselines)


def outer_run(
    outer: ParserTables,
    island: ParserTables,
    text: str,
    island_rule: str,
    reducer: Reducer,
    counters: Counters,
    artefact: ContinuationArtefact,
    nested: ParserTables | None = None,
    nested_rule: str = "",
) -> OuterRun:
    """Recognize the document ONCE with the island interior delegated."""
    inner: dict[int, Delegate] | None = None
    if nested is not None:
        inner = {
            harness._rule_id(island, nested_rule): partial(
                island_meanings,
                nested,
                reducer=reducer,
                counters=counters,
                delegates=None,
                artefact=artefact,
                rule=nested_rule,
            )
        }
    delegate = partial(
        island_meanings,
        island,
        reducer=reducer,
        counters=counters,
        delegates=inner,
        artefact=artefact,
        rule=island_rule,
    )
    kernel = run_document(
        outer, text, {harness._rule_id(outer, island_rule): delegate}, counters
    )
    seeds: dict[int, IslandSeed] = {}
    for leaf in kernel.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, IslandSeed):
            raise UnsupportedConstructError("island continuation: leaf carries no seed")
        if payload.alternates:
            seeds[id(leaf)] = payload
    return OuterRun(kernel, accept_handle(kernel), seeds)


# ── locating a contextual occurrence in the finished chart ────────────────


class Route(NamedTuple):
    """One realized root→occurrence route and the occurrence it names."""

    steps: tuple[tuple[str, int], ...]
    clone: str
    slot: int


def rules_reaching(artefact: ContinuationArtefact, target: str) -> frozenset[str]:
    """The rules from which ``target`` is reachable, read off the compiled rows.

    The rows ARE the flow graph — ``(clone, slot) -> child`` — so this needs no
    second structure and no document. It is what keeps the descent below
    proportional to the sub-grammar that can hold the occurrence rather than to
    the chart.
    """
    parents: dict[str, list[str]] = {}
    for row in artefact.rows:
        parents.setdefault(row.child, []).append(row.key.clone)
    seen = {target}
    pending = [target]
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return frozenset(seen)


def realized_routes(
    kernel: Kernel,
    roots: tuple[int, ...],
    leaf: PayloadLeaf,
    reaching: frozenset[str],
    counters: Counters,
) -> tuple[Route, ...]:
    """EVERY realized route from an accepting item down to one leaf OBJECT.

    Every route, not one: the DROP certificate is universal over consumers, so
    a leaf reachable through two different consuming clones must satisfy the
    certificate at both. The descent is pruned to the rules from which the
    island rule is reachable, so it is bounded by that sub-chart rather than by
    the document.

    This descent is a PROTOTYPE stand-in. Production does not search for the
    consumer: the island is entered FROM its contextual clone, so the key is in
    hand at island entry — the PDA frame holds it and the Earley waiter's
    packed code is it.
    """
    found: list[Route] = []
    pending: list[tuple[int, tuple[tuple[str, int], ...]]] = [
        (root, ()) for root in roots if harness._name(kernel, root) in reaching
    ]
    while pending:
        handle, prefix = pending.pop()
        counters.descent_steps += 1
        name = harness._name(kernel, handle)
        keys = algebra.local_choice_keys(kernel, handle)
        for assignment in algebra.assignments(kernel, list(keys)):
            resolved = algebra.selected_resolved(kernel, handle, assignment)
            found.extend(_leaf_hits(resolved, leaf, name, prefix))
            pending.extend(_descend(kernel, resolved, name, prefix, reaching))
    return tuple(dedup_routes(found))


def _leaf_hits(
    resolved: harness.Resolved,
    leaf: PayloadLeaf,
    name: str,
    prefix: tuple[tuple[str, int], ...],
) -> list[Route]:
    """The routes this family completes by holding ``leaf`` at one slot."""
    out: list[Route] = []
    for found, slot in zip(resolved.leaves, resolved.slots, strict=True):
        if found is leaf:
            out.append(Route(prefix + ((name, slot),), name, slot))
    return out


def _descend(
    kernel: Kernel,
    resolved: harness.Resolved,
    name: str,
    prefix: tuple[tuple[str, int], ...],
    reaching: frozenset[str],
) -> list[tuple[int, tuple[tuple[str, int], ...]]]:
    """The child handles that can still reach the occurrence, with their routes."""
    return [
        (child, prefix + ((name, slot),))
        for slot, child in zip(algebra.child_slots(resolved), resolved.children)
        if harness._name(kernel, child) in reaching
    ]


def dedup_routes(routes: Sequence[Route]) -> list[Route]:
    """First-seen unique routes."""
    seen: set[tuple[tuple[str, int], ...]] = set()
    out: list[Route] = []
    for route in routes:
        if route.steps not in seen:
            seen.add(route.steps)
            out.append(route)
    return out


def route_is_injective(
    artefact: ContinuationArtefact, route: Route, counters: Counters
) -> bool:
    """Whether every step of one REALIZED route carries its slot injectively."""
    for clone, slot in route.steps:
        counters.lookups += 1
        if row_for(artefact, clone, slot).slot_kind not in (laws.IDENT, laws.GROW):
            return False
    return True


# ── the exact composition, restricted to the live continuations ───────────


class Settlement(NamedTuple):
    """One document's verdict and how it was reached."""

    differs: bool
    meanings: tuple[IrSelf, ...]
    reason: str
    dropped: int
    executed: bool


def settle(
    run: OuterRun,
    artefact: ContinuationArtefact,
    island_rule: str,
    reducer: Reducer,
    counters: Counters,
) -> Settlement:
    """Settle the document from the cached rows, executing only when they say to.

    Order is the certificate's: every occurrence's alternates are discarded
    where the universal DROP row licenses it; a realized injective route then
    proves root inequality with no execution at all; only what neither row
    settles reaches the exact per-node relation.
    """
    if not run.seeds:
        return Settlement(False, (), "no-alternate", 0, False)
    roots = algebra.accepting_roots(run.kernel, run.root)
    live: dict[int, tuple[IrSelf, ...]] = {}
    dropped = 0
    injective = False
    reaching = rules_reaching(artefact, island_rule)
    for leaf_id, seed in run.seeds.items():
        routes = _routes_for(run, roots, leaf_id, reaching, counters)
        if _all_unobservable(artefact, routes, counters):
            counters.dropped_alternates += len(seed.alternates)
            dropped += len(seed.alternates)
            continue
        live[leaf_id] = _seed_options(seed)
        injective = injective or any(
            route_is_injective(artefact, route, counters) for route in routes
        )
    if injective:
        counters.injective_settlements += 1
        return Settlement(True, (), "injective-route", dropped, False)
    if not live:
        return Settlement(False, (), "every-alternate-dropped", dropped, False)
    meanings = exact_root_meanings(run, roots, live, reducer, counters)
    return Settlement(len(meanings) > 1, meanings, "executed", dropped, True)


def _routes_for(
    run: OuterRun,
    roots: tuple[int, ...],
    leaf_id: int,
    reaching: frozenset[str],
    counters: Counters,
) -> tuple[Route, ...]:
    """The realized routes of one delegated occurrence, by leaf object."""
    for leaf in run.kernel.delegated.values():
        if id(leaf) == leaf_id:
            return realized_routes(run.kernel, roots, leaf, reaching, counters)
    raise UnsupportedConstructError("island continuation: seed has no delegated leaf")


def _all_unobservable(
    artefact: ContinuationArtefact, routes: Sequence[Route], counters: Counters
) -> bool:
    """Whether EVERY realized consumer of one occurrence licenses the drop."""
    for route in routes:
        counters.lookups += 1
        if row_for(artefact, route.clone, route.slot).observable:
            return False
    return bool(routes)


def exact_root_meanings(
    run: OuterRun,
    roots: tuple[int, ...],
    live: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counters: Counters,
) -> tuple[IrSelf, ...]:
    """The document's exact requested-root meaning set."""
    options: dict[int, tuple[IrSelf, ...]] = {}
    for leaf in run.kernel.delegated.values():
        payload = leaf.payload
        if isinstance(payload, IslandSeed):
            options[id(leaf)] = live.get(id(leaf), _seed_options(payload)[:1])
    return exact_meanings(
        run.kernel, roots, options, reducer, counters, SETTLEMENT_LANE
    )


def exact_meanings(
    kernel: Kernel,
    roots: tuple[int, ...],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counters: Counters,
    lane: str,
) -> tuple[IrSelf, ...]:
    """The exact requested-root meaning set, by per-node option products.

    Each node's set is its OWN packed families × its children's DEDUPLICATED
    option sets. No global family assignment is ever formed anywhere in the
    mechanism — the island's set comes through this same function.

    **What is document-wide and what is not, exactly.** Every node is folded
    ONCE to its baseline meaning, in the ``baseline_products`` lane: that fold
    is the parse's own product, the value it would build with no ambiguity
    machinery at all, and it is counted separately for precisely that reason.
    The SET lane then runs only on the DIRTY cone — the upward closure of the
    nodes that hold a live occurrence or carry more than one family — because
    every node outside it has only non-dirty descendants and therefore a
    singleton set equal to its baseline. ``executed_products`` counts that
    cone's applications alone, so the ambiguity machinery's own cost is
    cone-proportional even though the baseline fold is not.
    """
    chart = algebra.build_chart(kernel, roots)
    _refuse_cyclic(chart, kernel)
    order = _topological(chart, roots)
    baselines: dict[int, IrSelf] = {}
    for handle in order:
        counters.baseline(lane)
        baselines[handle] = _baseline_node(
            kernel, handle, chart, baselines, options, reducer
        )
    dirty = _dirty_cone(chart, options)
    counters.chart(lane, len(chart.nodes), len(dirty))
    sets: dict[int, tuple[IrSelf, ...]] = {}
    for handle in order:
        if handle not in dirty:
            sets[handle] = (baselines[handle],)
            continue
        found = _node_set(kernel, handle, chart, sets, options, reducer, counters, lane)
        sets[handle] = found
        if len(found) > 1:
            counters.multiple(lane)
    return dedup([meaning for root in roots for meaning in sets.get(root, ())])


def _baseline_node(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    baselines: dict[int, IrSelf],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
) -> IrSelf:
    """One node's baseline meaning — the parse's own value, folded once."""
    resolved = chart.resolveds[handle][0]
    kids: list[IrSelf] = []
    ints = iter(resolved.children)
    for index in range(len(resolved.children) + len(resolved.leaves)):
        if index in resolved.slots:
            kids.append(options[id(resolved.leaves[resolved.slots.index(index)])][0])
            continue
        kids.append(baselines[next(ints)])
    return meaning_of(reducer, harness._name(kernel, handle), kids)


def _dirty_cone(
    chart: algebra.Chart, options: dict[int, tuple[IrSelf, ...]]
) -> frozenset[int]:
    """Nodes whose meaning can be more than one thing, and their ancestors.

    Seeded by a node that carries more than one packed family or holds an
    occurrence with more than one option; closed upward through the chart's own
    family-aware edges. Everything outside has only non-dirty descendants, so
    its set is its baseline.
    """
    parents: dict[int, list[int]] = {}
    for edge in chart.edges:
        parents.setdefault(edge.child, []).append(edge.parent)
    pending = [node for node in chart.nodes if _node_is_multiple(chart, node, options)]
    dirty = set(pending)
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in dirty:
                dirty.add(parent)
                pending.append(parent)
    return frozenset(dirty)


def _node_is_multiple(
    chart: algebra.Chart, node: int, options: dict[int, tuple[IrSelf, ...]]
) -> bool:
    """Whether this completion can mean more than one thing by itself."""
    if len(chart.resolveds[node]) > 1:
        return True
    return any(
        len(options[id(leaf)]) > 1
        for resolved in chart.resolveds[node]
        for leaf in resolved.leaves
    )


def _refuse_cyclic(chart: algebra.Chart, kernel: Kernel) -> None:
    """A cyclic chart is `cyclic_meaning.py`'s established owner, not this one."""
    looped = _looping_node(chart)
    if looped is None:
        return
    raise UnsupportedConstructError(
        "island continuation: this chart has a zero-width component at"
        f" {harness._name(kernel, looped)!r}; the exact relation there belongs"
        " to cyclic_meaning.exact_meanings, not to this module"
    )


def _looping_node(chart: algebra.Chart) -> int | None:
    """One completion inside a zero-width component, or ``None`` if acyclic."""
    groups: list[tuple[int, ...]] = algebra.components(chart.nodes, chart.children)
    for group in groups:
        for node in group:
            if len(group) > 1 or node in chart.children.get(node, ()):
                return node
    return None


def _topological(chart: algebra.Chart, roots: tuple[int, ...]) -> list[int]:
    """Completions in dependency order over the family-aware chart."""
    order: list[int] = []
    seen: set[int] = set()
    stack: list[tuple[int, bool]] = [(root, False) for root in roots]
    while stack:
        handle, expanded = stack.pop()
        if expanded:
            order.append(handle)
            continue
        if handle in seen:
            continue
        seen.add(handle)
        stack.append((handle, True))
        for child in chart.children.get(handle, ()):
            stack.append((child, False))
    return order


def _node_set(
    kernel: Kernel,
    handle: int,
    chart: algebra.Chart,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
    reducer: Reducer,
    counters: Counters,
    lane: str,
) -> tuple[IrSelf, ...]:
    """One node's exact set over its own families × its children's sets."""
    name = harness._name(kernel, handle)
    found: list[IrSelf] = []
    for resolved in chart.resolveds[handle]:
        for kids in product(*_slot_options(resolved, sets, options)):
            counters.product(lane)
            found.append(meaning_of(reducer, name, kids))
    return dedup(found)


def _slot_options(
    resolved: harness.Resolved,
    sets: dict[int, tuple[IrSelf, ...]],
    options: dict[int, tuple[IrSelf, ...]],
) -> list[tuple[IrSelf, ...]]:
    """One family's per-slot option lanes.

    An empty lane RAISES. Skipping the family instead would shrink the meaning
    set — declaring a document unambiguous because a child's set was missing —
    which is the silent default `docs/STYLE.md` §2 forbids, in the one place
    where it would produce a wrong acceptance rather than a wrong error.
    """
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    out: list[tuple[IrSelf, ...]] = []
    for index in range(width):
        if index in resolved.slots:
            lane = options[id(resolved.leaves[resolved.slots.index(index)])]
        else:
            lane = sets.get(next(ints), ())
        if not lane:
            raise UnsupportedConstructError(
                "island continuation: a child slot has no meaning; the exact"
                " set cannot be formed and must not be silently narrowed"
            )
        out.append(lane)
    return out


# ── the rejected one-flip lane, executed for comparison only ──────────────


def one_flip_differs(
    run: OuterRun, roots: tuple[int, ...], reducer: Reducer, counters: Counters
) -> bool:
    """The REJECTED lane: substitute one occurrence's alternate at a time.

    Kept only so the interaction witness can show what it misses.
    `ambiguity_interaction.py` is where it is disproven on the shipped
    `another_meaning`; this lane repeats the shape over real reducer values.
    """
    baseline = _baseline_meaning(run, reducer, counters)
    for leaf_id, seed in run.seeds.items():
        for alternate in _seed_options(seed)[1:]:
            overrides = _baseline_overrides(run)
            overrides[leaf_id] = alternate
            for root in roots:
                if not same_value(
                    baseline, _root_meaning(run, root, overrides, reducer, counters)
                ):
                    return True
    return False


def _baseline_overrides(run: OuterRun) -> dict[int, IrSelf]:
    """Each delegated occurrence's baseline meaning, by leaf identity."""
    out: dict[int, IrSelf] = {}
    for leaf in run.kernel.delegated.values():
        payload = leaf.payload
        if isinstance(payload, IslandSeed):
            out[id(leaf)] = _seed_options(payload)[0]
    return out


def _baseline_meaning(run: OuterRun, reducer: Reducer, counters: Counters) -> IrSelf:
    """The meaning of the engine's own derivation under baseline leaf options."""
    return _root_meaning(run, run.root, _baseline_overrides(run), reducer, counters)


def _root_meaning(
    run: OuterRun,
    root: int,
    overrides: dict[int, IrSelf],
    reducer: Reducer,
    counters: Counters,
) -> IrSelf:
    """One complete derivation's root meaning, through a real `ParseTree`."""
    tree = build_tree(run.kernel, root, {}, counters, FLIP_LANE)
    return tree_meaning(tree, reducer, overrides)


# ── the independent oracle: complete Earley folds over every family ───────


def oracle_root_meanings(
    run: OuterRun, reducer: Reducer, counters: Counters
) -> tuple[IrSelf, ...]:
    """Every requested-root meaning, by complete derivation enumeration.

    Independent of the mechanism in traversal and in enumeration: it builds a
    real `ParseTree` per global family assignment per accepting item, folds it
    over the tree with the same real reducer, and varies every delegated
    occurrence's option set. Exhaustive on these small families — which is
    what makes it an oracle and what makes it unusable as a mechanism.
    """
    roots = algebra.accepting_roots(run.kernel, run.root)
    leaf_options: dict[int, tuple[IrSelf, ...]] = {}
    for leaf in run.kernel.delegated.values():
        payload = leaf.payload
        if isinstance(payload, IslandSeed):
            leaf_options[id(leaf)] = _seed_options(payload)
    points = _arm_points(run.kernel, roots)
    found: list[IrSelf] = []
    for root in roots:
        for assignment in algebra.assignments(run.kernel, points):
            found.extend(
                _all_leaf_meanings(
                    run.kernel,
                    root,
                    assignment,
                    reducer,
                    leaf_options,
                    counters,
                    ORACLE_LANE,
                )
            )
    if not found:
        raise UnsupportedConstructError("island continuation: oracle built nothing")
    return dedup(found)


# ── the witnesses ─────────────────────────────────────────────────────────


def reducer_of(actions: tuple[tuple[str, IrSelf], ...]) -> Reducer:
    """A real `Reducer` over authored IR bodies — the shape shipped ones have."""
    return Reducer(
        actions=IrMap.from_table(
            tuple((IrRuleRef(name), body) for name, body in actions)
        ),
        default=IrArgs(),
        literal=DROP,
    )


WRAP_GBNF = (
    'root ::= wrap\nwrap ::= t\nt ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
)
WRAP_ABNF = (
    'root = wrap\r\nwrap = t\r\nt = alpha / beta\r\nalpha = "x"\r\nbeta = "x"\r\n'
)
DIRECT_GBNF = 'root ::= t\nt ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
DIRECT_ABNF = 'root = t\r\nt = alpha / beta\r\nalpha = "x"\r\nbeta = "x"\r\n'
ISLAND_GBNF = 't ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
ISLAND_ABNF = 't = alpha / beta\r\nalpha = "x"\r\nbeta = "x"\r\n'
PAIR_GBNF = 'root ::= t t\nt ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
PAIR_ABNF = 'root = t t\r\nt = alpha / beta\r\nalpha = "x"\r\nbeta = "x"\r\n'
SITES_GBNF = (
    "root ::= left right\nleft ::= t\nright ::= t\n"
    't ::= "x" inner\ninner ::= p | q\np ::= "y"\nq ::= "y"\n'
)
NESTED_ISLAND = 't ::= "x" inner\ninner ::= p | q\np ::= "y"\nq ::= "y"\n'
NESTED_INNER = 'inner ::= p | q\np ::= "y"\nq ::= "y"\n'
DISTANT_GBNF = (
    "root ::= left t right\n"
    "left ::= item left | item\n"
    "right ::= item right | item\n"
    "item ::= [ab]\n"
    't ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
)
DISTANT_PAD = 40
DISTANT_TEXT = "a" * DISTANT_PAD + "x" + "b" * DISTANT_PAD

TRIPLE_GBNF = (
    "root ::= inner\ninner ::= t hidden t\nhidden ::= t\n"
    't ::= alpha | beta\nalpha ::= "x"\nbeta ::= "x"\n'
)
PLAIN_GBNF = 'root ::= wrap\nwrap ::= t\nt ::= "x"\n'
PLAIN_ISLAND = 't ::= "x"\n'

ISLAND_ARMS = (("t", IrArg(0)), ("alpha", IrStr("one")), ("beta", IrStr("two")))
NESTED_ARMS = (
    ("t", IrArg(0)),
    ("inner", IrArg(0)),
    ("p", IrStr("one")),
    ("q", IrStr("two")),
)
MARKER = IrStr("one")
BOTH_MARKED = IrTuple(MARKER, MARKER)
HIDDEN = IrStr("h")
THREE_MARKED = IrTuple(MARKER, HIDDEN, MARKER)


class Witness(NamedTuple):
    """One case of the composition, with the verdict every lane must agree on."""

    name: str
    case: str
    outer: str
    island: str
    text: str
    actions: tuple[tuple[str, IrSelf], ...]
    differs: bool
    reason: str
    nested: str = ""
    nested_rule: str = ""
    flavour: IrFlavour = GBNF_FLAVOUR
    skipped: int = 0


WITNESSES = (
    Witness(
        "const-consumer",
        "1 — a continuation constant in the island slot",
        WRAP_GBNF,
        ISLAND_GBNF,
        "x",
        (("root", IrBuild(IrTuple)), ("wrap", IrStr("fixed"))) + ISLAND_ARMS,
        False,
        "no-alternate",
        skipped=1,
    ),
    Witness(
        "injective-consumer",
        "2 — an injectively retaining continuation",
        WRAP_GBNF,
        ISLAND_GBNF,
        "x",
        (("root", IrBuild(IrTuple)), ("wrap", IrBuild(IrTuple))) + ISLAND_ARMS,
        True,
        "injective-route",
    ),
    Witness(
        "finite-consumer-equal",
        "3 — a finite continuation whose alternatives agree at the root",
        DIRECT_GBNF,
        ISLAND_GBNF,
        "x",
        (("root", IrCompare(IrArg(0), IrOp("=="), IrStr("three"))),) + ISLAND_ARMS,
        False,
        "executed",
    ),
    Witness(
        "finite-consumer-differs",
        "3 — a finite continuation whose alternatives differ at the root",
        DIRECT_GBNF,
        ISLAND_GBNF,
        "x",
        (("root", IrCompare(IrArg(0), IrOp("=="), IrStr("two"))),) + ISLAND_ARMS,
        True,
        "executed",
    ),
    Witness(
        "distant-island",
        "3 — a finite continuation whose cone does not grow with the document",
        DISTANT_GBNF,
        ISLAND_GBNF,
        DISTANT_TEXT,
        (
            ("root", IrCompare(IrArg(1), IrOp("=="), MARKER)),
            ("left", IrStr("f")),
            ("right", IrStr("f")),
            ("item", IrStr("i")),
        )
        + ISLAND_ARMS,
        True,
        "executed",
    ),
    Witness(
        "interacting-islands",
        "4 — two island choices, invisible apart and visible together",
        PAIR_GBNF,
        ISLAND_GBNF,
        "xx",
        (("root", IrCompare(IrArgs(), IrOp("=="), BOTH_MARKED)),) + ISLAND_ARMS,
        True,
        "executed",
    ),
    Witness(
        "slot-discriminating",
        "5 — one consumer rule whose two SLOTS settle differently",
        PAIR_GBNF,
        ISLAND_GBNF,
        "xx",
        (("root", IrArg(1)),) + ISLAND_ARMS,
        True,
        "injective-route",
    ),
    Witness(
        "interacting-with-a-dropped-third",
        "4 — three occurrences, one of them settled by the const row",
        TRIPLE_GBNF,
        ISLAND_GBNF,
        "xxx",
        (
            ("root", IrBuild(IrTuple)),
            ("inner", IrCompare(IrArgs(), IrOp("=="), THREE_MARKED)),
            ("hidden", HIDDEN),
        )
        + ISLAND_ARMS,
        True,
        "executed",
    ),
    Witness(
        "sibling-and-nested",
        "5 — two sibling occurrences and a nested delegation",
        SITES_GBNF,
        NESTED_ISLAND,
        "xyxy",
        (
            ("root", IrBuild(IrTuple)),
            ("left", IrStr("k")),
            ("right", IrBuild(IrTuple)),
        )
        + NESTED_ARMS,
        True,
        "injective-route",
        NESTED_INNER,
        "inner",
    ),
    Witness(
        "unambiguous-control",
        "6 — no alternate, no execution, no graph, no tree",
        PLAIN_GBNF,
        PLAIN_ISLAND,
        "x",
        (("root", IrBuild(IrTuple)), ("wrap", IrBuild(IrTuple)), ("t", IrStr("one"))),
        False,
        "no-alternate",
    ),
    Witness(
        "const-consumer-abnf",
        "1 — the same case under a second flavour",
        WRAP_ABNF,
        ISLAND_ABNF,
        "x",
        (("root", IrBuild(IrTuple)), ("wrap", IrStr("fixed"))) + ISLAND_ARMS,
        False,
        "no-alternate",
        flavour=ABNF_FLAVOUR,
        skipped=1,
    ),
    Witness(
        "injective-consumer-abnf",
        "2 — the same case under a second flavour",
        WRAP_ABNF,
        ISLAND_ABNF,
        "x",
        (("root", IrBuild(IrTuple)), ("wrap", IrBuild(IrTuple))) + ISLAND_ARMS,
        True,
        "injective-route",
        flavour=ABNF_FLAVOUR,
    ),
    Witness(
        "interacting-islands-abnf",
        "4 — the same interaction under a second flavour",
        PAIR_ABNF,
        ISLAND_ABNF,
        "xx",
        (("root", IrCompare(IrArgs(), IrOp("=="), BOTH_MARKED)),) + ISLAND_ARMS,
        True,
        "executed",
        flavour=ABNF_FLAVOUR,
    ),
)


class Grammars(NamedTuple):
    """Both grammar moments one witness needs.

    The chart runs on ``normalized``; the authored bodies index the channel the
    CANONICAL arms describe. :func:`aligned_rules` is where the two are held
    against each other, so both have to be kept.
    """

    canonical: IrAst
    normalized: IrAst


_GRAMMARS: dict[tuple[str, str], Grammars] = {}
"""Witness source → its grammar moments, so one witness has ONE identity.

Without this every caller minted fresh objects, every bind missed, and the
registry's HIT path — the thing "compiled once and shared by every parse"
claims — was never exercised by a witness at all.
"""


def _grammars(source: str, flavour: IrFlavour) -> Grammars:
    """One witness grammar's canonical and normalized moments, built once."""
    key = (source, type(flavour).__name__)
    found = _GRAMMARS.get(key)
    if found is not None:
        return found
    canonical = canonical_grammar(source, flavour)
    built = Grammars(canonical, normalize(canonical))
    _GRAMMARS[key] = built
    return built


def _ast(source: str, flavour: IrFlavour) -> IrAst:
    """One witness grammar, normalized for the real Earley kernel."""
    return _grammars(source, flavour).normalized


def _tables(source: str, flavour: IrFlavour, size: int) -> ParserTables:
    """Real compiled tables for one witness grammar."""
    return compile_tables(_ast(source, flavour), tier_for(size))


class Lanes(NamedTuple):
    """Everything one witness produced, mechanism and oracle side by side."""

    settlement: Settlement
    oracle: tuple[IrSelf, ...]
    one_flip: bool
    artefact: ContinuationArtefact
    run: OuterRun
    counters: Counters


EMPTY_TABLE = ContinuationArtefact(0, "", ())
"""A table that decides nothing — the control the certificate is measured against.

`unobservable_rule` returns ``False`` for every rule against it, so an island
handed this table enumerates its complete alternate set. Running a witness
twice, once with its real table and once with this one, is what makes the
shortcut FALSIFIABLE: if a skip or a drop ever changed the requested-root
meaning set, the two runs' oracles would differ.
"""


def run_witness(witness: Witness, artefact: ContinuationArtefact) -> Lanes:
    """Run one witness under ``artefact``'s decisions and oracle the result.

    Binding comes FIRST in the caller: the table is compiled before the
    document is recognized, because the delegate consults it to decide whether
    an alternate is worth enumerating at all.
    """
    counters = Counters()
    reducer = reducer_for(witness)
    grammars = _grammars(witness.outer, witness.flavour)
    size = len(witness.text)
    outer = compile_tables(grammars.normalized, tier_for(size))
    island = _tables(witness.island, witness.flavour, size)
    nested = _tables(witness.nested, witness.flavour, size) if witness.nested else None
    run = outer_run(
        outer,
        island,
        witness.text,
        "t",
        reducer,
        counters,
        artefact,
        nested,
        witness.nested_rule,
    )
    settlement = settle(run, artefact, "t", reducer, counters)
    oracle = oracle_root_meanings(run, reducer, counters)
    roots = algebra.accepting_roots(run.kernel, run.root)
    flip = one_flip_differs(run, roots, reducer, counters)
    return Lanes(settlement, oracle, flip, artefact, run, counters)


_REDUCERS: dict[str, Reducer] = {}
"""Witness name → its reducer, so a witness's binding identity is stable."""


def reducer_for(witness: Witness) -> Reducer:
    """One witness's reducer, built once."""
    found = _REDUCERS.get(witness.name)
    if found is not None:
        return found
    built = reducer_of(witness.actions)
    _REDUCERS[witness.name] = built
    return built


def bind_witness(witness: Witness) -> ContinuationArtefact:
    """Compile one witness's continuation table before its document is read."""
    grammars = _grammars(witness.outer, witness.flavour)
    return bind_continuations(
        grammars.canonical, grammars.normalized, reducer_for(witness)
    )


def _exercise(witness: Witness) -> Lanes:
    """Run one witness twice — shortcut and control — and check every claim.

    The control run hands the island :data:`EMPTY_TABLE`, so it enumerates
    every alternate the certificate would have skipped or dropped. Three things
    are then required of every witness, not only the executed ones:

    - the exact per-node lane over the control run equals the control run's
      complete-Earley oracle, which is what validates a DROP or an INJECTIVE
      settlement that computed no set of its own;
    - the shortcut run's oracle equals the control run's, so the skip changed
      nothing observable at the requested root;
    - the declared verdict follows from the control oracle's cardinality.
    """
    lanes = run_witness(witness, bind_witness(witness))
    control = run_witness(witness, EMPTY_TABLE)
    settlement, counters = lanes.settlement, lanes.counters
    full = exact_root_meanings(
        control.run,
        algebra.accepting_roots(control.run.kernel, control.run.root),
        {leaf: _seed_options(seed) for leaf, seed in control.run.seeds.items()},
        reducer_for(witness),
        control.counters,
    )
    assert same_set(full, control.oracle), witness.name
    assert same_set(lanes.oracle, control.oracle), witness.name
    assert (len(control.oracle) > 1) == witness.differs, witness.name
    assert settlement.differs == witness.differs, witness.name
    assert settlement.reason == witness.reason, (witness.name, settlement.reason)
    assert counters.document_recognitions == 1, witness.name
    assert counters.settlement_trees == 0, witness.name
    assert counters.skipped_enumerations == witness.skipped, witness.name
    if witness.reason == "no-alternate":
        assert not lanes.run.seeds, witness.name
        assert counters.descent_steps == 0 and counters.lookups == 0, witness.name
    if settlement.executed:
        assert same_set(settlement.meanings, lanes.oracle), witness.name
    else:
        assert counters.executed_products == 0, witness.name
        assert counters.chart_nodes == 0, witness.name
    print(
        "case",
        witness.case,
        witness.name,
        f"flavour={type(witness.flavour).__name__}",
        f"differs={settlement.differs}",
        f"reason={settlement.reason}",
        f"dropped_alternates={settlement.dropped}",
        f"skipped_enumerations={counters.skipped_enumerations}",
        f"control_root_meanings={len(control.oracle)}",
        f"shortcut_root_meanings={len(lanes.oracle)}",
        f"exact_lane_matches_control_oracle={same_set(full, control.oracle)}",
        f"one_flip_differs={lanes.one_flip}",
        f"settlement_products={counters.executed_products}",
        f"settlement_chart_nodes={counters.chart_nodes}",
        f"settlement_dirty_nodes={counters.dirty_nodes}",
        f"settlement_baseline_products={counters.baseline_products}",
        f"multiplicity_nodes={counters.multiplicity_nodes}",
        f"seed_chart_nodes={counters.seed_chart_nodes}",
        f"seed_dirty_nodes={counters.seed_dirty_nodes}",
        f"seed_baseline_products={counters.seed_baseline_products}",
        f"seed_products={counters.seed_products}",
        f"control_seed_products={control.counters.seed_products}",
        f"retained_island_kernels={counters.retained_island_kernels}",
        f"row_lookups={counters.lookups}",
        f"descent_steps={counters.descent_steps}",
        f"document_recognitions={counters.document_recognitions}",
        f"settlement_trees={counters.settlement_trees}",
        f"seed_trees={counters.seed_trees}",
        f"control_seed_trees={control.counters.seed_trees}",
        f"one_flip_trees={counters.one_flip_trees}",
        f"oracle_trees={counters.oracle_trees}",
        f"seeds={len(lanes.run.seeds)}",
        f"control_seeds={len(control.run.seeds)}",
        sep="\t",
    )
    return lanes


def prove_interaction(lanes: Lanes) -> None:
    """Case 4: both one-flip comparisons equal the baseline; the joint differs."""
    assert len(lanes.run.seeds) >= 2
    cartesian = 1
    for seed in lanes.run.seeds.values():
        # Pin the witness: the marker the root tests for must be the ALTERNATE
        # at both occurrences, or the interaction would collapse into an
        # ordinary one-flip difference and the case would prove nothing.
        assert not same_value(seed.baseline, MARKER)
        assert any(same_value(MARKER, other) for other in seed.alternates)
        cartesian *= 1 + len(seed.alternates)
    assert not lanes.one_flip
    assert lanes.settlement.differs
    print(
        "interaction",
        "one_flip_differs=False",
        f"exact_differs={lanes.settlement.differs}",
        f"root_meanings={len(lanes.settlement.meanings)}",
        f"seeds={len(lanes.run.seeds)}",
        f"dropped_alternates={lanes.settlement.dropped}",
        f"executed_products={lanes.counters.executed_products}",
        f"rejected_cartesian_assignment_count={cartesian}",
        "the exact lane forms per-node products over DEDUPLICATED child sets;"
        " no global family assignment is ever built, and no alternative is"
        " discarded for equalling the baseline under the other choices'"
        " baseline values",
        sep="\t",
    )


def prove_oracle_precondition(lanes: Lanes, witness: Witness) -> None:
    """The condition under which per-node sets and global assignments agree.

    The mechanism gives every OCCURRENCE its own family choice; the oracle
    fixes one family per KEY across a whole derivation. Those two relations
    coincide exactly when no node — and so no arm-choice key — is reachable
    twice inside one derivation. That is a real precondition, not a detail, so
    it is checked rather than assumed: every completion of the outer chart has
    at most one distinct parent, and every arm-choice key is claimed by exactly
    one completion.

    Where it fails, the per-node relation is the DESIGN's relation (each
    occurrence derives independently) and the global-assignment enumeration is
    the narrower one; the oracle would then have to change, and no witness here
    exercises that shape.
    """
    roots = algebra.accepting_roots(lanes.run.kernel, lanes.run.root)
    chart = algebra.build_chart(lanes.run.kernel, roots)
    parents: dict[int, set[int]] = {}
    for edge in chart.edges:
        parents.setdefault(edge.child, set()).add(edge.parent)
    shared = sorted(node for node, found in parents.items() if len(found) > 1)
    claims: dict[int, int] = {}
    for node in chart.nodes:
        for key in algebra.local_choice_keys(lanes.run.kernel, node):
            claims[key] = claims.get(key, 0) + 1
    twice = sorted(key for key, count in claims.items() if count > 1)
    assert not shared and not twice, (witness.name, shared, twice)
    print(
        "oracle-precondition",
        witness.name,
        f"chart_nodes={len(chart.nodes)}",
        f"nodes_with_two_parents={len(shared)}",
        f"keys_claimed_twice={len(twice)}",
        "per-node sets and per-assignment derivations coincide on this chart;"
        " where they would not, the per-node relation is the design's and the"
        " oracle would have to change — no witness exercises that shape",
        sep="\t",
    )


def prove_occurrence_identity(lanes: Lanes) -> None:
    """Case 5: sibling occurrences and one nested level, addressed by object."""
    tree = build_tree(
        lanes.run.kernel, lanes.run.root, {}, lanes.counters, SETTLEMENT_LANE
    )
    leaves = pairs.payload_leaves(tree)
    assert len(leaves) == 2 and leaves[0] is not leaves[1]
    assert all(pairs.leaf_occurrences(tree, leaf) == 1 for leaf in leaves)
    roots = algebra.accepting_roots(lanes.run.kernel, lanes.run.root)
    keys: list[ContinuationKey] = []
    verdicts: list[str] = []
    reaching = rules_reaching(lanes.artefact, "t")
    for leaf in leaves:
        routes = realized_routes(
            lanes.run.kernel, roots, leaf, reaching, lanes.counters
        )
        assert len(routes) == 1
        row = row_for(lanes.artefact, routes[0].clone, routes[0].slot)
        keys.append(row.key)
        verdicts.append(row.verdict)
    assert keys[0] != keys[1]
    assert set(verdicts) == {DROP_VERDICT, INJECTIVE_VERDICT}
    nested = sum(
        1
        for leaf in lanes.run.kernel.delegated.values()
        if isinstance(leaf.payload, IslandSeed)
    )
    print(
        "occurrence-identity",
        f"outer_delegated_leaves={len(leaves)}",
        f"distinct_leaf_objects={leaves[0] is not leaves[1]}",
        f"occurrences_per_leaf={[pairs.leaf_occurrences(tree, leaf) for leaf in leaves]}",
        f"distinct_continuation_keys={keys[0] != keys[1]}",
        f"verdicts={verdicts}",
        f"outer_seeds_published={nested}",
        "one delegated leaf per occurrence, so the occurrence names its own"
        " row: the same island rule settles differently at its two sites",
        sep="\t",
    )


def prove_drop_is_not_a_guess(witness: Witness) -> None:
    """Execute the DROP certificate's claim, per occurrence, as a differential.

    The certificate says a DROPPED occurrence cannot change the requested root
    while every other occurrence keeps its full option set. That is a claim
    about VALUES, so it is executed: the island runs against
    :data:`EMPTY_TABLE` so every alternate really exists, then the exact lane
    runs twice — once with the dropped occurrences collapsed to their baseline
    and every other occurrence admitted, once with ALL occurrences admitted —
    and the two requested-root meaning sets must be equal.

    An unsound drop shows up here as a set that grew, which is exactly the
    failure a boolean verdict comparison would miss.
    """
    counters = Counters()
    reducer = reducer_for(witness)
    ast = _ast(witness.outer, witness.flavour)
    size = len(witness.text)
    run = outer_run(
        compile_tables(ast, tier_for(size)),
        _tables(witness.island, witness.flavour, size),
        witness.text,
        "t",
        reducer,
        counters,
        EMPTY_TABLE,
    )
    artefact = bind_witness(witness)
    roots = algebra.accepting_roots(run.kernel, run.root)
    reaching = rules_reaching(artefact, "t")
    admitted = {leaf: _seed_options(seed) for leaf, seed in run.seeds.items()}
    certified: dict[int, tuple[IrSelf, ...]] = {}
    dropped = 0
    for leaf_id, options in admitted.items():
        routes = _routes_for(run, roots, leaf_id, reaching, counters)
        if _all_unobservable(artefact, routes, counters):
            certified[leaf_id] = options[:1]
            dropped += 1
            continue
        certified[leaf_id] = options
    without = exact_root_meanings(run, roots, certified, reducer, counters)
    with_them = exact_root_meanings(run, roots, admitted, reducer, counters)
    assert same_set(without, with_them), witness.name
    print(
        "drop-differential",
        witness.name,
        f"occurrences={len(admitted)}",
        f"occurrences_the_rows_dropped={dropped}",
        f"root_meanings_with_the_dropped_alternates_removed={len(without)}",
        f"root_meanings_with_every_alternate_admitted={len(with_them)}",
        f"equal={same_set(without, with_them)}",
        "the universal const certificate is executed, not asserted",
        sep="\t",
    )


def prove_registry_residency() -> None:
    """Every pinned entry, counted — then released, and counted again.

    `parsing/caches.py` ships `cached_entries()` as its own leak meter for
    exactly this reason: a pinned identity key is an immortal key, so the
    entry count is the cost, and asserting it is benign without reporting it
    would be the claim this row exists to avoid.
    """
    resident = len(_REGISTRY)
    witnesses = len({(witness.outer, witness.name) for witness in WITNESSES})
    for witness in WITNESSES:
        release_continuations(
            _grammars(witness.outer, witness.flavour).normalized, reducer_for(witness)
        )
    print(
        "registry-residency",
        f"entries_after_the_run={resident}",
        f"distinct_bound_products={witnesses}",
        f"entries_after_release={len(_REGISTRY)}",
        "one entry per bound product, each pinning its grammar and reducer"
        " until released; release drains every one",
        sep="\t",
    )
    assert not _REGISTRY


def prove_artefact_is_flat(artefact: ContinuationArtefact) -> None:
    """The cached table holds ints and declarations only — no value, no callback.

    The walk is typed by :data:`Flat`: if the table ever held a kernel, a
    derivation, a meaning or a callable, the annotation would not accept it and
    the walk would raise rather than count it.
    """
    leaves = 0
    pending: list[Flat] = [artefact]
    while pending:
        node = pending.pop()
        if isinstance(node, tuple):
            pending.extend(node)
            continue
        if isinstance(node, (int, str)):
            leaves += 1
            continue
        raise AssertionError(f"continuation table holds {type(node).__name__!r}")
    print(
        "artefact-flatness",
        f"rows={len(artefact.rows)}",
        f"flat_leaves={leaves}",
        "every leaf is an int or a declaration string: no ParseTree, no kernel,"
        " no meaning, no callable, so the table cannot retain a parse",
        sep="\t",
    )


def _semantics_of(artefact: ContinuationArtefact) -> tuple[Continuation, ...]:
    """One table's rows with the residency token removed.

    The product id is a fresh residency token, not semantics: an evicted table
    recompiles to the same rows under a new id, which is exactly the "eviction
    changes residency only" property the design requires.
    """
    return tuple(row._replace(key=row.key._replace(product=0)) for row in artefact.rows)


def prove_artefact_lifetime() -> None:
    """Compiled once per bound product; eviction changes residency only."""
    witness = WITNESSES[1]
    reducer = reducer_for(witness)
    grammars = _grammars(witness.outer, witness.flavour)
    ast = grammars.normalized
    first = bind_continuations(grammars.canonical, ast, reducer)
    again = bind_continuations(grammars.canonical, ast, reducer)
    assert first is again
    assert release_continuations(ast, reducer)
    rebound = bind_continuations(grammars.canonical, ast, reducer)
    assert rebound is not first
    assert _semantics_of(rebound) == _semantics_of(first)
    spare = reducer_of(WITNESSES[0].actions)
    other = bind_continuations(grammars.canonical, ast, spare)
    assert other.product != rebound.product
    assert _semantics_of(other) != _semantics_of(rebound)
    assert release_continuations(ast, spare)
    print(
        "artefact-lifetime",
        f"same_object_on_rebind={first is again}",
        f"eviction_recomputes_equal_rows="
        f"{_semantics_of(rebound) == _semantics_of(first)}",
        f"distinct_reducer_gets_a_distinct_product={other.product != rebound.product}",
        "the entry PINS its key objects, which is what `parsing/caches.py`"
        " says a bare id-keyed dict must do to stay correct against address"
        " reuse — correct, and immortal until released. Production's mortal"
        " owner is the CompiledGrammar artefact through parsing.caches, which"
        " cache_lifetime.py proved and this module does not re-derive",
        sep="\t",
    )


def prove_no_witness_reads_the_focus() -> None:
    """No witness body reads the focus, so `YIELD`'s span question is absent."""
    focus_reading = ("IrThis", "Yield", "IrChild", "IrChildren", "IrField", "IrAt")
    seen: set[str] = set()
    for witness in WITNESSES:
        for _name, body in witness.actions:
            seen.update(_node_type_names(body))
    offending = sorted(seen & set(focus_reading))
    assert not offending, offending
    print(
        "focus-free",
        f"operation_types_used={sorted(seen)}",
        "no witness action reads the focus, so the drop-aware text view stays"
        " Prototype 14's open obligation and is not smuggled in here",
        sep="\t",
    )


def _node_type_names(body: IrSelf) -> set[str]:
    """Every operation type name inside one authored body."""
    found: set[str] = set()
    pending: list[IrSelf] = [body]
    while pending:
        node = pending.pop()
        found.add(type(node).__name__)
        if isinstance(node, laws.IrNode):
            pending.extend(node.children())
    return found


def prove_row_census() -> None:
    """What the certificate settles on the four shipped self-grammars.

    A scale row, deliberately not a claim: the shipped surfaces are recursive,
    so most of their rules ARE reachable through a carrying edge and most rows
    are ``execute``. What the census establishes is that the compile step runs
    on real shipped grammars and reducers and produces a row for every
    occurrence — including the ones it refuses to shortcut.
    """
    started = time.process_time()
    for surface, reducer in laws.DISPATCHERS.items():
        artefact = compile_continuations(
            laws._canonical(surface), laws._normalized(surface), reducer, 0
        )
        census: dict[str, int] = {}
        for row in artefact.rows:
            census[row.verdict] = census.get(row.verdict, 0) + 1
        kinds: dict[str, int] = {}
        for row in artefact.rows:
            kinds[row.slot_kind] = kinds.get(row.slot_kind, 0) + 1
        print(
            "row-census",
            surface,
            f"rows={len(artefact.rows)}",
            f"verdicts={dict(sorted(census.items()))}",
            f"slot_classes={dict(sorted(kinds.items()))}",
            sep="\t",
        )
    print(
        "row-census",
        f"cpu={time.process_time() - started:.6f}",
        "ONE un-repeated process-CPU sample with no control row: it says the"
        " compile step runs, not how much it costs. docs/STYLE.md wants a"
        " control beside any number that carries a conclusion, and no"
        " conclusion is drawn from this one",
        sep="\t",
    )


def prove_resolver_materialization(witness: Witness) -> None:
    """Complete trees are built ONLY after root inequality and a real resolver.

    The splice itself is `resolver_pair.py`'s established evidence and is not
    re-derived: this row invokes its occurrence-addressed
    :func:`resolver_pair.splice_leaf` on the island's own derivations, counts
    what that costs, and pins that the settlement path before it built nothing.
    """
    counters = Counters()
    reducer = reducer_for(witness)
    ast = _ast(witness.outer, witness.flavour)
    size = len(witness.text)
    island_tables = _tables(witness.island, witness.flavour, size)
    artefact = bind_witness(witness)
    run = outer_run(
        compile_tables(ast, tier_for(size)),
        island_tables,
        witness.text,
        "t",
        reducer,
        counters,
        artefact,
    )
    settlement = settle(run, artefact, "t", reducer, counters)
    assert settlement.differs
    assert counters.settlement_trees == 0
    recognitions = counters.document_recognitions
    islands = counters.island_runs
    assert recognitions == 1
    before = counters.resolver_trees
    trees = _resolver_pair(run, counters)
    counters.resolver_calls += 1
    assert counters.document_recognitions == recognitions
    assert counters.island_runs == islands
    chosen = trees[0]
    print(
        "resolver-materialization",
        witness.name,
        f"complete_document_trees_before_the_resolver={before}",
        f"trees_after_the_resolver={counters.resolver_trees}",
        f"recognitions_before_the_resolver={recognitions}",
        f"recognitions_after_the_resolver={counters.document_recognitions}",
        f"resolver_calls={counters.resolver_calls}",
        f"chosen_root={chosen.symbol}",
        f"pair_is_two_distinct_trees={trees[0] is not trees[1]}",
        f"island_recognitions_after={counters.island_runs}",
        f"retained_island_kernels={counters.retained_island_kernels}",
        "the pair is spliced from the kernel the SEED retained, so neither the"
        " document nor the island is recognized again — and the price is that"
        " retention, one live kernel per ambiguous occurrence. No"
        " COMPLETE-DOCUMENT tree existed before inequality was proven; the"
        " island's own single derivation did, exactly as it does today",
        sep="\t",
    )
    assert trees[0] is not trees[1]


def _resolver_pair(run: OuterRun, counters: Counters) -> tuple[ParseTree, ParseTree]:
    """Two complete derivations, by occurrence-addressed splice.

    Built from the island kernel the SEED retained, so this performs no second
    recognition of any kind — neither of the document nor of the island. That
    retention is the price: one live kernel per ambiguous delegated occurrence,
    from the moment the island publishes an alternate until settlement.
    `islands.island_parse` retains nothing today, which is exactly why
    `PROTOTYPE_14.md` §2 calls a document-rooted pair new deferred state rather
    than free re-use.
    """
    outer_tree = build_tree(run.kernel, run.root, {}, counters, RESOLVER_LANE)
    leaf = pairs.payload_leaves(outer_tree)[0]
    payload = leaf.payload
    if not isinstance(payload, IslandSeed) or payload.kernel is None:
        raise UnsupportedConstructError(
            "island continuation: this occurrence retained no island kernel"
        )
    kern = payload.kernel
    built: list[ParseTree] = []
    accepting = (payload.root,) + harness._sibling_accepts(kern, payload.root)
    for handle in accepting:
        derivation = build_tree(kern, handle, {}, counters, RESOLVER_LANE)
        built.append(pairs.splice_leaf(outer_tree, leaf, derivation))
    if len(built) < 2:
        raise UnsupportedConstructError("island continuation: no complete pair")
    return built[0], built[1]


def _island_is_observable(lanes: Lanes) -> bool:
    """Whether any compiled row makes the island rule observable at the root."""
    return not unobservable_rule(lanes.artefact, "t")


def _island_value_carried(lanes: Lanes, value: IrSelf | None) -> bool:
    """Whether the island's own meaning stands inside the shipped value.

    Separates a CARRYING continuation from a constant one on the rows where
    the shipped path returns a value at all: a constant consumer discards the
    island, so its meaning must not appear; a retaining one must show it.
    """
    if value is None:
        return False
    for leaf in lanes.run.kernel.delegated.values():
        payload = leaf.payload
        if isinstance(payload, IslandSeed):
            return repr(payload.baseline) in repr(value)
    return False


def prove_shipped_path(witness: Witness, lanes: Lanes) -> None:
    """The SHIPPED `CompiledGrammar.reduce`, on the same grammar and reducer.

    This is what grounds "real reducer/action, not a toy policy": where the
    shipped reduction path returns a value, that value must be the meaning
    this module computes as its baseline. The shipped path recognizes the
    whole document with no delegation and folds through `ReduceFold`, so
    agreement is a differential across two independent executions of one
    authored semantics.

    **Where the differential is blind, and why it cannot be widened today.**
    A shipped row can only AGREE on a document the shipped gate does not
    refuse, and the shipped gate refuses on the generated MODEL: any island
    with two derivations builds two models, so it refuses even when both
    derivations mean the same reducer value (`prove_value_relation_divergence`
    is that case). `CompiledGrammar.reduce` has no `resolve=` channel today —
    adding it is `goal.md`'s own public-surface work — so there is no way to
    obtain a shipped VALUE for a document whose island choice is live. The
    blindness is a property of the shipped gate, not a missing witness, and it
    is one more instance of the §5 value-versus-model divergence.

    What the agreeing rows DO check is that the continuation carries: the row
    reports whether the island's own published meaning stands inside the
    shipped value, which separates a carrying consumer from a constant one.
    """
    compiled = compile_text(witness.outer, flavour=witness.flavour)
    reducer = reducer_for(witness)
    outcome = ""
    value: IrSelf | None = None
    try:
        value = compiled.reduce(witness.text, reducer, cores=1)
        outcome = "value"
    except LexicError as error:
        outcome = f"refused: {error}"
    baseline = _baseline_meaning(lanes.run, reducer, Counters())
    if value is not None:
        assert same_value(value, baseline), (witness.name, value, baseline)
    carried = _island_value_carried(lanes, value)
    if value is not None and lanes.run.kernel.delegated:
        assert carried == _island_is_observable(lanes), witness.name
    print(
        "shipped-path",
        witness.name,
        f"reduce={outcome}",
        f"shipped_value={value!r}",
        f"mechanism_baseline={baseline!r}",
        f"agree={value is not None and same_value(value, baseline)}",
        f"island_value_stands_in_the_shipped_value={carried}",
        sep="\t",
    )


def prove_value_relation_divergence(lanes: Lanes, witness: Witness) -> None:
    """The shipped MODEL relation refuses a document whose VALUE is unambiguous.

    `goal.md` rules the definitive reduced-root value relation the successor of
    the variant-model relation and requires the differences to be enumerated.
    This is one of them, executable: the two derivations build different
    generated models, so the shipped `reduce` refuses, while the reducer's own
    value is the same both ways and the exact relation accepts.

    It is not a fourth shipped defect. The shipped behaviour follows the
    relation the engine currently declares; the divergence is the migration
    `goal.md` §5 already owns.
    """
    compiled = compile_text(witness.outer, flavour=witness.flavour)
    reducer = reducer_for(witness)
    refusal = ""
    try:
        compiled.reduce(witness.text, reducer, cores=1)
    except LexicError as error:
        refusal = str(error)
    assert refusal
    assert len(lanes.oracle) == 1
    assert not lanes.settlement.differs
    print(
        "value-relation-divergence",
        witness.name,
        f"shipped_reduce={refusal}",
        f"exact_root_meanings={len(lanes.oracle)}",
        f"exact_differs={lanes.settlement.differs}",
        "the shipped gate compares generated MODELS; the target-shaped product"
        " compares the requested-root VALUE — one enumerated goal.md §5"
        " migration difference, executed rather than asserted",
        sep="\t",
    )


def main() -> None:
    """Run the six cases, both flavours, and every ownership proof."""
    prove_no_witness_reads_the_focus()
    lanes = {witness.name: _exercise(witness) for witness in WITNESSES}
    prove_interaction(lanes["interacting-islands"])
    prove_interaction(lanes["interacting-islands-abnf"])
    prove_interaction(lanes["interacting-with-a-dropped-third"])
    prove_occurrence_identity(lanes["sibling-and-nested"])
    for witness in WITNESSES:
        prove_oracle_precondition(lanes[witness.name], witness)
    prove_value_relation_divergence(
        lanes["finite-consumer-equal"],
        next(w for w in WITNESSES if w.name == "finite-consumer-equal"),
    )
    for name in ("const-consumer", "sibling-and-nested", "slot-discriminating"):
        prove_drop_is_not_a_guess(next(w for w in WITNESSES if w.name == name))
    prove_artefact_is_flat(lanes["injective-consumer"].artefact)
    prove_artefact_lifetime()
    prove_registry_residency()
    prove_resolver_materialization(WITNESSES[1])
    prove_row_census()
    for witness in WITNESSES:
        prove_shipped_path(witness, lanes[witness.name])
    print(
        "invariant",
        "one immutable row per contextual occurrence settles a constant"
        " continuation universally and an injective one existentially, both"
        " without executing an operation or recognizing the document again;"
        " everything else reaches the exact per-node relation, where"
        " interacting occurrences compose through deduplicated option products"
        " rather than global assignments — nowhere, island included, is a"
        " global family assignment formed; the set lane runs only on the dirty"
        " cone, while the per-node baseline fold beside it is the parse's own"
        " product; an unambiguous document allocates no alternate, no node set,"
        " no chart walk and no COMPLETE-DOCUMENT tree, and its island builds"
        " the one derivation `islands.island_parse` builds today",
        sep="\t",
    )


if __name__ == "__main__":
    main()
