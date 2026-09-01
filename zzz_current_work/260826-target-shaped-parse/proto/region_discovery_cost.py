"""Measure current grammar-derived structural region discovery on Qwen."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR
from lexic.parsing.parallel.discovery.regions import Region, find


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int

    def validate(self) -> None:
        """Refuse a non-positive round count."""
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "region discovery prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """One structural-discovery reading."""

    process_seconds: float
    wall_seconds: float


def _measure(text: str) -> tuple[Reading, list[Region]]:
    """Measure one current structural sweep with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        regions = find(JSON_GRAMMAR, text, min_span=2_048)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), regions


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse the isolated discovery probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Discover real Qwen regions and print raw timings."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    vocab_marker = '"vocab": {'
    merge_marker = '"merges": ['
    vocab_open = text.index(vocab_marker) + len(vocab_marker) - 1
    merge_open = text.index(merge_marker) + len(merge_marker) - 1
    readings: list[Reading] = []
    expected: tuple[tuple[int, int, int], ...] | None = None
    for number in range(1, options.rounds + 1):
        reading, regions = _measure(text)
        observed = tuple(
            (region.opener, region.closer, len(region.marks)) for region in regions
        )
        if not any(region.opener == vocab_open for region in regions):
            raise AssertionError("structural discovery lost model.vocab")
        if not any(region.opener == merge_open for region in regions):
            raise AssertionError("structural discovery lost model.merges")
        if expected is None:
            expected = observed
        elif observed != expected:
            raise AssertionError("structural discovery changed its regions")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            len(regions),
            sum(len(region.marks) for region in regions),
            sep="\t",
        )
        del regions
        gc.collect()
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
