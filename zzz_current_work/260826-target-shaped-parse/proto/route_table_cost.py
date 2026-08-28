"""Compare finite-route representations outside the parser source tree."""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from typing import NamedTuple

EXTENSION = 0
ROUNDS = 9
TARGET_LOOKUPS = 1_000_000

SCHEMA_KEYS = (
    "model",
    "added_tokens",
    "normalizer",
    "pre_tokenizer",
    "post_processor",
    "decoder",
    "type",
    "vocab",
    "merges",
    "dropout",
    "unk_token",
    "continuing_subword_prefix",
    "end_of_word_suffix",
    "fuse_unk",
    "byte_fallback",
    "content",
    "single_word",
    "lstrip",
    "rstrip",
    "normalized",
    "special",
    "id",
    "pattern",
    "behavior",
    "invert",
    "replacement",
    "prepend_scheme",
    "trim_offsets",
    "use_regex",
    "add_prefix_space",
    "lowercase",
    "strip_accents",
    "synthetic_32",
    "synthetic_33",
    "synthetic_34",
    "synthetic_35",
    "synthetic_36",
    "synthetic_37",
    "synthetic_38",
    "synthetic_39",
    "synthetic_40",
    "synthetic_41",
    "synthetic_42",
    "synthetic_43",
    "synthetic_44",
    "synthetic_45",
    "synthetic_46",
    "synthetic_47",
    "synthetic_48",
    "synthetic_49",
    "synthetic_50",
    "synthetic_51",
    "synthetic_52",
    "synthetic_53",
    "synthetic_54",
    "synthetic_55",
    "synthetic_56",
    "synthetic_57",
    "synthetic_58",
    "synthetic_59",
    "synthetic_60",
    "synthetic_61",
    "synthetic_62",
    "synthetic_63",
)


class Reading(NamedTuple):
    """One representation's lookup cost."""

    name: str
    minimum_ns: float
    median_ns: float


def _queries(keys: tuple[str, ...]) -> tuple[str, ...]:
    """Interleave hits and misses without random-number overhead."""
    return tuple(
        value
        for index, key in enumerate(keys)
        for value in (key, f"extension_{index}")
    )


def _linear(
    keys: tuple[str, ...], queries: tuple[str, ...], repeats: int
) -> int:
    """Classify through the prototype's tuple scan."""
    total = 0
    for _repeat in range(repeats):
        for query in queries:
            route = EXTENSION
            for index, key in enumerate(keys, 1):
                if query == key:
                    route = index
                    break
            total += route
    return total


def _indexed(
    keys: tuple[str, ...], queries: tuple[str, ...], repeats: int
) -> int:
    """Classify through a bound private dictionary."""
    table = {key: index for index, key in enumerate(keys, 1)}
    get = table.get
    total = 0
    for _repeat in range(repeats):
        for query in queries:
            total += get(query, EXTENSION)
    return total


def _singleton(
    keys: tuple[str, ...], queries: tuple[str, ...], repeats: int
) -> int:
    """Classify one known key through one equality test."""
    key = keys[0]
    total = 0
    for _repeat in range(repeats):
        for query in queries:
            total += 1 if query == key else EXTENSION
    return total


def _uniform(
    _keys: tuple[str, ...], queries: tuple[str, ...], repeats: int
) -> int:
    """Exercise the dynamic-map route which performs no classification."""
    total = 0
    for _repeat in range(repeats):
        for _query in queries:
            total += 1
    return total


def _measure(
    run: Callable[[tuple[str, ...], tuple[str, ...], int], int],
    keys: tuple[str, ...],
    queries: tuple[str, ...],
    repeats: int,
) -> tuple[float, int]:
    """Return process nanoseconds per lookup and the retained witness."""
    started = time.process_time_ns()
    witness = run(keys, queries, repeats)
    elapsed = time.process_time_ns() - started
    return elapsed / (len(queries) * repeats), witness


def _readings(size: int) -> tuple[Reading, ...]:
    """Alternate every applicable representation at one cardinality."""
    keys = SCHEMA_KEYS[:size]
    queries = _queries(keys)
    repeats = max(1, TARGET_LOOKUPS // len(queries))
    runners: tuple[
        tuple[
            str,
            Callable[[tuple[str, ...], tuple[str, ...], int], int],
        ],
        ...,
    ] = (
        (("singleton", _singleton),) if size == 1 else ()
    ) + (("linear", _linear), ("indexed", _indexed), ("uniform", _uniform))
    samples: dict[str, list[float]] = {name: [] for name, _run in runners}
    witness: int | None = None
    for round_number in range(ROUNDS):
        ordered = runners if round_number % 2 == 0 else tuple(reversed(runners))
        for name, run in ordered:
            elapsed, observed = _measure(run, keys, queries, repeats)
            samples[name].append(elapsed)
            if name == "uniform":
                continue
            if witness is None:
                witness = observed
            elif observed != witness:
                raise AssertionError("route representations disagree")
    return tuple(
        Reading(name, min(values), statistics.median(values))
        for name, values in samples.items()
    )


def _choice_scan(
    routes: tuple[int, ...],
    _destinations: tuple[int, ...],
    choices: tuple[tuple[int, int], ...],
    repeats: int,
) -> int:
    """Resolve route destinations through a choice scan."""
    total = 0
    for _repeat in range(repeats):
        for route in routes:
            for candidate, destination in choices:
                if route == candidate:
                    total += destination
                    break
    return total


def _dense_index(
    routes: tuple[int, ...],
    destinations: tuple[int, ...],
    _choices: tuple[tuple[int, int], ...],
    repeats: int,
) -> int:
    """Resolve dense route ids by direct tuple indexing."""
    total = 0
    for _repeat in range(repeats):
        for route in routes:
            total += destinations[route]
    return total


def _dense_destination() -> tuple[Reading, Reading]:
    """Compare route-to-child tuple indexing with a choice scan."""
    routes = tuple(range(1, 33))
    destinations = tuple(index + 1000 for index in range(33))
    choices = tuple((route, destinations[route]) for route in routes)
    repeats = max(1, TARGET_LOOKUPS // len(routes))
    samples = {"choice_scan": [], "dense_index": []}
    witness: int | None = None
    runners = (("choice_scan", _choice_scan), ("dense_index", _dense_index))
    for round_number in range(ROUNDS):
        ordered = runners if round_number % 2 == 0 else tuple(reversed(runners))
        for name, run in ordered:
            started = time.process_time_ns()
            observed = run(routes, destinations, choices, repeats)
            elapsed = time.process_time_ns() - started
            samples[name].append(elapsed / (len(routes) * repeats))
            if witness is None:
                witness = observed
            elif observed != witness:
                raise AssertionError("route destinations disagree")
    choice = samples["choice_scan"]
    dense_values = samples["dense_index"]
    return (
        Reading("choice_scan", min(choice), statistics.median(choice)),
        Reading(
            "dense_index", min(dense_values), statistics.median(dense_values)
        ),
    )


def main() -> None:
    """Print alternating in-process route representation measurements."""
    print("cardinality\trepresentation\tminimum_ns\tmedian_ns")
    for size in (1, 2, 4, 8, 16, 32, 64):
        for reading in _readings(size):
            print(
                size,
                reading.name,
                f"{reading.minimum_ns:.3f}",
                f"{reading.median_ns:.3f}",
                sep="\t",
            )
    for reading in _dense_destination():
        print(
            "destination",
            reading.name,
            f"{reading.minimum_ns:.3f}",
            f"{reading.median_ns:.3f}",
            sep="\t",
        )


if __name__ == "__main__":
    main()
