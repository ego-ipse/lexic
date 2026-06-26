"""Helpers for performance tests — guarded subprocess runner and timer."""

from __future__ import annotations

import multiprocessing
import multiprocessing.queues
import resource
import time
from typing import Any, Callable, Literal

from lexic.ir.base import IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)

# ── Sentinel values returned by guarded() ────────────────────────────

TIMED_OUT: Literal["timed_out"] = "timed_out"
MEMORY_EXCEEDED: Literal["memory_exceeded"] = "memory_exceeded"

_GuardedResult = Any | Literal["timed_out", "memory_exceeded"]


def _worker(
    fn: Callable[[], Any],
    mem_bytes: int,
    result_queue: multiprocessing.queues.Queue[tuple[str, Any]],
) -> None:
    """Child-process target: apply a memory limit, call fn, put result on queue."""
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except ValueError:
        pass  # platform may disallow lowering AS limit below current usage
    try:
        value = fn()
    except MemoryError:
        result_queue.put(("oom", None))
        return
    result_queue.put(("ok", value))


def guarded(fn: Callable[[], Any], *, seconds: float, mem_bytes: int) -> _GuardedResult:
    """Run ``fn`` in a child process bounded by wall-clock time and virtual memory.

    :param fn: The zero-argument callable to run.
    :param seconds: Wall-clock timeout; returns :data:`TIMED_OUT` on expiry.
    :param mem_bytes: Virtual-address limit (RLIMIT_AS); returns
        :data:`MEMORY_EXCEEDED` when the child process OOMs.
    :returns: The return value of ``fn``, :data:`TIMED_OUT`, or
        :data:`MEMORY_EXCEEDED`.
    """
    ctx = multiprocessing.get_context("fork")
    q: multiprocessing.queues.Queue[tuple[str, Any]] = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(fn, mem_bytes, q))
    proc.start()
    proc.join(timeout=seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return TIMED_OUT
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
