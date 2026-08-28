"""Restate the composed-carrier budget with the collector enabled."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from anchored_tokenizer_regions import _merge_replica, _vocab_replica, _warm
from composed_native_tokenizer import (
    Product,
    _capture,
    _construct,
    _freeze,
    _validate,
)
from parallel_merge_region_cost import (
    RegionProgram as MergeProgram,
    _program as _merge_program,
)
from parallel_region_cost import (
    CaptureProgram,
    _capture_program as _vocab_program,
)

from lexic.exceptions import UnsupportedConstructError


class Options(NamedTuple):
    """Validated worker allocation and per-state round count."""

    region_workers: int
    rounds: int


def _validate_options(options: Options) -> None:
    """Refuse unsupported worker allocations and non-positive rounds."""
    if options.region_workers not in (1, 2, 3, 4, 5, 6, 7):
        raise UnsupportedConstructError(
            "carrier gc prototype: region workers must be 1 through 7"
        )
    if options.rounds < 1:
        raise UnsupportedConstructError("carrier gc prototype: rounds must be positive")


class Prepared(NamedTuple):
    """Retained inputs one measured round consumes."""

    text: str
    workers: int
    vocab_programs: tuple[CaptureProgram, ...]
    merge_programs: tuple[MergeProgram, ...]
    pool: ThreadPoolExecutor


class Reading(NamedTuple):
    """One composed-carrier reading under a stated collector policy."""

    process_seconds: float
    wall_seconds: float


def _measure(prepared: Prepared, collector_on: bool) -> tuple[Reading, Product]:
    """Time capture through record construction under one collector state."""
    if not collector_on:
        gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        native = _capture(
            prepared.text,
            prepared.workers,
            prepared.vocab_programs,
            prepared.merge_programs,
            prepared.pool,
        )
        indexes = _freeze(native.vocab, native.ranks)
        product = Product(_construct(indexes), indexes)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), product


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated collector-policy comparison."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-workers", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=7)
    space = parser.parse_args(arguments)
    options = Options(int(space.region_workers), int(space.rounds))
    _validate_options(options)
    return options


def _prepare(options: Options) -> Prepared:
    """Build the resident witness, worker-owned programs, and warm pool."""
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    shared_vocab = _vocab_program()
    shared_merge = _merge_program()
    total_workers = options.region_workers * 2
    pool = ThreadPoolExecutor(max_workers=total_workers)
    _warm(pool, total_workers)
    return Prepared(
        source.read_text(encoding="utf-8"),
        options.region_workers,
        tuple(
            _vocab_replica(shared_vocab, index)
            for index in range(options.region_workers)
        ),
        tuple(
            _merge_replica(shared_merge, index)
            for index in range(options.region_workers)
        ),
        pool,
    )


def _median(readings: list[Reading]) -> Reading:
    """The per-state median row."""
    return Reading(
        statistics.median(reading.process_seconds for reading in readings),
        statistics.median(reading.wall_seconds for reading in readings),
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Alternate collector states round by round and report both medians."""
    options = _parse_options(arguments)
    prepared = _prepare(options)
    enabled: list[Reading] = []
    disabled: list[Reading] = []
    try:
        for number in range(1, options.rounds + 1):
            for collector_on in (True, False):
                reading, product = _measure(prepared, collector_on)
                _validate(prepared.text, product)
                (enabled if collector_on else disabled).append(reading)
                print(
                    "round",
                    number,
                    "enabled" if collector_on else "disabled",
                    f"{reading.process_seconds:.6f}",
                    f"{reading.wall_seconds:.6f}",
                    sep="\t",
                )
                del product
                gc.collect()
    finally:
        prepared.pool.shutdown()
    on_row = _median(enabled)
    off_row = _median(disabled)
    print(
        "median_enabled",
        f"{on_row.process_seconds:.6f}",
        f"{on_row.wall_seconds:.6f}",
        sep="\t",
    )
    print(
        "median_disabled",
        f"{off_row.process_seconds:.6f}",
        f"{off_row.wall_seconds:.6f}",
        sep="\t",
    )
    print(
        "collector_wall_delta",
        f"{on_row.wall_seconds - off_row.wall_seconds:.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
