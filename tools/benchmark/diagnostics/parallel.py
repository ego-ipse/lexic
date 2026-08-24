"""The parallel layer's report — what splitting can do, per grammar, HERE.

Three tables, all derived through the standard pipeline (no formulation is
privileged): the anchor analysis and site multiplicity, the derived roles
(pairs + separators) with the scan's verdict on each grammar's own corpus,
and the worker-count policy's answer on THIS machine (interpreter, GIL
state, cores) for representative document sizes.

When the interpreter is free-threaded with at least two cores, the report
also measures document-level speedup — N threads parsing N copies of the
corpus against one shared artefact. On a GIL build it prints the gate
reason instead of a misleading number: splitting there measured 0.82–0.92x.

    uv run python -m tools.benchmark.diagnostics.parallel
"""

from __future__ import annotations

import os
import sys
import threading
import time

from lexic.parsing.parallel import (
    MIN_CHUNK,
    Scanner,
    anchor_sites,
    anchors,
    roles,
    worker_count,
)
from tools.benchmark.cases.grammars import BENCHES


def _free_threaded() -> bool:
    """Whether this interpreter runs without the GIL (free-threaded build)."""
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


def analysis_table() -> None:
    """Print each grammar's derived anchors, site multiplicity and roles."""
    print("=== anchors and roles (derived, per grammar) ===")
    print(
        f"{'grammar':<12} {'anchors':>7} {'multi':>6}  {'chars':<22} {'pairs':<16} separators"
    )
    for bench in BENCHES:
        grammar = bench.compiled.codegen_grammar
        certified = anchors(grammar)
        multi = sum(1 for sites in anchor_sites(grammar).values() if len(sites) > 1)
        derived = roles(grammar)
        pairs = " ".join(f"{o}{c}" for o, c in derived.pairs) or "-"
        seps = "".join(sorted(derived.separators))
        shown = "".join(sorted(certified))[:20]
        print(
            f"{bench.name:<12} {len(certified):>7d} {multi:>6d}  "
            f"{shown!r:<22} {pairs:<16} {seps or '-'!r}"
        )


def scan_table() -> None:
    """Print each grammar's split-point supply on its own corpus."""
    print("\n=== scan verdict on each grammar's own corpus ===")
    print(f"{'grammar':<12} {'chars':>8} {'depth0':>8} {'depth1':>8}  workers (auto)")
    for bench in BENCHES:
        derived = roles(bench.compiled.codegen_grammar)
        scanner = Scanner(derived)
        window = scanner.window(bench.corpus, 0, len(bench.corpus))
        top = len(scanner.offsets([window], depth=0))
        inner = len(scanner.offsets([window], depth=1))
        auto = worker_count(len(bench.corpus), max(top, inner))
        print(f"{bench.name:<12} {len(bench.corpus):>8d} {top:>8d} {inner:>8d}  {auto}")


def policy_table() -> None:
    """Print the worker-count policy's answers for this machine."""
    cpus = os.process_cpu_count() or 1
    print("\n=== policy on this machine ===")
    print(
        f"python {sys.version.split()[0]}  free-threaded={_free_threaded()}  "
        f"cpus={cpus}  chunk floor={MIN_CHUNK // 1024} KiB"
    )
    print(f"{'size':>10} {'splits':>8} -> workers (auto)")
    for size in (16 * 1024, 128 * 1024, 1024 * 1024, 16 * 1024 * 1024):
        print(f"{size:10d} {1000:8d} -> {worker_count(size, 1000):d}")


def doc_level_speedup() -> None:
    """Measure N threads × N documents against one shared artefact, or say why not."""
    print("\n=== document-level speedup (shared artefact, N threads) ===")
    if not _free_threaded():
        print("gated: GIL build — splitting measured 0.82-0.92x here, not run")
        return
    cpus = os.process_cpu_count() or 1
    if cpus < 2:
        print("gated: one core — nothing to win, not run")
        return
    bench = next(b for b in BENCHES if b.name == "json")
    parse = bench.compiled.parse
    parse(bench.corpus)
    for threads in (1, 2, 4, min(8, cpus)):
        started = time.perf_counter()
        pool = [
            threading.Thread(target=parse, args=(bench.corpus,)) for _ in range(threads)
        ]
        for worker in pool:
            worker.start()
        for worker in pool:
            worker.join()
        elapsed = time.perf_counter() - started
        print(f"threads={threads:<3d} {threads} docs in {elapsed * 1e3:.1f} ms")


def main() -> None:
    """Print every parallel-layer table for this machine."""
    analysis_table()
    scan_table()
    policy_table()
    doc_level_speedup()


if __name__ == "__main__":
    main()
