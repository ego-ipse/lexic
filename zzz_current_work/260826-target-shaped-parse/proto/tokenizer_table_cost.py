"""Measure Qwen-scale final tokenizer table construction outside ``src``."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.api import json_tokenizer
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrChr, IrInt, IrMap, IrStr, IrTokenizer, IrTuple

type VocabPair = tuple[IrStr, IrChr]
type RankPair = tuple[IrTuple, IrInt]


class Fixture(NamedTuple):
    """One ready tokenizer and its immutable source entries."""

    reference: IrTokenizer
    vocab: tuple[VocabPair, ...]
    ranks: tuple[RankPair, ...]
    merges: tuple[tuple[str, str], ...]


class Reading(NamedTuple):
    """One construction reading."""

    process_seconds: float
    wall_seconds: float


class Options(argparse.Namespace):
    """Validated command-line options."""

    mode: str
    rounds: int
    memory: bool

    def validate(self) -> None:
        """Refuse unsupported modes and non-positive rounds."""
        if self.mode not in (
            "current",
            "indexed",
            "pairs",
            "staged",
            "streamed",
        ):
            raise UnsupportedConstructError(
                f"tokenizer table prototype: unknown mode {self.mode!r}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "tokenizer table prototype: rounds must be positive"
            )


class PairTables:
    """Append pairs and duplicate sets, then freeze each final map once."""

    __slots__ = (
        "decode_keys",
        "decode_pairs",
        "encode_keys",
        "encode_pairs",
        "rank_keys",
        "rank_pairs",
    )

    def __init__(self) -> None:
        self.encode_pairs: list[VocabPair] = []
        self.encode_keys: set[IrStr] = set()
        self.decode_pairs: list[tuple[IrChr, IrStr]] = []
        self.decode_keys: set[IrChr] = set()
        self.rank_pairs: list[RankPair] = []
        self.rank_keys: set[IrTuple] = set()

    def vocab(self, spelling: IrStr, ordinal: IrChr) -> None:
        """Append both vocabulary directions while checking both keys."""
        if spelling in self.encode_keys or ordinal in self.decode_keys:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated vocabulary key or id"
            )
        self.encode_keys.add(spelling)
        self.decode_keys.add(ordinal)
        self.encode_pairs.append((spelling, ordinal))
        self.decode_pairs.append((ordinal, spelling))

    def rank(self, dyad: IrTuple, rank: IrInt) -> None:
        """Append one merge rank while checking its key."""
        if dyad in self.rank_keys:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated merge dyad"
            )
        self.rank_keys.add(dyad)
        self.rank_pairs.append((dyad, rank))

    def finish(self, fixture: Fixture) -> IrTokenizer:
        """Freeze three canonical maps and construct the record directly."""
        return fixture.reference.rebuild(
            (
                fixture.reference.name,
                IrMap.from_table(self.encode_pairs),
                IrMap.from_table(self.decode_pairs),
                IrMap.from_table(self.rank_pairs),
                fixture.reference.pipeline,
                fixture.reference.segmenter,
            )
        )


class IndexedTables:
    """Accumulate mutable indexes, then copy each into its final map."""

    __slots__ = ("decode", "encode", "ranks")

    def __init__(self) -> None:
        self.encode: dict[IrStr, IrChr] = {}
        self.decode: dict[IrChr, IrStr] = {}
        self.ranks: dict[IrTuple, IrInt] = {}

    def vocab(self, spelling: IrStr, ordinal: IrChr) -> None:
        """Insert both vocabulary directions."""
        if spelling in self.encode or ordinal in self.decode:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated vocabulary key or id"
            )
        self.encode[spelling] = ordinal
        self.decode[ordinal] = spelling

    def rank(self, dyad: IrTuple, rank: IrInt) -> None:
        """Insert one merge rank."""
        if dyad in self.ranks:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated merge dyad"
            )
        self.ranks[dyad] = rank

    def finish(self, fixture: Fixture) -> IrTokenizer:
        """Copy the three indexes into canonical maps."""
        return fixture.reference.rebuild(
            (
                fixture.reference.name,
                IrMap.from_table(self.encode.items()),
                IrMap.from_table(self.decode.items()),
                IrMap.from_table(self.ranks.items()),
                fixture.reference.pipeline,
                fixture.reference.segmenter,
            )
        )


class StagedIndexedTables(IndexedTables):
    """Freeze and release one mutable index before freezing the next."""

    __slots__ = ()

    def finish(self, fixture: Fixture) -> IrTokenizer:
        """Limit finalization overlap to one source and destination map."""
        encode_source = self.encode
        self.encode = {}
        encode = IrMap.from_table(encode_source.items())
        del encode_source

        decode_source = self.decode
        self.decode = {}
        decode = IrMap.from_table(decode_source.items())
        del decode_source

        rank_source = self.ranks
        self.ranks = {}
        ranks = IrMap.from_table(rank_source.items())
        del rank_source

        return fixture.reference.rebuild(
            (
                fixture.reference.name,
                encode,
                decode,
                ranks,
                fixture.reference.pipeline,
                fixture.reference.segmenter,
            )
        )


def _rank_value(pair: RankPair) -> int:
    """Return one merge's source-order rank."""
    return int(pair[1])


def _fixture() -> Fixture:
    """Load the real Qwen tokenizer once, outside every measured interval."""
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    reference = json_tokenizer.read_from_path(
        source, JSON_GRAMMAR, JSON_REDUCER
    )
    vocab: list[VocabPair] = []
    for key, value in reference.encode.items():
        vocab.append(
            (
                IrStr.ensure(key, "a Qwen vocabulary spelling"),
                IrChr.ensure(value, "a Qwen vocabulary id"),
            )
        )
    ranks: list[RankPair] = []
    for key, value in reference.ranks.items():
        ranks.append(
            (
                IrTuple.ensure(key, "a Qwen merge dyad"),
                IrInt.ensure(value, "a Qwen merge rank"),
            )
        )
    ranks.sort(key=_rank_value)
    merges: list[tuple[str, str]] = []
    for dyad, _rank in ranks:
        merges.append(
            (
                str(IrStr.ensure(dyad[0], "a Qwen merge left spelling")),
                str(IrStr.ensure(dyad[1], "a Qwen merge right spelling")),
            )
        )
    return Fixture(reference, tuple(vocab), tuple(ranks), tuple(merges))


def _current(fixture: Fixture) -> IrTokenizer:
    """Run the current inverse/rank rebuilding constructor."""
    return IrTokenizer.from_merges(
        str(fixture.reference.name),
        fixture.reference.encode,
        fixture.merges,
        pipeline=fixture.reference.pipeline,
    )


def _pairs(fixture: Fixture) -> IrTokenizer:
    """Build paired buffers and freeze final maps once."""
    tables = PairTables()
    for spelling, ordinal in fixture.vocab:
        tables.vocab(spelling, ordinal)
    for dyad, rank in fixture.ranks:
        tables.rank(dyad, rank)
    return tables.finish(fixture)


def _indexed(fixture: Fixture) -> IrTokenizer:
    """Build mutable indexes before final canonical maps."""
    tables = IndexedTables()
    for spelling, ordinal in fixture.vocab:
        tables.vocab(spelling, ordinal)
    for dyad, rank in fixture.ranks:
        tables.rank(dyad, rank)
    return tables.finish(fixture)


def _staged(fixture: Fixture) -> IrTokenizer:
    """Build indexes and release each as its final map freezes."""
    tables = StagedIndexedTables()
    for spelling, ordinal in fixture.vocab:
        tables.vocab(spelling, ordinal)
    for dyad, rank in fixture.ranks:
        tables.rank(dyad, rank)
    return tables.finish(fixture)


def _streamed(fixture: Fixture) -> IrTokenizer:
    """Freeze each table family as soon as its dependencies are complete."""
    encode_source: dict[IrStr, IrChr] = {}
    decode_source: dict[IrChr, IrStr] = {}
    for spelling, ordinal in fixture.vocab:
        if spelling in encode_source or ordinal in decode_source:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated vocabulary key or id"
            )
        encode_source[spelling] = ordinal
        decode_source[ordinal] = spelling
    encode = IrMap.from_table(encode_source.items())
    del encode_source
    decode = IrMap.from_table(decode_source.items())
    del decode_source

    rank_source: dict[IrTuple, IrInt] = {}
    for dyad, rank in fixture.ranks:
        if dyad in rank_source:
            raise UnsupportedConstructError(
                "tokenizer table prototype: repeated merge dyad"
            )
        rank_source[dyad] = rank
    ranks = IrMap.from_table(rank_source.items())
    del rank_source

    return fixture.reference.rebuild(
        (
            fixture.reference.name,
            encode,
            decode,
            ranks,
            fixture.reference.pipeline,
            fixture.reference.segmenter,
        )
    )


def _builder(mode: str) -> Callable[[Fixture], IrTokenizer]:
    """Select one prototype arm at the command-line boundary."""
    if mode == "current":
        return _current
    if mode == "indexed":
        return _indexed
    if mode == "pairs":
        return _pairs
    if mode == "staged":
        return _staged
    if mode == "streamed":
        return _streamed
    raise UnsupportedConstructError(
        f"tokenizer table prototype: unknown mode {mode!r}"
    )


def _measure(
    build: Callable[[Fixture], IrTokenizer], fixture: Fixture
) -> tuple[Reading, IrTokenizer]:
    """Measure one construction with GC disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        result = build(fixture)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), result


def _timings(
    build: Callable[[Fixture], IrTokenizer], fixture: Fixture, rounds: int
) -> None:
    """Print every raw reading plus medians."""
    readings: list[Reading] = []
    for number in range(1, rounds + 1):
        reading, result = _measure(build, fixture)
        if result != fixture.reference:
            raise AssertionError("tokenizer table prototype changed the result")
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
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


def _memory(
    build: Callable[[Fixture], IrTokenizer], fixture: Fixture
) -> None:
    """Measure allocations separately from timing evidence."""
    gc.collect()
    tracemalloc.start()
    result = build(fixture)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if result != fixture.reference:
        raise AssertionError("tokenizer table prototype changed the result")
    print("memory", current, peak, sep="\t")


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse the isolated prototype arm."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--memory", action="store_true")
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Load Qwen, then measure exactly one final-table representation."""
    options = _parse_options(arguments)
    fixture = _fixture()
    print(
        "fixture",
        len(fixture.vocab),
        len(fixture.ranks),
        sep="\t",
    )
    build = _builder(options.mode)
    if options.memory:
        _memory(build, fixture)
        return
    _timings(build, fixture, options.rounds)


if __name__ == "__main__":
    main()
