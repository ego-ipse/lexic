"""Tracked pipeline benchmark — instance parse+fold and compile-time.

Two workloads, both best/median-of-N, gc disabled per sample, warm-up work
excluded from every timed loop:

  instance parse+fold   ``CompiledGrammar.parse(text)`` over fixed corpora
                         (arithmetic ~4800 chars, c ~3280 chars). Promotes
                         ``zzz_current_work/260703-ir-codegen/bench_task7.py``'s
                         methodology verbatim — same snippets, same target
                         lengths, same sampling discipline — into a tracked
                         harness so future deltas are comparable. Chess and
                         json corpora (~4200 chars each) joined 2026-07-05 for
                         the hybrid-PDA effort (island-heavy shapes; see
                         ``zzz_current_work/260705-hybrid-parse-poc/PLAN.md``);
                         each is one whole-input parse (a single game / a
                         single JSON document), pinned here like the others.

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
import random
import statistics
import sys
import time
from collections.abc import Sequence
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
from tests.integration.pda_parity_helpers import (
    ARITHMETIC_BENCH_SNIPPETS as _ARITHMETIC_SNIPPETS,
)
from tests.integration.pda_parity_helpers import JSON_BENCH_ITEMS as _JSON_ITEMS

ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
BASELINE_PATH = Path(__file__).parent / "pipeline_baseline.json"

# ── Workload A: instance parse+fold ─────────────────────────────────────
# Snippets and target lengths pinned verbatim from bench_task7.py so this
# harness's numbers are directly comparable to that spike's.
_C_SNIPPETS = [
    # root ::= (declaration)* — no separator required/allowed between them.
    "int foo(){}",
    "char bar(int x){}",
    "float baz(){}",
    "int qux(char y){}",
]
# root ::= "1. " move " " move "\n" ([1-9] [0-9]? ". " move " " move "\n")+
# — one continuous game; line numbers cycle 2..99 ([1-9][0-9]? admits any
# 1-2 digit number, sequence not required). Pairs exercise every move arm:
# pawn (incl. capture + promotion), nonpawn (incl. disambiguators — the
# PoC's one chess island), castle, and [+#] suffixes.
_CHESS_OPENING = "1. e4 e5\n"
_CHESS_PAIRS = [
    "Nf3 Nc6",
    "Bb5 a6",
    "Bxc6 dxc6",
    "O-O f6",
    "d4 exd4",
    "Nxd4 c5",
    "Nb3 Qxd1+",
    "Rxd1 Bg4",
    "f3 Be6",
    "Nc3 Bd6",
    "Be3 b6",
    "a4 Kf7",
    "a5 Ne7",
    "Rd2 Rd8",
    "Rad1 Bc8",
    "h3 h5",
    "Kf2 Nc6",
    "Nd5 Bxd5",
    "exd5 Ne7",
    "axb6 cxb6",
    "c4 e8=Q",
    "O-O-O Kg6",
    "g4 hxg4",
    "hxg4 Rh8#",
]
# JSON-text ::= ws value ws — one document; the items cycle inside a single
# top-level array. Escapes (\" \\ \uXXXX \t), frac/exp numbers, and nested
# containers exercise the PoC's json islands (value/char arm overlaps,
# string loops) and the ws noise shapes (pivots 4/5). Escapes parse since
# the 2026-07-05 mixed-group fix (see the 260705 plan ledger).


def _chess_corpus(target_len: int) -> str:
    """One continuous chess game of at least ``target_len`` chars.

    :param target_len: Minimum length of the returned corpus.
    :returns: The game text (opening line + cycled numbered move pairs).
    """
    parts = [_CHESS_OPENING]
    total = len(_CHESS_OPENING)
    i = 0
    while total < target_len:
        piece = f"{2 + i % 98}. {_CHESS_PAIRS[i % len(_CHESS_PAIRS)]}\n"
        parts.append(piece)
        total += len(piece)
        i += 1
    return "".join(parts)


def _json_corpus(target_len: int) -> str:
    """One JSON document of at least ``target_len`` chars.

    :param target_len: Minimum length of the returned corpus.
    :returns: A single top-level array cycling the pinned items.
    """
    items: list[str] = []
    total = 0
    i = 0
    while total < target_len:
        piece = _JSON_ITEMS[i % len(_JSON_ITEMS)]
        items.append(piece)
        total += len(piece) + 4
        i += 1
    return "[\n  " + ",\n  ".join(items) + "\n]\n"


_INSTANCE_WORKLOADS: tuple[tuple[str, Callable[[], str]], ...] = (
    ("arithmetic.gbnf", lambda: _corpus(_ARITHMETIC_SNIPPETS, 4800)),
    ("c.gbnf", lambda: _corpus(_C_SNIPPETS, 3280)),
    ("chess.gbnf", lambda: _chess_corpus(4200)),
    ("json.gbnf", lambda: _json_corpus(4200)),
)

# ── Workload A2: non-repeated json corpus (additive; NOT in _INSTANCE_WORKLOADS —
#    compare_bench.py imports that tuple and double-keys each stem against both
#    GROUND_TRUTH and lark_refs, so a corpus without its own ground-truth file
#    stays out of it. Wired into _run_instance_workloads below instead.) ──────
_VARIED_SEED = 260720
_VARIED_KEYS = (
    "id",
    "name",
    "email",
    "active",
    "score",
    "tags",
    "meta",
    "created_at",
    "updated_at",
    "children",
    "parent",
    "config",
    "items",
    "count",
    "ratio",
    "description",
    "status",
    "owner",
    "region",
    "flags",
)


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _json_varied_scalar(rng: random.Random, kind: str) -> JsonValue:
    """Build one scalar JSON leaf of the given kind.

    :param rng: The seeded random source (reproducible across runs).
    :param kind: One of ``"str"``/``"int"``/``"float"``/``"bool"``/``"null"``.
    :returns: The generated scalar.
    """
    if kind == "str":
        length = rng.randint(3, 12)
        return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz_") for _ in range(length))
    if kind == "int":
        return rng.randint(-10_000, 10_000)
    if kind == "float":
        return round(rng.uniform(-1000.0, 1000.0), 4)
    if kind == "bool":
        return rng.choice([True, False])
    return None  # "null"


def _json_varied_value(rng: random.Random, depth: int) -> JsonValue:
    """Build one randomly-shaped JSON-serializable value.

    :param rng: The seeded random source (reproducible across runs).
    :param depth: Remaining nesting budget; ``0`` forces a scalar leaf.
    :returns: A JSON-serializable value.
    """
    kinds = ("str", "int", "float", "bool", "null")
    if depth > 0:
        kinds += ("array", "object")
    kind = rng.choice(kinds)
    if kind == "array":
        return [_json_varied_value(rng, depth - 1) for _ in range(rng.randint(0, 4))]
    if kind == "object":
        keys = rng.sample(_VARIED_KEYS, k=rng.randint(1, 5))
        return {key: _json_varied_value(rng, depth - 1) for key in keys}
    return _json_varied_scalar(rng, kind)


def _json_varied_corpus(target_len: int, seed: int = _VARIED_SEED) -> str:
    """A single NON-REPEATED JSON document, seeded for reproducibility.

    Unlike :func:`_json_corpus` (which cycles six fixed items — friendly to
    string/model interning), every value here is freshly drawn from a
    seeded RNG: object keys sampled per-object from a 20-key pool (never
    the same set twice), nesting up to 3 levels deep, and every scalar
    kind mixed in — random lowercase strings, ints, floats, bools, and
    null — plus arrays and nested objects at every level. Shape mix: a
    top-level array of independently-generated values, each 0-4 levels
    deep, each object 1-5 keys wide. No two generated values are expected
    to repeat, so this corpus does not benefit from interning the way the
    cycled corpus would — the honest single-pass estimate Task 5's
    interning gate reads.

    :param target_len: Minimum length of the returned corpus, in characters.
    :param seed: RNG seed — fixed by default so the corpus is reproducible.
    :returns: A single top-level JSON array of varied-shape values.
    """
    rng = random.Random(seed)
    items: list[JsonValue] = []
    text = "[]"
    while len(text) < target_len:
        items.append(_json_varied_value(rng, depth=3))
        text = json.dumps(items, indent=2)
    return text + "\n"


# ── Workload B: compile-time ─────────────────────────────────────────────
_COMPILE_STEMS = ("json.gbnf", "c.gbnf", "arithmetic.gbnf")
_WARMUP_GBNF = 'root ::= "a"\n'


def _corpus(snippets: Sequence[str], target_len: int) -> str:
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
    for stem, make_corpus in _INSTANCE_WORKLOADS:
        text = make_corpus()
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
    results["json_varied"] = _run_json_varied_workload()
    print()
    return results


def _run_json_varied_workload() -> dict[str, float]:
    """Time ``CompiledGrammar.parse`` over the non-repeated json corpus.

    Reuses ``json.gbnf`` (the same grammar the cycled ``json.gbnf`` workload
    compiles) — only the corpus differs, so the two rows read as a direct
    repeated-vs-non-repeated comparison.

    :returns: ``{"chars", "best_ms", "median_ms"}`` for the ``json_varied`` row.
    """
    text = _json_varied_corpus(4600)
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    compiled.parse(text)  # warm-up — not timed
    best, median = _time_calls(
        lambda compiled=compiled, text=text: compiled.parse(text), 15
    )
    print(
        f"  {'json_varied':16s} {len(text):6d} chars  best {best:7.2f} ms  "
        f"median {median:7.2f} ms"
    )
    return {"chars": len(text), "best_ms": best, "median_ms": median}


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
