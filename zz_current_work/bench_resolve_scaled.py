"""Resolve EAFP: check at various N to find the true speedup."""

from __future__ import annotations

import gc
import statistics
import time

from lexic.exceptions import IrKeyError
from lexic.ir.action import IrThis
from lexic.ir.base import IrNone, IrNoneType, IrTuple
from lexic.ir.mapping8 import IR_DEFAULT
from lexic.ir.mapping8 import IrTypeMap as IrTypeMap8
from lexic.ir.nodes import IrCharClass, IrLiteral, IrRange, IrRuleRef

TRIALS = 51
_SENTINEL = object()

_earley_td = (
    IrTuple(IrRuleRef, IrThis()),
    IrTuple(IrLiteral, IrThis()),
    IrTuple(IrCharClass, IrThis()),
    IrTuple(IrRange, IrThis()),
    IrTuple(IrNoneType, IrThis()),
)
_earley_tm8 = IrTypeMap8(*_earley_td)


def _eafp_resolve(self, n):
    table = self._table
    t = type(n)
    try:
        return table[t]
    except KeyError:
        for base in t.__mro__:
            body = table.get(base)
            if body is not None:
                return body
        body = table.get(IR_DEFAULT)
        if body is not None:
            return body
        raise IrKeyError(f"{type(self).__name__}: no entry for {type(n).__name__}")


_orig_resolve = IrTypeMap8.resolve


def bench_n(n, label_prefix=""):
    nodes = (
        [IrRuleRef("expr")] * 60
        + [IrLiteral("a")] * 20
        + [IrNone] * 15
        + [IrCharClass()] * 5
    ) * (n // 100)

    def _current():
        tm = _earley_tm8
        for nd in nodes:
            tm.resolve(nd)

    IrTypeMap8.resolve = _eafp_resolve

    def _eafp():
        tm = _earley_tm8
        for nd in nodes:
            tm.resolve(nd)

    IrTypeMap8.resolve = _orig_resolve

    times_c = []
    times_e = []
    for _ in range(TRIALS):
        gc.disable()
        t0 = time.perf_counter_ns()
        _current()
        t1 = time.perf_counter_ns()
        gc.enable()
        times_c.append(t1 - t0)

        IrTypeMap8.resolve = _eafp_resolve
        gc.disable()
        t0 = time.perf_counter_ns()
        _eafp()
        t1 = time.perf_counter_ns()
        gc.enable()
        IrTypeMap8.resolve = _orig_resolve
        times_e.append(t1 - t0)

    mc = statistics.median(times_c) / 1e3
    me = statistics.median(times_e) / 1e3
    print(f"  N={n:6d}: current={mc:7.1f}us  eafp={me:7.1f}us  ratio={mc / me:.2f}x")


print("\n== IrTypeMap.resolve: current vs EAFP at varying N ==")
for n in [100, 500, 1000, 2000, 5000, 10000, 50000]:
    bench_n(n)
