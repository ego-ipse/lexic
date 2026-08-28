"""Measure the path-only boundary excluded from resident-text products."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int

    def validate(self) -> None:
        """Refuse a non-positive round count."""
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "source read prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """One source-read process/wall reading."""

    process_seconds: float
    wall_seconds: float


def _read(path: Path) -> tuple[Reading, str]:
    """Read and decode one complete UTF-8 source under timing."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        text = path.read_text(encoding="utf-8")
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), text


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated source-read run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Print first and warm source-read timings for the Qwen witness."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    readings: list[Reading] = []
    expected: int | None = None
    for number in range(1, options.rounds + 1):
        reading, text = _read(source)
        if expected is None:
            expected = len(text)
        elif len(text) != expected:
            raise AssertionError("source read prototype changed decoded length")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            len(text),
            sep="\t",
        )
        del text
        gc.collect()
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
