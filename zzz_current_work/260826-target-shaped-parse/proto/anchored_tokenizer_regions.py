"""Measure one-pass target-region capture from schema route anchors."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import NamedTuple

from capture_ownership_cost import _program_replica as _vocab_replica
from parallel_merge_region_cost import (
    Chunk,
    Ranks,
)
from parallel_merge_region_cost import RegionProgram as MergeProgram
from parallel_merge_region_cost import _capture_chunk as _capture_merge
from parallel_merge_region_cost import _expected as _expected_merges
from parallel_merge_region_cost import _program as _merge_program
from parallel_region_cost import (
    CaptureProgram,
    Span,
)
from parallel_region_cost import _capture_chunk as _capture_vocab
from parallel_region_cost import _capture_program as _vocab_program
from parallel_region_cost import (
    _expected_vocab,
)
from parallel_region_cost import _join as _join_vocab
from schema_region_cost import Tables
from self_locating_region_cuts import (
    CutProgram,
)
from self_locating_region_cuts import _program as _cut_program
from self_locating_region_cuts import (
    _trim_ws,
)

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.core.scanner import compile_source


class Options(argparse.Namespace):
    """Validated workers per high-volume region and rounds."""

    region_workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker allocations and non-positive rounds."""
        if self.region_workers not in (1, 2, 3, 4, 5, 6, 7):
            raise UnsupportedConstructError(
                "anchored tokenizer prototype: region workers must be 1 through 7"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "anchored tokenizer prototype: rounds must be positive"
            )


class RegionBounds(NamedTuple):
    """The two schema-routed high-volume container bounds."""

    vocab_open: int
    vocab_close: int
    merges_open: int
    merges_close: int


class Reading(NamedTuple):
    """One complete anchor, capture, and join reading."""

    process_seconds: float
    wall_seconds: float


class Product(NamedTuple):
    """The final native high-volume tokenizer tables."""

    vocab: Tables
    ranks: Ranks


def _bounds(text: str) -> RegionBounds:
    """Locate ordinary-spelling schema routes and their nested closers."""
    vocab_marker = '"vocab": {'
    merges_marker = '"merges": ['
    vocab_open = text.index(vocab_marker) + len(vocab_marker) - 1
    merges_member = text.index(merges_marker, vocab_open)
    vocab_close = text.rfind("}", vocab_open, merges_member)
    merges_open = merges_member + len(merges_marker) - 1
    root_close = text.rfind("}")
    model_close = text.rfind("}", merges_open, root_close)
    merges_close = text.rfind("]", merges_open, model_close)
    if min(vocab_close, model_close, merges_close) < 0:
        raise UnsupportedConstructError(
            "anchored tokenizer prototype: routed closer was not found"
        )
    return RegionBounds(vocab_open, vocab_close, merges_open, merges_close)


def _spans(
    text: str,
    opener: int,
    closer: int,
    workers: int,
    program: CutProgram,
) -> tuple[Span, ...]:
    """Find O(workers) grammar-entry boundaries inside known container bounds."""
    opened = program.begin.match(text, opener)
    if opened is None:
        raise UnsupportedConstructError(
            "anchored tokenizer prototype: container opener did not match"
        )
    first = opened.end()
    last = _trim_ws(text, first, closer)
    starts = [first]
    ends: list[int] = []
    for index in range(1, workers):
        want = first + (last - first) * index // workers
        boundary = program.boundary.search(text, want, last)
        if boundary is None:
            break
        previous = _trim_ws(text, starts[-1], boundary.start())
        next_start = boundary.start("entry")
        if previous <= starts[-1] or next_start >= last:
            continue
        ends.append(previous)
        starts.append(next_start)
    ends.append(last)
    return tuple(zip(starts, ends, strict=True))


def _distinct(source: str, index: int, field: str) -> str:
    """Append one inert cache-distinguishing regex comment."""
    return f"{source}(?#anchored-merge-{index}-{field})"


def _merge_replica(program: MergeProgram, index: int) -> MergeProgram:
    """Compile cache-distinct merge patterns with identical semantics."""
    return MergeProgram(
        compile_source(_distinct(program.begin.pattern, index, "begin")),
        compile_source(_distinct(program.first.pattern, index, "first")),
        compile_source(_distinct(program.next.pattern, index, "next")),
        compile_source(_distinct(program.fragment.pattern, index, "fragment")),
        compile_source(
            _distinct(program.capture_first.pattern, index, "capture-first")
        ),
        compile_source(_distinct(program.capture_next.pattern, index, "capture-next")),
    )


def _merge_part(text: str, program: MergeProgram, span: Span) -> Ranks:
    """Build one ordered merge fragment with fragment-local ranks."""
    return _capture_merge(text, program, Chunk(span[0], span[1], 0))


def _join_merges(parts: tuple[Ranks, ...]) -> Ranks:
    """Assign exact global ranks while joining ordered local mappings once."""
    ranks: Ranks = {}
    for part in parts:
        for dyad in part:
            if dyad in ranks:
                raise UnsupportedConstructError(
                    "anchored tokenizer prototype: repeated merge dyad"
                )
            ranks[dyad] = len(ranks)
    return ranks


def _results[Value](futures: tuple[Future[Value], ...]) -> tuple[Value, ...]:
    """Collect one homogeneous future family in document order."""
    return tuple(future.result() for future in futures)


def _arrive(barrier: Barrier) -> None:
    """Hold one cold task until the complete retained pool exists."""
    barrier.wait()


def _warm(pool: ThreadPoolExecutor, workers: int) -> None:
    """Start every retained worker before a timing interval."""
    barrier = Barrier(workers + 1)
    futures = tuple(pool.submit(_arrive, barrier) for _ in range(workers))
    barrier.wait()
    for future in futures:
        future.result()


def _measure(
    text: str,
    workers: int,
    vocab_cut: CutProgram,
    merge_cut: CutProgram,
    vocab_programs: tuple[CaptureProgram, ...],
    merge_programs: tuple[MergeProgram, ...],
    pool: ThreadPoolExecutor,
) -> tuple[Reading, Product]:
    """Measure anchor planning, direct captures, synchronization, and joins."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        bounds = _bounds(text)
        vocab_spans = _spans(
            text,
            bounds.vocab_open,
            bounds.vocab_close,
            workers,
            vocab_cut,
        )
        merge_spans = _spans(
            text,
            bounds.merges_open,
            bounds.merges_close,
            workers,
            merge_cut,
        )
        vocab_futures = tuple(
            pool.submit(_capture_vocab, text, program, span)
            for program, span in zip(vocab_programs, vocab_spans, strict=True)
        )
        merge_futures = tuple(
            pool.submit(_merge_part, text, program, span)
            for program, span in zip(merge_programs, merge_spans, strict=True)
        )
        vocab = _join_vocab(_results(vocab_futures))
        ranks = _join_merges(_results(merge_futures))
        product = Product(vocab, ranks)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), product


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated anchored-region run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Measure both Qwen high-volume regions on one retained worker pool."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    vocab_cut = _cut_program("vocab")
    merge_cut = _cut_program("merges")
    shared_vocab = _vocab_program()
    shared_merge = _merge_program()
    vocab_programs = tuple(
        _vocab_replica(shared_vocab, index) for index in range(options.region_workers)
    )
    merge_programs = tuple(
        _merge_replica(shared_merge, index) for index in range(options.region_workers)
    )
    expected = Product(_expected_vocab(text), _expected_merges(text))
    total_workers = options.region_workers * 2
    pool = ThreadPoolExecutor(max_workers=total_workers)
    _warm(pool, total_workers)
    readings: list[Reading] = []
    try:
        for number in range(1, options.rounds + 1):
            reading, product = _measure(
                text,
                options.region_workers,
                vocab_cut,
                merge_cut,
                vocab_programs,
                merge_programs,
                pool,
            )
            if product != expected:
                raise AssertionError(
                    "anchored tokenizer prototype changed high-volume tables"
                )
            readings.append(reading)
            print(
                "round",
                number,
                f"{reading.process_seconds:.6f}",
                f"{reading.wall_seconds:.6f}",
                sep="\t",
            )
            del product
            gc.collect()
    finally:
        pool.shutdown()
    print(
        "median",
        f"{statistics.median(value.process_seconds for value in readings):.6f}",
        f"{statistics.median(value.wall_seconds for value in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
