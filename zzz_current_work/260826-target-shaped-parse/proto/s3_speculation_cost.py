"""Measure valid and failed speculation against large retained builders.

The §3 claim under test: a mark is constant size and undo is proportional to
what was MUTATED since the mark — not to what the builders already hold. That
is the difference between speculation costing what it did and speculation
costing what exists, and it is the property a deep PDA attempt over a
half-built document depends on.

Method, per docs/STYLE.md §7: `time.process_time()` rather than wall clock, so
a loaded machine stops mattering; repeated trials taking the MIN, so a
scheduler hiccup cannot inflate a row; and the retained size varied across two
orders of magnitude with the mutation count held fixed. A cost proportional to
mutations reads FLAT across those rows; a cost proportional to retained size
reads as a straight multiple of it.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import time
from typing import NamedTuple

from lexic.exceptions import SemanticVerdict
from lexic.parsing.product import ParseState

RETAINED = (10_000, 100_000, 1_000_000)
"""Values already committed before speculation opens — two orders of magnitude."""

MUTATIONS = 64
"""Mutations performed inside the speculation. Held FIXED across every row, so
a flat column is proportional-to-mutations and a rising one is not."""

TRIALS = 5
"""Repeats per row; the minimum is reported (a slower run only ever means the
machine interfered)."""


class Row(NamedTuple):
    """One retained size and what speculation cost at it, in CPU seconds."""

    retained: int
    mark: float
    rollback: float
    commit: float


def _loaded(retained: int) -> ParseState[int]:
    """A state holding ``retained`` committed values, outside any transaction."""
    state: ParseState[int] = ParseState()
    handle = state.begin_sequence()
    for value in range(retained):
        state.append_sequence(handle, value)
    return state


def _time_rollback(retained: int) -> float:
    """CPU seconds for mark + MUTATIONS appends + rollback."""
    best = float("inf")
    for _ in range(TRIALS):
        state = _loaded(retained)
        handle = state.begin_sequence()
        started = time.process_time()
        mark = state.mark()
        for value in range(MUTATIONS):
            state.append_sequence(handle, value)
        state.rollback(mark)
        best = min(best, time.process_time() - started)
    return best


def _time_commit(retained: int) -> float:
    """CPU seconds for mark + MUTATIONS appends + commit."""
    best = float("inf")
    for _ in range(TRIALS):
        state = _loaded(retained)
        handle = state.begin_sequence()
        started = time.process_time()
        mark = state.mark()
        for value in range(MUTATIONS):
            state.append_sequence(handle, value)
        state.commit(mark)
        best = min(best, time.process_time() - started)
    return best


def _time_mark(retained: int) -> float:
    """CPU seconds for one mark/commit pair alone — the transaction's floor."""
    best = float("inf")
    for _ in range(TRIALS):
        state = _loaded(retained)
        started = time.process_time()
        state.commit(state.mark())
        best = min(best, time.process_time() - started)
    return best


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 speculation: {claim}")


def rollback_restores_exactly_the_speculation() -> None:
    """Correctness first: a measurement of the wrong thing is worthless."""
    state: ParseState[int] = ParseState()
    handle = state.begin_sequence()
    for value in range(1000):
        state.append_sequence(handle, value)
    mapping = state.begin_mapping()
    state.insert_mapping(mapping, "kept", 1, SemanticVerdict("dup", "kept"))

    mark = state.mark()
    for value in range(MUTATIONS):
        state.append_sequence(handle, -value)
    state.insert_mapping(mapping, "spec", 2, SemanticVerdict("dup", "spec"))
    state.rollback(mark)

    _check(
        "rollback did not restore the sequence exactly",
        state.finish_sequence(handle) == tuple(range(1000)),
    )
    _check(
        "rollback did not restore the mapping exactly",
        state.finish_mapping(mapping) == (("kept", 1),),
    )
    print("correctness\trollback restores the pre-mark state exactly")


def speculation_is_proportional_to_mutations() -> None:
    """The headline: cost is flat as retained size grows 100x."""
    rows = [
        Row(size, _time_mark(size), _time_rollback(size), _time_commit(size))
        for size in RETAINED
    ]
    print(f"{'retained':>10} {'mark+commit':>13} {'rollback':>12} {'commit':>12}")
    for row in rows:
        print(
            f"{row.retained:>10} {row.mark:>13.6f} {row.rollback:>12.6f} "
            f"{row.commit:>12.6f}"
        )

    smallest, largest = rows[0], rows[-1]
    growth = largest.retained / smallest.retained
    for label, small, large in (
        ("rollback", smallest.rollback, largest.rollback),
        ("commit", smallest.commit, largest.commit),
        ("mark+commit", smallest.mark, largest.mark),
    ):
        # A cost proportional to RETAINED would rise by ~100x here. Timing at
        # this scale is noisy in absolute terms, so the bar is deliberately
        # loose: anything under a small multiple is flat, and a proportional
        # cost would miss it by two orders of magnitude.
        ratio = large / small if small > 0 else 1.0
        _check(
            f"{label} grew {ratio:.1f}x as retained grew {growth:.0f}x — "
            "that is proportional to what is HELD, not to what was mutated",
            ratio < 10.0,
        )
        print(f"flat\t{label}\t{ratio:.2f}x cost for {growth:.0f}x retained")


def failed_speculation_costs_what_it_did() -> None:
    """Rollback scales with the mutation count, which is the other half."""
    retained = RETAINED[1]
    counts = (16, 256, 4096)
    timings: list[tuple[int, float]] = []
    for count in counts:
        best = float("inf")
        for _ in range(TRIALS):
            state = _loaded(retained)
            handle = state.begin_sequence()
            started = time.process_time()
            mark = state.mark()
            for value in range(count):
                state.append_sequence(handle, value)
            state.rollback(mark)
            best = min(best, time.process_time() - started)
        timings.append((count, best))

    for count, seconds in timings:
        print(f"mutations\t{count:>5}\t{seconds:.6f}s")
    _check(
        "rollback did not grow with the mutation count at all — the "
        "measurement is not reaching the undo path",
        timings[-1][1] > timings[0][1],
    )
    print("proportional\trollback grows with mutations, not with retained size")


def main() -> None:
    """Correctness, then the two scaling claims."""
    rollback_restores_exactly_the_speculation()
    speculation_is_proportional_to_mutations()
    failed_speculation_costs_what_it_did()
    print("s3 speculation\tPASS\tconstant marks, mutation-proportional undo")


if __name__ == "__main__":
    main()
