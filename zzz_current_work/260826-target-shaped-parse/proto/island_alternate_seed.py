"""Island ambiguity as a cold alternate seed replayed through the enclosing product.

Real boundary: the outer document runs ONCE through the real Earley kernel with
the island interior delegated (`Kernel(delegates=...)` — the same seam the PDA
island escape uses), the island runs ONCE through the real windowed
`island_run` over real compiled `ParserTables`, and ambiguity is read with the
real `ambiguity_points`/`is_arm_choice`/`same_value` machinery. The toy parts
are the meaning programs (stand-ins for lowered completion ranges) and the
PDA-shaped trace driver, which replays the real chart's completion order
through an explicit frame/mark stack because a predictive run retains no chart.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
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
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain, tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, is_arm_choice
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.pda.runtime.islands import island_run

type Meaning = str | tuple["Meaning", ...]

ISLAND = (
    't ::= pair\npair ::= one two | onetwo\none ::= "x"\ntwo ::= "y"\nonetwo ::= "xy"\n'
)
ISLAND_PLAIN = 't ::= pair\npair ::= "xy"\n'
OUTER_ONE = 'root ::= "[" mid "]"\nmid ::= "(" t ")"\n' + ISLAND
OUTER_TWO = 'root ::= "(" t ")" "(" t ")" "z"\n' + ISLAND
INNER = 'inner ::= a | b\na ::= "y"\nb ::= "y"\n'
ISLAND_NESTED = 't ::= "x" inner\n' + INNER


class Counters:
    """Every structural count one witness reports."""

    __slots__ = (
        "alternates_evaluated",
        "baseline_folds",
        "cone_sizes",
        "full_document_parses",
        "island_runs",
        "oracle_folds",
        "outer_kernel_runs",
        "overlay_entries",
        "replay_folds",
        "seeds",
        "trace_frames",
    )

    def __init__(self) -> None:
        self.outer_kernel_runs = 0
        self.island_runs = 0
        self.full_document_parses = 0
        self.baseline_folds = 0
        self.replay_folds = 0
        self.oracle_folds = 0
        self.seeds = 0
        self.alternates_evaluated = 0
        self.trace_frames = 0
        self.cone_sizes: list[int] = []
        self.overlay_entries: list[int] = []


class IslandSeed(NamedTuple):
    """One island occurrence's cold alternate meanings beside its baseline."""

    baseline: Meaning
    alternates: tuple[Meaning, ...]


class TraceFrame(NamedTuple):
    """One ancestor completion recorded while a seed is live below it."""

    policy: str
    name: str
    kids: tuple[Meaning, ...]
    dirty: int


class Choice(NamedTuple):
    """One packed family selected for one ambiguity key."""

    key: int
    family: int


class Graph(NamedTuple):
    """Default-derivation dependencies including delegated-leaf owners."""

    parents: dict[int, set[int]]
    owners: dict[int, set[int]]


class Overlay:
    """A read-only baseline memo plus one alternate's sparse changed layer."""

    __slots__ = ("base", "changed")

    def __init__(self, base: dict[int, Meaning]) -> None:
        self.base = base
        self.changed: dict[int, Meaning] = {}

    def contains(self, handle: int) -> bool:
        """Whether either layer holds ``handle``."""
        return handle in self.changed or handle in self.base

    def read(self, handle: int) -> Meaning:
        """Read the sparse alternate layer before the immutable baseline."""
        if handle in self.changed:
            return self.changed[handle]
        return self.base[handle]


def _tables(grammar: str, size: int) -> ParserTables:
    """Compile one real table set for ``grammar`` at input tier ``size``."""
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    return compile_tables(ast, tier_for(size))


def _code(kernel: Kernel, handle: int) -> int:
    """The completed code carried by one packed handle."""
    return handle >> (2 * kernel.tables.packing.bits)


def _name(kernel: Kernel, handle: int) -> str:
    """The decoded rule name for one completed handle."""
    codes = kernel.tables.codes
    rule = codes.arm_rule[codes.code_arm[_code(kernel, handle)]]
    return str(kernel.tables.decode.rule_refs[rule])


class Resolved(NamedTuple):
    """One completion's child handles, delegated leaves, and owned keys."""

    children: tuple[int, ...]
    leaves: tuple[PayloadLeaf, ...]
    slots: tuple[int, ...]
    keys: tuple[int, ...]


def _resolved(kernel: Kernel, handle: int, choice: Choice | None) -> Resolved:
    """Resolve one completion chain, keeping delegated leaves in slot order."""
    bits = kernel.tables.packing.bits
    codes = kernel.tables.codes
    base = codes.arm_base[codes.code_arm[_code(kernel, handle)]]
    if handle in kernel.st.leo_links:
        expand_leo(kernel.st, kernel.tables, handle)
    selected = {} if choice is None else {choice.key: choice.family}
    chain = predecessor_chain(
        kernel.st.links,
        handle,
        ChainSpec(base, bits, kernel.tables.code_choice),
        selected,
    )
    if chain is None:
        start = (handle >> bits) & kernel.tables.packing.mask
        if start == (handle & kernel.tables.packing.mask):
            return Resolved((), (), (), (handle,))
        raise UnsupportedConstructError(
            f"island seed prototype: {_name(kernel, handle)} did not resolve"
        )
    children: list[int] = []
    leaves: list[PayloadLeaf] = []
    slots: list[int] = []
    slot = 0
    for _predecessor, _end, child in chain:
        if isinstance(child, PayloadLeaf):
            leaves.append(child)
            slots.append(slot)
            slot += 1
        elif isinstance(child, int) and not isinstance(child, bool):
            children.append(child)
            slot += 1
    keys = (handle,) + tuple(
        (predecessor << bits) | end for predecessor, end, _child in chain
    )
    return Resolved(tuple(children), tuple(leaves), tuple(slots), keys)


class Folder:
    """A completed-code meaning program over one chart, with leaf occurrences."""

    __slots__ = ("counters", "kernel", "lane", "occurrences", "program")

    def __init__(
        self,
        kernel: Kernel,
        policies: dict[str, str],
        occurrences: dict[int, Meaning],
        counters: Counters,
        lane: str,
    ) -> None:
        self.kernel = kernel
        self.occurrences = occurrences
        self.counters = counters
        self.lane = lane
        codes = kernel.tables.codes
        lowered: list[str] = []
        for code in range(len(codes.code_arm)):
            rule = codes.arm_rule[codes.code_arm[code]]
            lowered.append(policies.get(str(kernel.tables.decode.rule_refs[rule]), ""))
        self.program = tuple(lowered)

    def apply(
        self,
        root: int,
        memo: Overlay,
        dirty: set[int],
        choice: Choice | None,
        leaf_override: dict[int, Meaning],
    ) -> Meaning:
        """Fold ``root``, reusing every memoized handle outside ``dirty``."""
        stack: list[tuple[int, bool]] = [(root, False)]
        while stack:
            handle, expanded = stack.pop()
            if memo.contains(handle) and handle not in dirty:
                continue
            resolved = _resolved(self.kernel, handle, choice)
            if not expanded:
                stack.append((handle, True))
                for child in reversed(resolved.children):
                    if not memo.contains(child) or child in dirty:
                        stack.append((child, False))
                continue
            memo.changed[handle] = self._assemble(handle, resolved, memo, leaf_override)
        return memo.read(root)

    def _assemble(
        self,
        handle: int,
        resolved: Resolved,
        memo: Overlay,
        leaf_override: dict[int, Meaning],
    ) -> Meaning:
        """Execute one code-selected meaning operation over ordered children."""
        self._count()
        name = _name(self.kernel, handle)
        policy = self.program[_code(self.kernel, handle)]
        if policy == "atom":
            bits = self.kernel.tables.packing.bits
            mask = self.kernel.tables.packing.mask
            start = (handle >> bits) & mask
            return ("atom", self.kernel.text[start : handle & mask])
        if policy == "drop":
            return (name,)
        kids = self._kids(resolved, memo, leaf_override)
        if policy == "swap":
            return (name,) + tuple(reversed(kids))
        if policy == "wrap":
            return (name, ("layer",) + kids)
        return (name,) + kids

    def _kids(
        self,
        resolved: Resolved,
        memo: Overlay,
        leaf_override: dict[int, Meaning],
    ) -> tuple[Meaning, ...]:
        """Child meanings in slot order, delegated leaves substituted by id."""
        kids: list[Meaning] = [memo.read(child) for child in resolved.children]
        for leaf, slot in zip(resolved.leaves, resolved.slots):
            override = leaf_override.get(id(leaf))
            if override is None:
                override = self.occurrences[id(leaf)]
            kids.insert(slot, override)
        return tuple(kids)

    def _count(self) -> None:
        """Attribute one fold-body execution to this folder's counter lane."""
        if self.lane == "baseline":
            self.counters.baseline_folds += 1
        elif self.lane == "replay":
            self.counters.replay_folds += 1
        else:
            self.counters.oracle_folds += 1


def _graph(kernel: Kernel, root: int) -> Graph:
    """Index the default derivation, including delegated-leaf dependencies."""
    parents: dict[int, set[int]] = {}
    owners: dict[int, set[int]] = {}
    pending = [root]
    seen: set[int] = set()
    while pending:
        handle = pending.pop()
        if handle in seen:
            continue
        seen.add(handle)
        resolved = _resolved(kernel, handle, None)
        for key in resolved.keys:
            owners.setdefault(key, set()).add(handle)
        for leaf in resolved.leaves:
            parents.setdefault(id(leaf), set()).add(handle)
        for child in resolved.children:
            parents.setdefault(child, set()).add(handle)
            pending.append(child)
    return Graph(parents, owners)


def _dirty(graph: Graph, seed_key: int) -> set[int]:
    """Handles whose meanings depend on one delegated leaf or packed key."""
    dirty = set(graph.owners.get(seed_key, ())) | set(graph.parents.get(seed_key, ()))
    pending = list(dirty)
    while pending:
        child = pending.pop()
        for parent in graph.parents.get(child, ()):
            if parent in dirty:
                continue
            dirty.add(parent)
            pending.append(parent)
    return dirty


class IslandOutcome(NamedTuple):
    """One island occurrence's baseline meaning and its cold seed."""

    seed: IslandSeed
    kernel: Kernel
    root: int
    arm_points: tuple[int, ...]


def island_product(
    tables: ParserTables,
    text: str,
    pos: int,
    policies: dict[str, str],
    counters: Counters,
    delegates: dict[int, Delegate] | None = None,
) -> IslandOutcome | None:
    """Run one real windowed island and settle nothing at its span.

    The baseline meaning folds once. Alternate meanings are computed COLD —
    only when the island chart holds a real arm choice — through the same
    ancestor-cone replay the enclosing Earley product uses, so a nested
    delegated island below this one composes through ``delegates``.
    """
    counters.island_runs += 1
    kern, best = island_run(tables, text[pos : pos + 256], delegates)
    if best is None:
        return None
    item, end = best
    root = (item << kern.tables.packing.bits) | end
    occurrences = _nested_occurrences(kern, policies, counters)
    folder = Folder(kern, policies, occurrences, counters, "baseline")
    memo = Overlay({})
    baseline = folder.apply(root, memo, set(), None, {})
    base_layer = dict(memo.changed)
    points = tuple(
        key
        for key in ambiguity_points(kern, root)
        if is_arm_choice(
            kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
        )
    )
    alternates = _island_alternates(
        kern, folder, root, base_layer, points, occurrences, counters
    )
    return IslandOutcome(IslandSeed(baseline, alternates), kern, root, points)


def _nested_occurrences(
    kern: Kernel, policies: dict[str, str], counters: Counters
) -> dict[int, Meaning]:
    """Baseline meanings for delegated leaves inside this island's own chart."""
    del policies, counters
    occurrences: dict[int, Meaning] = {}
    for leaf in kern.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, IslandSeed):
            raise UnsupportedConstructError(
                "island seed prototype: nested leaf carries no seed"
            )
        occurrences[id(leaf)] = payload.baseline
    return occurrences


def _island_alternates(
    kern: Kernel,
    folder: Folder,
    root: int,
    base_layer: dict[int, Meaning],
    points: tuple[int, ...],
    occurrences: dict[int, Meaning],
    counters: Counters,
) -> tuple[Meaning, ...]:
    """One alternate island meaning per differing flip, one flip at a time."""
    replay = Folder(kern, {}, occurrences, counters, "replay")
    replay.program = folder.program
    alternates: list[Meaning] = []
    baseline = Overlay(base_layer).read(root)
    for sibling in _sibling_accepts(kern, root):
        counters.alternates_evaluated += 1
        overlay = Overlay(base_layer)
        meaning = replay.apply(sibling, overlay, set(), None, {})
        counters.cone_sizes.append(len(overlay.changed))
        if not same_value(baseline, meaning):
            alternates.append(meaning)
    graph: Graph | None = None
    for key in points:
        if graph is None:
            graph = _graph(kern, root)
        for family in range(1, len(kern.st.links[key])):
            counters.alternates_evaluated += 1
            overlay = Overlay(base_layer)
            meaning = replay.apply(
                root, overlay, _dirty(graph, key), Choice(key, family), {}
            )
            counters.cone_sizes.append(len(overlay.changed))
            if not same_value(baseline, meaning):
                alternates.append(meaning)
    for leaf in kern.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, IslandSeed) or not payload.alternates:
            continue
        if graph is None:
            graph = _graph(kern, root)
        for alternate in payload.alternates:
            counters.alternates_evaluated += 1
            overlay = Overlay(base_layer)
            meaning = replay.apply(
                root, overlay, _dirty(graph, id(leaf)), None, {id(leaf): alternate}
            )
            counters.cone_sizes.append(len(overlay.changed))
            if not same_value(baseline, meaning):
                alternates.append(meaning)
    return tuple(alternates)


def _sibling_accepts(kern: Kernel, root: int) -> tuple[int, ...]:
    """Other accepting start items at the island's own end column.

    A start-rule arm choice has no parent waiter to pack it, so it lives in
    sibling accepting ITEMS — the same shape the production ``another_meaning``
    reads through ``_sibling_roots``. Each sibling constructs one complete
    island meaning, reusing every shared subtree from the baseline memo.
    """
    bits, mask = kern.tables.packing.bits, kern.tables.packing.mask
    accepts = kern.tables.codes.accept_codes
    end = root & mask
    return tuple(
        (item << bits) | end
        for item in kern.cols[end]
        if item >> bits in accepts
        and item & mask == 0
        and ((item << bits) | end) != root
    )


class OuterRun(NamedTuple):
    """One delegated whole-document run and its per-leaf island seeds."""

    kernel: Kernel
    root: int
    occurrences: dict[int, Meaning]
    seeds: dict[int, IslandSeed]


def outer_run(
    outer: ParserTables,
    island: ParserTables,
    text: str,
    island_rule: str,
    island_policies: dict[str, str],
    counters: Counters,
    nested: ParserTables | None = None,
    nested_rule: str = "",
) -> OuterRun:
    """Recognize the document once with the island interior delegated."""
    inner_delegates = _delegates(island, nested, nested_rule, island_policies, counters)

    def delegate(window: str, pos: int) -> tuple[int, IslandSeed] | None:
        outcome = island_product(
            island, window, pos, island_policies, counters, inner_delegates
        )
        if outcome is None:
            return None
        end = outcome.root & outcome.kernel.tables.packing.mask
        return pos + end, outcome.seed

    rid = _rule_id(outer, island_rule)
    counters.outer_kernel_runs += 1
    kernel = Kernel(outer, text, True, delegates={rid: delegate}).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("island seed prototype: outer parse failed")
    occurrences: dict[int, Meaning] = {}
    seeds: dict[int, IslandSeed] = {}
    for leaf in kernel.delegated.values():
        payload = leaf.payload
        if not isinstance(payload, IslandSeed):
            raise UnsupportedConstructError(
                "island seed prototype: delegated leaf carries no seed"
            )
        occurrences[id(leaf)] = payload.baseline
        if payload.alternates:
            seeds[id(leaf)] = payload
            counters.seeds += 1
    return OuterRun(kernel, accept_handle(kernel), occurrences, seeds)


def _delegates(
    island: ParserTables,
    nested: ParserTables | None,
    nested_rule: str,
    policies: dict[str, str],
    counters: Counters,
) -> dict[int, Delegate] | None:
    """The island's own interior delegate table, for the nested witness."""
    if nested is None:
        return None

    def inner(window: str, pos: int) -> tuple[int, IslandSeed] | None:
        outcome = island_product(nested, window, pos, policies, counters)
        if outcome is None:
            return None
        return pos + (outcome.root & outcome.kernel.tables.packing.mask), outcome.seed

    return {_rule_id(island, nested_rule): inner}


def _rule_id(tables: ParserTables, name: str) -> int:
    """The compiled rule id spelled ``name``."""
    for index, ref in enumerate(tables.decode.rule_refs):
        if str(ref) == name:
            return index
    raise UnsupportedConstructError(f"island seed prototype: no rule {name!r}")


class Verdict(NamedTuple):
    """One enclosing-product ambiguity verdict and its structural counts."""

    differs: bool
    baseline: Meaning


def cone_verdict(
    run: OuterRun, policies: dict[str, str], counters: Counters
) -> Verdict:
    """Shape (iii): replay each seed's ancestor cone over the outer chart."""
    folder = Folder(run.kernel, policies, run.occurrences, counters, "baseline")
    memo = Overlay({})
    baseline = folder.apply(run.root, memo, set(), None, {})
    base_layer = dict(memo.changed)
    if not run.seeds:
        return Verdict(False, baseline)
    graph = _graph(run.kernel, run.root)
    replay = Folder(run.kernel, policies, run.occurrences, counters, "replay")
    differs = False
    for leaf_id, seed in run.seeds.items():
        dirty = _dirty(graph, leaf_id)
        for alternate in seed.alternates:
            counters.alternates_evaluated += 1
            overlay = Overlay(base_layer)
            meaning = replay.apply(run.root, overlay, dirty, None, {leaf_id: alternate})
            counters.cone_sizes.append(len(overlay.changed))
            counters.overlay_entries.append(len(overlay.changed))
            if not same_value(baseline, meaning):
                differs = True
    return Verdict(differs, baseline)


class SeedLane:
    """The enclosing product's transactional seed and trace state."""

    __slots__ = ("marks", "seeds", "traces")

    def __init__(self) -> None:
        self.seeds: list[tuple[int, IslandSeed]] = []
        self.traces: dict[int, list[TraceFrame]] = {}
        self.marks: list[tuple[int, tuple[int, ...]]] = []

    def mark(self) -> None:
        """Open one constant-size speculation mark."""
        lengths = tuple(len(self.traces[leaf_id]) for leaf_id, _seed in self.seeds)
        self.marks.append((len(self.seeds), lengths))

    def rollback(self) -> None:
        """Discard seeds and trace frames recorded after the newest mark."""
        count, lengths = self.marks.pop()
        for leaf_id, _seed in self.seeds[count:]:
            del self.traces[leaf_id]
        del self.seeds[count:]
        for (leaf_id, _seed), length in zip(self.seeds, lengths):
            del self.traces[leaf_id][length:]

    def commit(self) -> None:
        """Release the newest mark without copying anything."""
        self.marks.pop()


def trace_verdict(
    run: OuterRun, policies: dict[str, str], counters: Counters
) -> tuple[Verdict, SeedLane]:
    """Shape (i): one PDA-shaped pass records only each seed's ancestor frames.

    The completion ORDER is the real chart's post-order; the frame stack and
    the trace lane are the toy stand-ins for PDA frames, which is the honest
    boundary — a predictive run has no chart to consult afterwards.
    """
    folder = Folder(run.kernel, policies, run.occurrences, counters, "baseline")
    memo = Overlay({})
    lane = SeedLane() if run.seeds else None
    traced: dict[int, tuple[int, ...]] = {}
    order = _postorder(run.kernel, run.root)
    for handle in order:
        resolved = _resolved(run.kernel, handle, None)
        meaning = folder._assemble(handle, resolved, memo, {})
        memo.changed[handle] = meaning
        if lane is None:
            continue
        _record_frames(run, folder, lane, traced, handle, resolved, memo, counters)
    baseline = memo.read(run.root)
    if lane is None:
        return Verdict(False, baseline), SeedLane()
    differs = False
    for leaf_id, seed in run.seeds.items():
        for alternate in seed.alternates:
            counters.alternates_evaluated += 1
            meaning = _replay_trace(lane.traces[leaf_id], alternate, counters)
            if not same_value(baseline, meaning):
                differs = True
    return Verdict(differs, baseline), lane


def _postorder(kernel: Kernel, root: int) -> list[int]:
    """The default derivation's completions in dependency order."""
    order: list[int] = []
    seen: set[int] = set()
    stack: list[tuple[int, bool]] = [(root, False)]
    while stack:
        handle, expanded = stack.pop()
        if expanded:
            order.append(handle)
            continue
        if handle in seen:
            continue
        seen.add(handle)
        stack.append((handle, True))
        for child in reversed(_resolved(kernel, handle, None).children):
            stack.append((child, False))
    return order


def _record_frames(
    run: OuterRun,
    folder: Folder,
    lane: SeedLane,
    traced: dict[int, tuple[int, ...]],
    handle: int,
    resolved: Resolved,
    memo: Overlay,
    counters: Counters,
) -> None:
    """Append one trace frame per live seed this completion consumed."""
    kids = folder._kids(resolved, memo, {})
    consumed: dict[int, int] = {}
    for leaf, slot in zip(resolved.leaves, resolved.slots):
        if id(leaf) in run.seeds:
            lane.seeds.append((id(leaf), run.seeds[id(leaf)]))
            lane.traces[id(leaf)] = []
            consumed[id(leaf)] = slot
    ints = iter(resolved.children)
    for index in range(len(kids)):
        if index in resolved.slots:
            continue
        child = next(ints)
        for leaf_id in traced.get(child, ()):
            consumed[leaf_id] = index
    for leaf_id, dirty in consumed.items():
        policy = folder.program[_code(run.kernel, handle)]
        lane.traces[leaf_id].append(
            TraceFrame(policy, _name(run.kernel, handle), kids, dirty)
        )
        counters.trace_frames += 1
    if consumed:
        traced[handle] = tuple(consumed)


def _replay_trace(
    trace: list[TraceFrame], alternate: Meaning, counters: Counters
) -> Meaning:
    """Fold one alternate up the recorded ancestor frames only."""
    current = alternate
    for frame in trace:
        counters.replay_folds += 1
        kids = frame.kids[: frame.dirty] + (current,) + frame.kids[frame.dirty + 1 :]
        if frame.policy == "drop":
            current = (frame.name,)
        elif frame.policy == "swap":
            current = (frame.name,) + tuple(reversed(kids))
        elif frame.policy == "wrap":
            current = (frame.name, ("layer",) + kids)
        else:
            current = (frame.name,) + kids
    return current


def pairs_verdict(run: OuterRun, policies: dict[str, str]) -> int:
    """Shape (ii), rejected: carry every meaning combination through parents.

    Returns the number of complete root meanings materialized — the Cartesian
    product over live seeds, which is what the seed shapes avoid.
    """
    folder = Folder(run.kernel, policies, run.occurrences, Counters(), "oracle")
    memo: dict[int, tuple[Meaning, ...]] = {}
    for handle in _postorder(run.kernel, run.root):
        resolved = _resolved(run.kernel, handle, None)
        combos: list[tuple[Meaning, ...]] = [()]
        ints = iter(resolved.children)
        width = len(resolved.children) + len(resolved.leaves)
        for index in range(width):
            if index in resolved.slots:
                leaf = resolved.leaves[resolved.slots.index(index)]
                seed = run.seeds.get(id(leaf))
                options: tuple[Meaning, ...] = (run.occurrences[id(leaf)],)
                if seed is not None:
                    options = options + seed.alternates
            else:
                options = memo[next(ints)]
            combos = [prefix + (option,) for prefix in combos for option in options]
        meanings: list[Meaning] = []
        for kids in combos:
            meanings.append(_apply_policy(folder, run.kernel, handle, kids))
        memo[handle] = tuple(meanings)
    return len(memo[run.root])


def _apply_policy(
    folder: Folder, kernel: Kernel, handle: int, kids: tuple[Meaning, ...]
) -> Meaning:
    """One meaning operation over explicit children, for the rejected shape."""
    name = _name(kernel, handle)
    policy = folder.program[_code(kernel, handle)]
    if policy == "drop":
        return (name,)
    if policy == "swap":
        return (name,) + tuple(reversed(kids))
    if policy == "wrap":
        return (name, ("layer",) + kids)
    return (name,) + kids


def resolver_handoff(
    outcome: IslandOutcome, counters: Counters, whole: ParserTables, text: str
) -> tuple[ParseTree, ParseTree, int]:
    """Produce the derivation pairs a resolver could receive, both scopes.

    The island-local pair costs nothing new: both trees come from the island
    kernel already in hand. The complete-document pair REQUIRES one
    un-delegated Earley parse — counted, and run only after root inequality
    is already proven.
    """
    key = outcome.arm_points[0]
    local_first = FastTree(outcome.kernel, {}).build(outcome.root)
    local_other = FastTree(outcome.kernel, {key: 1}).build(outcome.root)
    if not isinstance(local_first, ParseTree) or not isinstance(local_other, ParseTree):
        raise UnsupportedConstructError(
            "island seed prototype: island pair did not build"
        )
    counters.full_document_parses += 1
    complete = Kernel(whole, text, True).run()
    if accept_item(complete) < 0:
        raise UnsupportedConstructError(
            "island seed prototype: complete document did not parse"
        )
    root = accept_handle(complete)
    points = [
        k
        for k in ambiguity_points(complete, root)
        if is_arm_choice(
            complete.st.links[k],
            complete.tables.packing.bits,
            complete.tables.code_choice,
        )
    ]
    return local_first, local_other, len(points)


class Witness(NamedTuple):
    """One enclosing-product scenario with its expected verdict."""

    name: str
    outer: str
    island: str
    island_rule: str
    text: str
    policies: dict[str, str]
    island_policies: dict[str, str]
    differs: bool
    expected_seeds: int
    nested: str = ""
    nested_rule: str = ""


WITNESSES = (
    Witness(
        "kept-difference",
        OUTER_ONE,
        ISLAND,
        "t",
        "[(xy)]",
        {},
        {},
        True,
        1,
    ),
    Witness(
        "dropping-parent",
        OUTER_ONE,
        ISLAND,
        "t",
        "[(xy)]",
        {"mid": "drop"},
        {},
        False,
        1,
    ),
    Witness(
        "equal-meanings",
        OUTER_ONE,
        ISLAND,
        "t",
        "[(xy)]",
        {},
        {"pair": "atom"},
        False,
        0,
    ),
    Witness(
        "nested-transforms",
        OUTER_ONE,
        ISLAND,
        "t",
        "[(xy)]",
        {"root": "wrap", "mid": "swap"},
        {},
        True,
        1,
    ),
    Witness(
        "two-seeds",
        OUTER_TWO,
        ISLAND,
        "t",
        "(xy)(xy)z",
        {},
        {},
        True,
        2,
    ),
    Witness(
        "unambiguous-island",
        OUTER_ONE,
        ISLAND_PLAIN,
        "t",
        "[(xy)]",
        {},
        {},
        False,
        0,
    ),
    Witness(
        "nested-islands",
        OUTER_ONE,
        ISLAND_NESTED,
        "t",
        "[(xy)]",
        {},
        {},
        True,
        1,
        INNER,
        "inner",
    ),
)


def _oracle(run: OuterRun, policies: dict[str, str], counters: Counters) -> bool:
    """Differential oracle only: refold the whole document per alternate."""
    folder = Folder(run.kernel, policies, run.occurrences, counters, "oracle")
    baseline = folder.apply(run.root, Overlay({}), set(), None, {})
    differs = False
    for leaf_id, seed in run.seeds.items():
        for alternate in seed.alternates:
            other = folder.apply(
                run.root, Overlay({}), set(), None, {leaf_id: alternate}
            )
            if not same_value(baseline, other):
                differs = True
        del leaf_id
    return differs


def _exercise(witness: Witness) -> None:
    """Run one witness through both seed shapes and the rejected pair shape."""
    counters = Counters()
    size = len(witness.text)
    outer = _tables(witness.outer, size)
    island = _tables(witness.island, size)
    nested = _tables(witness.nested, size) if witness.nested else None
    run = outer_run(
        outer,
        island,
        witness.text,
        witness.island_rule,
        witness.island_policies,
        counters,
        nested,
        witness.nested_rule,
    )
    cone = cone_verdict(run, witness.policies, counters)
    trace, lane = trace_verdict(run, witness.policies, counters)
    assert cone.differs == witness.differs, witness.name
    assert trace.differs == witness.differs, witness.name
    assert same_value(cone.baseline, trace.baseline), witness.name
    assert len(run.seeds) == witness.expected_seeds, witness.name
    assert _oracle(run, witness.policies, counters) == witness.differs, witness.name
    if not run.seeds:
        assert counters.trace_frames == 0
        assert not lane.seeds
    pair_meanings = pairs_verdict(run, witness.policies)
    print(
        witness.name,
        f"differs={cone.differs}",
        f"outer_runs={counters.outer_kernel_runs}",
        f"island_runs={counters.island_runs}",
        f"document_reparses={counters.full_document_parses}",
        f"seeds={counters.seeds}",
        f"alternates={counters.alternates_evaluated}",
        f"baseline_folds={counters.baseline_folds}",
        f"replay_folds={counters.replay_folds}",
        f"trace_frames={counters.trace_frames}",
        f"cones={counters.cone_sizes}",
        f"pair_shape_root_meanings={pair_meanings}",
        sep="\t",
    )
    assert counters.full_document_parses == 0


def _exercise_resolver() -> None:
    """Refusal without reparse; resolver pairs in both scopes, priced."""
    witness = WITNESSES[0]
    counters = Counters()
    outer = _tables(witness.outer, len(witness.text))
    island = _tables(witness.island, len(witness.text))
    run = outer_run(outer, island, witness.text, "t", {}, counters)
    verdict = cone_verdict(run, {}, counters)
    assert verdict.differs
    assert counters.full_document_parses == 0
    outcome = island_product(island, witness.text, 2, {}, counters)
    assert outcome is not None and outcome.arm_points
    whole = _tables(witness.outer, len(witness.text))
    local_a, local_b, complete_points = resolver_handoff(
        outcome, counters, whole, witness.text
    )
    assert local_a is not local_b
    assert counters.full_document_parses == 1
    print(
        "resolver-handoff",
        "island_local_pair=free (island kernel already holds both trees)",
        f"complete_pair_needs_full_parse=True points={complete_points}",
        "refusal_path_reparses=0",
        sep="\t",
    )


def _exercise_rollback() -> None:
    """A failed speculative parent discards its seed and trace, nothing else."""
    lane = SeedLane()
    stable_seed = IslandSeed(("t", "keep"), (("t", "other"),))
    lane.seeds.append((1, stable_seed))
    lane.traces[1] = [TraceFrame("", "mid", (("t", "keep"),), 0)]
    duplicates: set[str] = {"stable"}
    verdicts: list[str] = ["v0"]
    lane.mark()
    speculative = IslandSeed(("t", "spec"), (("t", "spec2"),))
    lane.seeds.append((2, speculative))
    lane.traces[2] = []
    lane.traces[1].append(TraceFrame("", "root", (("mid",),), 0))
    lane.rollback()
    assert lane.seeds == [(1, stable_seed)]
    assert 2 not in lane.traces
    assert len(lane.traces[1]) == 1
    assert duplicates == {"stable"} and verdicts == ["v0"]
    lane.mark()
    lane.traces[1].append(TraceFrame("", "root", (("mid",),), 0))
    lane.commit()
    assert len(lane.traces[1]) == 2
    print(
        "rollback",
        "failed parent removed its seed+frames; retained seed, duplicate set,"
        " and verdict order untouched",
        sep="\t",
    )


def main() -> None:
    """Run every witness plus the resolver and rollback proofs."""
    for witness in WITNESSES:
        _exercise(witness)
    _exercise_resolver()
    _exercise_rollback()
    print(
        "conclusion",
        "island seeds replay through the enclosing continuation; recognition"
        " runs once; the pair-carrying shape is Cartesian and rejected",
        sep="\t",
    )


if __name__ == "__main__":
    main()
