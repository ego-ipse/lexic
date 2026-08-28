"""Measure the stdlib recursive-Python lower-bound witness on Qwen."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int

    def validate(self) -> None:
        """Refuse non-positive round counts."""
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "Python tree prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """One recursive-tree construction reading."""

    process_seconds: float
    wall_seconds: float


def _load(text: str) -> JsonValue:
    """Decode one document into the recursive Python target shape."""
    return json.loads(text)


def _measure(text: str) -> tuple[Reading, JsonValue]:
    """Measure one stdlib construction with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        result = _load(text)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), result


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse the isolated recursive-tree probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Load source once, validate one result, then print raw timings."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    reference = _load(text)
    if not isinstance(reference, dict):
        raise AssertionError("Qwen recursive Python product is not a mapping")
    if "model" not in reference or "added_tokens" not in reference:
        raise AssertionError("Qwen recursive Python product lost required sections")

    readings: list[Reading] = []
    for number in range(1, options.rounds + 1):
        reading, result = _measure(text)
        if result != reference:
            raise AssertionError("stdlib recursive Python product changed")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            sep="\t",
        )
        del result
        gc.collect()
    print("document_chars", len(text), sep="\t")
    print("document_bytes", source.stat().st_size, sep="\t")
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
