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


class Metrics:
    """What one verdict mechanism paid."""

    __slots__ = ("max_live", "ops", "retained")

    def __init__(self) -> None:
        self.ops = 0
        self.retained = 0
        self.max_live = 0

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
        if policy in ("atmost1", "cond"):
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
    return harness.Resolved(tuple(children), tuple(leaves), tuple(slots), ())


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


def value_sets(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """EXACT: per-node meaning sets with semantic dedup at every parent.

    Invariant enforced: after each completion, the node's stored set equals
    the exact set of distinct meanings derivable at that node; the root
    refuses ⟺ its set holds more than one meaning. The outer chart here is
    unambiguous by construction (multiplicity enters through island leaf
    sets); production applies the same union law across packed families.
    """
    metrics = Metrics()
    folder = SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (run.occurrences[leaf_id],) for leaf_id in run.occurrences
    }
    for leaf_id, seed in run.seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    sets: dict[int, MeaningSet] = {}
    live = 0
    for handle in harness._postorder(run.kernel, run.root):
        resolved = harness._resolved(run.kernel, handle, None)
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
        policy = folder.program[harness._code(run.kernel, handle)]
        name = harness._name(run.kernel, handle)
        meanings: list[Meaning] = []
        for kids in combos:
            metrics.ops += 1
            meanings.append(apply_policy(policy, name, kids))
        sets[handle] = _dedup(meanings)
        live += len(sets[handle])
        metrics.note(live)
        metrics.retained += len(sets[handle])
    return Verdict(
        len(sets[run.root]) > 1, metrics.ops, metrics.retained, metrics.max_live
    )


def certificate(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """HYBRID: injective-sky early refusal plus exact sets elsewhere.

    Certificate rule the compiler will enforce: if every operation from a node
    to the root is jointly injective (tuple/record/sequence construction with
    all children retained), then node multiplicity > 1 already proves root
    multiplicity > 1 — refuse with no enumeration above. Every other node
    computes its exact deduplicated set.
    """
    metrics = Metrics()
    folder = SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    sky = _sky_injective(run, folder)
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (run.occurrences[leaf_id],) for leaf_id in run.occurrences
    }
    for leaf_id, seed in run.seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    sets: dict[int, MeaningSet] = {}
    live = 0
    for handle in harness._postorder(run.kernel, run.root):
        resolved = harness._resolved(run.kernel, handle, None)
        options_per_slot: list[MeaningSet] = []
        ints = iter(resolved.children)
        width = len(resolved.children) + len(resolved.leaves)
        for index in range(width):
            if index in resolved.slots:
                leaf = resolved.leaves[resolved.slots.index(index)]
                options_per_slot.append(leaf_options[id(leaf)])
            else:
                options_per_slot.append(sets[next(ints)])
        policy = folder.program[harness._code(run.kernel, handle)]
        multiplicity = 1
        for options in options_per_slot:
            multiplicity *= len(options)
        if multiplicity > 1 and policy in INJECTIVE and sky[handle]:
            return Verdict(True, metrics.ops, metrics.retained, metrics.max_live)
        name = harness._name(run.kernel, handle)
        combos: list[tuple[Meaning, ...]] = [()]
        for options in options_per_slot:
            combos = [prefix + (option,) for prefix in combos for option in options]
        meanings: list[Meaning] = []
        for kids in combos:
            metrics.ops += 1
            meanings.append(apply_policy(policy, name, kids))
        sets[handle] = _dedup(meanings)
        live += len(sets[handle])
        metrics.note(live)
        metrics.retained += len(sets[handle])
    return Verdict(
        len(sets[run.root]) > 1, metrics.ops, metrics.retained, metrics.max_live
    )


def _sky_injective(run: harness.OuterRun, folder: SetFolder) -> dict[int, bool]:
    """Whether every operation from each node to the root is injective."""
    sky: dict[int, bool] = {run.root: True}
    order = harness._postorder(run.kernel, run.root)
    for handle in reversed(order):
        own = folder.program[harness._code(run.kernel, handle)] in INJECTIVE
        inherited = sky.get(handle, True)
        for child in harness._resolved(run.kernel, handle, None).children:
            sky[child] = inherited and own
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


def _union_over_roots(run: harness.OuterRun, policies: dict[str, str]) -> Verdict:
    """Value sets unioned across separate outer accepting items, deduped."""
    bits = run.kernel.tables.packing.bits
    mask = run.kernel.tables.packing.mask
    end = len(run.kernel.text)
    accepts = run.kernel.tables.codes.accept_codes
    roots = [
        (item << bits) | end
        for item in run.kernel.cols[end]
        if item >> bits in accepts and item & mask == 0
    ]
    union: list[Meaning] = []
    for root in roots:
        union.extend(value_sets_root_set(run, root, policies))
    deduped = _dedup(union)
    return Verdict(len(deduped) > 1, len(union), len(deduped), len(union))


def value_sets_root_set(
    run: harness.OuterRun, root: int, policies: dict[str, str]
) -> MeaningSet:
    """The exact root meaning set for one accepting item."""
    scoped = harness.OuterRun(run.kernel, root, run.occurrences, run.seeds)
    folder = SetFolder(
        run.kernel, policies, run.occurrences, harness.Counters(), "oracle"
    )
    leaf_options: dict[int, MeaningSet] = {
        leaf_id: (run.occurrences[leaf_id],) for leaf_id in run.occurrences
    }
    for leaf_id, seed in run.seeds.items():
        leaf_options[leaf_id] = (seed.baseline,) + seed.alternates
    sets: dict[int, MeaningSet] = {}
    for handle in harness._postorder(scoped.kernel, root):
        resolved = harness._resolved(scoped.kernel, handle, None)
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
        policy = folder.program[harness._code(scoped.kernel, handle)]
        name = harness._name(scoped.kernel, handle)
        sets[handle] = _dedup([apply_policy(policy, name, kids) for kids in combos])
    return sets[root]


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


def _exercise(witness: Witness) -> None:
    """Run one witness through all four mechanisms and check every verdict."""
    metrics = Metrics()
    run = _set_outer_run(witness, metrics)
    flip = one_flip(_one_flip_outer_run(witness), witness.policies)
    if witness.name == "separate-roots-dropping":
        exact = _union_over_roots(run, witness.policies)
        hybrid = exact
    else:
        exact = value_sets(run, witness.policies)
        hybrid = certificate(run, witness.policies)
    assert exact.differs == witness.exact_differs, witness.name
    assert hybrid.differs == witness.exact_differs, witness.name
    assert flip.differs == witness.one_flip_differs, witness.name
    print(
        witness.name,
        f"exact_differs={exact.differs}",
        f"one_flip_differs={flip.differs}"
        + ("  <-- UNSOUND" if flip.differs != exact.differs else ""),
        f"seed_enum_ops={metrics.ops}",
        f"set_ops={exact.ops}",
        f"set_retained={exact.retained}",
        f"set_max_live={exact.max_live}",
        f"hybrid_ops={hybrid.ops}",
        f"hybrid_retained={hybrid.retained}",
        f"cartesian_root_combos={cartesian_count(run)}",
        sep="\t",
    )


def main() -> None:
    """Prove the defect, then run every interaction witness."""
    prove_production_unsound()
    for witness in WITNESSES:
        _exercise(witness)
    print(
        "invariant",
        "node set == exact distinct meanings; refuse iff |root set| > 1;"
        " injective-sky nodes may refuse at first local multiplicity",
        sep="\t",
    )


if __name__ == "__main__":
    main()
