"""Isolated reduce timing: parse once, time only ABNF_REDUCER.apply(tree).

Removes the subtract-two-minima artifact in bench_parsing.py. Reports the full
distribution (min/median/p90) so a directional shift is distinguishable from jitter.
"""

from __future__ import annotations

import gc
import statistics
import time

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCER
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2.normalize import (
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)

BASE = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
NORM = split_literals(desugar_quantifiers(flatten_groups(ABNF_GRAMMAR)))


def samples(text: str, n: int) -> list[float]:
    tree = earley_parse(NORM, text)  # parse ONCE, outside the timed loop
    out = []
    for _ in range(n):
        gc.disable()
        t0 = time.perf_counter()
        ABNF_REDUCER.apply(tree)
        t1 = time.perf_counter()
        gc.enable()
        out.append((t1 - t0) * 1e3)
    return out


def main() -> None:
    for repeat in (1, 2, 4):
        text = BASE * repeat
        s = sorted(samples(text, 60))
        p90 = s[int(len(s) * 0.9)]
        print(
            f"x{repeat} ({len(text)} chars)  reduce  "
            f"min={min(s):6.2f}ms  median={statistics.median(s):6.2f}ms  "
            f"p90={p90:6.2f}ms  n={len(s)}"
        )


if __name__ == "__main__":
    main()
