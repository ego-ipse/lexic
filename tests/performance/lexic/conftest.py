"""Helpers for performance tests — guarded subprocess runner and timer."""

from __future__ import annotations

import multiprocessing
import multiprocessing.queues
import resource
import signal
import time
from typing import Any, Callable, Literal

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing.parallel import reset_pools

# ── Sentinel values returned by guarded() ────────────────────────────

TIMED_OUT: Literal["timed_out"] = "timed_out"
MEMORY_EXCEEDED: Literal["memory_exceeded"] = "memory_exceeded"

GuardedResult = Any | Literal["timed_out", "memory_exceeded"]


def _vm_size() -> int:
    """This process's current virtual size in bytes, from ``/proc``."""
    with open("/proc/self/status", encoding="ascii") as status:
        for line in status:
            if line.startswith("VmSize"):
                return int(line.split()[1]) * 1024
    return 0


def guarded_worker(
    fn: Callable[[], Any],
    mem_bytes: int,
    cpu_seconds: int,
    result_queue: multiprocessing.queues.Queue[tuple[str, Any]],
) -> None:
    """Child-process target: apply the limits, call fn, put result on queue.

    ``mem_bytes`` is a BUDGET for the guarded work, applied on top of the
    child's inherited address space — an absolute cap would measure the
    parent's allocation history (a fork after a long suite inherits gigabytes
    of arenas), exactly as a wall clock measures the machine's load. A
    runaway allocation blows through any budget; an innocent child under a
    fat parent does not.
    """
    try:
        budget = _vm_size() + mem_bytes
        resource.setrlimit(resource.RLIMIT_AS, (budget, budget))
    except ValueError, OSError:
        pass  # platform without /proc or one refusing the limit
    try:
        # SIGXCPU at the soft limit, SIGKILL one second later — the child dies
        # either way and the parent reads the empty queue as the bound firing.
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    except ValueError:
        pass
    try:
        value = fn()
    except MemoryError:
        result_queue.put(("oom", None))
        return
    result_queue.put(("ok", value))


_CPU_SIGNALS = frozenset({signal.SIGXCPU, signal.SIGKILL})
"""How a child dies when RLIMIT_CPU fires — ``SIGXCPU`` at the soft limit, and
``SIGKILL`` at the hard one a second later if it somehow survives that."""

HANG_BACKSTOP = 120.0
"""Wall-clock ceiling, generous by design. It is NOT the gate: a wall bound on
a machine running the suite under ``-n auto`` measures scheduler starvation,
not the parse, and a contended run would fail a gate about runaway work. This
exists only so a genuinely hung child cannot wedge the suite forever."""


def guarded(fn: Callable[[], Any], *, seconds: float, mem_bytes: int) -> GuardedResult:
    """Run ``fn`` in a child process bounded by CPU time and virtual memory.

    ``seconds`` bounds **CPU time**, not wall clock. What these gates catch is
    runaway or exponential work, and that is a CPU property: an exponential
    enumeration burns through any CPU budget whatever else the machine is
    doing, while a merely descheduled process burns none. Wall clock conflates
    the two, and under sixteen xdist workers plus a memory-capped subprocess it
    reports starvation as a parse regression.

    :param fn: The zero-argument callable to run.
    :param seconds: CPU-time budget (RLIMIT_CPU); returns :data:`TIMED_OUT`
        when the child exhausts it.
    :param mem_bytes: Virtual-address BUDGET for the guarded work (RLIMIT_AS
        set to the child's inherited size plus this); returns
        :data:`MEMORY_EXCEEDED` when the child process OOMs.
    :returns: The return value of ``fn``, :data:`TIMED_OUT`, or
        :data:`MEMORY_EXCEEDED`.
    """
    # Fork safety, not perf: a forked child of a threaded parent inherits
    # every lock in whatever state the owning thread left it, and this test
    # process holds live split-parse worker pools once any split engaged.
    # Releasing them first is the engine's own seam for exactly this state.
    reset_pools()
    ctx = multiprocessing.get_context("fork")
    q: multiprocessing.queues.Queue[tuple[str, Any]] = ctx.Queue()
    cpu = max(1, int(seconds))
    proc = ctx.Process(target=guarded_worker, args=(fn, mem_bytes, cpu, q))
    proc.start()
    proc.join(timeout=HANG_BACKSTOP)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return TIMED_OUT
    if q.empty() and proc.exitcode is not None and -proc.exitcode in _CPU_SIGNALS:
        return TIMED_OUT  # RLIMIT_CPU fired: SIGXCPU at the soft limit, then KILL
    if q.empty():
        # Process died (OOM via SIGKILL from OS, or RLIMIT_AS SIGSEGV)
        return MEMORY_EXCEEDED
    tag, value = q.get_nowait()
    if tag == "oom":
        return MEMORY_EXCEEDED
    return value


def timed(fn: Callable[[], Any]) -> tuple[Any, float]:
    """Run ``fn`` and return ``(result, elapsed_seconds)`` using :func:`time.perf_counter`.

    :param fn: The zero-argument callable to time.
    :returns: ``(result, seconds)``.
    """
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def rep_grammar() -> IrAst:
    """Right-recursive repetition grammar: list = elem list / elem ; elem = [a-z].

    This is the CURRENT shape (right-recursive, O(n²) parse, O(n) chart). The
    upcoming F1 optimisation will change it; the benchmark captures the baseline.
    """
    elem_rule = IrRule(
        "elem",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    list_rule = IrRule(
        "list",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("elem")), IrItem(IrRuleRef("list"))),
            IrSequence(IrItem(IrRuleRef("elem"))),
        ),
    )
    return IrAst(rules=IrSeq(list_rule, elem_rule), start="list")
