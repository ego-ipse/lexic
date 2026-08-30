"""Price the ambiguous-parse structures — flat index, real frames, honest control.

Modes (each invocation is one isolated process; run alone under
`tools/guarded.sh`):

- `--mode control`: an UNAMBIGUOUS variant of the witness grammar. Every
  ambiguity-only structure is constructed through ONE allocator object, and
  the control installs a refusing allocator whose every method raises — so the
  row completing IS the proof that no meaning memo, dependency index, overlay,
  seed, or trace frame was allocated, and the zero counters are read off the
  same allocator afterwards. The ordinary direct product's own state is
  reported beside it, separately and by name.
- `--mode ambiguity`: the `DISTANT` witness. Stages, each in its own
  tracemalloc window after one pre-expansion sweep: baseline meaning memo,
  dict-of-sets dependency index (the REJECTED oracle), the dictionary-free
  CSR/forward-star replacement with dirty-cone parity against the oracle,
  sparse alternate overlay, and the replay verdict. The flat index's TRANSIENT
  build peak (which does hold a handle→number dict, the thing production gets
  free from completion state) is measured and released BEFORE the retained
  structure is measured.
- `--mode frames`: REAL `TraceFrame`/seed allocations with ONE child tuple per
  completed ancestor, shared only among the seeds crossing that completion —
  the shape `island_alternate_seed._record_frames` actually allocates. Ancestor
  depth, simultaneous seed count, child arity, and the dirty slot all vary.

tracemalloc attributes only Python-level allocations made inside a window; it
cannot attribute the kernel's own chart arrays or allocations served from
freelists, and peak RSS is monotonic per process — both stated per row.
"""

from __future__ import annotations

import argparse
import gc
import resource
import time
import tracemalloc
from array import array
from bisect import bisect_left
from collections.abc import Sequence
from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.kernel.forest.support.ambiguity import ambiguity_points
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
from lexic.parsing.earley.kernel.tables.atoms import predecessor_chain, tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.splits import ChainSpec, is_arm_choice
from lexic.parsing.earley.normalize import normalize

type Meaning = str | tuple["Meaning", ...]

DISTANT = (
    "root ::= filler t filler\n"
    "filler ::= item*\n"
    "item ::= [ab]\n"
    "t ::= u | v\n"
    'u ::= "q"\nv ::= "q"\n'
)
DISTANT_TWO = (
    "root ::= filler w filler\n"
    "w ::= x y\n"
    'x ::= t "-"\n'
    'y ::= t2 "-"\n'
    "filler ::= item*\n"
    "item ::= [ab]\n"
    "t ::= u | v\n"
    "t2 ::= u2 | v2\n"
    'u ::= "q"\nv ::= "q"\nu2 ::= "r"\nv2 ::= "r"\n'
)
CONTROL = (
    'root ::= filler t filler\nfiller ::= item*\nitem ::= [ab]\nt ::= u\nu ::= "q"\n'
)

TIERS = (("B", 1 << 8), ("H", 1 << 16), ("i", 1 << 31))
"""Unsigned/int typecode tiers and the exclusive population each one holds."""


def tier_code(population: int) -> str:
    """The narrowest array typecode that holds every index below ``population``.

    :param population: How many distinct node numbers the index must address.
    :returns: The `array` typecode.
    :raises UnsupportedConstructError: When no tier holds it — production
        escalates to 64-bit rather than truncating, and saying so out loud is
        the point of the refusal.
    """
    for code, ceiling in TIERS:
        if population < ceiling:
            return code
    raise UnsupportedConstructError(
        f"ambiguity index: {population} nodes exceeds the 32-bit index tier"
    )


class Choice(NamedTuple):
    """One packed family selected for one ambiguity key."""

    key: int
    family: int


class TraceFrame(NamedTuple):
    """One PDA ancestor completion recorded while a seed is live."""

    policy: int
    name: str
    kids: tuple[Meaning, ...]
    dirty: int


class SeedRecord(NamedTuple):
    """One island seed as the enclosing product retains it."""

    baseline: Meaning
    alternates: tuple[Meaning, ...]


class Overlay:
    """Read-only baseline memo plus one alternate's sparse changed layer."""

    __slots__ = ("base", "changed")

    def __init__(self, base: dict[int, Meaning]) -> None:
        self.base = base
        self.changed: dict[int, Meaning] = {}

    def contains(self, handle: int) -> bool:
        """Whether either layer holds ``handle``."""
        return handle in self.changed or handle in self.base

    def read(self, handle: int) -> Meaning:
        """Sparse layer first, immutable baseline second."""
        if handle in self.changed:
            return self.changed[handle]
        return self.base[handle]


class DictGraph(NamedTuple):
    """The REJECTED dict-of-sets dependency index — retained as the oracle."""

    parents: dict[int, set[int]]
    owners: dict[int, set[int]]


class FlatGraph(NamedTuple):
    """CSR parent edges and forward-star key owners — NO numbering dictionary.

    Production assigns each completion its dense number as the completion is
    created, so the number lives in existing completion state. An external
    prototype has no such state, so the build uses a TRANSIENT dict which is
    measured and released before the retained structure is priced; nothing
    here survives it.
    """

    handles: array
    parent_offsets: array
    parent_edges: array
    owner_keys: array
    owner_offsets: array
    owner_nodes: array

    def bytes_total(self) -> int:
        """Buffer bytes of every retained array."""
        return sum(
            lane.itemsize * len(lane)
            for lane in (
                self.handles,
                self.parent_offsets,
                self.parent_edges,
                self.owner_keys,
                self.owner_offsets,
                self.owner_nodes,
            )
        )

    def parents_of(self, index: int) -> tuple[int, ...]:
        """The parent node numbers of one node — the parent-edge law."""
        return tuple(
            self.parent_edges[at]
            for at in range(self.parent_offsets[index], self.parent_offsets[index + 1])
        )

    def owners_of(self, key: int) -> tuple[int, ...]:
        """The node numbers owning one ambiguity key — the owner law."""
        slot = bisect_left(self.owner_keys, key)
        if slot >= len(self.owner_keys) or self.owner_keys[slot] != key:
            return ()
        return tuple(
            self.owner_nodes[at]
            for at in range(self.owner_offsets[slot], self.owner_offsets[slot + 1])
        )


class Counts(NamedTuple):
    """How many of each ambiguity-only structure were constructed."""

    memo: int
    dict_index: int
    flat_index: int
    overlay: int
    seed: int
    frame: int

    def total(self) -> int:
        """Every ambiguity-only allocation this run made."""
        return sum(self)


class Structures:
    """The ONE constructor of every ambiguity-only structure, with counters.

    Nothing else in this file builds an `Overlay`, a dependency index, a
    retained meaning memo, a seed, or a trace frame, so an external counter on
    these methods really is a count of ambiguity allocations.
    """

    __slots__ = (
        "_dict_index",
        "_flat_index",
        "_frame",
        "_memo",
        "_overlay",
        "_seed",
    )

    def __init__(self) -> None:
        self._memo = 0
        self._dict_index = 0
        self._flat_index = 0
        self._overlay = 0
        self._seed = 0
        self._frame = 0

    @property
    def counts(self) -> Counts:
        """The current allocation census."""
        return Counts(
            self._memo,
            self._dict_index,
            self._flat_index,
            self._overlay,
            self._seed,
            self._frame,
        )

    def retained_memo(self, table: dict[int, Meaning]) -> dict[int, Meaning]:
        """The completed-handle meaning memo an alternate would later reuse."""
        self._memo += 1
        return dict(table)

    def overlay(self, base: dict[int, Meaning]) -> Overlay:
        """One alternate's sparse layer over the read-only baseline."""
        self._overlay += 1
        return Overlay(base)

    def dict_index(self, kernel: Kernel, order: list[int]) -> DictGraph:
        """The rejected dict-of-sets dependency index."""
        self._dict_index += 1
        return _dict_graph(kernel, order)

    def flat_index(self, kernel: Kernel, order: list[int]) -> FlatBuild:
        """The dictionary-free CSR/forward-star dependency index."""
        self._flat_index += 1
        return _flat_graph(kernel, order)

    def seed(self, baseline: Meaning, alternates: tuple[Meaning, ...]) -> SeedRecord:
        """One island seed record."""
        self._seed += 1
        return SeedRecord(baseline, alternates)

    def frame(
        self, policy: int, name: str, kids: tuple[Meaning, ...], dirty: int
    ) -> TraceFrame:
        """One ancestor completion recorded while a seed is live."""
        self._frame += 1
        return TraceFrame(policy, name, kids, dirty)


class RefusingStructures(Structures):
    """The control's allocator: every ambiguity structure is a hard error."""

    __slots__ = ()

    def retained_memo(self, table: dict[int, Meaning]) -> dict[int, Meaning]:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: a meaning memo was retained")

    def overlay(self, base: dict[int, Meaning]) -> Overlay:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: an alternate overlay was built")

    def dict_index(self, kernel: Kernel, order: list[int]) -> DictGraph:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: a dependency index was built")

    def flat_index(self, kernel: Kernel, order: list[int]) -> FlatBuild:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: a dependency index was built")

    def seed(self, baseline: Meaning, alternates: tuple[Meaning, ...]) -> SeedRecord:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: an island seed was published")

    def frame(
        self, policy: int, name: str, kids: tuple[Meaning, ...], dirty: int
    ) -> TraceFrame:
        """:raises UnsupportedConstructError: Always."""
        raise UnsupportedConstructError("control: a trace frame was recorded")


def _rss_kib() -> int:
    """This process's high-water RSS in KiB (monotonic)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _kernel(grammar: str, text: str) -> Kernel:
    """Run the real kernel over one witness input."""
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("ambiguity RSS witness: no parse")
    return kernel


def _resolved(
    kernel: Kernel, handle: int, choice: Choice | None
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """One completion's child handles and every predecessor key it owns."""
    bits = kernel.tables.packing.bits
    codes = kernel.tables.codes
    code = handle >> (2 * bits)
    base = codes.arm_base[codes.code_arm[code]]
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
            return (), (handle,)
        raise UnsupportedConstructError("ambiguity RSS witness: unresolved handle")
    children = tuple(
        child
        for _predecessor, _end, child in chain
        if isinstance(child, int) and not isinstance(child, bool)
    )
    keys = (handle,) + tuple(
        (predecessor << bits) | end for predecessor, end, _child in chain
    )
    return children, keys


def _preexpand(kernel: Kernel, root: int) -> list[int]:
    """Resolve every reachable handle once BEFORE any measured window, so
    lazy Leo expansion cannot land inside a named structure's tracemalloc
    bucket. Returns the default derivation's postorder."""
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
        children, _keys = _resolved(kernel, handle, None)
        for child in reversed(children):
            stack.append((child, False))
    return order


def _names(kernel: Kernel) -> tuple[str, ...]:
    """Every decoded rule name, built once outside a measured window."""
    return tuple(str(ref) for ref in kernel.tables.decode.rule_refs)


def _name_of(kernel: Kernel, names: tuple[str, ...], handle: int) -> str:
    """The rule name of one completed handle."""
    bits = kernel.tables.packing.bits
    codes = kernel.tables.codes
    return names[codes.arm_rule[codes.code_arm[handle >> (2 * bits)]]]


def _fold(
    kernel: Kernel,
    root: int,
    memo: Overlay,
    dirty: set[int],
    choice: Choice | None,
    names: tuple[str, ...],
) -> tuple[Meaning, int]:
    """Fold ``root`` with reuse, returning the meaning and fold-body count."""
    bits = kernel.tables.packing.bits
    mask = kernel.tables.packing.mask
    folds = 0
    stack: list[tuple[int, bool]] = [(root, False)]
    while stack:
        handle, expanded = stack.pop()
        if memo.contains(handle) and handle not in dirty:
            continue
        children, _keys = _resolved(kernel, handle, choice)
        if not expanded:
            stack.append((handle, True))
            for child in reversed(children):
                if not memo.contains(child) or child in dirty:
                    stack.append((child, False))
            continue
        folds += 1
        name = _name_of(kernel, names, handle)
        if not children:
            start = (handle >> bits) & mask
            memo.changed[handle] = (name, kernel.text[start : handle & mask])
        else:
            memo.changed[handle] = (name,) + tuple(
                memo.read(child) for child in children
            )
    return memo.read(root), folds


class DirectFold(NamedTuple):
    """The ordinary unambiguous product: its value and its own state."""

    value: Meaning
    folds: int
    peak_table: int


def _direct_fold(kernel: Kernel, root: int, names: tuple[str, ...]) -> DirectFold:
    """The plain product fold — no `Overlay`, no retained memo, no index.

    Its transient value table IS ordinary direct product state: it is dropped
    when the root value is returned, and the control row prices it under that
    name rather than calling it an ambiguity structure.
    """
    bits = kernel.tables.packing.bits
    mask = kernel.tables.packing.mask
    table: dict[int, Meaning] = {}
    folds = 0
    peak = 0
    stack: list[tuple[int, bool]] = [(root, False)]
    while stack:
        handle, expanded = stack.pop()
        if handle in table:
            continue
        children, _keys = _resolved(kernel, handle, None)
        if not expanded:
            stack.append((handle, True))
            for child in reversed(children):
                if child not in table:
                    stack.append((child, False))
            continue
        folds += 1
        name = _name_of(kernel, names, handle)
        if not children:
            start = (handle >> bits) & mask
            table[handle] = (name, kernel.text[start : handle & mask])
        else:
            table[handle] = (name,) + tuple(table[child] for child in children)
        if len(table) > peak:
            peak = len(table)
    value = table[root]
    table.clear()
    return DirectFold(value, folds, peak)


def _dict_graph(kernel: Kernel, order: list[int]) -> DictGraph:
    """Build the oracle index over the default derivation."""
    parents: dict[int, set[int]] = {}
    owners: dict[int, set[int]] = {}
    for handle in order:
        children, keys = _resolved(kernel, handle, None)
        for key in keys:
            owners.setdefault(key, set()).add(handle)
        for child in children:
            parents.setdefault(child, set()).add(handle)
    return DictGraph(parents, owners)


def _dict_dirty(graph: DictGraph, key: int) -> set[int]:
    """Oracle dirty cone."""
    dirty = set(graph.owners.get(key, ()))
    pending = list(dirty)
    while pending:
        child = pending.pop()
        for parent in graph.parents.get(child, ()):
            if parent in dirty:
                continue
            dirty.add(parent)
            pending.append(parent)
    return dirty


class FlatBuild(NamedTuple):
    """The retained flat index plus what its BUILD transiently cost."""

    graph: FlatGraph
    numbering_cpu: float
    numbering_wall: float
    csr_cpu: float
    csr_wall: float
    index_code: str


def _flat_graph(kernel: Kernel, order: list[int]) -> FlatBuild:
    """Build the flat index; the transient numbering dict is released here.

    Production numbers a completion when it creates it, so the dict below is
    a prototype-only stand-in. It is measured, then dropped: nothing in the
    returned `FlatGraph` references it.
    """
    code = tier_code(len(order))
    numbering_cpu = time.process_time()
    numbering_wall = time.perf_counter()
    numbering = {handle: index for index, handle in enumerate(order)}
    numbering_cost = time.process_time() - numbering_cpu
    numbering_elapsed = time.perf_counter() - numbering_wall

    build_cpu = time.process_time()
    build_wall = time.perf_counter()
    degree = array(code, bytes(_width(code) * (len(order) + 1)))
    child_lists: list[tuple[int, ...]] = []
    key_pairs: list[tuple[int, int]] = []
    for handle in order:
        children, keys = _resolved(kernel, handle, None)
        child_lists.append(children)
        owner = numbering[handle]
        for key in keys:
            key_pairs.append((key, owner))
        for child in children:
            degree[numbering[child]] += 1
    parent_offsets = array("i", bytes(4 * (len(order) + 1)))
    total = 0
    for index in range(len(order)):
        parent_offsets[index] = total
        total += degree[index]
    parent_offsets[len(order)] = total
    cursor = array("i", parent_offsets)
    parent_edges = array(code, bytes(_width(code) * total))
    for parent_index, children in enumerate(child_lists):
        for child in children:
            child_index = numbering[child]
            parent_edges[cursor[child_index]] = parent_index
            cursor[child_index] += 1
    key_pairs.sort()
    owner_nodes = array(code, (owner for _key, owner in key_pairs))
    distinct: list[int] = []
    owner_offsets_list: list[int] = []
    previous = -1
    for position, (key, _owner) in enumerate(key_pairs):
        if key != previous:
            distinct.append(key)
            owner_offsets_list.append(position)
            previous = key
    owner_offsets_list.append(len(key_pairs))
    graph = FlatGraph(
        array("q", order),
        parent_offsets,
        parent_edges,
        array("q", distinct),
        array("i", owner_offsets_list),
        owner_nodes,
    )
    csr_cost = time.process_time() - build_cpu
    csr_elapsed = time.perf_counter() - build_wall
    del numbering, degree, cursor, child_lists, key_pairs
    return FlatBuild(
        graph, numbering_cost, numbering_elapsed, csr_cost, csr_elapsed, code
    )


def _width(code: str) -> int:
    """Bytes per element of one array typecode."""
    return array(code).itemsize


def _flat_dirty(graph: FlatGraph, key: int) -> set[int]:
    """Dirty cone over the flat index, returned as HANDLES for parity."""
    owners = graph.owners_of(key)
    if not owners:
        return set()
    seen = bytearray(len(graph.handles))
    pending = list(owners)
    for index in pending:
        seen[index] = 1
    while pending:
        index = pending.pop()
        for at in range(graph.parent_offsets[index], graph.parent_offsets[index + 1]):
            parent = graph.parent_edges[at]
            if not seen[parent]:
                seen[parent] = 1
                pending.append(parent)
    return {graph.handles[index] for index in range(len(seen)) if seen[index]}


def _prove_index_laws(
    graph: FlatGraph, kernel: Kernel, order: list[int], code: str
) -> str:
    """Assert the lookup, owner, parent-edge, and integer-tier laws.

    Scope: the index, the oracle, and this check all read
    ``_resolved(kernel, handle, None)`` — the DEFAULT family. The laws below
    therefore say the CSR encodes the default derivation's graph exactly; a
    family-aware edge set (which `cyclic_meaning.build_chart` builds) is a
    production obligation, not something the dirty-cone parity here proves.
    """
    assert len(graph.handles) == len(order)
    assert all(graph.handles[index] == order[index] for index in range(len(order)))
    numbers = {handle: index for index, handle in enumerate(order)}
    edges = 0
    for handle in order:
        children, keys = _resolved(kernel, handle, None)
        edges += len(children)
        for child in children:
            assert numbers[handle] in graph.parents_of(numbers[child])
        for key in keys:
            assert numbers[handle] in graph.owners_of(key)
    assert graph.parent_offsets[len(order)] == len(graph.parent_edges) == edges
    assert graph.owners_of(-1) == ()
    assert code == tier_code(len(order))
    assert len(order) < dict(TIERS)[code]
    overflowed = False
    lane = array(code, [0])
    try:
        lane[0] = dict(TIERS)[code]
    except OverflowError:
        overflowed = True
    assert overflowed, "the selected tier accepted a value beyond its ceiling"
    return (
        f"lookup+owner+parent-edge laws hold over the DEFAULT derivation's"
        f" {len(order)} nodes and {edges} edges; tier {code!r} refuses its own"
        " ceiling"
    )


class Stage(NamedTuple):
    """One structure's population, attributed bytes, and RSS afterwards."""

    name: str
    population: int
    traced_bytes: int
    rss_kib: int


def _arm_points(kernel: Kernel, root: int) -> list[int]:
    """Arm-choice keys reachable from the root."""
    bits = kernel.tables.packing.bits
    return [
        key
        for key in ambiguity_points(kernel, root)
        if is_arm_choice(kernel.st.links[key], bits, kernel.tables.code_choice)
    ]


def _same_meaning(one: Meaning, other: Meaning) -> bool:
    """Iterative exact equality (the engine's recursive walk overflows at
    this witness's depth — the standing §8 obligation)."""
    pending: list[tuple[Meaning, Meaning]] = [(one, other)]
    while pending:
        left, right = pending.pop()
        if left is right:
            continue
        if isinstance(left, str) or isinstance(right, str):
            if left != right:
                return False
            continue
        if len(left) != len(right):
            return False
        pending.extend(zip(left, right))
    return True


def _gc_state() -> str:
    """The collector's state, recorded on every row."""
    return "enabled" if gc.isenabled() else "disabled"


def control_row(pad: int) -> None:
    """The genuinely-unreachable control: zero ambiguity allocations.

    The allocator installed here raises on every ambiguity structure, so the
    row reaching its final print is the evidence — the zero counters are the
    same object's census, not a separate empty container.
    """
    text = "a" * pad + "q" + "b" * pad
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    structures: Structures = RefusingStructures()
    kernel = _kernel(CONTROL, text)
    root = accept_handle(kernel)
    names = _names(kernel)
    _preexpand(kernel, root)
    points = _arm_points(kernel, root)
    if points:
        # The ambiguous branch begins here and is the ONLY caller of the
        # allocator. It is unreachable on this grammar, and the refusing
        # allocator makes any future reachability a hard failure.
        structures.dict_index(kernel, [])
    tracemalloc.start()
    started_fold_cpu = time.process_time()
    started_fold_wall = time.perf_counter()
    direct = _direct_fold(kernel, root, names)
    fold_cpu = time.process_time() - started_fold_cpu
    fold_wall = time.perf_counter() - started_fold_wall
    product_bytes, product_peak = tracemalloc.get_traced_memory()
    root_head = direct.value[0] if isinstance(direct.value, tuple) else direct.value
    folds, peak_table = direct.folds, direct.peak_table
    del direct
    gc.collect()
    residual_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    counts = structures.counts
    assert counts.total() == 0, counts
    print("mode", "control", sep="\t")
    print("pad", pad, "chars", len(text), "gc", _gc_state(), sep="\t")
    print("arm_points", 0, "root", root_head, sep="\t")
    print(
        "ambiguity-allocations",
        f"allocator={type(structures).__name__}",
        f"meaning_memo={counts.memo}",
        f"dependency_index={counts.dict_index + counts.flat_index}",
        f"overlay={counts.overlay}",
        f"seeds={counts.seed}",
        f"trace_frames={counts.frame}",
        f"total={counts.total()}",
        "every one of these is constructed ONLY through the allocator above,"
        " whose control implementation raises — the row completed, so none ran",
        sep="\t",
    )
    print(
        "direct-product-state",
        f"fold_bodies={folds}",
        f"peak_value_table_entries={peak_table}",
        f"root_product_value_bytes={product_bytes}",
        f"fold_peak_bytes={product_peak}",
        f"fold_cpu={fold_cpu:.6f}",
        f"fold_wall={fold_wall:.6f}",
        f"residual_bytes_after_release={residual_bytes}",
        "ordinary direct product state, named as such: the value bytes are"
        " the root product the fold RETURNS, the peak additionally holds the"
        " transient value table the fold clears before returning, and neither"
        " is a post-parse meaning memo",
        sep="\t",
    )
    print(
        "totals",
        f"wall_seconds={time.perf_counter() - started_wall:.6f}",
        f"cpu_seconds={time.process_time() - started_cpu:.6f}",
        f"peak_rss_kib={_rss_kib()}",
        f"chart_keys={len(kernel.st.links)}",
        sep="\t",
    )


def ambiguity_row(pad: int) -> None:
    """The ambiguous candidate row: oracle index, flat index, parity, replay."""
    text = "a" * pad + "q" + "b" * pad
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    structures = Structures()
    kernel = _kernel(DISTANT, text)
    root = accept_handle(kernel)
    names = _names(kernel)
    order = _preexpand(kernel, root)
    stages: list[Stage] = [Stage("chart", len(kernel.st.links), 0, _rss_kib())]

    tracemalloc.start()
    scratch = structures.overlay({})
    baseline, baseline_folds = _fold(kernel, root, scratch, set(), None, names)
    base_layer = structures.retained_memo(scratch.changed)
    memo_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del scratch
    stages.append(Stage("meaning-memo", len(base_layer), memo_bytes, _rss_kib()))

    tracemalloc.start()
    oracle = structures.dict_index(kernel, order)
    oracle_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    stages.append(
        Stage(
            "dict-of-sets-index[REJECTED oracle]",
            len(oracle.parents) + len(oracle.owners),
            oracle_bytes,
            _rss_kib(),
        )
    )

    tracemalloc.start()
    built = structures.flat_index(kernel, order)
    _live, transient_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    flat = built.graph
    tracemalloc.start()
    retained = _retained_copy(flat)
    flat_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del retained
    edges = len(flat.parent_edges)
    keys = len(flat.owner_keys)
    stages.append(
        Stage("flat-csr-index", len(order) + edges + keys, flat_bytes, _rss_kib())
    )
    laws = _prove_index_laws(flat, kernel, order, built.index_code)
    print(
        "flat-index-detail",
        f"nodes={len(order)}",
        f"parent_edges={edges}",
        f"distinct_keys={keys}",
        f"index_typecode={built.index_code}",
        f"retained_array_bytes={flat.bytes_total()}",
        f"retained_bytes_per_edge={flat.bytes_total() / max(edges, 1):.1f}",
        f"retained_bytes_per_char={flat.bytes_total() / len(text):.1f}",
        f"transient_build_peak_bytes={transient_bytes}",
        f"transient_bytes_per_char={transient_bytes / len(text):.1f}",
        f"owner_edges={len(flat.owner_nodes)}",
        f"numbering_cpu={built.numbering_cpu:.6f}",
        f"numbering_wall={built.numbering_wall:.6f}",
        f"csr_build_cpu={built.csr_cpu:.6f}",
        f"csr_build_wall={built.csr_wall:.6f}",
        f"laws={laws}",
        sep="\t",
    )

    parity_counts = _two_key_parity()

    points = _arm_points(kernel, root)
    replay_folds = 0
    replay_cpu = 0.0
    replay_wall = 0.0
    differs = False
    parity_checked = 0
    for key in points:
        oracle_dirty = _dict_dirty(oracle, key)
        flat_dirty = _flat_dirty(flat, key)
        if oracle_dirty != flat_dirty:
            raise UnsupportedConstructError(
                "ambiguity RSS witness: flat dirty cone diverged from oracle"
            )
        parity_checked += 1
        for family in range(1, len(kernel.st.links[key])):
            tracemalloc.start()
            started_replay_cpu = time.process_time()
            started_replay_wall = time.perf_counter()
            overlay = structures.overlay(base_layer)
            alternate, folds = _fold(
                kernel, root, overlay, set(flat_dirty), Choice(key, family), names
            )
            replay_cpu += time.process_time() - started_replay_cpu
            replay_wall += time.perf_counter() - started_replay_wall
            overlay_bytes, _peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            replay_folds += folds
            stages.append(
                Stage(
                    "alternate-overlay", len(overlay.changed), overlay_bytes, _rss_kib()
                )
            )
            if not _same_meaning(baseline, alternate):
                differs = True
    if not differs:
        raise UnsupportedConstructError(
            "ambiguity RSS witness: expected a differing root meaning"
        )

    cleanup_before = len(oracle.parents)
    del oracle
    del flat
    tracemalloc.start()
    rebuilt = structures.flat_index(kernel, order)
    held, _peak = tracemalloc.get_traced_memory()
    del rebuilt
    gc.collect()
    residual, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        "cleanup",
        f"released oracle+flat (oracle_parents={cleanup_before})",
        f"rebuild_traced_bytes={held}",
        f"post_release_residual_bytes={residual}",
        "peak RSS is monotonic and cannot show the release; the tracemalloc"
        " residual does",
        sep="\t",
    )

    counts = structures.counts
    print("mode", "ambiguity", sep="\t")
    print("pad", pad, "chars", len(text), "gc", _gc_state(), sep="\t")
    print(
        "counts",
        f"baseline_folds={baseline_folds}",
        f"replay_folds={replay_folds}",
        f"replay_cpu={replay_cpu:.6f}",
        f"replay_wall={replay_wall:.6f}",
        f"parity_checked_keys={parity_checked}",
        f"verdict_differs={differs}",
        sep="\t",
    )
    print(
        "ambiguity-allocations",
        f"meaning_memo={counts.memo}",
        f"dependency_index={counts.dict_index + counts.flat_index}",
        f"overlay={counts.overlay}",
        f"seeds={counts.seed}",
        f"trace_frames={counts.frame}",
        f"two_key_parity_indexes={parity_counts.dict_index + parity_counts.flat_index}",
        "every one is constructed through an allocator; the parity witness owns"
        " a separate one so this census describes only the measured row",
        sep="\t",
    )
    for stage in stages:
        print(
            "stage",
            stage.name,
            f"population={stage.population}",
            f"traced_bytes={stage.traced_bytes}",
            f"rss_kib={stage.rss_kib}",
            sep="\t",
        )
    print(
        "attribution-note",
        "tracemalloc windows exclude pre-expanded chart growth; kernel-internal"
        " arrays and freelist-served allocations are not attributable and are"
        " visible only in peak RSS",
        sep="\t",
    )
    print(
        "totals",
        f"wall_seconds={time.perf_counter() - started_wall:.6f}",
        f"cpu_seconds={time.process_time() - started_cpu:.6f}",
        f"peak_rss_kib={_rss_kib()}",
        sep="\t",
    )


def _retained_copy(graph: FlatGraph) -> FlatGraph:
    """A fresh copy of exactly the retained arrays, for attribution."""
    return FlatGraph(
        array(graph.handles.typecode, graph.handles),
        array(graph.parent_offsets.typecode, graph.parent_offsets),
        array(graph.parent_edges.typecode, graph.parent_edges),
        array(graph.owner_keys.typecode, graph.owner_keys),
        array(graph.owner_offsets.typecode, graph.owner_offsets),
        array(graph.owner_nodes.typecode, graph.owner_nodes),
    )


def _two_key_parity() -> Counts:
    """Two genuinely overlapping cones agree with the oracle and stay distinct.

    It builds its own indexes, so it carries its own allocator and reports its
    own census: the main row's counters stay a statement about the main row.
    """
    structures = Structures()
    two = "a" * 400 + "q-r-" + "b" * 400
    kernel = _kernel(DISTANT_TWO, two)
    root = accept_handle(kernel)
    order = _preexpand(kernel, root)
    oracle = structures.dict_index(kernel, order)
    flat = structures.flat_index(kernel, order).graph
    points = _arm_points(kernel, root)
    checked = 0
    for key in points:
        if _dict_dirty(oracle, key) != _flat_dirty(flat, key):
            raise UnsupportedConstructError(
                "ambiguity RSS witness: two-key parity diverged"
            )
        checked += 1
    cones = [_flat_dirty(flat, key) for key in points]
    shared = set.intersection(*cones) if len(cones) > 1 else set()
    if len(cones) > 1 and (cones[0] == cones[1] or not shared):
        raise UnsupportedConstructError(
            "ambiguity RSS witness: parity cones must overlap without coinciding"
        )
    print(
        "two-key-parity",
        f"keys={checked}",
        f"cone_sizes={[len(cone) for cone in cones]}",
        f"shared_ancestors={len(shared)}",
        f"distinct={cones[0] != cones[1] if len(cones) > 1 else True}",
        f"own_indexes={structures.counts.dict_index + structures.counts.flat_index}",
        sep="\t",
    )
    return structures.counts


def frames_row() -> None:
    """REAL seed + trace-frame allocations, ONE child tuple per completion.

    `island_alternate_seed._record_frames` calls `Folder._kids` once per
    completed ancestor and hands THAT tuple to every seed crossing it, so the
    child tuple is a per-COMPLETION cost and the frame record is a per-seed
    one. Rule names and child meanings come from pools built outside the
    window; production shares interned names and already-built child meanings.
    """
    print("mode", "frames", "gc", _gc_state(), sep="\t")
    names = tuple(f"ancestor{level}" for level in range(8_192))
    pool: tuple[Meaning, ...] = tuple(("kid", f"value{index}") for index in range(8))
    for depth in (128, 1_024, 8_192):
        for seeds in (1, 2, 4):
            for arity in (1, 2, 4):
                _frames_case(names, pool, depth, seeds, arity)
    print(
        "note",
        "child meanings and rule names are shared by reference; the measured"
        " bytes are one kids TUPLE per completion plus one TraceFrame record"
        " per (completion, crossing seed) plus the seed records themselves",
        sep="\t",
    )


def _frames_case(
    names: tuple[str, ...],
    pool: tuple[Meaning, ...],
    depth: int,
    seeds: int,
    arity: int,
) -> None:
    """One depth × seed-count × arity row."""
    structures = Structures()
    tracemalloc.start()
    started_cpu = time.process_time()
    started_wall = time.perf_counter()
    records = [
        structures.seed(("t", "baseline"), (("t", f"alt{seed}"),))
        for seed in range(seeds)
    ]
    lanes: list[list[TraceFrame]] = [[] for _ in range(seeds)]
    for level in range(depth):
        # ONE child tuple per completed ancestor, shared by the seeds that
        # cross this completion — the `_record_frames` shape exactly.
        kids = tuple(pool[(level + slot) % len(pool)] for slot in range(arity))
        for seed in range(seeds):
            lanes[seed].append(structures.frame(0, names[level], kids, seed % arity))
    build_cpu = time.process_time() - started_cpu
    build_wall = time.perf_counter() - started_wall
    traced, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    frames = sum(len(lane) for lane in lanes)
    counts = structures.counts
    assert counts.frame == frames and counts.seed == seeds
    print(
        "frames",
        f"depth={depth}",
        f"seeds={seeds}",
        f"arity={arity}",
        f"dirty_slots={sorted({seed % arity for seed in range(seeds)})}",
        f"allocated_seed_records={counts.seed}",
        f"allocated_child_tuples={depth}",
        f"allocated_frames={counts.frame}",
        f"traced_bytes={traced}",
        f"bytes_per_completion={traced / depth:.1f}",
        f"bytes_per_frame={traced / max(frames, 1):.1f}",
        f"tracemalloc_peak={peak}",
        f"build_cpu={build_cpu:.6f}",
        f"build_wall={build_wall:.6f}",
        sep="\t",
    )
    del lanes, records


def main(arguments: Sequence[str] | None = None) -> None:
    """Run exactly one isolated row."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pad", type=int, default=2_000)
    parser.add_argument("--mode", default="ambiguity")
    options = parser.parse_args(arguments)
    if options.pad < 1 or options.pad > 200_000:
        raise UnsupportedConstructError("ambiguity RSS witness: pad out of range")
    if options.mode == "control":
        control_row(options.pad)
    elif options.mode == "ambiguity":
        ambiguity_row(options.pad)
    elif options.mode == "frames":
        frames_row()
    else:
        raise UnsupportedConstructError(
            f"ambiguity RSS witness: unsupported mode {options.mode!r}"
        )


if __name__ == "__main__":
    main()
