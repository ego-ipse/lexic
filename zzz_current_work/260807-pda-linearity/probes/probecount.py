"""How general is the probe quadratic? — PLAN item 1, first measurement.

`PROBE-QUADRATIC.md` measured n^2 on ONE construct of ONE grammar. Before
building the lockstep fix, the question that sizes it: does every grammar with a
repeated attempt-gated construct pay this, or is it vyx-shaped?

Counts `_probe` calls and their share of wall clock across every ground-truth
grammar, on inputs GENERATED from each grammar (the reviewer's note 3 — the
corpus never trips this at painful scale, which is exactly how it survived).

    uv run python .../probes/probecount.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import random

import common  # noqa: F401  (path bootstrap)

from lexic.compile import CompiledGrammar, compile_from_path
from lexic.generate import generate
from lexic.parsing import PdaKernel


class Counting(PdaKernel):
    """A kernel that tallies every stop-probe and what it costs."""

    calls = 0
    seconds = 0.0

    def _probe(self, arm, i, pos, taken):  # noqa: ANN001, ANN201
        """One probe — counted and timed, behaviour untouched."""
        Counting.calls += 1
        start = time.perf_counter()
        try:
            return super()._probe(arm, i, pos, taken)
        finally:
            Counting.seconds += time.perf_counter() - start


def measure(compiled: CompiledGrammar, text: str) -> tuple[float, int, float]:
    """Parse ``text`` under the counting kernel — (total, probe calls, probe s)."""
    Counting.calls, Counting.seconds = 0, 0.0
    start = time.perf_counter()
    try:
        Counting(compiled.pda_tables(), text, compiled.fold).run()
    except Exception:  # a refusal still tells us what the probes cost
        pass
    return time.perf_counter() - start, Counting.calls, Counting.seconds


def main() -> None:
    """Generate growing inputs per grammar and report the probe share."""
    print(f"{'grammar':18} {'chars':>7} {'total':>9} {'probes':>8} {'in probes':>10}  share")
    for path in sorted(common.GROUND_TRUTH.glob("*.gbnf")):
        try:
            compiled = compile_from_path(str(path))
            compiled.pda_tables()
        except Exception as refusal:
            print(f"  {path.name:16} — no PDA tables ({type(refusal).__name__})")
            continue
        rules = {str(rule.name): rule for rule in compiled.grammar.rules}
        start = str(compiled.grammar.start)
        for depth in (6, 9, 12):
            try:
                text = generate(
                    start, rules, rng=random.Random(11), max_depth=depth
                )
            except Exception as refusal:
                print(f"  {path.name:16} — generate refused ({type(refusal).__name__})")
                break
            total, calls, in_probes = measure(compiled, text)
            share = in_probes / total * 100 if total else 0
            print(
                f"  {path.name:16} {len(text):7} {total:8.3f}s {calls:8} "
                f"{in_probes:9.3f}s  {share:4.0f}%"
            )


main()
