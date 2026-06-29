"""IrMultiMap.__contains__ — the nullable set membership hot path.

In the Earley predictor, `ref in ctx.nullable` is called per prediction.
The current implementation: `key in self._table`.
The original mapping: `key in self._table` (same dict lookup).
Can we beat `key in dict`?
"""

from __future__ import annotations

import gc
import statistics
import time
import timeit

from lexic.ir.mapping8 import IrMultiMap
from lexic.ir.nodes import IrRuleRef

TRIALS = 51

_nullable: IrMultiMap = IrMultiMap()
for name in ["ws", "sp", "opt_space", "comment"]:
    ref = IrRuleRef(name)
    _nullable += (ref, ref)

# Typical mix: 30% hit (nullable), 70% miss (non-nullable)
_refs_mix = (
    [IrRuleRef("ws"), IrRuleRef("sp")] * 3
    + [
        IrRuleRef("expr"),
        IrRuleRef("term"),
        IrRuleRef("factor"),
        IrRuleRef("item"),
        IrRuleRef("rule"),
    ]
    * 7
) * 200  # 2000 checks


def bench(label, fn) -> float:
    times = []
    for _ in range(TRIALS):
        gc.disable()
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        gc.enable()
        times.append((t1 - t0) / 1_000)
    med = statistics.median(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<60} median={med:8.1f}us  stdev={stdev:6.1f}us")
    return med


print(
    f"\n== IrMultiMap.__contains__ variants ({len(_refs_mix)} checks, 30/70 hit/miss) =="
)


def _via_op():
    n = _nullable
    for ref in _refs_mix:
        _ = ref in n


def _via_table():
    table = _nullable._table
    for ref in _refs_mix:
        _ = ref in table


bench("ref in mm  (via __contains__ dunder)", _via_op)
bench("ref in mm._table (direct dict access)", _via_table)

# Overhead of the IrMultiMap.__contains__ method vs raw dict
n_rep = 100_000
n = _nullable
ref = IrRuleRef("ws")
ref_miss = IrRuleRef("expr")

t_op = timeit.timeit(lambda: ref in n, number=n_rep) * 1e6 / n_rep
t_dict = timeit.timeit(lambda: ref in n._table, number=n_rep) * 1e6 / n_rep
print(
    f"\n  per-call: ref in mm = {t_op:.3f}us  ref in mm._table = {t_dict:.3f}us  "
    f"overhead = {t_op - t_dict:.3f}us ({(t_op - t_dict) / t_dict * 100:.0f}%)"
)

t_op_miss = timeit.timeit(lambda: ref_miss in n, number=n_rep) * 1e6 / n_rep
t_dict_miss = timeit.timeit(lambda: ref_miss in n._table, number=n_rep) * 1e6 / n_rep
print(
    f"  per-call (miss): ref in mm = {t_op_miss:.3f}us  ref in mm._table = {t_dict_miss:.3f}us  "
    f"overhead = {t_op_miss - t_dict_miss:.3f}us ({(t_op_miss - t_dict_miss) / t_dict_miss * 100:.0f}%)"
)
