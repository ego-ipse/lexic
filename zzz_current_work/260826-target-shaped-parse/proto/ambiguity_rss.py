"""Price the ambiguous-parse structures the §12 RSS row must observe.

One bounded distant-ambiguity witness (the `root_meaning_incremental.py`
grammar at a parametric pad) runs the REAL Earley kernel, then stages the
ambiguity machinery one structure at a time and reports each structure's
population and tracemalloc bytes beside monotonic peak RSS:

- the chart itself (the control every mode pays);
- the baseline completed-meaning memo;
- the predecessor/parent dependency index;
- the sparse alternate overlay;
- the island-seed continuation lane (O(ancestor depth), priced directly);
- one persistent sequence contribution tree over the filler items (the §8
  sequence meaning at the same document size).

Modes are separate processes so RSS rows never share an arena:
`--mode fold` is the no-ambiguity-machinery control; `--mode ambiguity`
stages everything. Run each invocation alone under `tools/guarded.sh`.
"""

from __future__ import annotations

import argparse
import resource
import time
import tracemalloc
from collections.abc import Sequence
from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
)
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


class Choice(NamedTuple):
    """One packed family selected for one ambiguity key."""

    key: int
    family: int


class Graph(NamedTuple):
    """Default-derivation dependency index — parents and key owners."""

    parents: dict[int, set[int]]
    owners: dict[int, set[int]]


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


class Branch(NamedTuple):
    """One persistent sequence contribution join with a cached size."""

    size: int
    left: "Contribution"
    right: "Contribution"


type Contribution = str | Branch


def _rss_kib() -> int:
    """This process's high-water RSS in KiB (monotonic)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


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


def _graph(kernel: Kernel, root: int) -> Graph:
    """Index the default derivation once — the priced dependency structure."""
    parents: dict[int, set[int]] = {}
    owners: dict[int, set[int]] = {}
    pending = [root]
    seen: set[int] = set()
    while pending:
        handle = pending.pop()
        if handle in seen:
            continue
        seen.add(handle)
        children, keys = _resolved(kernel, handle, None)
        for key in keys:
            owners.setdefault(key, set()).add(handle)
        for child in children:
            parents.setdefault(child, set()).add(handle)
            pending.append(child)
    return Graph(parents, owners)


def _dirty(graph: Graph, key: int) -> set[int]:
    """Handles whose meanings depend on one packed key."""
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


def _same_meaning(one: Meaning, other: Meaning) -> bool:
    """Iterative exact equality — the engine's recursive ``same_value``
    overflows the interpreter stack at this witness's depth (pad 2000 nests
    about 2000 levels through the desugared quantifier chain), which is the
    §8 iterative-walk obligation observed live."""
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


def _contribution_tree(items: Sequence[str]) -> Contribution:
    """One balanced persistent sequence meaning over the filler items."""
    level: list[Contribution] = list(items)
    while len(level) > 1:
        joined: list[Contribution] = []
        for index in range(0, len(level) - 1, 2):
            left, right = level[index], level[index + 1]
            left_size = left.size if isinstance(left, Branch) else 1
            right_size = right.size if isinstance(right, Branch) else 1
            joined.append(Branch(left_size + right_size, left, right))
        if len(level) % 2:
            joined.append(level[-1])
        level = joined
    return level[0] if level else ""


class Stage(NamedTuple):
    """One structure's population, attributed bytes, and RSS afterwards."""

    name: str
    population: int
    traced_bytes: int
    rss_kib: int


def _measure(pad: int, mode: str) -> None:
    """Run one isolated row: parse, fold, then stage the ambiguity machinery."""
    text = "a" * pad + "q" + "b" * pad
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    ast = normalize(canonical_grammar(DISTANT, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("ambiguity RSS witness: no parse")
    root = accept_handle(kernel)
    stages: list[Stage] = [Stage("chart", len(kernel.st.links), 0, _rss_kib())]

    tracemalloc.start()
    memo = Overlay({})
    baseline, baseline_folds = _fold(kernel, root, memo, set(), None)
    base_layer = dict(memo.changed)
    memo_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    stages.append(Stage("meaning-memo", len(base_layer), memo_bytes, _rss_kib()))

    replay_folds = 0
    differs = False
    if mode == "ambiguity":
        tracemalloc.start()
        graph = _graph(kernel, root)
        graph_bytes, _peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        stages.append(
            Stage(
                "dependency-index",
                len(graph.parents) + len(graph.owners),
                graph_bytes,
                _rss_kib(),
            )
        )
        bits = kernel.tables.packing.bits
        for key in ambiguity_points(kernel, root):
            bucket = kernel.st.links[key]
            if not is_arm_choice(bucket, bits, kernel.tables.code_choice):
                continue
            for family in range(1, len(bucket)):
                tracemalloc.start()
                overlay = Overlay(base_layer)
                alternate, folds = _fold(
                    kernel, root, overlay, _dirty(graph, key), Choice(key, family)
                )
                overlay_bytes, _peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                replay_folds += folds
                stages.append(
                    Stage(
                        "alternate-overlay",
                        len(overlay.changed),
                        overlay_bytes,
                        _rss_kib(),
                    )
                )
                if not _same_meaning(baseline, alternate):
                    differs = True
        if not differs:
            raise UnsupportedConstructError(
                "ambiguity RSS witness: expected a differing root meaning"
            )
        seed_frames = len(_dirty(graph, root)) + 1
        stages.append(Stage("island-seed-lane", seed_frames, 0, _rss_kib()))

        tracemalloc.start()
        tree = _contribution_tree(tuple(text))
        tree_bytes, _peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        population = tree.size if isinstance(tree, Branch) else 1
        stages.append(
            Stage("sequence-contribution-tree", population, tree_bytes, _rss_kib())
        )

    wall = time.perf_counter() - started_wall
    cpu = time.process_time() - started_cpu
    print("mode", mode, sep="\t")
    print("pad", pad, "chars", len(text), sep="\t")
    print("baseline_folds", baseline_folds, "replay_folds", replay_folds, sep="\t")
    for stage in stages:
        print(
            "stage",
            stage.name,
            f"population={stage.population}",
            f"traced_bytes={stage.traced_bytes}",
            f"rss_kib={stage.rss_kib}",
            sep="\t",
        )
    print("verdict_differs", differs if mode == "ambiguity" else "n/a", sep="\t")
    print(
        "totals",
        f"wall_seconds={wall:.6f}",
        f"cpu_seconds={cpu:.6f}",
        f"peak_rss_kib={_rss_kib()}",
        sep="\t",
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Run exactly one isolated scale/mode row."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pad", type=int, required=True)
    parser.add_argument("--mode", default="ambiguity")
    options = parser.parse_args(arguments)
    if options.mode not in ("ambiguity", "fold"):
        raise UnsupportedConstructError(
            f"ambiguity RSS witness: unsupported mode {options.mode!r}"
        )
    if options.pad < 1 or options.pad > 200_000:
        raise UnsupportedConstructError(
            "ambiguity RSS witness: pad outside the bounded range"
        )
    _measure(options.pad, options.mode)


if __name__ == "__main__":
    main()
