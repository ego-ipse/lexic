"""Profile cumulative costs inside grammar-derived parallel capture."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from parallel_region_cost import (
    CaptureProgram,
    Span,
    _capture_program,
    _chunks,
    _entry_spans,
    _program,
)
from schema_region_cost import Tables, _decode_key

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.scanner import compile_source


class Options(argparse.Namespace):
    """Validated worker count and rounds."""

    workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker counts and non-positive rounds."""
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"capture profile: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError("capture profile: rounds must be positive")


class Product(NamedTuple):
    """One stage's checksum and optional published tables."""

    checksum: int
    tables: Tables | None


class Reading(NamedTuple):
    """One cumulative stage reading."""

    process_seconds: float
    wall_seconds: float


class Stage(NamedTuple):
    """One named cumulative capture operation."""

    name: str
    run: Callable[[str, CaptureProgram, Span], Product]


def _match(text: str, program: CaptureProgram, span: Span) -> Product:
    """Run every captured transition without extracting captured text."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: match failed at {pos}")
        pos = matched.end()
        checksum ^= pos
        transition = program.next
    return Product(checksum, None)


def _groups(text: str, program: CaptureProgram, span: Span) -> Product:
    """Add named capture extraction and resulting string allocation."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: groups failed at {pos}")
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("capture profile lost a group")
        checksum += len(key) + len(ordinal)
        pos = matched.end()
        transition = program.next
    return Product(checksum, None)


def _group_indexes(text: str, program: CaptureProgram, span: Span) -> Product:
    """Extract the same captures by integer index."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"capture profile: indexed groups failed at {pos}"
            )
        key = matched.group(1)
        ordinal = matched.group(2)
        checksum += len(key) + len(ordinal)
        pos = matched.end()
        transition = program.next
    return Product(checksum, None)


def _group_slices(text: str, program: CaptureProgram, span: Span) -> Product:
    """Extract the same captures from numeric group boundaries."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"capture profile: sliced groups failed at {pos}"
            )
        key = text[matched.start(1) : matched.end(1)]
        ordinal = text[matched.start(2) : matched.end(2)]
        checksum += len(key) + len(ordinal)
        pos = matched.end()
        transition = program.next
    return Product(checksum, None)


def _decode(text: str, program: CaptureProgram, span: Span) -> Product:
    """Add grammar-string decoding while leaving ordinals as text."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: decode failed at {pos}")
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("capture profile lost a decoded group")
        checksum += len(_decode_key(key)) + len(ordinal)
        pos = matched.end()
        transition = program.next
    return Product(checksum, None)


def _convert(text: str, program: CaptureProgram, span: Span) -> Product:
    """Add integer conversion to decoded captured strings."""
    pos, end = span
    transition = program.first
    checksum = 0
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: convert failed at {pos}")
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("capture profile lost a converted group")
        checksum += len(_decode_key(key)) + int(ordinal)
        pos = matched.end()
        transition = program.next
    return Product(checksum, None)


def _encode(text: str, program: CaptureProgram, span: Span) -> Product:
    """Add duplicate checking and publication into one native index."""
    pos, end = span
    transition = program.first
    encode: dict[str, int] = {}
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: encode failed at {pos}")
        raw_key = matched.group("key")
        raw_ordinal = matched.group("ordinal")
        if raw_key is None or raw_ordinal is None:
            raise AssertionError("capture profile lost an encoded group")
        key = _decode_key(raw_key)
        if key in encode:
            raise UnsupportedConstructError("capture profile: repeated key")
        encode[key] = int(raw_ordinal)
        pos = matched.end()
        transition = program.next
    return Product(len(encode), None)


def _indexes(text: str, program: CaptureProgram, span: Span) -> Product:
    """Add the inverse index and both duplicate checks."""
    pos, end = span
    transition = program.first
    tables = Tables({}, {})
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(f"capture profile: indexes failed at {pos}")
        raw_key = matched.group("key")
        raw_ordinal = matched.group("ordinal")
        if raw_key is None or raw_ordinal is None:
            raise AssertionError("capture profile lost an indexed group")
        key = _decode_key(raw_key)
        ordinal = int(raw_ordinal)
        if key in tables.encode or ordinal in tables.decode:
            raise UnsupportedConstructError("capture profile: repeated index value")
        tables.encode[key] = ordinal
        tables.decode[ordinal] = key
        pos = matched.end()
        transition = program.next
    return Product(len(tables.encode), tables)


STAGES = (
    Stage("match", _match),
    Stage("group-names", _groups),
    Stage("group-indexes", _group_indexes),
    Stage("group-slices", _group_slices),
    Stage("decode", _decode),
    Stage("convert", _convert),
    Stage("encode", _encode),
    Stage("indexes", _indexes),
)


def _program_replica(program: CaptureProgram, index: int) -> CaptureProgram:
    """Compile cache-distinct patterns with identical capture semantics."""
    return CaptureProgram(
        compile_source(f"{program.first.pattern}(?#capture-profile-{index}-first)"),
        compile_source(f"{program.next.pattern}(?#capture-profile-{index}-next)"),
        compile_source(f"{program.stream.pattern}(?#capture-profile-{index}-stream)"),
    )


def _measure(
    text: str,
    chunks: tuple[Span, ...],
    programs: tuple[CaptureProgram, ...],
    pool: ThreadPoolExecutor | None,
    stage: Stage,
) -> tuple[Reading, int]:
    """Measure timed worker-owned slices and one cumulative stage."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        fragments = tuple(text[start:end] for start, end in chunks)
        spans = tuple((0, len(fragment)) for fragment in fragments)
        if pool is None:
            products = tuple(
                stage.run(fragment, program, span)
                for fragment, program, span in zip(
                    fragments, programs, spans, strict=True
                )
            )
        else:
            products = tuple(pool.map(stage.run, fragments, programs, spans))
        checksum = sum(product.checksum for product in products)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), checksum


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated cumulative capture profile."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Alternate cumulative capture stages and print raw timings."""
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
    entries = _entry_spans(text, start, _program())
    chunks = _chunks(entries, options.workers)
    shared_program = _capture_program()
    programs = tuple(
        _program_replica(shared_program, index) for index, _chunk in enumerate(chunks)
    )
    pool = (
        None
        if options.workers == 1
        else ThreadPoolExecutor(max_workers=options.workers)
    )
    if pool is not None:
        tuple(pool.map(int, range(options.workers)))
    readings: dict[str, list[Reading]] = {stage.name: [] for stage in STAGES}
    checksums: dict[str, int] = {}
    try:
        for number in range(1, options.rounds + 1):
            order = STAGES if number % 2 else tuple(reversed(STAGES))
            for stage in order:
                reading, checksum = _measure(text, chunks, programs, pool, stage)
                previous = checksums.setdefault(stage.name, checksum)
                if checksum != previous:
                    raise AssertionError(
                        f"capture profile checksum changed: {stage.name}"
                    )
                readings[stage.name].append(reading)
                print(
                    "round",
                    number,
                    stage.name,
                    f"{reading.process_seconds:.6f}",
                    f"{reading.wall_seconds:.6f}",
                    sep="\t",
                )
            gc.collect()
    finally:
        if pool is not None:
            pool.shutdown()
    for stage in STAGES:
        values = readings[stage.name]
        print(
            "median",
            stage.name,
            f"{statistics.median(value.process_seconds for value in values):.6f}",
            f"{statistics.median(value.wall_seconds for value in values):.6f}",
            sep="\t",
        )


if __name__ == "__main__":
    main()
