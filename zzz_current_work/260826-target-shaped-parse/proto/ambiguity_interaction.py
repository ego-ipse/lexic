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

Unconditional Cartesian enumeration is priced as the rejected upper bound.
"""

from __future__ import annotations

import tracemalloc
from typing import NamedTuple

import island_alternate_seed as harness
from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
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
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain, tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, is_arm_choice
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.pda.runtime.islands import island_run

type Meaning = harness.Meaning
type MeaningSet = tuple[Meaning, ...]

# Flag content that never appears in a DEFAULT-family baseline (the
# engine's first families spell onetwo/m1/b), so a threshold over these
# markers reads 0 on every baseline and counts alternates only.
MARKERS = frozenset({"two", "m2", "a"})
INJECTIVE = frozenset({"", "swap", "wrap"})

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
    """One meaning operation — the planned algebra's shapes, including the
    non-injective validation/conditional forms."""
    if policy == "atom":
        raise UnsupportedConstructError(
            "interaction: the set lanes do not carry span text; span policies"
            " are island-internal in these witnesses"
        )
    if policy == "drop":
        return (name,)
    if policy == "swap":
        return (name,) + tuple(reversed(kids))
    if policy == "wrap":
        return (name, ("layer",) + kids)
    if policy == "atmost1":
        count = sum(_flagged(kid) for kid in kids)
        return ("verdict", "ok" if count <= 1 else "too-many")
    if policy == "cond":
        left = _flagged(kids[0]) > 0
        right = _flagged(kids[1]) > 0 if len(kids) > 1 else False
        return ("cond", "same" if left == right else "mixed")
    if policy == "dupkey":
        keys = ["K" if _flagged(kid) else f"k{index}" for index, kid in enumerate(kids)]
        duplicate = len(keys) != len(set(keys))
        return ("verdict", "dup" if duplicate else "ok")
    return (name,) + kids


class SetFolder(harness.Folder):
    """The harness meaning folder extended with the interaction operations."""

    def _assemble(
        self,
        handle: int,
        resolved: harness.Resolved,
        memo: harness.Overlay,
        leaf_override: dict[int, Meaning],
    ) -> Meaning:
        """Apply the extended algebra; fall back to the harness for spans."""
        policy = self.program[harness._code(self.kernel, handle)]
        if policy in ("atmost1", "cond", "dupkey"):
            self._count()
            kids = self._kids(resolved, memo, leaf_override)
            return apply_policy(policy, harness._name(self.kernel, handle), kids)
        return super()._assemble(handle, resolved, memo, leaf_override)


def _dedup(meanings: list[Meaning]) -> MeaningSet:
    """Semantic deduplication, first-seen order (meanings are value tuples)."""
    seen: set[Meaning] = set()
    out: list[Meaning] = []
    for meaning in meanings:
        if meaning not in seen:
            seen.add(meaning)
            out.append(meaning)
    return tuple(out)


def _tables(grammar: str, size: int) -> ParserTables:
    """Real compiled tables for one witness grammar."""
    return compile_tables(
        normalize(canonical_grammar(grammar, GBNF_FLAVOUR)), tier_for(size)
    )


def _selected_resolved(
    kernel: Kernel, handle: int, selected: dict[int, int]
) -> harness.Resolved:
    """`harness._resolved` under a MULTI-key family selection."""
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
        raise UnsupportedConstructError("interaction: handle did not resolve")
    children: list[int] = []
    leaves = []
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


def _local_choice_keys(kernel: Kernel, handle: int) -> tuple[int, ...]:
    """Every arm-choice packed key owned by THIS completion's chains.

    Family indices and even the key population are only stable at a census
    fixpoint under lazy Leo expansion, so the discovery iterates assignments
    until no new key appears.
    """
    bits = kernel.tables.packing.bits
    known: tuple[int, ...] = ()
    for _round in range(8):
        found: set[int] = set(known)
        for assignment in _assignments(kernel, list(known)):
            for key in _selected_resolved(kernel, handle, assignment).keys:
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
    raise UnsupportedConstructError("interaction: local key census did not settle")


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
    for _round in range(8):
        points = [
            key
            for key in _all_arm_points(kern, roots)
            if is_arm_choice(
                kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
            )
        ]
        meanings = []
        for accepting in roots:
            for assignment in _assignments(kern, points):
                for overrides in _leaf_combos(leaf_sets):
                    metrics.ops += 1
                    meanings.append(
                        _fold_selected(kern, accepting, policies, assignment, overrides)
                    )
                    metrics.note(len(meanings))
        after = [(key, len(kern.st.links[key])) for key in points]
        if after == census:
            break
        census = after
    else:
        raise UnsupportedConstructError("interaction: family census did not settle")
    deduped = _dedup(meanings)
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


def _assignments(kern: Kernel, points: list[int]) -> list[dict[int, int]]:
    """Every family assignment over the island's own arm-choice keys."""
    combos: list[dict[int, int]] = [{}]
    for key in points:
        families = len(kern.st.links[key])
        combos = [
            {**combo, key: family} for combo in combos for family in range(families)
        ]
    return combos


def _leaf_combos(leaf_sets: dict[int, MeaningSet]) -> list[dict[int, Meaning]]:
    """Every override combination over nested delegated leaves."""
    combos: list[dict[int, Meaning]] = [{}]
    for leaf_id, options in leaf_sets.items():
        combos = [{**combo, leaf_id: option} for combo in combos for option in options]
    return combos


def _fold_selected(
    kern: Kernel,
    root: int,
    policies: dict[str, str],
    selected: dict[int, int],
    overrides: dict[int, Meaning],
) -> Meaning:
    """Fold one fully selected island derivation to its meaning."""
    occurrences = {leaf_id: override for leaf_id, override in overrides.items()}
    folder = SetFolder(kern, policies, occurrences, harness.Counters(), "oracle")
    memo: dict[int, Meaning] = {}
    stack: list[tuple[int, bool]] = [(root, False)]
    while stack:
        handle, expanded = stack.pop()
        if handle in memo:
            continue
        resolved = _selected_resolved(kern, handle, selected)
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
        for meaning in _dedup(candidates)
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
    folder = SetFolder(run.kernel, policies, run.occurrences, counters, "baseline")
    memo = harness.Overlay({})
    baseline = folder.apply(run.root, memo, set(), None, {})
    base_layer = dict(memo.changed)
    if not run.seeds:
        return Verdict(False, counters.baseline_folds, 1, len(base_layer))
    graph = harness._graph(run.kernel, run.root)
    replay = SetFolder(run.kernel, policies, run.occurrences, counters, "replay")
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
    folder: SetFolder,
    sets: dict[int, MeaningSet],
    leaf_options: dict[int, MeaningSet],
    metrics: Metrics,
) -> tuple[MeaningSet, tuple[int, ...]] | tuple[None, tuple[int, ...]]:
    """One node's exact set: union over its OWN packed families × child sets.

    Returns ``(None, missing_children)`` when a child set is not yet
    computed (the caller re-pushes), else ``(set, ())``.
    """
    keys = _local_choice_keys(kernel, handle)
    assignments = _assignments(kernel, list(keys))
    resolveds = [
        _selected_resolved(kernel, handle, assignment) for assignment in assignments
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
    if metrics.early_ok and not keys and policy in INJECTIVE:
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
            meanings.append(apply_policy(policy, name, kids))
    return _dedup(meanings), ()


class ChartCycle(UnsupportedConstructError):
    """A back edge was found: the chart is cyclic and the walk must switch
    to production's consume-on-first-visit (one-lap unroll) discipline."""


def _exact_root_set(
    run: harness.OuterRun,
    root: int,
    policies: dict[str, str],
    metrics: Metrics,
    sky: dict[int, bool] | None,
) -> MeaningSet | None:
    """The exact meaning set at ``root`` — packed families AND leaf options.

    With ``sky`` supplied, a node whose exact local set exceeds one meaning
    under a choice-free all-injective sky refuses immediately (returns
    ``None``) without enumerating anything above it.

    :raises ChartCycle: When a missing child is already in progress — a unit
        cycle. The caller falls back to the one-lap tree enumeration.
    """
    folder = SetFolder(
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
        metrics.early_ok = sky is not None and sky.get(handle, False)
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
        if sky is not None and len(node_set) > 1 and sky.get(handle, False):
            return None
        stack.pop()
    return sets[root]


def _accepting_roots(run: harness.OuterRun) -> list[int]:
    """EVERY accepting item at the document end — a many-production start
    symbol has no parent waiter, so its alternatives are sibling accepting
    ITEMS, invisible to the link table (production's `_sibling_roots`)."""
    bits = run.kernel.tables.packing.bits
    mask = run.kernel.tables.packing.mask
    end = len(run.kernel.text)
    accepts = run.kernel.tables.codes.accept_codes
    roots = [
        (item << bits) | end
        for item in run.kernel.cols[end]
        if item >> bits in accepts and item & mask == 0
    ]
    if run.root not in roots:
        roots.insert(0, run.root)
    return roots


def _all_points_everywhere(run: harness.OuterRun, roots: list[int]) -> list[int]:
    """Every arm-choice key reachable from any accepting root."""
    bits = run.kernel.tables.packing.bits
    found: list[int] = []
    seen: set[int] = set()
    for root in roots:
        for key in ambiguity_points(run.kernel, root):
            bucket = run.kernel.st.links.get(key)
            if key in seen or bucket is None:
                continue
            seen.add(key)
            if is_arm_choice(bucket, bits, run.kernel.tables.code_choice):
                found.append(key)
    return sorted(found)


def _one_lap_meanings(
    run: harness.OuterRun,
    roots: list[int],
    policies: dict[str, str],
    metrics: Metrics,
) -> MeaningSet:
    """The cyclic-chart rule, adopted verbatim from production: build each
    derivation with `FastTree`, whose choices dict is CONSUMED at first
    visit, so a flipped point names the one-lap unroll and the enumeration
    terminates. Meanings are tree folds under the same policy algebra."""
    leaf_options = _leaf_option_table(run)
    meanings: list[Meaning] = []
    points = _all_points_everywhere(run, roots)
    assignments = _assignments(run.kernel, points)
    for root in roots:
        for assignment in assignments:
            tree = FastTree(run.kernel, dict(assignment)).build(root)
            if not isinstance(tree, ParseTree):
                continue
            for overrides in _leaf_combos(leaf_options):
                metrics.ops += 1
                meanings.append(_tree_policy_meaning(tree, policies, overrides))
                metrics.note(len(meanings))
    if not meanings:
        raise UnsupportedConstructError("interaction: no derivation built")
    deduped = _dedup(meanings)
    metrics.retained += len(deduped)
    return deduped


def _tree_policy_meaning(
    tree: ParseTree, policies: dict[str, str], overrides: dict[int, Meaning]
) -> Meaning:
    """Fold one real derivation under the policy algebra, substituting
    delegated leaves from the override table.

    ITERATIVE by explicit stack: derivation depth is ordinary under
    quantifier desugaring (the standing iterative-equality ruling), so a
    recursive fold would die on a 2,000-character cyclic-rule document.
    """
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


def value_sets(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """EXACT: per-node meaning sets with semantic dedup at every parent.

    Invariant enforced: after each completion, the node's stored set equals
    the exact set of distinct meanings derivable at that node — the union
    over the node's OWN packed arm-choice families and its delegated-leaf
    option sets, mapped through the node's operation and deduplicated. The
    root refuses ⟺ its set holds more than one meaning.
    """
    metrics = Metrics()
    roots = _accepting_roots(run)
    union: list[Meaning] = []
    try:
        for root in roots:
            root_set = _exact_root_set(run, root, policies, metrics, None)
            assert root_set is not None
            union.extend(root_set)
    except ChartCycle:
        union = list(_one_lap_meanings(run, roots, policies, metrics))
    deduped = _dedup(union)
    return Verdict(len(deduped) > 1, metrics.ops, metrics.retained, metrics.max_live)


def certificate(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """HYBRID: sky-certified early refusal plus exact sets elsewhere.

    Certificate rule: a node may refuse the moment its exact local set holds
    two meanings IF every ancestor completion (across ALL parent edges, over
    ALL family assignments) applies a jointly injective operation and owns no
    arm-choice key. Choice-free injective ancestors both preserve the node's
    multiplicity and guarantee the node appears in every derivation, so root
    multiplicity follows. Anywhere that certificate fails, exact deduplicated
    sets continue to the root.
    """
    metrics = Metrics()
    roots = _accepting_roots(run)
    union: list[Meaning] = []
    try:
        # With sibling accepting roots the certificate is skipped entirely:
        # sound (it only ever forgoes an early exit, never causes one), and
        # stated in the report — multi-root charts pay full set propagation.
        sky = _sky_certificate(run, policies) if len(roots) == 1 else None
        for root in roots:
            root_set = _exact_root_set(run, root, policies, metrics, sky)
            if root_set is None:
                return Verdict(True, metrics.ops, metrics.retained, metrics.max_live)
            union.extend(root_set)
    except ChartCycle:
        union = list(_one_lap_meanings(run, roots, policies, metrics))
    deduped = _dedup(union)
    return Verdict(len(deduped) > 1, metrics.ops, metrics.retained, metrics.max_live)


def _sky_certificate(
    run: harness.OuterRun, policies: dict[str, str]
) -> dict[int, bool]:
    """The conservative sky predicate over the FULL family-aware DAG.

    ``sky[n]`` holds only when every parent edge of ``n`` (discovered under
    every family assignment, not just the default derivation) leads to a
    parent with a jointly injective operation, no local arm-choice key, and a
    true sky of its own — a meet over all parents on a real topological
    order, never a last-write over one tree.
    """
    kernel = run.kernel
    folder = SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    parents: dict[int, set[int]] = {run.root: set()}
    injective_op: dict[int, bool] = {}
    choice_free: dict[int, bool] = {}
    pending = [run.root]
    while pending:
        handle = pending.pop()
        if handle in injective_op:
            continue
        keys = _local_choice_keys(kernel, handle)
        choice_free[handle] = not keys
        policy = folder.program[harness._code(kernel, handle)]
        injective_op[handle] = policy in INJECTIVE
        for assignment in _assignments(kernel, list(keys)):
            for child in _selected_resolved(kernel, handle, assignment).children:
                parents.setdefault(child, set()).add(handle)
                pending.append(child)
    sky: dict[int, bool] = {}
    queue = [run.root] + list(injective_op)
    stalled = 0
    while queue and stalled <= len(queue):
        node = queue.pop(0)
        if node in sky:
            continue
        node_parents = parents.get(node, set())
        if not all(parent in sky for parent in node_parents):
            # No topological order exists on a cyclic parent graph; a node
            # whose sky never settles simply carries NO certificate (readers
            # default missing entries to False), which is the sound answer.
            queue.append(node)
            stalled += 1
            continue
        stalled = 0
        sky[node] = all(
            sky[parent] and injective_op[parent] and choice_free[parent]
            for parent in node_parents
        )
    return sky


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
    outer = _tables(witness.outer, size)
    island = _tables(witness.island, size)
    inner: dict[int, Delegate] | None = None
    if witness.nested:
        nested = _tables(witness.nested, size)
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
    outer = _tables(witness.outer, size)
    island = _tables(witness.island, size)
    metrics = Metrics()
    inner: dict[int, Delegate] | None = None
    if witness.nested:
        nested = _tables(witness.nested, size)
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
    kern = Kernel(_tables(TWO_POINT, len(text)), text, True).run()
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
    return _tree_policy_meaning(tree, {}, {})


def prove_chart_differential() -> None:
    """value_sets vs TWO oracles on island-free ambiguous charts.

    Oracle 1 (always): an independent exhaustive enumeration — every family
    assignment through `FastTree` (whose consumed choices dict is exactly
    production's one-lap cycle rule) across every accepting item, folded and
    deduplicated. Oracle 2 (injective default policies only, where the
    production one-flip IS sound): `another_meaning`. Cases include both
    sibling-accepting-root shapes, two same-meaning NEGATIVES under a
    dropping policy, and a unit cycle.
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
        ("deep-cycle-pad2000", DEEP_CYCLE, "x" + "a" * 2_000, {}, True),
        ("shared-node-kept", shared_node, "[xz]", {}, True),
        ("NEGATIVE-shared-node-dropped", shared_node, "[xz]", {"m": "drop"}, False),
    )
    for name, grammar, text, policies, expected in cases:
        kern = Kernel(_tables(grammar, len(text)), text, True).run()
        if accept_item(kern) < 0:
            raise UnsupportedConstructError(f"interaction differential: {name}")
        run = harness.OuterRun(kern, accept_handle(kern), {}, {})
        exact = value_sets(run, policies)
        hybrid = certificate(run, policies)
        enum_oracle = (
            len(_one_lap_meanings(run, _accepting_roots(run), policies, Metrics())) > 1
        )
        assert exact.differs == hybrid.differs == enum_oracle == expected, name
        am_note = ""
        if not policies:
            first = FastTree(kern, {}).build(run.root)
            assert isinstance(first, ParseTree)
            production = (
                another_meaning(kern, run.root, _tree_tuple_meaning, first) is not None
            )
            assert exact.differs == production, name
            am_note = f"\tanother_meaning={production}"
        print(
            "chart-differential",
            name,
            f"value_sets={exact.differs}",
            f"enumeration_oracle={enum_oracle}" + am_note,
            "AGREE",
            sep="\t",
        )


def prove_cycle_pricing() -> None:
    """The cycle fallback IS the rejected general architecture, accepted
    only as the bounded cycle path — price it: 2^k tree builds over k
    reachable arm points."""
    for points in (1, 2, 3):
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
        kern = Kernel(_tables(grammar, len(text)), text, True).run()
        if accept_item(kern) < 0:
            raise UnsupportedConstructError("interaction: pricing parse failed")
        run = harness.OuterRun(kern, accept_handle(kern), {}, {})
        verdict = value_sets(run, {})
        print(
            "cycle-fallback-pricing",
            f"arm_points={points}",
            f"one_lap_ops={verdict.ops}",
            f"retained={verdict.retained}",
            "growth is 2^k in reachable arm points — the rejected general"
            " architecture, accepted only as the bounded cycle fallback",
            sep="\t",
        )


def main() -> None:
    """Prove the defect, then run every interaction witness."""
    prove_production_unsound()
    prove_chart_differential()
    prove_cycle_pricing()
    for witness in WITNESSES:
        _exercise(witness)
    print(
        "invariant",
        "node set == exact distinct meanings over the node's OWN packed"
        " families x leaf options, unioned across accepting items; refuse iff"
        " |root set| > 1; on a CYCLIC chart the relation is one-lap-bounded"
        " (both here and in production) and computed by the consumed-choices"
        " enumeration, which is interaction-exact and therefore strictly"
        " broader than production's single flips; a node may refuse early"
        " only under a choice-free all-injective sky (meet over ALL"
        " family-aware parent edges; skipped under sibling accepting roots)",
        sep="\t",
    )


if __name__ == "__main__":
    main()
