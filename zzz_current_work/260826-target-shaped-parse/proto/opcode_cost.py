"""CPU-time check for enum values leaking into flattened opcode tables."""

from __future__ import annotations

from enum import IntEnum
from time import process_time

ITERATIONS = 12_000_000
REPEATS = 5


class Op(IntEnum):
    """Cold authored spelling of one opcode."""

    ACCEPT = 1


def int_compare() -> int:
    """Compare a lowered integer opcode."""
    opcode = 1
    accepted = 0
    for _ in range(ITERATIONS):
        if opcode == 1:
            accepted += 1
    return accepted


def control_compare() -> int:
    """Byte-identical control for the integer row."""
    opcode = 1
    accepted = 0
    for _ in range(ITERATIONS):
        if opcode == 1:
            accepted += 1
    return accepted


def enum_to_int_compare() -> int:
    """Compare an enum instance which leaked into a flat table."""
    opcode = Op.ACCEPT
    accepted = 0
    for _ in range(ITERATIONS):
        if opcode == 1:
            accepted += 1
    return accepted


def enum_member_compare() -> int:
    """Look up and compare an enum member in the paid loop."""
    opcode = Op.ACCEPT
    accepted = 0
    for _ in range(ITERATIONS):
        if opcode == Op.ACCEPT:
            accepted += 1
    return accepted


def main() -> None:
    """Alternate all rows in one process, then print their minimums."""
    assert int_compare.__code__.co_code == control_compare.__code__.co_code
    runs = (
        ("int", int_compare),
        ("control", control_compare),
        ("enum-to-int", enum_to_int_compare),
        ("enum-member", enum_member_compare),
    )
    for _name, run in runs:
        assert run() == ITERATIONS
    results: dict[str, float] = {name: 0.0 for name, _run in runs}
    samples: dict[str, list[float]] = {name: [] for name, _run in runs}
    for _ in range(REPEATS):
        for name, run in runs:
            start = process_time()
            assert run() == ITERATIONS
            samples[name].append(process_time() - start)
    for name, _run in runs:
        results[name] = min(samples[name])
        print(name, f"{results[name]:.9f}")


if __name__ == "__main__":
    main()
