"""Measure shared versus private recognizers across non-JSON grammars."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.scanner import Pattern, compile_source

from bulk_lexical_cost import _pattern, _recognizer, _witness


class Options(argparse.Namespace):
    """Validated non-JSON grammar, worker count, and rounds."""

    grammar: str
    workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported grammars, widths, and rounds."""
        if self.grammar not in ("gbnf", "abnf", "ebnf"):
            raise UnsupportedConstructError(
                f"parallel lexical prototype: unknown grammar {self.grammar!r}"
            )
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"parallel lexical prototype: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "parallel lexical prototype: rounds must be positive"
            )


class Arm(NamedTuple):
    """One recognizer-ownership arrangement."""

    name: str
    private: bool


class Reading(NamedTuple):
    """One complete lexical fragment reading."""

    process_seconds: float
    wall_seconds: float


type Span = tuple[int, int]

ARMS = (Arm("shared-pattern", False), Arm("private-patterns", True))


def _spans(text: str, workers: int) -> tuple[Span, ...]:
    """Cut the synthetic lexical witness after complete grammar tokens."""
    starts = [0]
    for index in range(1, workers):
        want = len(text) * index // workers
        boundary = text.find(" ", want)
        if boundary < 0:
            break
        starts.append(boundary + 1)
    ends = starts[1:] + [len(text)]
    return tuple(zip(starts, ends, strict=True))


def _scan(text: str, pattern: Pattern, span: Span) -> int:
    """Recognize one rooted lexical fragment and return its event count."""
    pos, end = span
    count = 0
    match = pattern.match
    while pos < end:
        found = match(text, pos, end)
        if found is None or found.end() == pos:
            raise UnsupportedConstructError(
                f"parallel lexical prototype: no event at {pos}"
            )
        pos = found.end()
        count += 1
    return count


def _replica(pattern: Pattern, index: int) -> Pattern:
    """Compile one cache-distinct equal lexical recognizer."""
    return compile_source(
        f"{pattern.pattern}(?#parallel-lexical-{index})"
    )


def _measure(
    text: str,
    span: tuple[Span, ...],
    shared: Pattern,
    private: tuple[Pattern, ...],
    pool: ThreadPoolExecutor | None,
    arm: Arm,
) -> tuple[Reading, int]:
    """Measure one ownership arm and its complete event count."""
    patterns = private if arm.private else (shared,) * len(span)
    texts = (text,) * len(span)
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        if pool is None:
            counts = tuple(
                _scan(source, pattern, bounds)
                for source, pattern, bounds in zip(
                    texts, patterns, span, strict=True
                )
            )
        else:
            counts = tuple(pool.map(_scan, texts, patterns, span))
        total = sum(counts)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), total


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated non-JSON ownership run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--grammar", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Alternate recognizer ownership and require exact event parity."""
    options = _parse_options(arguments)
    witness = _witness(options.grammar)
    shared = _pattern(_recognizer(witness), witness.roots)
    spans = _spans(witness.text, options.workers)
    private = tuple(_replica(shared, index) for index in range(len(spans)))
    pool = (
        None
        if options.workers == 1
        else ThreadPoolExecutor(max_workers=options.workers)
    )
    if pool is not None:
        tuple(pool.map(int, range(options.workers)))
    readings: dict[str, list[Reading]] = {arm.name: [] for arm in ARMS}
    expected: int | None = None
    try:
        for number in range(1, options.rounds + 1):
            order = ARMS if number % 2 else tuple(reversed(ARMS))
            for arm in order:
                reading, count = _measure(
                    witness.text, spans, shared, private, pool, arm
                )
                if expected is None:
                    expected = count
                elif count != expected:
                    raise AssertionError(
                        "parallel lexical prototype changed its event count"
                    )
                readings[arm.name].append(reading)
                print(
                    "round",
                    number,
                    arm.name,
                    f"{reading.process_seconds:.6f}",
                    f"{reading.wall_seconds:.6f}",
                    count,
                    sep="\t",
                )
            gc.collect()
    finally:
        if pool is not None:
            pool.shutdown()
    for arm in ARMS:
        values = readings[arm.name]
        print(
            "median",
            arm.name,
            f"{statistics.median(value.process_seconds for value in values):.6f}",
            f"{statistics.median(value.wall_seconds for value in values):.6f}",
            sep="\t",
        )


if __name__ == "__main__":
    main()
