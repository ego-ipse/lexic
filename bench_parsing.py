"""Ad-hoc benchmark: parsing/ (Lark) vs parsing_2/ (native Earley).

Both pipelines take the same ABNF source text and produce an IrAst:

  parsing/   : MetaGrammarParser.for_flavour(ABNF_FLAVOUR).parse(text)
  parsing_2/ : reduce(parse(normalize(ABNF_GRAMMAR), text))

We measure steady-state parse cost (setup excluded) at a few input sizes.
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
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)


def _normalize(g):
    return split_literals(desugar_quantifiers(flatten_groups(g)))


# ── Inputs: the ABNF-of-ABNF text, and scaled-up multiples ────────────
BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))


def make_input(repeat: int) -> str:
    """Concatenate `repeat` copies of the ABNF source (rules get suffixed
    so names stay unique-ish; parsing cost is what matters, not validity)."""
    if repeat == 1:
        return BASE_TEXT
    return "".join(BASE_TEXT for _ in range(repeat))


# ── Pre-built, setup excluded ─────────────────────────────────────────
LARK_PARSER = MetaGrammarParser.for_flavour(ABNF_FLAVOUR)
NORM_GRAMMAR = _normalize(ABNF_GRAMMAR)


def run_lark(text: str):
    return LARK_PARSER.parse(text)


def run_earley(text: str):
    tree = earley_parse(NORM_GRAMMAR, text)
    return ABNF_REDUCER.apply(tree)


def run_earley_parse_only(text: str):
    return earley_parse(NORM_GRAMMAR, text)


def run_earley_recognize(text: str):
    return earley_recognize(NORM_GRAMMAR, text)


def time_it(fn: Callable[[str], object], text: str, n: int) -> list[float]:
    samples = []
    for _ in range(n):
        gc.disable()
        t0 = time.perf_counter()
        fn(text)
        t1 = time.perf_counter()
        gc.enable()
        samples.append(t1 - t0)
    return samples


def report(label: str, samples: list[float]) -> float:
    best = min(samples)
    med = statistics.median(samples)
    print(f"  {label:10s} best={best * 1e3:8.3f}ms  median={med * 1e3:8.3f}ms")
    return best


def main() -> None:
    print(f"Base ABNF source: {len(BASE_TEXT)} chars\n")

    # correctness sanity on the base input
    lark_ir = run_lark(BASE_TEXT)
    earley_ir = run_earley(BASE_TEXT)
    print(f"Lark   produced {len(list(lark_ir.rules))} rules")
    print(f"Earley produced {len(list(earley_ir.rules))} rules")
    print(f"Earley fixpoint == ABNF_GRAMMAR: {earley_ir == ABNF_GRAMMAR}\n")

    for repeat in (1, 2, 4):
        text = make_input(repeat)
        n = max(3, 30 // repeat)
        print(f"input x{repeat}  ({len(text)} chars, {n} runs):")
        lark_best = report("lark", time_it(run_lark, text, n))
        rec_best = report("e:recognize", time_it(run_earley_recognize, text, n))
        po_best = report("e:parse", time_it(run_earley_parse_only, text, n))
        earley_best = report("e:parse+red", time_it(run_earley, text, n))
        print(
            f"  recognize={rec_best * 1e3:.1f}ms  parse={po_best * 1e3:.1f}ms  "
            f"reduce={(earley_best - po_best) * 1e3:.1f}ms"
        )
        ratio = earley_best / lark_best
        print(f"  ratio earley/lark = {ratio:.2f}x (Lark faster)\n")


def profile() -> None:
    """cProfile the parsing_2 parse+reduce on the base input."""
    text = make_input(4)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(5):
        run_earley(text)
    pr.disable()
    stats = pstats.Stats(pr)
    stats.sort_stats("tottime")
    print("\n=== cProfile parsing_2 (parse+reduce), sorted by tottime ===")
    stats.print_stats(25)


if __name__ == "__main__":
    if "--profile" in sys.argv:
        profile()
    else:
        main()
