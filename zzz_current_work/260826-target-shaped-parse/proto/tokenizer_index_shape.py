"""Measure tokenizer-native immutable indexes over real IR leaves."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Iterable, Sequence
from typing import NamedTuple, Self

from tokenizer_table_cost import Fixture, _fixture
from tokenizer_table_phases import NativeTables, _native_fixture, _populate_native

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrTuple
from lexic.ir.action.mapping import IrMapping


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int

    def validate(self) -> None:
        """Refuse a non-positive round count."""
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "tokenizer index prototype: rounds must be positive"
            )


class IrTokenIndex[Key, Value](IrMapping[Key, Value, Value]):
    """Immutable tokenizer lookup base; concrete roles own canonical order."""

    __slots__ = ()

    @classmethod
    def from_owned(cls, table: dict[Key, Value]) -> Self:
        """Freeze a validated builder table without sorting its keys."""
        index = super().__new__(cls)
        index._table.update(table)
        return index


class IrTokenEncode(IrTokenIndex[str, int]):
    """Spelling-to-id index, canonical by id then spelling."""

    __slots__ = ()

    def __new__(cls, *dyads: IrTuple[str, int]) -> Self:
        """Reconstruct notation/repr dyads under canonical id order."""
        return cls.from_table((dyad[0], dyad[1]) for dyad in dyads)

    @classmethod
    def from_table(cls, pairs: Iterable[tuple[str, int]]) -> Self:
        """Build a canonical public/readback index with duplicate refusal."""
        return super().from_table(sorted(pairs, key=lambda pair: (pair[1], pair[0])))


class IrTokenDecode(IrTokenIndex[int, str]):
    """Id-to-spelling index, canonical by id."""

    __slots__ = ()

    def __new__(cls, *dyads: IrTuple[int, str]) -> Self:
        """Reconstruct notation/repr dyads under canonical id order."""
        return cls.from_table((dyad[0], dyad[1]) for dyad in dyads)

    @classmethod
    def from_table(cls, pairs: Iterable[tuple[int, str]]) -> Self:
        """Build a canonical public/readback index with duplicate refusal."""
        return super().from_table(sorted(pairs, key=lambda pair: pair[0]))


class IrTokenRanks(IrTokenIndex[tuple[str, str], int]):
    """Merge-dyad index, canonical by rank then dyad."""

    __slots__ = ()

    def __new__(cls, *dyads: IrTuple[tuple[str, str], int]) -> Self:
        """Reconstruct notation/repr dyads under canonical rank order."""
        return cls.from_table((dyad[0], dyad[1]) for dyad in dyads)

    @classmethod
    def from_table(cls, pairs: Iterable[tuple[tuple[str, str], int]]) -> Self:
        """Build a canonical public/readback index with duplicate refusal."""
        return super().from_table(sorted(pairs, key=lambda pair: (pair[1], pair[0])))


class ReadyIndexes(NamedTuple):
    """The three final tokenizer-native lookup mappings."""

    encode: IrTokenEncode
    decode: IrTokenDecode
    ranks: IrTokenRanks


class Reading(NamedTuple):
    """One final-index construction reading."""

    process_seconds: float
    wall_seconds: float


def _freeze(tables: NativeTables) -> ReadyIndexes:
    """Canonicalize validated native builders and freeze each once."""
    decode = dict(sorted(tables.decode.items()))
    encode = {spelling: identifier for identifier, spelling in decode.items()}
    ranks = dict(sorted(tables.ranks.items(), key=lambda pair: pair[1]))
    return ReadyIndexes(
        IrTokenEncode.from_owned(encode),
        IrTokenDecode.from_owned(decode),
        IrTokenRanks.from_owned(ranks),
    )


def _validate(indexes: ReadyIndexes, tables: NativeTables, fixture: Fixture) -> None:
    """Require exact lookup values and deterministic source-order views."""
    if dict(indexes.encode.items()) != tables.encode:
        raise AssertionError("tokenizer index prototype changed encode")
    if dict(indexes.decode.items()) != tables.decode:
        raise AssertionError("tokenizer index prototype changed decode")
    if dict(indexes.ranks.items()) != tables.ranks:
        raise AssertionError("tokenizer index prototype changed ranks")
    expected_ids = tuple(sorted(tables.decode))
    if tuple(indexes.encode.values()) != expected_ids:
        raise AssertionError("tokenizer index prototype changed encode order")
    if tuple(indexes.decode.keys()) != expected_ids:
        raise AssertionError("tokenizer index prototype changed decode order")
    if tuple(indexes.ranks.values()) != tuple(range(len(tables.ranks))):
        raise AssertionError("tokenizer index prototype changed rank order")
    for spelling, ordinal in _native_fixture(fixture).vocab:
        if indexes.encode[spelling] != ordinal:
            raise AssertionError("tokenizer index prototype lost vocab lookup")
        if indexes.decode[ordinal] != spelling:
            raise AssertionError("tokenizer index prototype lost inverse lookup")
    reversed_encode = tuple(reversed(tuple(tables.encode.items())))
    reversed_decode = tuple(reversed(tuple(tables.decode.items())))
    reversed_ranks = tuple(reversed(tuple(tables.ranks.items())))
    rebuilt = ReadyIndexes(
        IrTokenEncode.from_table(reversed_encode),
        IrTokenDecode.from_table(reversed_decode),
        IrTokenRanks.from_table(reversed_ranks),
    )
    if rebuilt != indexes or hash(rebuilt) != hash(indexes):
        raise AssertionError("tokenizer index canonical readback changed identity")
    first = IrTokenEncode.from_table((("later", 1), ("first", 0)))
    second = IrTokenEncode.from_table((("first", 0), ("later", 1)))
    reconstructed = IrTokenEncode(IrTuple("later", 1), IrTuple("first", 0))
    if first != reconstructed or repr(first) != repr(second):
        raise AssertionError("tokenizer index canonical readback changed repr")


def _measure(tables: NativeTables) -> tuple[Reading, ReadyIndexes]:
    """Measure final index construction with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        indexes = _freeze(tables)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), indexes


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated final-index run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Build real-IR tokenizer indexes and print raw timings."""
    options = _parse_options(arguments)
    fixture = _fixture()
    tables = _populate_native(_native_fixture(fixture))
    readings: list[Reading] = []
    for number in range(1, options.rounds + 1):
        reading, indexes = _measure(tables)
        _validate(indexes, tables, fixture)
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            sep="\t",
        )
        del indexes
        gc.collect()
    print(
        "median",
        f"{statistics.median(value.process_seconds for value in readings):.6f}",
        f"{statistics.median(value.wall_seconds for value in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
