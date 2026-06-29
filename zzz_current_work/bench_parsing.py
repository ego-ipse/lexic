"""Parsing benchmark: Lark (``parsing/``) vs native Earley (``parsing_2/``).

Both pipelines take the same ABNF source text and produce an ``IrAst``:

  lark   : MetaGrammarParser.for_flavour(ABNF_FLAVOUR).parse(text)
  earley : reduce(parse(normalize(ABNF_GRAMMAR), text))

Improvements over the old ``z_current_work/bench_parsing.py``:

- **warm-up** before timing (drops cold import/cache samples),
- **interleaved** sampling — one sample of every variant per round, so machine
  drift hits all variants equally instead of skewing whichever ran first,
- reports **min / median / stdev** and the **earley/lark ratio** per variant,
- breaks Earley into recognize / parse / parse+reduce,
- input sizes x1/x2/x4, plus a ``--profile`` mode.

Usage:
  uv run python zzz_current_work/bench_parsing.py [label]
  uv run python zzz_current_work/bench_parsing.py --profile
"""

from __future__ import annotations

import cProfile
import gc
import pstats
import statistics
import sys
import time
from typing import Callable

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCER
from lexic.parsing.meta_parser import MetaGrammarParser
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2 import recognize as earley_recognize
from lexic.parsing_2.normalize import normalize

# ── Setup (excluded from timing) ──────────────────────────────────────
BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
LARK_PARSER = MetaGrammarParser.for_flavour(ABNF_FLAVOUR)
NORM_GRAMMAR = normalize(ABNF_GRAMMAR)
SIZES = (1, 2, 4)


def make_input(repeat: int) -> str:
    """``repeat`` concatenated copies of the ABNF-of-ABNF source.

    A concatenation of valid rulelists is itself a valid (longer) rulelist —
    parsing cost is what we measure, duplicate rule names are immaterial here.
    """
    return BASE_TEXT * repeat


# ── Variants under test ───────────────────────────────────────────────
def run_lark(text: str) -> object:
    return LARK_PARSER.parse(text)


def run_recognize(text: str) -> object:
    return earley_recognize(NORM_GRAMMAR, text)


def run_parse(text: str) -> object:
    return earley_parse(NORM_GRAMMAR, text)


def run_parse_reduce(text: str) -> object:
    return ABNF_REDUCER.apply(earley_parse(NORM_GRAMMAR, text))


# lark first so the ratio column reads "earley vs lark"
VARIANTS: dict[str, Callable[[str], object]] = {
    "lark": run_lark,
    "e:recognize": run_recognize,
    "e:parse": run_parse,
    "e:parse+reduce": run_parse_reduce,
}


def interleaved(text: str, rounds: int) -> dict[str, list[float]]:
    """Time every variant ``rounds`` times, one sample each per round (gc off).

    Interleaving makes any machine drift fall on all variants alike, so the
    cross-variant ratios stay honest even if absolute numbers wander.
    """
    samples: dict[str, list[float]] = {name: [] for name in VARIANTS}
    for fn in VARIANTS.values():  # warm up every variant first
        fn(text)
    for _ in range(rounds):
        for name, fn in VARIANTS.items():
            gc.disable()
            t0 = time.perf_counter_ns()
            fn(text)
            t1 = time.perf_counter_ns()
            gc.enable()
            samples[name].append((t1 - t0) / 1e6)
    return samples


def main(label: str) -> None:
    print(f"== parsing benchmark: {label} ==")
    print(f"base ABNF source: {len(BASE_TEXT)} chars\n")

    # correctness sanity on the base input
    lark_rules = len(list(run_lark(BASE_TEXT).rules))
    earley_ir = ABNF_REDUCER.apply(earley_parse(NORM_GRAMMAR, BASE_TEXT))
    print(
        f"lark rules={lark_rules}  earley rules={len(list(earley_ir.rules))}  "
        f"fixpoint(earley==ABNF_GRAMMAR)={earley_ir == ABNF_GRAMMAR}\n"
    )

    for repeat in SIZES:
        text = make_input(repeat)
        rounds = max(7, 40 // repeat)
        samples = interleaved(text, rounds)
        lark_med = statistics.median(samples["lark"])
        print(f"input x{repeat}  ({len(text)} chars, {rounds} rounds):")
        print(f"  {'variant':<16} {'min':>9} {'median':>9} {'stdev':>7}  vs lark")
        for name in VARIANTS:
            s = samples[name]
            med = statistics.median(s)
            ratio = med / lark_med
            tag = "—" if name == "lark" else f"{ratio:5.2f}x"
            print(
                f"  {name:<16} {min(s):7.2f}ms {med:7.2f}ms {statistics.stdev(s):6.2f}  {tag}"
            )
        print()


def profile() -> None:
    """cProfile parsing_2 parse+reduce on the x4 input."""
    text = make_input(4)
    run_parse_reduce(text)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(5):
        run_parse_reduce(text)
    pr.disable()
    print("\n=== cProfile parsing_2 (parse+reduce), x4, sorted by tottime ===")
    pstats.Stats(pr).sort_stats("tottime").print_stats(25)


if __name__ == "__main__":
    if "--profile" in sys.argv:
        profile()
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "run")
