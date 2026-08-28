"""Measure grammar-derived regular-region fragments over a retained pool."""

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
from lexic.parsing.pda.core.scanner import Pattern, compile_source

from schema_region_cost import (
    RegionProgram,
    Tables,
    _decode_key,
    _expected_vocab,
    _program,
    _recognizer,
    _source,
)


class Options(argparse.Namespace):
    """Validated worker count and rounds."""

    workers: int
    rounds: int
    mode: str

    def validate(self) -> None:
        """Refuse unsupported worker counts and non-positive rounds."""
        if self.mode not in ("recognize", "capture", "capture-stream"):
            raise UnsupportedConstructError(
                f"parallel region prototype: unknown mode {self.mode!r}"
            )
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"parallel region prototype: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "parallel region prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """One fragment-recognition reading."""

    process_seconds: float
    wall_seconds: float


type Span = tuple[int, int]


class CaptureProgram(NamedTuple):
    """First and subsequent captured-entry transitions for a fragment."""

    first: Pattern
    next: Pattern
    stream: Pattern


def _fragment_pattern() -> Pattern:
    """Compile a non-empty repeated-entry fragment from lower grammar rules."""
    recognizer = _recognizer()
    string = _source(recognizer, "string")
    integer = _source(recognizer, "int")
    name_sep = _source(recognizer, "name-separator")
    value_sep = _source(recognizer, "value-separator")
    entry = rf"(?:{string})(?:{name_sep})(?:{integer})"
    return compile_source(rf"{entry}(?:(?:{value_sep}){entry})*+")


def _capture_program() -> CaptureProgram:
    """Compile captured entry transitions from the same lower rules."""
    recognizer = _recognizer()
    string = _source(recognizer, "string")
    integer = _source(recognizer, "int")
    name_sep = _source(recognizer, "name-separator")
    value_sep = _source(recognizer, "value-separator")
    entry = rf"(?P<key>{string}){name_sep}(?P<ordinal>{integer})"
    return CaptureProgram(
        compile_source(entry),
        compile_source(rf"(?:{value_sep}){entry}"),
        compile_source(rf"(?:(?:{value_sep}))?+{entry}"),
    )


def _entry_spans(text: str, start: int, program: RegionProgram) -> tuple[Span, ...]:
    """Locate entry spans once, outside every timing interval."""
    opened = program.begin.match(text, start)
    if opened is None:
        raise UnsupportedConstructError(
            "parallel region prototype: mapping opener did not match"
        )
    pos = opened.end()
    transition = program.first
    spans: list[Span] = []
    while True:
        matched = transition.match(text, pos)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"parallel region prototype: mapping transition failed at {pos}"
            )
        pos = matched.end()
        if matched.group("end") is not None:
            return tuple(spans)
        spans.append((matched.start("key"), matched.end("ordinal")))
        transition = program.next


def _chunks(entries: tuple[Span, ...], workers: int) -> tuple[Span, ...]:
    """Group adjacent entries into near-equal non-empty fragment spans."""
    count = len(entries)
    chunks: list[Span] = []
    for worker in range(workers):
        lo = count * worker // workers
        hi = count * (worker + 1) // workers
        if lo < hi:
            chunks.append((entries[lo][0], entries[hi - 1][1]))
    return tuple(chunks)


def _match_chunk(text: str, pattern: Pattern, span: Span) -> int:
    """Recognize one certified fragment span."""
    start, end = span
    matched = pattern.fullmatch(text, start, end)
    if matched is None:
        raise UnsupportedConstructError(
            f"parallel region prototype: fragment {start}:{end} did not match"
        )
    return matched.end()


def _capture_chunk(text: str, program: CaptureProgram, span: Span) -> Tables:
    """Recognize and directly build one fragment's owned native indexes."""
    pos, end = span
    tables = Tables({}, {})
    transition = program.first
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"parallel region prototype: capture failed at {pos}"
            )
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("parallel region transition lost its captures")
        decoded = _decode_key(key)
        value = int(ordinal)
        if decoded in tables.encode or value in tables.decode:
            raise UnsupportedConstructError(
                "parallel region prototype: repeated vocabulary key or id"
            )
        tables.encode[decoded] = value
        tables.decode[value] = decoded
        pos = matched.end()
        transition = program.next
    if pos != end:
        raise AssertionError("parallel region capture changed its fragment end")
    return tables


def _capture_chunk_stream(
    text: str, program: CaptureProgram, span: Span
) -> Tables:
    """Stream compiled captures into indexes without a retained pair sidecar."""
    pos, end = span
    tables = Tables({}, {})
    for matched in program.stream.finditer(text, pos, end):
        if matched.start() != pos:
            raise UnsupportedConstructError(
                f"parallel region prototype: stream skipped syntax at {pos}"
            )
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("parallel stream transition lost its captures")
        decoded = _decode_key(key)
        value = int(ordinal)
        if decoded in tables.encode or value in tables.decode:
            raise UnsupportedConstructError(
                "parallel region prototype: repeated vocabulary key or id"
            )
        tables.encode[decoded] = value
        tables.decode[value] = decoded
        pos = matched.end()
    if pos != end:
        raise UnsupportedConstructError(
            f"parallel region prototype: stream stopped at {pos} before {end}"
        )
    return tables


def _join(parts: tuple[Tables, ...]) -> Tables:
    """Join disjoint owned indexes and detect cross-fragment duplicates."""
    encode: dict[str, int] = {}
    decode: dict[int, str] = {}
    expected = 0
    for part in parts:
        expected += len(part.encode)
        encode.update(part.encode)
        decode.update(part.decode)
    if len(encode) != expected or len(decode) != expected:
        raise UnsupportedConstructError(
            "parallel region prototype: cross-fragment vocabulary duplicate"
        )
    return Tables(encode, decode)


def _run(
    text: str,
    pattern: Pattern,
    chunks: tuple[Span, ...],
    pool: ThreadPoolExecutor | None,
) -> tuple[int, ...]:
    """Recognize all fragments sequentially or through the retained pool."""
    if pool is None:
        return tuple(_match_chunk(text, pattern, span) for span in chunks)
    return tuple(pool.map(lambda span: _match_chunk(text, pattern, span), chunks))


def _measure(
    text: str,
    pattern: Pattern,
    chunks: tuple[Span, ...],
    pool: ThreadPoolExecutor | None,
) -> Reading:
    """Measure only fragment execution and synchronization."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        ends = _run(text, pattern, chunks, pool)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    if ends != tuple(end for _start, end in chunks):
        raise AssertionError("parallel region prototype changed a fragment end")
    return Reading(process_elapsed, wall_elapsed)


def _measure_capture(
    text: str,
    program: CaptureProgram,
    chunks: tuple[Span, ...],
    pool: ThreadPoolExecutor | None,
    streaming: bool,
) -> tuple[Reading, Tables]:
    """Measure direct fragment construction, synchronization, and join."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        capture = _capture_chunk_stream if streaming else _capture_chunk
        if pool is None:
            parts = tuple(capture(text, program, span) for span in chunks)
        else:
            parts = tuple(
                pool.map(lambda span: capture(text, program, span), chunks)
            )
        tables = _join(parts)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), tables


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated worker-count probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Prepare certified spans and a pool, then measure fragment recognition."""
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
    program = _program()
    planning_started = time.perf_counter()
    entries = _entry_spans(text, start, program)
    chunks = _chunks(entries, options.workers)
    planning_wall = time.perf_counter() - planning_started
    pattern = _fragment_pattern()
    capture_program = _capture_program()
    expected = _expected_vocab(text)
    pool = (
        None
        if options.workers == 1
        else ThreadPoolExecutor(max_workers=options.workers)
    )
    if pool is not None:
        tuple(pool.map(lambda value: value, range(options.workers)))

    readings: list[Reading] = []
    try:
        for number in range(1, options.rounds + 1):
            if options.mode == "recognize":
                reading = _measure(text, pattern, chunks, pool)
            else:
                reading, tables = _measure_capture(
                    text,
                    capture_program,
                    chunks,
                    pool,
                    options.mode == "capture-stream",
                )
                if tables != expected:
                    raise AssertionError(
                        "parallel region prototype changed the vocabulary"
                    )
            readings.append(reading)
            print(
                "round",
                number,
                f"{reading.process_seconds:.6f}",
                f"{reading.wall_seconds:.6f}",
                sep="\t",
            )
            gc.collect()
    finally:
        if pool is not None:
            pool.shutdown()
    print("entries", len(entries), sep="\t")
    print("chunks", len(chunks), sep="\t")
    print("planning_wall", f"{planning_wall:.6f}", sep="\t")
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
