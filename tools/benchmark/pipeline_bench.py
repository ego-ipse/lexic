"""Tracked pipeline benchmark — instance parse+fold and compile-time.

Two workloads, both best/median-of-N, gc disabled per sample, warm-up work
excluded from every timed loop:

  instance parse+fold   ``CompiledGrammar.parse(text)`` over fixed corpora
                         (arithmetic ~4800 chars, c ~3280 chars). Promotes
                         ``zzz_current_work/260703-ir-codegen/bench_task7.py``'s
                         methodology verbatim — same snippets, same target
                         lengths, same sampling discipline — into a tracked
                         harness so future deltas are comparable.

  compile-time           per ground-truth grammar (json/c/arithmetic .gbnf):
                         ``canonical_grammar(text, flavour)`` alone (touches no
                         compile cache — unaffected by the below), and the full
                         ``compile_text(text, cache_key=None)``. Since Task 1,
                         ``cache_key=None`` defaults to content-keyed
                         memoisation (``(stem, flavour)``), so each
                         ``compile_text`` sample calls
                         ``lexic.compile.reset_cache_for_tests()`` first (untimed
                         setup, run before the timed region starts) to force the
                         cold path every sample. The flavour's self-grammar
                         tables are warmed with one tiny parse before timing
                         starts, so the numbers measure the compile pipeline,
                         not first-use table compilation.

Usage:
  uv run python tools/benchmark/pipeline_bench.py           # print report
  uv run python tools/benchmark/pipeline_bench.py --save    # also write pipeline_baseline.json
"""

from __future__ import annotations

import gc
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

from lexic.compile import (
    canonical_grammar,
    compile_from_path,
    compile_text,
)
from lexic.compile import parse_grammar as _warm_parse_grammar
from lexic.compile import (
    reset_cache_for_tests,
)
from lexic.grammars import flavour_for_extension
from lexic.ir.flavour import IrFlavour

ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
BASELINE_PATH = Path(__file__).parent / "pipeline_baseline.json"

# ── Workload A: instance parse+fold ─────────────────────────────────────
# Snippets and target lengths pinned verbatim from bench_task7.py so this
# harness's numbers are directly comparable to that spike's.
_ARITHMETIC_SNIPPETS = [
    # root ::= (expr "=" ws term "\n")+ — LHS is a full expr (operators OK),
    # RHS after "=" is a single term (ident / num / "(" expr ")").
    "x=1\n",
    "y=z\n",
    "a+b=100\n",
    "foo=(bar)\n",
    "abc123-xyz=42\n",
]
_C_SNIPPETS = [
    # root ::= (declaration)* — no separator required/allowed between them.
    "int foo(){}",
    "char bar(int x){}",
    "float baz(){}",
    "int qux(char y){}",
]
_INSTANCE_WORKLOADS = (
    ("arithmetic.gbnf", _ARITHMETIC_SNIPPETS, 4800),
    ("c.gbnf", _C_SNIPPETS, 3280),
)

# ── Workload B: compile-time ─────────────────────────────────────────────
_COMPILE_STEMS = ("json.gbnf", "c.gbnf", "arithmetic.gbnf")
_WARMUP_GBNF = 'root ::= "a"\n'


def _corpus(snippets: list[str], target_len: int) -> str:
    """Concatenate ``snippets`` round-robin until at least ``target_len`` chars.

    :param snippets: Valid input snippets to cycle through.
    :param target_len: Minimum length of the returned corpus.
    :returns: The concatenated corpus.
    """
    parts: list[str] = []
    total = 0
    i = 0
    while total < target_len:
        piece = snippets[i % len(snippets)]
        parts.append(piece)
        total += len(piece)
        i += 1
    return "".join(parts)


def _time_calls(
    fn: Callable[[], object], n: int, setup: Callable[[], None] | None = None
) -> tuple[float, float]:
    """Time ``n`` no-arg calls to ``fn``, gc disabled per sample.

    :param fn: The zero-argument callable to time.
    :param n: Number of samples to take.
    :param setup: Optional untimed callable run before each sample (outside
        the timed region) — e.g. resetting a cache to force a cold path.
    :returns: ``(best_ms, median_ms)`` across the samples.
    """
    samples = []
    for _ in range(n):
        if setup is not None:
            setup()
        gc.disable()
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        gc.enable()
        samples.append((t1 - t0) * 1000)
    return min(samples), statistics.median(samples)


def _run_instance_workloads() -> dict[str, dict[str, float]]:
    """Time ``CompiledGrammar.parse`` over the fixed arithmetic/c corpora.

    :returns: Stem → ``{"chars", "best_ms", "median_ms"}``.
    """
    results: dict[str, dict[str, float]] = {}
    print("== workload: instance parse+fold ==")
    for stem, snippets, target_len in _INSTANCE_WORKLOADS:
        text = _corpus(snippets, target_len)
        compiled = compile_from_path(GROUND_TRUTH / stem)
        compiled.parse(text)  # warm-up — not timed
        best, median = _time_calls(
            lambda compiled=compiled, text=text: compiled.parse(text), 15
        )
        results[stem] = {"chars": len(text), "best_ms": best, "median_ms": median}
        print(
            f"  {stem:16s} {len(text):6d} chars  best {best:7.2f} ms  "
            f"median {median:7.2f} ms"
        )
    print()
    return results


def _warm_flavours(flavours: set[IrFlavour]) -> None:
    """Warm each flavour's self-grammar normalisation with one tiny parse.

    Excludes first-use table compilation from the timed compile-time
    samples, so they measure the pipeline rather than one-time setup.

    :param flavours: The flavours about to be timed.
    """
    for flavour in flavours:
        _warm_parse_grammar(_WARMUP_GBNF, flavour)


def _run_compile_workloads() -> dict[str, dict[str, dict[str, float]]]:
    """Time ``canonical_grammar`` alone and cold-cache ``compile_text``.

    ``canonical_grammar`` touches no compile cache. ``compile_text`` defaults
    ``cache_key=None`` to content-keyed memoisation, so each sample resets
    the cache first to force the cold path (see :func:`_time_calls`'s
    ``setup``).

    :returns: Stem → phase (``"canonical_grammar"`` / ``"compile_text"``) →
        ``{"best_ms", "median_ms"}``.
    """
    texts: dict[str, str] = {}
    flavours: dict[str, IrFlavour] = {}
    for stem in _COMPILE_STEMS:
        path = GROUND_TRUTH / stem
        texts[stem] = path.read_text(encoding="utf-8")
        flavours[stem] = flavour_for_extension(path)
    _warm_flavours(set(flavours.values()))

    results: dict[str, dict[str, dict[str, float]]] = {}
    print("== workload: compile-time ==")
    for stem in _COMPILE_STEMS:
        text, flavour = texts[stem], flavours[stem]
        canon_best, canon_median = _time_calls(
            lambda text=text, flavour=flavour: canonical_grammar(text, flavour), 5
        )
        compile_best, compile_median = _time_calls(
            lambda text=text, flavour=flavour: compile_text(
                text, cache_key=None, flavour=flavour.name
            ),
            5,
            setup=reset_cache_for_tests,
        )
        results[stem] = {
            "canonical_grammar": {"best_ms": canon_best, "median_ms": canon_median},
            "compile_text": {"best_ms": compile_best, "median_ms": compile_median},
        }
        print(
            f"  {stem:16s} canonical_grammar  best {canon_best:7.2f} ms  "
            f"median {canon_median:7.2f} ms"
        )
        print(
            f"  {stem:16s} compile_text       best {compile_best:7.2f} ms  "
            f"median {compile_median:7.2f} ms"
        )
    print()
    return results


def _save_baseline(
    instance: dict[str, dict[str, float]],
    compile_time: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Write both workloads' results to :data:`BASELINE_PATH`.

    :param instance: The instance parse+fold results.
    :param compile_time: The compile-time results.
    """
    baseline = {"instance_parse": instance, "compile_time": compile_time}
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True))
    print(f"baseline saved -> {BASELINE_PATH.name}")


def main() -> None:
    """Run both workloads, print the report, and optionally save the baseline."""
    save = "--save" in sys.argv[1:]
    instance = _run_instance_workloads()
    compile_time = _run_compile_workloads()
    if save:
        _save_baseline(instance, compile_time)


if __name__ == "__main__":
    main()
