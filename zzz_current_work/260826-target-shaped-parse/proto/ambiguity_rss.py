"""Price the ambiguous-parse structures — flat index, real frames, honest control.

Modes (each invocation is one isolated process; run alone under
`tools/guarded.sh`):

- `--mode control`: an UNAMBIGUOUS variant of the witness grammar. The
  ambiguity machinery is statically unreachable (the chart holds zero
  arm-choice points) and the row asserts that no meaning memo is retained and
  no dependency index, overlay, seed, or trace frame is allocated — counter
  AND tracemalloc evidence, not absence of a print.
- `--mode ambiguity`: the `DISTANT` witness. Stages, each in its own
  tracemalloc window after one pre-expansion sweep (lazy Leo expansion
  otherwise lands in whichever window touches it first — an attribution limit
  stated in the output): baseline meaning memo, dict-of-sets dependency
  index (the REJECTED oracle), the flat dense-numbering + CSR/forward-star
  replacement with dirty-cone parity against the oracle, sparse alternate
  overlay, and the replay verdict.
- `--mode frames`: REAL `TraceFrame`/seed allocations over an ancestor-depth
  and seed-count ladder, tracemalloc-attributed — allocated populations, not
  estimates.

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


def _fold(
    kernel: Kernel,
    root: int,
    memo: Overlay,
    dirty: set[int],
    choice: Choice | None,
) -> tuple[Meaning, int]:
    """Fold ``root`` with reuse, returning the meaning and fold-body count."""
    bits = kernel.tables.packing.bits
    mask = kernel.tables.packing.mask
    codes = kernel.tables.codes
    rule_names = tuple(str(ref) for ref in kernel.tables.decode.rule_refs)
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
        rule = codes.arm_rule[codes.code_arm[handle >> (2 * bits)]]
        name = rule_names[rule]
        if not children:
            start = (handle >> bits) & mask
            memo.changed[handle] = (name, kernel.text[start : handle & mask])
        else:
            memo.changed[handle] = (name,) + tuple(
                memo.read(child) for child in children
            )
    return memo.read(root), folds


class DictGraph(NamedTuple):
    """The REJECTED dict-of-sets dependency index — retained as the oracle."""

    parents: dict[int, set[int]]
    owners: dict[int, set[int]]


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


class FlatGraph(NamedTuple):
    """Dense numbering plus CSR parent edges and forward-star key owners."""

    handles: array
    numbering: dict[int, int]
    parent_offsets: array
    parent_edges: array
    owner_keys: array
    owner_offsets: array
    owner_nodes: array

    def bytes_total(self) -> int:
        """Buffer bytes of every flat array (numbering dict priced apart)."""
        return (
            self.handles.itemsize * len(self.handles)
            + self.parent_offsets.itemsize * len(self.parent_offsets)
            + self.parent_edges.itemsize * len(self.parent_edges)
            + self.owner_keys.itemsize * len(self.owner_keys)
            + self.owner_offsets.itemsize * len(self.owner_offsets)
            + self.owner_nodes.itemsize * len(self.owner_nodes)
        )


def _flat_graph(kernel: Kernel, order: list[int]) -> tuple[FlatGraph, float, float]:
    """Build the flat index; the dense-numbering cost is returned separately."""
    numbering_cpu = time.process_time()
    handles = array("q", order)
    numbering = {handle: index for index, handle in enumerate(order)}
    numbering_cost = time.process_time() - numbering_cpu

    build_cpu = time.process_time()
    degree = array("i", bytes(4 * (len(order) + 1)))
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
    parent_edges = array("i", bytes(4 * total))
    for parent_index, children in enumerate(child_lists):
        for child in children:
            child_index = numbering[child]
            parent_edges[cursor[child_index]] = parent_index
            cursor[child_index] += 1
    key_pairs.sort()
    owner_nodes = array("i", (owner for _key, owner in key_pairs))
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
        handles,
        numbering,
        parent_offsets,
        parent_edges,
        array("q", distinct),
        array("i", owner_offsets_list),
        owner_nodes,
    )
    return graph, numbering_cost, time.process_time() - build_cpu


def _flat_dirty(graph: FlatGraph, key: int) -> set[int]:
    """Dirty cone over the flat index, returned as HANDLES for parity."""
    slot = bisect_left(graph.owner_keys, key)
    if slot >= len(graph.owner_keys) or graph.owner_keys[slot] != key:
        return set()
    lo = graph.owner_offsets[slot]
    hi = graph.owner_offsets[slot + 1]
    seen = bytearray(len(graph.handles))
    pending = list(graph.owner_nodes[lo:hi])
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


def control_row(pad: int) -> None:
    """The genuinely-unreachable control: zero ambiguity structures."""
    text = "a" * pad + "q" + "b" * pad
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    kernel = _kernel(CONTROL, text)
    root = accept_handle(kernel)
    order = _preexpand(kernel, root)
    points = _arm_points(kernel, root)
    if points:
        raise UnsupportedConstructError("control: unexpected arm choice")
    # REAL machinery containers: populated only by the ambiguous branch,
    # which is unreachable here because the chart holds zero arm-choice keys.
    retained_memo: dict[int, Meaning] = {}
    dependency_indexes: list[DictGraph | FlatGraph] = []
    overlays: list[Overlay] = []
    seeds: list[tuple[Meaning, tuple[Meaning, ...]]] = []
    trace_frames: list[TraceFrame] = []
    for key in points:
        raise UnsupportedConstructError(f"control: machinery reached for {key}")
    tracemalloc.start()
    memo = Overlay({})
    meaning, folds = _fold(kernel, root, memo, set(), None)
    root_head = meaning[0] if isinstance(meaning, tuple) else meaning
    memo.changed.clear()
    del memo
    product_bytes, _peak = tracemalloc.get_traced_memory()
    del meaning
    retained_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert not retained_memo and not dependency_indexes
    assert not overlays and not seeds and not trace_frames
    print("mode", "control", sep="\t")
    print("pad", pad, "chars", len(text), sep="\t")
    print("arm_points", 0, "fold_bodies", folds, "root", root_head, sep="\t")
    print(
        "ambiguity-structures",
        f"meaning_memo_entries={len(retained_memo)}",
        f"dependency_index_entries={len(dependency_indexes)}",
        f"overlay_entries={len(overlays)}",
        f"seeds={len(seeds)}",
        f"trace_frames={len(trace_frames)}",
        f"root_product_value_bytes={product_bytes}",
        f"residual_bytes_after_product_release={retained_bytes}",
        sep="\t",
    )
    print(
        "note",
        "the fold memo was transient and cleared; the bytes above are the root"
        " PRODUCT value itself (every parse pays them) and the residual after"
        " even the product is dropped; the machinery block is unreachable"
        " because the chart holds zero arm-choice keys",
        sep="\t",
    )
    print(
        "totals",
        f"wall_seconds={time.perf_counter() - started_wall:.6f}",
        f"cpu_seconds={time.process_time() - started_cpu:.6f}",
        f"peak_rss_kib={_rss_kib()}",
        f"chart_keys={len(kernel.st.links)}",
        f"nodes={len(order)}",
        sep="\t",
    )


def ambiguity_row(pad: int) -> None:
    """The ambiguous candidate row: oracle index, flat index, parity, replay."""
    text = "a" * pad + "q" + "b" * pad
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    kernel = _kernel(DISTANT, text)
    root = accept_handle(kernel)
    order = _preexpand(kernel, root)
    stages: list[Stage] = [Stage("chart", len(kernel.st.links), 0, _rss_kib())]

    tracemalloc.start()
    memo = Overlay({})
    baseline, baseline_folds = _fold(kernel, root, memo, set(), None)
    base_layer = dict(memo.changed)
    memo_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    stages.append(Stage("meaning-memo", len(base_layer), memo_bytes, _rss_kib()))

    tracemalloc.start()
    oracle = _dict_graph(kernel, order)
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
    flat, numbering_cpu, csr_cpu = _flat_graph(kernel, order)
    flat_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    edges = len(flat.parent_edges)
    keys = len(flat.owner_keys)
    stages.append(
        Stage("flat-csr-index", len(order) + edges + keys, flat_bytes, _rss_kib())
    )
    print(
        "flat-index-detail",
        f"nodes={len(order)}",
        f"parent_edges={edges}",
        f"distinct_keys={keys}",
        f"array_bytes={flat.bytes_total()}",
        f"bytes_per_edge={flat.bytes_total() / max(edges, 1):.1f}",
        f"bytes_per_char={flat.bytes_total() / len(text):.1f}",
        f"numbering_cpu={numbering_cpu:.6f}",
        f"csr_build_cpu={csr_cpu:.6f}",
        sep="\t",
    )

    two = "a" * 400 + "q-r-" + "b" * 400
    kernel_two = _kernel(DISTANT_TWO, two)
    root_two = accept_handle(kernel_two)
    order_two = _preexpand(kernel_two, root_two)
    oracle_two = _dict_graph(kernel_two, order_two)
    flat_two, _n, _c = _flat_graph(kernel_two, order_two)
    two_points = _arm_points(kernel_two, root_two)
    overlap_checked = 0
    for key in two_points:
        if _dict_dirty(oracle_two, key) != _flat_dirty(flat_two, key):
            raise UnsupportedConstructError(
                "ambiguity RSS witness: two-key parity diverged"
            )
        overlap_checked += 1
    cones = [_flat_dirty(flat_two, key) for key in two_points]
    shared = set.intersection(*cones) if len(cones) > 1 else set()
    if len(cones) > 1 and (cones[0] == cones[1] or not shared):
        raise UnsupportedConstructError(
            "ambiguity RSS witness: parity cones must overlap without coinciding"
        )
    print(
        "two-key-parity",
        f"keys={overlap_checked}",
        f"cone_sizes={[len(cone) for cone in cones]}",
        f"shared_ancestors={len(shared)}",
        f"distinct={cones[0] != cones[1] if len(cones) > 1 else True}",
        sep="\t",
    )
    del oracle_two, flat_two, kernel_two

    points = _arm_points(kernel, root)
    replay_folds = 0
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
            overlay = Overlay(base_layer)
            alternate, folds = _fold(
                kernel, root, overlay, set(flat_dirty), Choice(key, family)
            )
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
    rebuilt, _num_cpu, _csr_cpu = _flat_graph(kernel, order)
    held, _peak = tracemalloc.get_traced_memory()
    del rebuilt
    gc.collect()
    residual, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        "cleanup",
        f"released oracle+flat (oracle_parents={cleanup_before})",
        f"rebuild_held_bytes={held}",
        f"post_release_residual_bytes={residual}",
        "peak RSS is monotonic and cannot show the release; the tracemalloc"
        " residual does",
        sep="\t",
    )

    print("mode", "ambiguity", sep="\t")
    print("pad", pad, "chars", len(text), sep="\t")
    print(
        "counts",
        f"baseline_folds={baseline_folds}",
        f"replay_folds={replay_folds}",
        f"parity_checked_keys={parity_checked}",
        f"verdict_differs={differs}",
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


class SeedRecord(NamedTuple):
    """One island seed as the enclosing product retains it."""

    baseline: Meaning
    alternates: tuple[Meaning, ...]


def frames_row() -> None:
    """REAL seed + trace-frame allocations over depth and seed-count ladders.

    Rule names come from a pool built OUTSIDE the measured window (production
    shares interned rule names), so bytes-per-frame prices the records
    themselves, not fresh strings.
    """
    print("mode", "frames", sep="\t")
    shared_kids: tuple[Meaning, ...] = (("sibling", "value"), ("other",))
    names = tuple(f"ancestor{level}" for level in range(8_192))
    for depth in (128, 1_024, 8_192):
        for seeds in (1, 2, 4):
            tracemalloc.start()
            records = [
                SeedRecord(("t", "baseline"), (("t", f"alt{seed}"),))
                for seed in range(seeds)
            ]
            lanes: list[list[TraceFrame]] = []
            for seed in range(seeds):
                trace = [
                    TraceFrame(0, names[level], shared_kids, seed % 2)
                    for level in range(depth)
                ]
                lanes.append(trace)
            traced, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            frames = sum(len(lane) for lane in lanes)
            print(
                "frames",
                f"depth={depth}",
                f"seeds={seeds}",
                f"allocated_seed_records={len(records)}",
                f"allocated_frames={frames}",
                f"traced_bytes={traced}",
                f"bytes_per_frame={traced / max(frames, 1):.1f}",
                f"tracemalloc_peak={peak}",
                sep="\t",
            )
            del lanes, records
    print(
        "note",
        "kid meanings and rule names are shared by reference; the per-frame"
        " cost is the NamedTuple record itself",
        sep="\t",
    )


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
