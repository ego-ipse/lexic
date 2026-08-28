"""Measure native target capture through canonical final tokenizer indexes."""

from __future__ import annotations

import argparse
import gc
import resource
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrStr, IrTokenPipeline, IrTokenizer, IrTuple
from lexic.ir.text.tokenizer import IrRankedMerge

from anchored_tokenizer_regions import (
    Product as NativeProduct,
    _bounds,
    _join_merges,
    _merge_part,
    _merge_replica,
    _spans,
    _vocab_replica,
    _warm,
)
from parallel_merge_region_cost import (
    Ranks,
    RegionProgram as MergeProgram,
    _expected as _expected_merges,
    _program as _merge_program,
)
from parallel_region_cost import (
    CaptureProgram,
    Span,
    _capture_chunk as _capture_vocab,
    _capture_program as _vocab_program,
    _expected_vocab,
    _join as _join_vocab,
)
from schema_region_cost import Tables
from self_locating_region_cuts import _program as _cut_program
from tokenizer_index_shape import IrTokenDecode, IrTokenEncode, IrTokenRanks


class Options(argparse.Namespace):
    """Validated worker allocation and round count."""

    region_workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker allocations and non-positive rounds."""
        if self.region_workers not in (1, 2, 3, 4, 5, 6, 7):
            raise UnsupportedConstructError(
                "composed native prototype: region workers must be 1 through 7"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "composed native prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """Attributed phases of one direct native-index product."""

    capture_seconds: float
    canonical_freeze_seconds: float
    construct_seconds: float
    process_seconds: float
    wall_seconds: float
    peak_rss_delta_kib: int


class FinalIndexes(NamedTuple):
    """Canonical tokenizer-native primitive lookup indexes."""

    encode: IrTokenEncode
    decode: IrTokenDecode
    ranks: IrTokenRanks


class Product(NamedTuple):
    """The actual tokenizer record and its native final indexes."""

    tokenizer: IrTokenizer
    indexes: FinalIndexes


def _collect[Value](futures: tuple[Future[Value], ...]) -> tuple[Value, ...]:
    """Collect one homogeneous future family in document order."""
    return tuple(future.result() for future in futures)


def _capture(
    text: str,
    workers: int,
    vocab_programs: tuple[CaptureProgram, ...],
    merge_programs: tuple[MergeProgram, ...],
    pool: ThreadPoolExecutor,
) -> NativeProduct:
    """Capture and join both routed regions in their final primitive types."""
    bounds = _bounds(text)
    vocab_spans = _spans(
        text,
        bounds.vocab_open,
        bounds.vocab_close,
        workers,
        _cut_program("vocab"),
    )
    merge_spans = _spans(
        text,
        bounds.merges_open,
        bounds.merges_close,
        workers,
        _cut_program("merges"),
    )
    vocab_futures = tuple(
        pool.submit(_capture_vocab, text, program, span)
        for program, span in zip(vocab_programs, vocab_spans, strict=True)
    )
    merge_futures = tuple(
        pool.submit(_merge_part, text, program, span)
        for program, span in zip(merge_programs, merge_spans, strict=True)
    )
    vocab = _join_vocab(_collect(vocab_futures))
    ranks = _join_merges(_collect(merge_futures))
    return NativeProduct(vocab, ranks)


def _freeze(vocab: Tables, ranks: Ranks) -> FinalIndexes:
    """Validate semantic id/rank order, repairing only a noncanonical input."""
    previous: int | None = None
    canonical_vocab = True
    for identifier in vocab.decode:
        if previous is not None and identifier <= previous:
            canonical_vocab = False
            break
        previous = identifier
    if canonical_vocab:
        encode = vocab.encode
        decode = vocab.decode
    else:
        decode = dict(sorted(vocab.decode.items()))
        encode = {
            spelling: identifier for identifier, spelling in decode.items()
        }
    if any(rank != expected for expected, rank in enumerate(ranks.values())):
        raise UnsupportedConstructError(
            "composed native prototype: merge ranks are not contiguous"
        )
    return FinalIndexes(
        IrTokenEncode.from_owned(encode),
        IrTokenDecode.from_owned(decode),
        IrTokenRanks.from_owned(ranks),
    )


def _construct(indexes: FinalIndexes) -> IrTokenizer:
    """Construct the actual runtime record with the proposed field subtype."""
    return IrTuple.__new__(
        IrTokenizer,
        IrStr("qwen3"),
        indexes.encode,
        indexes.decode,
        indexes.ranks,
        IrTokenPipeline(),
        IrRankedMerge(),
    )


def _measure(
    text: str,
    workers: int,
    vocab_programs: tuple[CaptureProgram, ...],
    merge_programs: tuple[MergeProgram, ...],
    pool: ThreadPoolExecutor,
) -> tuple[Reading, Product]:
    """Measure anchors through canonical indexes and actual record."""
    gc.disable()
    rss_started = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        native = _capture(
            text, workers, vocab_programs, merge_programs, pool
        )
        capture_finished = time.perf_counter()
        indexes = _freeze(native.vocab, native.ranks)
        freeze_finished = time.perf_counter()
        tokenizer = _construct(indexes)
        construct_finished = time.perf_counter()
        product = Product(tokenizer, indexes)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return (
        Reading(
            capture_finished - wall_started,
            freeze_finished - capture_finished,
            construct_finished - freeze_finished,
            process_elapsed,
            wall_elapsed,
            max(
                0,
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                - rss_started,
            ),
        ),
        product,
    )


def _validate(text: str, product: Product) -> None:
    """Require exact tables, canonical order, and current runtime lookups."""
    expected_vocab = _expected_vocab(text)
    expected_ranks = _expected_merges(text)
    indexes = product.indexes
    if dict(indexes.encode.items()) != expected_vocab.encode:
        raise AssertionError("composed native prototype changed encode")
    if dict(indexes.decode.items()) != expected_vocab.decode:
        raise AssertionError("composed native prototype changed decode")
    if dict(indexes.ranks.items()) != expected_ranks:
        raise AssertionError("composed native prototype changed ranks")
    expected_ids = tuple(sorted(expected_vocab.decode))
    if tuple(indexes.decode.keys()) != expected_ids:
        raise AssertionError("composed native prototype changed canonical ids")
    if tuple(indexes.encode.values()) != expected_ids:
        raise AssertionError("composed native prototype changed encode order")
    if tuple(indexes.ranks.values()) != tuple(range(len(expected_ranks))):
        raise AssertionError("composed native prototype changed rank order")
    if product.tokenizer.encode is not indexes.encode:
        raise AssertionError("composed native tokenizer copied encode")
    if product.tokenizer.decode is not indexes.decode:
        raise AssertionError("composed native tokenizer copied decode")
    if product.tokenizer.ranks is not indexes.ranks:
        raise AssertionError("composed native tokenizer copied ranks")
    for spelling, identifier in tuple(indexes.encode.items())[:32]:
        resolved = product.tokenizer.resolve(spelling)
        if not isinstance(resolved, int) or int(resolved) != identifier:
            raise AssertionError("composed native tokenizer changed forward lookup")
        if str(product.tokenizer.spell(identifier)) != spelling:
            raise AssertionError("composed native tokenizer changed inverse lookup")


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated composed-native run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Measure resident source through native indexes and tokenizer record."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    shared_vocab = _vocab_program()
    shared_merge = _merge_program()
    vocab_programs = tuple(
        _vocab_replica(shared_vocab, index)
        for index in range(options.region_workers)
    )
    merge_programs = tuple(
        _merge_replica(shared_merge, index)
        for index in range(options.region_workers)
    )
    total_workers = options.region_workers * 2
    pool = ThreadPoolExecutor(max_workers=total_workers)
    _warm(pool, total_workers)
    readings: list[Reading] = []
    try:
        for number in range(1, options.rounds + 1):
            reading, product = _measure(
                text,
                options.region_workers,
                vocab_programs,
                merge_programs,
                pool,
            )
            _validate(text, product)
            readings.append(reading)
            print(
                "round",
                number,
                f"{reading.capture_seconds:.6f}",
                f"{reading.canonical_freeze_seconds:.6f}",
                f"{reading.construct_seconds:.6f}",
                f"{reading.process_seconds:.6f}",
                f"{reading.wall_seconds:.6f}",
                reading.peak_rss_delta_kib,
                sep="\t",
            )
            del product
            gc.collect()
    finally:
        pool.shutdown()
    print(
        "median",
        f"{statistics.median(r.capture_seconds for r in readings):.6f}",
        f"{statistics.median(r.canonical_freeze_seconds for r in readings):.6f}",
        f"{statistics.median(r.construct_seconds for r in readings):.6f}",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        max(r.peak_rss_delta_kib for r in readings),
        sep="\t",
    )


if __name__ == "__main__":
    main()
