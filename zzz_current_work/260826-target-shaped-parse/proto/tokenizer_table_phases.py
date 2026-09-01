"""Separate Qwen tokenizer-table accumulation from canonical ordering."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Callable, Sequence
from typing import NamedTuple

from tokenizer_table_cost import Fixture, _fixture

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrChr, IrInt, IrStr, IrTuple


class OwnedTables(NamedTuple):
    """Mutable indexes whose producer relinquishes ownership after parsing."""

    encode: dict[IrStr, IrChr]
    decode: dict[IrChr, IrStr]
    ranks: dict[IrTuple, IrInt]


class CanonicalOrders(NamedTuple):
    """Canonical key order beside three already-owned indexes."""

    encode: tuple[IrStr, ...]
    decode: tuple[IrChr, ...]
    ranks: tuple[IrTuple, ...]


class NativeFixture(NamedTuple):
    """Tokenizer entries in the scalar types the final runtime consumes."""

    vocab: tuple[tuple[str, int], ...]
    ranks: tuple[tuple[tuple[str, str], int], ...]


class NativeTables(NamedTuple):
    """Owned native lookup indexes for a tokenizer-specific carrier."""

    encode: dict[str, int]
    decode: dict[int, str]
    ranks: dict[tuple[str, str], int]


class Reading(NamedTuple):
    """One isolated phase reading."""

    process_seconds: float
    wall_seconds: float


class Options(argparse.Namespace):
    """Validated phase selection."""

    mode: str
    rounds: int

    def validate(self) -> None:
        """Refuse unknown phases and non-positive round counts."""
        if self.mode not in (
            "populate",
            "canonical-order",
            "native-populate",
            "native-convert",
        ):
            raise UnsupportedConstructError(
                f"tokenizer phase prototype: unknown mode {self.mode!r}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "tokenizer phase prototype: rounds must be positive"
            )


def _populate(fixture: Fixture) -> OwnedTables:
    """Populate the three final lookup indexes with duplicate checks."""
    encode: dict[IrStr, IrChr] = {}
    decode: dict[IrChr, IrStr] = {}
    ranks: dict[IrTuple, IrInt] = {}
    for spelling, ordinal in fixture.vocab:
        if spelling in encode or ordinal in decode:
            raise UnsupportedConstructError(
                "tokenizer phase prototype: repeated vocabulary key or id"
            )
        encode[spelling] = ordinal
        decode[ordinal] = spelling
    for dyad, rank in fixture.ranks:
        if dyad in ranks:
            raise UnsupportedConstructError(
                "tokenizer phase prototype: repeated merge dyad"
            )
        ranks[dyad] = rank
    return OwnedTables(encode, decode, ranks)


def _canonical_order(fixture: Fixture) -> CanonicalOrders:
    """Sort keys while retaining the already-populated lookup indexes."""
    tables = _populate(fixture)
    return CanonicalOrders(
        tuple(sorted(tables.encode, key=repr)),
        tuple(sorted(tables.decode, key=repr)),
        tuple(sorted(tables.ranks, key=repr)),
    )


def _native_fixture(fixture: Fixture) -> NativeFixture:
    """Prepare the plain values a direct scalar decoder would publish."""
    vocab = tuple((str(key), int(value)) for key, value in fixture.vocab)
    ranks = tuple(
        (
            (str(dyad[0]), str(dyad[1])),
            int(rank),
        )
        for dyad, rank in fixture.ranks
    )
    return NativeFixture(vocab, ranks)


def _populate_native(fixture: NativeFixture) -> NativeTables:
    """Populate native final indexes with duplicate checks."""
    encode: dict[str, int] = {}
    decode: dict[int, str] = {}
    ranks: dict[tuple[str, str], int] = {}
    for spelling, ordinal in fixture.vocab:
        if spelling in encode or ordinal in decode:
            raise UnsupportedConstructError(
                "tokenizer phase prototype: repeated native vocabulary key or id"
            )
        encode[spelling] = ordinal
        decode[ordinal] = spelling
    for dyad, rank in fixture.ranks:
        if dyad in ranks:
            raise UnsupportedConstructError(
                "tokenizer phase prototype: repeated native merge dyad"
            )
        ranks[dyad] = rank
    return NativeTables(encode, decode, ranks)


def _convert_native(fixture: Fixture) -> NativeTables:
    """Include conversion from the current IR leaves as an upper-cost witness."""
    return _populate_native(_native_fixture(fixture))


def _validate_tables(result: OwnedTables, fixture: Fixture) -> None:
    """Require exact equality with the ready tokenizer's retained tables."""
    if result.encode != dict(fixture.reference.encode.items()):
        raise AssertionError("tokenizer phase prototype changed encode")
    if result.decode != dict(fixture.reference.decode.items()):
        raise AssertionError("tokenizer phase prototype changed decode")
    if result.ranks != dict(fixture.reference.ranks.items()):
        raise AssertionError("tokenizer phase prototype changed ranks")


def _validate_orders(result: CanonicalOrders, fixture: Fixture) -> None:
    """Require the same canonical order exposed by current ``IrMap`` values."""
    if result.encode != tuple(fixture.reference.encode.keys()):
        raise AssertionError("tokenizer phase prototype changed encode order")
    if result.decode != tuple(fixture.reference.decode.keys()):
        raise AssertionError("tokenizer phase prototype changed decode order")
    if result.ranks != tuple(fixture.reference.ranks.keys()):
        raise AssertionError("tokenizer phase prototype changed rank order")


def _validate_native(result: NativeTables, fixture: Fixture) -> None:
    """Require native indexes to preserve every tokenizer lookup."""
    expected = _native_fixture(fixture)
    if result.encode != dict(expected.vocab):
        raise AssertionError("tokenizer phase prototype changed native encode")
    if result.decode != {ordinal: spelling for spelling, ordinal in expected.vocab}:
        raise AssertionError("tokenizer phase prototype changed native decode")
    if result.ranks != dict(expected.ranks):
        raise AssertionError("tokenizer phase prototype changed native ranks")


def _measure[Source, Result](
    run: Callable[[Source], Result], fixture: Source
) -> tuple[Reading, Result]:
    """Measure one phase with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        result = run(fixture)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), result


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated table phase."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Load the reference outside timing, then measure one table phase."""
    options = _parse_options(arguments)
    fixture = _fixture()
    native_fixture = _native_fixture(fixture)
    readings: list[Reading] = []
    for number in range(1, options.rounds + 1):
        if options.mode == "populate":
            reading, result = _measure(_populate, fixture)
            _validate_tables(result, fixture)
        elif options.mode == "canonical-order":
            reading, result = _measure(_canonical_order, fixture)
            _validate_orders(result, fixture)
        elif options.mode == "native-populate":
            reading, result = _measure(_populate_native, native_fixture)
            _validate_native(result, fixture)
        else:
            reading, result = _measure(_convert_native, fixture)
            _validate_native(result, fixture)
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


if __name__ == "__main__":
    main()
