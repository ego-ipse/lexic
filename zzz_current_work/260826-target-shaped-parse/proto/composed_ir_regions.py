"""Measure routed high-volume capture directly into final tokenizer IR leaves."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from anchored_tokenizer_regions import (
    _bounds,
    _merge_replica,
    _spans,
    _vocab_replica,
    _warm,
)
from parallel_merge_region_cost import RegionProgram as MergeProgram
from parallel_merge_region_cost import _expected as _expected_merges
from parallel_merge_region_cost import _program as _merge_program
from parallel_region_cost import (
    CaptureProgram,
    Span,
)
from parallel_region_cost import _capture_program as _vocab_program
from parallel_region_cost import (
    _expected_vocab,
)
from schema_region_cost import _decode_key
from self_locating_region_cuts import _program as _cut_program
from tokenizer_index_shape import IrTokenIndex

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrChr, IrInt, IrStr, IrTokenizer, IrTokenPipeline, IrTuple
from lexic.ir.text.tokenizer import IrRankedMerge


class Options(argparse.Namespace):
    """Validated worker allocation and round count."""

    region_workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker allocations and non-positive rounds."""
        if self.region_workers not in (1, 2, 3, 4, 5, 6, 7):
            raise UnsupportedConstructError(
                "composed IR prototype: region workers must be 1 through 7"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "composed IR prototype: rounds must be positive"
            )


class IrTables(NamedTuple):
    """Vocabulary indexes populated with their final IR leaf identities."""

    encode: dict[IrStr, IrChr]
    decode: dict[IrChr, IrStr]


type IrRanks = dict[IrTuple, int]


class Reading(NamedTuple):
    """Attributed phases of one direct high-volume product."""

    capture_seconds: float
    freeze_seconds: float
    construct_seconds: float
    process_seconds: float
    wall_seconds: float


class Product(NamedTuple):
    """The final tokenizer plus its tokenizer-native indexes."""

    tokenizer: IrTokenizer
    encode: IrTokenIndex[IrStr, IrChr]
    decode: IrTokenIndex[IrChr, IrStr]
    ranks: IrTokenIndex[IrTuple, IrInt]


def _vocab_part(text: str, program: CaptureProgram, span: Span) -> IrTables:
    """Capture one vocab fragment directly into final scalar leaf types."""
    pos, end = span
    tables = IrTables({}, {})
    transition = program.first
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"composed IR prototype: vocab capture failed at {pos}"
            )
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("composed IR vocab transition lost captures")
        spelling = IrStr(_decode_key(key))
        identifier = IrChr(int(ordinal))
        if spelling in tables.encode or identifier in tables.decode:
            raise UnsupportedConstructError(
                "composed IR prototype: repeated vocabulary key or id"
            )
        tables.encode[spelling] = identifier
        tables.decode[identifier] = spelling
        pos = matched.end()
        transition = program.next
    if pos != end:
        raise AssertionError("composed IR vocab capture changed fragment end")
    return tables


def _merge_part(text: str, program: MergeProgram, span: Span) -> IrRanks:
    """Capture one merge fragment into final dyad leaves and local ranks."""
    pos, end = span
    ranks: IrRanks = {}
    transition = program.capture_first
    while pos < end:
        matched = transition.match(text, pos, end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"composed IR prototype: merge capture failed at {pos}"
            )
        left = matched.group("left")
        right = matched.group("right")
        if left is None or right is None:
            raise AssertionError("composed IR merge transition lost captures")
        dyad = IrTuple(IrStr(_decode_key(left)), IrStr(_decode_key(right)))
        if dyad in ranks:
            raise UnsupportedConstructError(
                "composed IR prototype: repeated merge dyad"
            )
        ranks[dyad] = len(ranks)
        pos = matched.end()
        transition = program.capture_next
    if pos != end:
        raise AssertionError("composed IR merge capture changed fragment end")
    return ranks


def _collect[Value](futures: tuple[Future[Value], ...]) -> tuple[Value, ...]:
    """Collect one homogeneous future family in source order."""
    return tuple(future.result() for future in futures)


def _join_vocab(parts: tuple[IrTables, ...]) -> IrTables:
    """Join vocab fragments once and refuse boundary duplicates."""
    encode: dict[IrStr, IrChr] = {}
    decode: dict[IrChr, IrStr] = {}
    expected = 0
    for part in parts:
        expected += len(part.encode)
        encode.update(part.encode)
        decode.update(part.decode)
    if len(encode) != expected or len(decode) != expected:
        raise UnsupportedConstructError(
            "composed IR prototype: cross-fragment vocab duplicate"
        )
    return IrTables(encode, decode)


def _join_ranks(parts: tuple[IrRanks, ...]) -> dict[IrTuple, IrInt]:
    """Join merge fragments once and assign final source-order rank leaves."""
    ranks: dict[IrTuple, IrInt] = {}
    for part in parts:
        for dyad in part:
            if dyad in ranks:
                raise UnsupportedConstructError(
                    "composed IR prototype: cross-fragment merge duplicate"
                )
            ranks[dyad] = IrInt(len(ranks))
    return ranks


def _freeze(
    vocab: IrTables, ranks: dict[IrTuple, IrInt]
) -> tuple[
    IrTokenIndex[IrStr, IrChr],
    IrTokenIndex[IrChr, IrStr],
    IrTokenIndex[IrTuple, IrInt],
]:
    """Copy relinquished builders into immutable tokenizer-native indexes."""
    return (
        IrTokenIndex.from_owned(vocab.encode),
        IrTokenIndex.from_owned(vocab.decode),
        IrTokenIndex.from_owned(ranks),
    )


def _construct(
    encode: IrTokenIndex[IrStr, IrChr],
    decode: IrTokenIndex[IrChr, IrStr],
    ranks: IrTokenIndex[IrTuple, IrInt],
) -> IrTokenizer:
    """Construct the current runtime record with the proposed field subtype."""
    return IrTuple.__new__(
        IrTokenizer,
        IrStr("qwen3"),
        encode,
        decode,
        ranks,
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
    """Measure anchors through final scalar leaves, indexes, and record."""
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
            pool.submit(_vocab_part, text, program, span)
            for program, span in zip(vocab_programs, vocab_spans, strict=True)
        )
        merge_futures = tuple(
            pool.submit(_merge_part, text, program, span)
            for program, span in zip(merge_programs, merge_spans, strict=True)
        )
        vocab = _join_vocab(_collect(vocab_futures))
        ranks = _join_ranks(_collect(merge_futures))
        capture_finished = time.perf_counter()
        encode, decode, frozen_ranks = _freeze(vocab, ranks)
        freeze_finished = time.perf_counter()
        tokenizer = _construct(encode, decode, frozen_ranks)
        construct_finished = time.perf_counter()
        product = Product(tokenizer, encode, decode, frozen_ranks)
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
        ),
        product,
    )


def _validate(text: str, product: Product) -> None:
    """Require exact native values, source order, and runtime lookup behavior."""
    expected_vocab = _expected_vocab(text)
    expected_ranks = _expected_merges(text)
    if {str(key): int(value) for key, value in product.encode.items()} != (
        expected_vocab.encode
    ):
        raise AssertionError("composed IR prototype changed encode")
    if {int(key): str(value) for key, value in product.decode.items()} != (
        expected_vocab.decode
    ):
        raise AssertionError("composed IR prototype changed decode")
    if {
        (str(key[0]), str(key[1])): int(value) for key, value in product.ranks.items()
    } != expected_ranks:
        raise AssertionError("composed IR prototype changed ranks")
    if product.tokenizer.encode is not product.encode:
        raise AssertionError("composed IR tokenizer copied encode")
    if product.tokenizer.decode is not product.decode:
        raise AssertionError("composed IR tokenizer copied decode")
    if product.tokenizer.ranks is not product.ranks:
        raise AssertionError("composed IR tokenizer copied ranks")
    for spelling, identifier in tuple(product.encode.items())[:32]:
        if product.tokenizer.resolve(spelling) != identifier:
            raise AssertionError("composed IR tokenizer changed forward lookup")
        if product.tokenizer.spell(identifier) != spelling:
            raise AssertionError("composed IR tokenizer changed inverse lookup")


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated composed-carrier run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Measure a native-source-to-final-IR high-volume tokenizer carrier."""
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
        _vocab_replica(shared_vocab, index) for index in range(options.region_workers)
    )
    merge_programs = tuple(
        _merge_replica(shared_merge, index) for index in range(options.region_workers)
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
                f"{reading.freeze_seconds:.6f}",
                f"{reading.construct_seconds:.6f}",
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
        f"{statistics.median(r.capture_seconds for r in readings):.6f}",
        f"{statistics.median(r.freeze_seconds for r in readings):.6f}",
        f"{statistics.median(r.construct_seconds for r in readings):.6f}",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
