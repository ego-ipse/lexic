"""Multiple/nested ambiguity is not one-flip separable — and the exact fix.

Part 1 proves the defect at the PUBLIC boundary: on a real two-point chart,
production `another_meaning` returns None for a pure threshold `build` whose
joint double-flip derivation builds a different value. Purity does not imply
separability; only joint injectivity of the consuming operations does.

Part 2 prototypes and counts three replacements over the accepted island-seed
harness (`island_alternate_seed.py` is imported as the shared real-kernel
harness; nothing there is re-implemented):

- exact value-SET propagation with semantic deduplication at every completed
  parent (the reference semantics: a node's set is exactly the distinct
  meanings derivable at it; refusal ⟺ |root set| > 1);
- an operation-specific separability certificate: a node whose "sky" (every
  operation from it to the root) is jointly injective may refuse as soon as
  its own multiplicity exceeds one, with no enumeration above it;
- the hybrid that uses the certificate where the compiler proves it and exact
  deduplicated sets inside every non-injective cone.

The meaning algebra, the chart-resolution helpers, and the exact CYCLIC
mechanism live in `cyclic_meaning`, which this module imports: one algebra, so
the acyclic and cyclic lanes cannot drift apart. Unconditional Cartesian
enumeration is priced here as the rejected upper bound, and the one-lap
relation it used for cyclic charts is now only a comparison lane.
"""

from __future__ import annotations

import tracemalloc
from typing import NamedTuple

import cyclic_meaning as algebra
import island_alternate_seed as harness

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
    another_meaning,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Delegate, Kernel
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.pda.runtime.islands import island_run

type Meaning = harness.Meaning
type MeaningSet = tuple[Meaning, ...]

TWO_POINT = (
    "root ::= s t\n"
    "s ::= a1 | a2\n"
    "t ::= b1 | b2\n"
    'a1 ::= "x"\na2 ::= "x"\nb1 ::= "y"\nb2 ::= "y"\n'
)
ISLAND_TWO_SOURCE = (
    't ::= mark inner\nmark ::= m1 | m2\nm1 ::= "x"\nm2 ::= "x"\n' + harness.INNER
)
OUTER_ROOTS = (
    'root ::= left | right\nleft ::= "(" t ")"\nright ::= "(" t ")"\n' + harness.ISLAND
)
OUTER_CHOICE = (
    'root ::= "[" m "]"\nm ::= p | q\np ::= "(" t ")"\nq ::= "(" t ")"\n'
    + harness.ISLAND_PLAIN
)
AMBIG_SIMPLE = 'root ::= t "z"\nt ::= u | v\nu ::= "x"\nv ::= "x"\n'
DEEP_CYCLE = 'root ::= c list\nc ::= d | "x"\nd ::= c\nlist ::= item*\nitem ::= [ab]\n'


class Metrics:
    """What one verdict mechanism paid."""

    __slots__ = ("early_ok", "max_live", "ops", "retained")

    def __init__(self) -> None:
        self.ops = 0
        self.retained = 0
        self.max_live = 0
        self.early_ok = False

    def note(self, live: int) -> None:
        """Track the peak count of concurrently stored meanings."""
        if live > self.max_live:
            self.max_live = live


def enumerate_island_meanings(
    tables: ParserTables,
    text: str,
    pos: int,
    policies: dict[str, str],
    metrics: Metrics,
    delegates: dict[int, Delegate] | None = None,
) -> MeaningSet:
    """The island's EXACT meaning set — the specification an island seed must
    carry: every combination of its own arm choices, sibling accepting roots,
    and nested leaf option sets, deduplicated. Island charts are small; the
    production shape generalizes the per-node union to packed families."""
    kern, best = island_run(tables, text[pos : pos + 256], delegates)
    if best is None:
        raise UnsupportedConstructError("interaction: island did not match")
    item, end = best
    root = (item << kern.tables.packing.bits) | end
    roots = (root,) + harness._sibling_accepts(kern, root)
    leaf_sets: dict[int, MeaningSet] = {}
    for leaf in kern.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, harness.IslandSeed):
            raise UnsupportedConstructError("interaction: nested leaf has no seed")
        leaf_sets[id(leaf)] = (payload.baseline,) + payload.alternates
    # Lazy Leo expansion appends families while alternates fold, so family
    # indices are only stable at a fixpoint: enumerate, then re-read the
    # point/family census and repeat until it stops changing.
    census: list[tuple[int, int]] = []
    meanings: list[Meaning] = []
    while True:
        points = [
            key
            for key in _all_arm_points(kern, roots)
            if is_arm_choice(
                kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
            )
        ]
        meanings = []
        for accepting in roots:
            for assignment in algebra.assignments(kern, points):
                for overrides in algebra._leaf_combos(leaf_sets):
                    metrics.ops += 1
                    meanings.append(
                        _fold_selected(kern, accepting, policies, assignment, overrides)
                    )
                    metrics.note(len(meanings))
        after = [(key, len(kern.st.links[key])) for key in points]
        if after == census:
            break
        census = after
    deduped = algebra.dedup(meanings)
    metrics.retained += len(deduped)
    return deduped


def _all_arm_points(kern: Kernel, roots: tuple[int, ...]) -> list[int]:
    """Union of ambiguity points reachable from every accepting root."""
    found: list[int] = []
    seen: set[int] = set()
    for root in roots:
        for key in ambiguity_points(kern, root):
            if key not in seen:
                seen.add(key)
                found.append(key)
    return sorted(found)


def _fold_selected(
    kern: Kernel,
    root: int,
    policies: dict[str, str],
    selected: dict[int, int],
    overrides: dict[int, Meaning],
) -> Meaning:
    """Fold one fully selected island derivation to its meaning."""
    occurrences = {leaf_id: override for leaf_id, override in overrides.items()}
    folder = algebra.SetFolder(
        kern, policies, occurrences, harness.Counters(), "oracle"
    )
    memo: dict[int, Meaning] = {}
    stack: list[tuple[int, bool]] = [(root, False)]
    while stack:
        handle, expanded = stack.pop()
        if handle in memo:
            continue
        resolved = algebra.selected_resolved(kern, handle, selected)
        missing = [child for child in resolved.children if child not in memo]
        if not expanded or missing:
            # Lazy Leo expansion can extend link buckets between the two
            # passes of one handle, so a child discovered late is re-pushed
            # rather than assumed present (the walk converges because a
            # post-expansion resolve is deterministic).
            stack.append((handle, True))
            for child in reversed(missing):
                stack.append((child, False))
            continue
        overlay = harness.Overlay(memo)
        memo[handle] = folder._assemble(handle, resolved, overlay, overrides)
    return memo[root]


def one_flip_island_meanings(
    tables: ParserTables,
    text: str,
    pos: int,
    policies: dict[str, str],
    metrics: Metrics,
    delegates: dict[int, Delegate] | None = None,
) -> MeaningSet:
    """The ACCEPTED single-flip island enumeration under the extended algebra
    — baseline plus one alternate per single arm flip, sibling accepting
    root, or single nested-leaf substitution. Deliberately unsound for
    interacting sources; the witnesses measure exactly that."""
    kern, best = island_run(tables, text[pos : pos + 256], delegates)
    if best is None:
        raise UnsupportedConstructError("interaction: island did not match")
    item, end = best
    root = (item << kern.tables.packing.bits) | end
    leaf_baselines: dict[int, Meaning] = {}
    leaf_alternates: dict[int, MeaningSet] = {}
    for leaf in kern.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, harness.IslandSeed):
            raise UnsupportedConstructError("interaction: nested leaf has no seed")
        leaf_baselines[id(leaf)] = payload.baseline
        leaf_alternates[id(leaf)] = payload.alternates
    baseline = _fold_selected(kern, root, policies, {}, leaf_baselines)
    candidates: list[Meaning] = []
    for sibling in harness._sibling_accepts(kern, root):
        metrics.ops += 1
        candidates.append(_fold_selected(kern, sibling, policies, {}, leaf_baselines))
    points = [
        key
        for key in ambiguity_points(kern, root)
        if is_arm_choice(
            kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
        )
    ]
    for key in points:
        for family in range(1, len(kern.st.links[key])):
            metrics.ops += 1
            candidates.append(
                _fold_selected(kern, root, policies, {key: family}, leaf_baselines)
            )
    for leaf_id, alternates in leaf_alternates.items():
        for alternate in alternates:
            metrics.ops += 1
            overrides = dict(leaf_baselines)
            overrides[leaf_id] = alternate
            candidates.append(_fold_selected(kern, root, policies, {}, overrides))
    alternates_found = tuple(
        meaning
        for meaning in algebra.dedup(candidates)
        if not harness.same_value(baseline, meaning)
    )
    return (baseline,) + alternates_found


def one_flip_delegate(
    island: ParserTables,
    policies: dict[str, str],
    metrics: Metrics,
    inner: dict[int, Delegate] | None = None,
) -> Delegate:
    """A delegate whose seed carries only single-flip island alternates."""

    def delegate(window: str, pos: int) -> tuple[int, harness.IslandSeed] | None:
        kern, best = island_run(island, window[pos : pos + 256], inner)
        if best is None:
            return None
        _item, end = best
        meanings = one_flip_island_meanings(
            island, window, pos, policies, metrics, inner
        )
        return pos + end, harness.IslandSeed(meanings[0], meanings[1:])

    return delegate


def set_delegate(
    island: ParserTables,
    policies: dict[str, str],
    metrics: Metrics,
    inner: dict[int, Delegate] | None = None,
) -> Delegate:
    """A delegate whose published seed carries the island's exact meaning set."""

    def delegate(window: str, pos: int) -> tuple[int, harness.IslandSeed] | None:
        kern, best = island_run(island, window[pos : pos + 256], inner)
        if best is None:
            return None
        _item, end = best
        meanings = enumerate_island_meanings(
            island, window, pos, policies, metrics, inner
        )
        return pos + end, harness.IslandSeed(meanings[0], meanings[1:])

    return delegate


class Verdict(NamedTuple):
    """One mechanism's answer plus its structural counts."""

    differs: bool
    ops: int
    retained: int
    max_live: int


def one_flip(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """The accepted single-seed replay, applied one flip at a time (unsound)."""
    counters = harness.Counters()
    folder = algebra.SetFolder(
        run.kernel, policies, run.occurrences, counters, "baseline"
    )
    memo = harness.Overlay({})
    baseline = folder.apply(run.root, memo, set(), None, {})
    base_layer = dict(memo.changed)
    if not run.seeds:
        return Verdict(False, counters.baseline_folds, 1, len(base_layer))
    graph = harness._graph(run.kernel, run.root)
    replay = algebra.SetFolder(
        run.kernel, policies, run.occurrences, counters, "replay"
    )
    differs = False
    for leaf_id, seed in run.seeds.items():
        dirty = harness._dirty(graph, leaf_id)
        for alternate in seed.alternates:
            overlay = harness.Overlay(base_layer)
            meaning = replay.apply(run.root, overlay, dirty, None, {leaf_id: alternate})
            if not harness.same_value(baseline, meaning):
                differs = True
    ops = counters.baseline_folds + counters.replay_folds
    return Verdict(
        differs,
        ops,
        1 + sum(len(s.alternates) for s in run.seeds.values()),
        len(base_layer),
    )


def _leaf_option_table(run: harness.OuterRun) -> dict[int, MeaningSet]:
    """Delegated-leaf option sets: baseline plus every seed alternate."""
    options: dict[int, MeaningSet] = {
        leaf_id: (run.occurrences[leaf_id],) for leaf_id in run.occurrences
    }
    for leaf_id, seed in run.seeds.items():
        options[leaf_id] = (seed.baseline,) + seed.alternates
    return options


def _node_meanings(
    kernel: Kernel,
    handle: int,
    folder: algebra.SetFolder,
    sets: dict[int, MeaningSet],
    leaf_options: dict[int, MeaningSet],
    metrics: Metrics,
) -> tuple[MeaningSet, tuple[int, ...]] | tuple[None, tuple[int, ...]]:
    """One node's exact set: union over its OWN packed families × child sets.

    Returns ``(None, missing_children)`` when a child set is not yet
    computed (the caller re-pushes), else ``(set, ())``.
    """
    keys = algebra.local_choice_keys(kernel, handle)
    assignments = algebra.assignments(kernel, list(keys))
    resolveds = [
        algebra.selected_resolved(kernel, handle, assignment)
        for assignment in assignments
    ]
    missing = tuple(
        child
        for resolved in resolveds
        for child in resolved.children
        if child not in sets
    )
    if missing:
        return None, missing
    policy = folder.program[harness._code(kernel, handle)]
    name = harness._name(kernel, handle)
    if metrics.early_ok and not keys and policy in algebra.INJECTIVE:
        # Sound precheck: with a SINGLE family, an operation jointly injective
        # in its children turns any child/leaf multiplicity into node
        # multiplicity — no local-family collision is possible because there
        # is no local family choice. (Local families must always be evaluated
        # and deduplicated: two arms CAN collide on equal children.)
        resolved = resolveds[0]
        child_multi = any(len(sets[child]) > 1 for child in resolved.children)
        leaf_multi = any(len(leaf_options[id(leaf)]) > 1 for leaf in resolved.leaves)
        if child_multi or leaf_multi:
            return None, ()
    meanings: list[Meaning] = []
    for resolved in resolveds:
        combos: list[tuple[Meaning, ...]] = [()]
        ints = iter(resolved.children)
        width = len(resolved.children) + len(resolved.leaves)
        for index in range(width):
            if index in resolved.slots:
                leaf = resolved.leaves[resolved.slots.index(index)]
                options = leaf_options[id(leaf)]
            else:
                options = sets[next(ints)]
            combos = [prefix + (option,) for prefix in combos for option in options]
        for kids in combos:
            metrics.ops += 1
            meanings.append(algebra.apply_policy(policy, name, kids))
    return algebra.dedup(meanings), ()


class ChartCycle(UnsupportedConstructError):
    """A back edge was found: the chart is cyclic and the walk must switch
    to the zero-width-SCC meaning mechanism."""


def _exact_root_set(
    run: harness.OuterRun,
    root: int,
    policies: dict[str, str],
    metrics: Metrics,
    root_path: dict[int, bool] | None,
) -> MeaningSet | None:
    """The exact meaning set at ``root`` — packed families AND leaf options.

    With ``root_path`` supplied, a node whose exact local set exceeds one
    meaning under an injective family path to an accepting root refuses
    immediately (returns ``None``) without enumerating anything above it.

    :raises ChartCycle: When a missing child is already in progress — a unit
        cycle. The caller switches to the SCC mechanism.
    """
    folder = algebra.SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    leaf_options = _leaf_option_table(run)
    sets: dict[int, MeaningSet] = {}
    in_progress: set[int] = set()
    live = 0
    stack: list[int] = [root]
    while stack:
        handle = stack[-1]
        if handle in sets:
            in_progress.discard(handle)
            stack.pop()
            continue
        in_progress.add(handle)
        metrics.early_ok = root_path is not None and root_path.get(handle, False)
        node_set, missing = _node_meanings(
            run.kernel, handle, folder, sets, leaf_options, metrics
        )
        if node_set is None and not missing:
            return None
        if node_set is None:
            for child in missing:
                if child in in_progress:
                    raise ChartCycle(
                        "interaction: cyclic chart — one-lap unroll required"
                    )
            stack.extend(missing)
            continue
        sets[handle] = node_set
        in_progress.discard(handle)
        live += len(node_set)
        metrics.note(live)
        metrics.retained += len(node_set)
        if root_path is not None and len(node_set) > 1 and root_path.get(handle, False):
            return None
        stack.pop()
    return sets[root]


def _cyclic(run: harness.OuterRun, policies: dict[str, str]) -> algebra.Outcome:
    """Hand a cyclic chart to the exact terminating component mechanism.

    The rejected fallback enumerated ``2^k`` global assignments through
    `FastTree` and answered over one lap; `cyclic_meaning` classifies each
    zero-width component instead and is exact, terminating, and linear in
    chart nodes.
    """
    return algebra.exact_meanings(
        run.kernel, run.root, policies, run.occurrences, run.seeds, algebra.Metrics()
    )


def value_sets(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """EXACT: per-node meaning sets with semantic dedup at every parent.

    Invariant enforced: after each completion, the node's stored set equals
    the exact set of distinct meanings derivable at that node — the union
    over the node's OWN packed arm-choice families and its delegated-leaf
    option sets, mapped through the node's operation and deduplicated. The
    root refuses ⟺ its set holds more than one meaning.
    """
    metrics = Metrics()
    roots = algebra.accepting_roots(run.kernel, run.root)
    union: list[Meaning] = []
    try:
        for root in roots:
            root_set = _exact_root_set(run, root, policies, metrics, None)
            assert root_set is not None
            union.extend(root_set)
    except ChartCycle:
        outcome = _cyclic(run, policies)
        return Verdict(outcome.differs, outcome.ops, outcome.retained, outcome.max_live)
    deduped = algebra.dedup(union)
    return Verdict(len(deduped) > 1, metrics.ops, metrics.retained, metrics.max_live)


def certificate(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """HYBRID: path-certified early refusal plus exact sets elsewhere.

    Certificate rule: a node may refuse the moment its exact local set holds
    two meanings when at least one complete family path carries that child
    through an injective slot to an accepting root. Fixing the families on
    that path and varying only the child's derivation constructs two distinct
    root meanings. Other parent paths may drop the child without invalidating
    the witness. Anywhere that certificate fails, exact deduplicated sets
    continue to the root.
    """
    metrics = Metrics()
    roots = algebra.accepting_roots(run.kernel, run.root)
    union: list[Meaning] = []
    try:
        root_path = _path_certificate(run, policies)
        for root in roots:
            root_set = _exact_root_set(run, root, policies, metrics, root_path)
            if root_set is None:
                return Verdict(True, metrics.ops, metrics.retained, metrics.max_live)
            union.extend(root_set)
    except ChartCycle:
        outcome = algebra.exact_meanings(
            run.kernel,
            run.root,
            policies,
            run.occurrences,
            run.seeds,
            algebra.Metrics(),
            early_exit=True,
        )
        return Verdict(outcome.differs, outcome.ops, outcome.retained, outcome.max_live)
    deduped = algebra.dedup(union)
    return Verdict(len(deduped) > 1, metrics.ops, metrics.retained, metrics.max_live)


def _path_certificate(
    run: harness.OuterRun, policies: dict[str, str]
) -> dict[int, bool]:
    """Nodes with an injective per-slot path to any accepting root.

    Every local family is inspected. A child is marked when at least one
    selected family places it in an ``ident`` or ``grow`` slot of an already
    marked parent. This is an existence proof over real family-aware edges,
    not a meet over unrelated parents and not a default-tree approximation.
    """
    kernel = run.kernel
    folder = algebra.SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    roots = algebra.accepting_roots(kernel, run.root)
    marked = {root: True for root in roots}
    visited: set[int] = set()
    pending = list(roots)
    while pending:
        handle = pending.pop()
        if handle in visited:
            continue
        visited.add(handle)
        keys = algebra.local_choice_keys(kernel, handle)
        policy = folder.program[harness._code(kernel, handle)]
        for assignment in algebra.assignments(kernel, list(keys)):
            resolved = algebra.selected_resolved(kernel, handle, assignment)
            for slot, child in zip(
                algebra.child_slots(resolved), resolved.children, strict=True
            ):
                if algebra.slot_class(policy, slot) in (algebra.IDENT, algebra.GROW):
                    marked[child] = True
                    pending.append(child)
    return marked


def cartesian_count(run: harness.OuterRun) -> int:
    """The rejected unconditional upper bound: root combinations, no dedup."""
    total = 1
    for seed in run.seeds.values():
        total *= 1 + len(seed.alternates)
    return total


class Witness(NamedTuple):
    """One interaction scenario and the exact expected verdict."""

    name: str
    outer: str
    island: str
    text: str
    policies: dict[str, str]
    island_policies: dict[str, str]
    exact_differs: bool
    one_flip_differs: bool
    nested: str = ""
    nested_rule: str = ""


WITNESSES = (
    Witness(
        "independent-injective",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {},
        {},
        True,
        True,
    ),
    Witness(
        "interacting-validation",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {"root": "atmost1"},
        {},
        True,
        False,
    ),
    Witness(
        "interacting-conditional",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {"root": "cond"},
        {},
        True,
        True,
    ),
    Witness(
        "dropped-parent",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {"root": "drop"},
        {},
        False,
        False,
    ),
    Witness(
        "equal-islands",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {},
        {"pair": "atom"},
        False,
        False,
    ),
    Witness(
        "nested-two-source-island",
        harness.OUTER_ONE,
        ISLAND_TWO_SOURCE,
        "[(xy)]",
        {},
        {"t": "atmost1"},
        True,
        False,
        harness.INNER,
        "inner",
    ),
    Witness(
        "separate-roots-dropping",
        OUTER_ROOTS,
        harness.ISLAND,
        "(xy)",
        {"left": "drop", "right": "drop", "root": "drop"},
        {},
        False,
        False,
    ),
    Witness(
        "keyed-duplicate-interaction",
        harness.OUTER_TWO,
        harness.ISLAND,
        "(xy)(xy)z",
        {"root": "dupkey"},
        {},
        True,
        False,
    ),
    Witness(
        "outer-arm-choice",
        OUTER_CHOICE,
        harness.ISLAND_PLAIN,
        "[(xy)]",
        {},
        {},
        True,
        False,
    ),
    Witness(
        "outer-arm-choice-dropped",
        OUTER_CHOICE,
        harness.ISLAND_PLAIN,
        "[(xy)]",
        {"m": "drop"},
        {},
        False,
        False,
    ),
)


def _set_outer_run(witness: Witness, metrics: Metrics) -> harness.OuterRun:
    """The delegated outer run whose seeds carry exact island meaning sets."""
    size = len(witness.text)
    outer = algebra.tables_for(witness.outer, size)
    island = algebra.tables_for(witness.island, size)
    inner: dict[int, Delegate] | None = None
    if witness.nested:
        nested = algebra.tables_for(witness.nested, size)
        inner = {
            harness._rule_id(island, witness.nested_rule): set_delegate(
                nested, witness.island_policies, metrics
            )
        }
    delegate = set_delegate(island, witness.island_policies, metrics, inner)
    rid = harness._rule_id(outer, "t")
    kernel = Kernel(outer, witness.text, True, delegates={rid: delegate}).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("interaction: outer parse failed")
    occurrences: dict[int, Meaning] = {}
    seeds: dict[int, harness.IslandSeed] = {}
    for leaf in kernel.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, harness.IslandSeed):
            raise UnsupportedConstructError("interaction: leaf carries no seed")
        occurrences[id(leaf)] = payload.baseline
        if payload.alternates:
            seeds[id(leaf)] = payload
    return harness.OuterRun(kernel, _outer_root(kernel), occurrences, seeds)


def _one_flip_outer_run(witness: Witness) -> harness.OuterRun:
    """The delegated outer run whose seeds carry only single-flip alternates."""
    size = len(witness.text)
    outer = algebra.tables_for(witness.outer, size)
    island = algebra.tables_for(witness.island, size)
    metrics = Metrics()
    inner: dict[int, Delegate] | None = None
    if witness.nested:
        nested = algebra.tables_for(witness.nested, size)
        inner = {
            harness._rule_id(island, witness.nested_rule): one_flip_delegate(
                nested, witness.island_policies, metrics
            )
        }
    delegate = one_flip_delegate(island, witness.island_policies, metrics, inner)
    rid = harness._rule_id(outer, "t")
    kernel = Kernel(outer, witness.text, True, delegates={rid: delegate}).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("interaction: one-flip outer parse failed")
    occurrences: dict[int, Meaning] = {}
    seeds: dict[int, harness.IslandSeed] = {}
    for leaf in kernel.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, harness.IslandSeed):
            raise UnsupportedConstructError("interaction: leaf carries no seed")
        occurrences[id(leaf)] = payload.baseline
        if payload.alternates:
            seeds[id(leaf)] = payload
    return harness.OuterRun(kernel, accept_handle(kernel), occurrences, seeds)


def _outer_root(kernel: Kernel) -> int:
    """The (single) outer accepting handle; separate roots handled below."""
    return accept_handle(kernel)


def prove_production_unsound() -> None:
    """Real kernel + real `another_meaning` + pure threshold build: unsound."""
    text = "xy"
    kern = Kernel(algebra.tables_for(TWO_POINT, len(text)), text, True).run()
    if accept_item(kern) < 0:
        raise UnsupportedConstructError("interaction: two-point parse failed")
    root = accept_handle(kern)
    points = [
        key
        for key in ambiguity_points(kern, root)
        if is_arm_choice(
            kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
        )
    ]
    assert len(points) == 2

    def build(tree: ParseTree) -> Meaning:
        return ("verdict", "ok" if _tree_flags(tree) <= 1 else "too-many")

    first = FastTree(kern, {}).build(root)
    assert isinstance(first, ParseTree)
    witness = another_meaning(kern, root, build, first)
    joint = FastTree(kern, {points[0]: 1, points[1]: 1}).build(root)
    assert isinstance(joint, ParseTree)
    assert witness is None
    assert build(joint) != build(first)
    print(
        "production-another_meaning",
        "UNSOUND for a pure threshold build: single flips equal, joint differs,"
        " and another_meaning returns None on a real two-point chart",
        sep="\t",
    )


def _tree_flags(tree: ParseTree) -> int:
    """Count flagged rules in a real ParseTree, iteratively."""
    count = 0
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop()
        if str(node.symbol) in ("a2", "b2"):
            count += 1
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
    return count


def _flip_marker(run: harness.OuterRun, flip: bool, exact: bool) -> str:
    """UNSOUND only where the seed lane CLAIMS the question (seeds exist);
    an outer-chart miss with no island seed is out of the accepted lane's
    scope — production `another_meaning` owns that shape today."""
    if flip == exact:
        return ""
    if run.seeds:
        return "  <-- UNSOUND"
    return "  <-- outer-chart scope (no seeds; production owns this shape)"


def _exercise(witness: Witness) -> None:
    """Run one witness through all four mechanisms and check every verdict."""
    metrics = Metrics()
    run = _set_outer_run(witness, metrics)
    flip = one_flip(_one_flip_outer_run(witness), witness.policies)
    tracemalloc.start()
    exact = value_sets(run, witness.policies)
    hybrid = certificate(run, witness.policies)
    allocated, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert exact.differs == witness.exact_differs, witness.name
    assert hybrid.differs == witness.exact_differs, witness.name
    assert flip.differs == witness.one_flip_differs, witness.name
    print(
        witness.name,
        f"exact_differs={exact.differs}",
        f"one_flip_differs={flip.differs}"
        + _flip_marker(run, flip.differs, exact.differs),
        f"seed_enum_ops={metrics.ops}",
        f"set_ops={exact.ops}",
        f"set_retained={exact.retained}",
        f"set_max_live={exact.max_live}",
        f"set+hybrid_alloc_bytes={allocated}",
        f"hybrid_ops={hybrid.ops}",
        f"hybrid_retained={hybrid.retained}",
        f"cartesian_root_combos={cartesian_count(run)}",
        sep="\t",
    )


def _tree_tuple_meaning(tree: ParseTree) -> Meaning:
    """The default injective tuple meaning of one real derivation (iterative)."""
    return algebra.tree_meaning(tree, {}, {})


CYCLIC_CASES = frozenset({"unit-cycle", "deep-cycle-pad20", "deep-cycle-pad2000"})
"""Differential cases whose chart carries a zero-width cycle."""

STACK_SAFETY_ONLY = frozenset({"deep-cycle-pad2000"})
"""Cyclic cases kept for DEPTH, whose verdict is oracled at a small twin.

The bounded-depth derivation oracle enumerates derivations, so it cannot be
run at 2,001 characters. Rather than fall back on production
`another_meaning` — which the round's own tasking forbids as an oracle — the
deep case is paired with `deep-cycle-pad20`: the SAME grammar and policies at
a size the oracle handles. The deep row then proves only that depth changes
neither the verdict nor the mechanism's stack safety.
"""


def _oracle_name(case: str) -> str:
    """Which independent oracle a differential case is held against."""
    if case in STACK_SAFETY_ONLY:
        return "verdict_oracled_at_pad20_twin"
    if case in CYCLIC_CASES:
        return "bounded_depth_oracle"
    return "enumeration_oracle"


def _oracle_verdict(case: str, run: harness.OuterRun, policies: dict[str, str]) -> bool:
    """The independent oracle's answer for one differential case.

    An ACYCLIC chart's every derivation is one global family assignment, so
    the `FastTree` enumeration is exhaustive there. A CYCLIC chart has
    infinitely many derivations and that enumeration is NOT exhaustive, so a
    cyclic case is held against the bounded-depth derivation oracle instead.
    The deep case borrows its twin's verdict; production `another_meaning` is
    used as an oracle nowhere.
    """
    if case in STACK_SAFETY_ONLY:
        return _twin_verdict(policies)
    if case in CYCLIC_CASES:
        report = algebra.bounded_depth_meanings(
            run.kernel, run.root, policies, run.occurrences, run.seeds, 5
        )
        return report.unbounded or len(report.meanings) > 1
    return (
        len(
            algebra.one_lap_meanings(
                run.kernel, run.root, policies, run.occurrences, run.seeds
            )
        )
        > 1
    )


def _twin_verdict(policies: dict[str, str]) -> bool:
    """The bounded-depth oracle's verdict on the pad-20 twin of DEEP_CYCLE."""
    text = "x" + "a" * 20
    kern = Kernel(algebra.tables_for(DEEP_CYCLE, len(text)), text, True).run()
    if accept_item(kern) < 0:
        raise UnsupportedConstructError("interaction: deep-cycle twin failed")
    twin = harness.OuterRun(kern, accept_handle(kern), {}, {})
    report = algebra.bounded_depth_meanings(
        kern, twin.root, policies, twin.occurrences, twin.seeds, 5
    )
    return report.unbounded or len(report.meanings) > 1


def prove_chart_differential() -> None:
    """value_sets against its ORACLE, plus a production cross-check.

    The oracle is `_oracle_verdict`: an exhaustive `FastTree` enumeration on an
    acyclic chart (where it really is exhaustive), and the bounded-depth
    derivation enumeration on a cyclic one. Production `another_meaning` is
    NOT an oracle here — it is reported and pinned as a CROSS-CHECK on today's
    shipped behaviour, on the default-policy cases only, so a change in
    shipped behaviour shows up as a failure rather than passing unnoticed. The
    truth source is the case's declared verdict and the oracle beside it.
    Cases include both sibling-accepting-root shapes, two same-meaning
    NEGATIVES under a dropping policy, and cyclic charts at two depths.
    """
    sibling_shared = 'root ::= p | q\np ::= t "z"\nq ::= t "z"\nt ::= "x"\n'
    sibling_two = 'root ::= u | v\nu ::= "x" "y"\nv ::= "x" "y"\n'
    unit_cycle = 'root ::= a\na ::= b | "x"\nb ::= a\n'
    shared_node = (
        'root ::= "[" m "]"\nm ::= p | q\np ::= t "z"\nq ::= t "z"\nt ::= "x"\n'
    )
    cases: tuple[tuple[str, str, str, dict[str, str], bool], ...] = (
        ("two-point", TWO_POINT, "xy", {}, True),
        ("simple-arm", AMBIG_SIMPLE, "xz", {}, True),
        (
            "outer-choice-shape",
            OUTER_CHOICE.replace(harness.ISLAND_PLAIN, 't ::= "xy"\n'),
            "[(xy)]",
            {},
            True,
        ),
        ("sibling-roots-shared-child", sibling_shared, "xz", {}, True),
        ("sibling-roots-two-prods", sibling_two, "xy", {}, True),
        ("NEGATIVE-simple-arm-dropped", AMBIG_SIMPLE, "xz", {"root": "drop"}, False),
        (
            "NEGATIVE-sibling-roots-dropped",
            sibling_shared,
            "xz",
            {"root": "drop", "p": "drop", "q": "drop"},
            False,
        ),
        ("unit-cycle", unit_cycle, "x", {}, True),
        ("deep-cycle-pad20", DEEP_CYCLE, "x" + "a" * 20, {}, True),
        ("deep-cycle-pad2000", DEEP_CYCLE, "x" + "a" * 2_000, {}, True),
        ("shared-node-kept", shared_node, "[xz]", {}, True),
        ("NEGATIVE-shared-node-dropped", shared_node, "[xz]", {"m": "drop"}, False),
    )
    for name, grammar, text, policies, expected in cases:
        kern = Kernel(algebra.tables_for(grammar, len(text)), text, True).run()
        if accept_item(kern) < 0:
            raise UnsupportedConstructError(f"interaction differential: {name}")
        run = harness.OuterRun(kern, accept_handle(kern), {}, {})
        exact = value_sets(run, policies)
        hybrid = certificate(run, policies)
        enum_oracle = _oracle_verdict(name, run, policies)
        assert exact.differs == hybrid.differs == enum_oracle == expected, name
        am_note = ""
        if not policies:
            first = FastTree(kern, {}).build(run.root)
            assert isinstance(first, ParseTree)
            production = (
                another_meaning(kern, run.root, _tree_tuple_meaning, first) is not None
            )
            # Cross-check, not oracle: it pins shipped behaviour on the
            # shapes where the one-flip walk is sound.
            assert exact.differs == production, name
            am_note = f"\tshipped_another_meaning={production}"
        print(
            "chart-differential",
            name,
            f"value_sets={exact.differs}",
            f"{_oracle_name(name)}={enum_oracle}" + am_note,
            "AGREE",
            sep="\t",
        )


def prove_cycle_replacement() -> None:
    """The cyclic lane: exact component ops beside the REJECTED 2^k lane."""
    for points in (1, 2, 3, 4):
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
        kern = Kernel(algebra.tables_for(grammar, len(text)), text, True).run()
        if accept_item(kern) < 0:
            raise UnsupportedConstructError("interaction: pricing parse failed")
        run = harness.OuterRun(kern, accept_handle(kern), {}, {})
        exact = value_sets(run, {})
        hybrid = certificate(run, {})
        assert exact.differs and hybrid.differs
        print(
            "cycle-replacement",
            f"arm_points={points}",
            f"exact_ops={exact.ops}",
            f"exact_retained={exact.retained}",
            f"certified_ops={hybrid.ops}",
            f"rejected_one_lap_assignments={2**points}",
            "the 2^k global-assignment fallback is replaced by component"
            " classification plus a per-node fixpoint",
            sep="\t",
        )


def main() -> None:
    """Prove the defect, then run every interaction witness."""
    prove_production_unsound()
    prove_chart_differential()
    prove_cycle_replacement()
    for witness in WITNESSES:
        _exercise(witness)
    print(
        "invariant",
        "node set == exact distinct meanings over the node's OWN packed"
        " families x leaf options, unioned across accepting items; refuse iff"
        " |root set| > 1; a CYCLIC chart is handed to `cyclic_meaning`, whose"
        " zero-width-component classification is exact and terminating and"
        " replaces the rejected 2^k one-lap fallback entirely; a node may"
        " refuse early when at least one real family path carries its differing"
        " slot injectively to an accepting root; unrelated dropping parents"
        " do not invalidate that constructive witness",
        sep="\t",
    )


if __name__ == "__main__":
    main()
