"""Baseline the public token-segmented grammar product in one process."""

from __future__ import annotations

import statistics
import time
from typing import NamedTuple

from lexic.compile import Vocabulary, compile_text
from lexic.ir import IrTokenizer

GRAMMAR = "root ::= <think> thinking </think>\nthinking ::= !</think>*"
VOCAB = {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "<": 4, "/think>": 5}
DOCUMENT = "<think>" + "ab" * 16_384 + "</think>"
ROUNDS = 15


class Reading(NamedTuple):
    """Process and wall seconds for one operation."""

    process_seconds: float
    wall_seconds: float


def _elapsed(process_started: float, wall_started: float) -> Reading:
    """Return elapsed process and wall seconds."""
    return Reading(
        time.process_time() - process_started,
        time.perf_counter() - wall_started,
    )


def main() -> None:
    """Measure compile, cold first parse, and warmed token parses."""
    tokenizer = IrTokenizer.from_vocab("tokens", VOCAB)
    process_started = time.process_time()
    wall_started = time.perf_counter()
    compiled = compile_text(GRAMMAR, vocabulary=Vocabulary(tokenizer))
    compile_reading = _elapsed(process_started, wall_started)

    process_started = time.process_time()
    wall_started = time.perf_counter()
    first = compiled.parse(DOCUMENT, cores=1)
    cold = _elapsed(process_started, wall_started)
    if first.to_text() != DOCUMENT:
        raise AssertionError("token-segmented cold parse changed the document")

    readings: list[Reading] = []
    for _round in range(ROUNDS):
        process_started = time.process_time()
        wall_started = time.perf_counter()
        model = compiled.parse(DOCUMENT, cores=1)
        reading = _elapsed(process_started, wall_started)
        if model.to_text() != DOCUMENT:
            raise AssertionError("token-segmented parse changed the document")
        readings.append(reading)

    print("document_bytes", len(DOCUMENT), sep="\t")
    print(
        "compile",
        f"{compile_reading.process_seconds:.6f}",
        f"{compile_reading.wall_seconds:.6f}",
        sep="\t",
    )
    print(
        "cold_first_parse",
        f"{cold.process_seconds:.6f}",
        f"{cold.wall_seconds:.6f}",
        sep="\t",
    )
    print(
        "warm_parse_median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )
    print(
        "warm_parse_minimum",
        f"{min(r.process_seconds for r in readings):.6f}",
        f"{min(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
