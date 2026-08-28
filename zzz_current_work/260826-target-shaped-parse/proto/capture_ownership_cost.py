"""Attribute parallel capture cost to shared mortal inputs."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.scanner import compile_source

from parallel_region_cost import (
    CaptureProgram,
    Reading,
    Span,
    _capture_chunk,
    _capture_program,
    _chunks,
    _entry_spans,
    _expected_vocab,
    _join,
    _program,
)
from schema_region_cost import Tables


class Options(argparse.Namespace):
    """Validated worker count and rounds."""

    workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker counts and non-positive rounds."""
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"capture ownership prototype: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "capture ownership prototype: rounds must be positive"
            )


class Arm(NamedTuple):
    """One shared-versus-owned input arrangement."""

    name: str
    own_text: bool
    own_program: bool


class Result(NamedTuple):
    """One timed arm and its exact product."""

    reading: Reading
    tables: Tables


ARMS = (
    Arm("shared-text/shared-program", False, False),
    Arm("owned-text/shared-program", True, False),
    Arm("shared-text/owned-program", False, True),
    Arm("owned-text/owned-program", True, True),
)


def _program_replica(program: CaptureProgram, index: int) -> CaptureProgram:
    """Compile cache-distinct patterns with identical capture semantics."""
    return CaptureProgram(
        compile_source(
            f"{program.first.pattern}(?#capture-ownership-{index}-first)"
        ),
        compile_source(
            f"{program.next.pattern}(?#capture-ownership-{index}-next)"
        ),
        compile_source(
            f"{program.stream.pattern}(?#capture-ownership-{index}-stream)"
        ),
    )


def _capture(text: str, program: CaptureProgram, span: Span) -> Tables:
    """Adapt one three-argument capture task for executor mapping."""
    return _capture_chunk(text, program, span)


def _inputs(
    text: str,
    chunks: tuple[Span, ...],
    shared_program: CaptureProgram,
    private_programs: tuple[CaptureProgram, ...],
    arm: Arm,
) -> tuple[tuple[str, ...], tuple[CaptureProgram, ...], tuple[Span, ...]]:
    """Create the selected worker inputs, including timed text copies."""
    count = len(chunks)
    programs = private_programs if arm.own_program else (shared_program,) * count
    if not arm.own_text:
        return (text,) * count, programs, chunks
    texts = tuple(text[start:end] for start, end in chunks)
    spans = tuple((0, len(fragment)) for fragment in texts)
    return texts, programs, spans


def _measure(
    text: str,
    chunks: tuple[Span, ...],
    shared_program: CaptureProgram,
    private_programs: tuple[CaptureProgram, ...],
    pool: ThreadPoolExecutor | None,
    arm: Arm,
) -> Result:
    """Measure input ownership, capture, synchronization, and join."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        texts, programs, spans = _inputs(
            text, chunks, shared_program, private_programs, arm
        )
        if pool is None:
            parts = tuple(
                _capture(fragment, program, span)
                for fragment, program, span in zip(
                    texts, programs, spans, strict=True
                )
            )
        else:
            parts = tuple(pool.map(_capture, texts, programs, spans))
        tables = _join(parts)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Result(Reading(process_elapsed, wall_elapsed), tables)


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated ownership attribution run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Alternate four ownership arrangements and print raw timings."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    marker = '"vocab": {'
    start = text.index(marker) + len(marker) - 1
    region_program = _program()
    entries = _entry_spans(text, start, region_program)
    chunks = _chunks(entries, options.workers)
    shared_program = _capture_program()
    private_programs = tuple(
        _program_replica(shared_program, index)
        for index, _chunk in enumerate(chunks)
    )
    expected = _expected_vocab(text)
    pool = (
        None
        if options.workers == 1
        else ThreadPoolExecutor(max_workers=options.workers)
    )
    if pool is not None:
        tuple(pool.map(int, range(options.workers)))
    readings: dict[str, list[Reading]] = {arm.name: [] for arm in ARMS}
    try:
        for number in range(1, options.rounds + 1):
            order = ARMS if number % 2 else tuple(reversed(ARMS))
            for arm in order:
                result = _measure(
                    text,
                    chunks,
                    shared_program,
                    private_programs,
                    pool,
                    arm,
                )
                if result.tables != expected:
                    raise AssertionError(
                        f"capture ownership arm changed vocabulary: {arm.name}"
                    )
                readings[arm.name].append(result.reading)
                print(
                    "round",
                    number,
                    arm.name,
                    f"{result.reading.process_seconds:.6f}",
                    f"{result.reading.wall_seconds:.6f}",
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
