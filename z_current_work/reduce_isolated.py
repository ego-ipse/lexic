"""Isolated, repeated timing of recognize / build / reduce on the ABNF workload.

Run this with the CURRENT normalize.py state (right- or left-recursive). It
prints median + min + stdev per phase so signal is separable from noise. The
key point vs bench_parsing.py: it times reduce IN ISOLATION (parse the tree
once, then fold it repeatedly) instead of subtracting two noisy minimums.
"""

from __future__ import annotations

import gc
import statistics
import time
from typing import Callable

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCER
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2 import recognize as earley_recognize
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)


def _normalize(g):
    return split_literals(desugar_quantifiers(flatten_groups(g)))


BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
NORM = _normalize(ABNF_GRAMMAR)


def samples(fn: Callable[[], object], n: int) -> list[float]:
    out = []
    for _ in range(n):
        gc.disable()
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
        gc.enable()
    return out


def report(label: str, s: list[float]) -> None:
    print(
        f"  {label:14s} median={statistics.median(s) * 1e3:8.3f}ms  "
        f"min={min(s) * 1e3:8.3f}ms  stdev={statistics.pstdev(s) * 1e3:6.3f}ms"
    )


def main() -> None:
    for repeat in (1, 2, 4):
        text = BASE_TEXT * repeat
        n = max(8, 60 // repeat)
        # Build the tree ONCE so reduce is timed in isolation.
        tree = earley_parse(NORM, text)
        print(f"\ninput x{repeat} ({len(text)} chars, {n} runs):")
        report("recognize", samples(lambda t=text: earley_recognize(NORM, t), n))
        report("parse(build)", samples(lambda t=text: earley_parse(NORM, t), n))
        report("reduce-only", samples(lambda tr=tree: ABNF_REDUCER.apply(tr), n))


if __name__ == "__main__":
    main()
