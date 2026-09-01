"""Prototype window-composable discovery through escaped opaque interiors."""

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
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir import IrLiteral
from lexic.parsing.parallel.discovery.regions import (
    Region,
    find,
    pair_rules,
    separators,
)


class Options(argparse.Namespace):
    """Validated window count and rounds."""

    windows: int
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported window counts and non-positive rounds."""
        if self.windows not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"windowed discovery prototype: unsupported windows {self.windows}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "windowed discovery prototype: rounds must be positive"
            )


class ScanState(NamedTuple):
    """Whether the cursor is inside an escaped delimited interior."""

    inside: bool
    escaped: bool


type Event = tuple[int, str]


class WindowResult(NamedTuple):
    """Both possible start-state answers for one arithmetic window."""

    outside_events: tuple[Event, ...]
    outside_end: bool
    inside_events: tuple[Event, ...]
    inside_end: bool


class Reading(NamedTuple):
    """One complete discovery reading."""

    process_seconds: float
    wall_seconds: float


class ScanSpec(NamedTuple):
    """Grammar-derived roles needed by the escaped-interior transducer."""

    quote: str
    escape: str
    pairs: dict[str, tuple[str, str]]
    closers: dict[str, str]
    marks: frozenset[str]

    @property
    def structural(self) -> frozenset[str]:
        """Every paired delimiter and separator reported outside interiors."""
        return frozenset(self.pairs) | frozenset(self.closers) | self.marks

    @property
    def watched(self) -> frozenset[str]:
        """Every character one window searches for."""
        return self.structural | {self.quote, self.escape}


def _spec() -> ScanSpec:
    """Build the prototype roles from the real lower grammar's structure."""
    pairs = pair_rules(JSON_GRAMMAR)
    literals: dict[str, str] = {}
    for rule in JSON_GRAMMAR.rules:
        if str(rule.name) not in ("quotation-mark", "escape"):
            continue
        values = tuple(
            str(item.atom)
            for arm in rule.body
            for item in arm
            if isinstance(item.atom, IrLiteral)
        )
        if len(values) != 1 or len(values[0]) != 1:
            raise UnsupportedConstructError(
                f"windowed discovery prototype: {rule.name} is not one literal"
            )
        literals[str(rule.name)] = values[0]
    return ScanSpec(
        literals["quotation-mark"],
        literals["escape"],
        pairs,
        {closer: opener for opener, (closer, _rule) in pairs.items()},
        separators(JSON_GRAMMAR),
    )


def _occurrences(text: str, char: str, lo: int, hi: int) -> list[Event]:
    """Find one watched character through C-level searches in a window."""
    events: list[Event] = []
    at = text.find(char, lo, hi)
    while at != -1:
        events.append((at, char))
        at = text.find(char, at + 1, hi)
    return events


def _escaped_at(text: str, lo: int) -> bool:
    """Whether the character at ``lo`` follows an odd backslash run."""
    count = 0
    at = lo - 1
    while at >= 0 and text[at] == "\\":
        count += 1
        at -= 1
    return count % 2 == 1


def _step(
    state: ScanState,
    char: str,
    event: Event,
    structural: frozenset[str],
    quote: str,
    escape: str,
    output: list[Event],
) -> ScanState:
    """Advance one candidate start state over one watched character."""
    if state.escaped:
        return ScanState(state.inside, False)
    if state.inside and char == escape:
        return ScanState(True, True)
    if char == quote:
        return ScanState(not state.inside, False)
    if not state.inside and char in structural:
        output.append(event)
    return state


def _window(text: str, lo: int, hi: int, spec: ScanSpec) -> WindowResult:
    """Compute both possible interior-state answers for one window."""
    events: list[Event] = []
    for char in spec.watched:
        events.extend(_occurrences(text, char, lo, hi))
    events.sort()

    outside = ScanState(False, False)
    inside = ScanState(True, _escaped_at(text, lo))
    outside_events: list[Event] = []
    inside_events: list[Event] = []
    outside_cursor = lo
    inside_cursor = lo
    structural = spec.structural
    quote = spec.quote
    escape = spec.escape
    for event in events:
        at, char = event
        if outside.escaped and at > outside_cursor:
            outside = ScanState(outside.inside, False)
        if inside.escaped and at > inside_cursor:
            inside = ScanState(inside.inside, False)
        outside = _step(
            outside,
            char,
            event,
            structural,
            quote,
            escape,
            outside_events,
        )
        inside = _step(
            inside,
            char,
            event,
            structural,
            quote,
            escape,
            inside_events,
        )
        outside_cursor = at + 1
        inside_cursor = at + 1
    if outside.escaped and hi > outside_cursor:
        outside = ScanState(outside.inside, False)
    if inside.escaped and hi > inside_cursor:
        inside = ScanState(inside.inside, False)
    return WindowResult(
        tuple(outside_events),
        outside.inside,
        tuple(inside_events),
        inside.inside,
    )


def _windows(length: int, count: int) -> tuple[tuple[int, int], ...]:
    """Divide the complete document arithmetically."""
    return tuple(
        (length * index // count, length * (index + 1) // count)
        for index in range(count)
    )


def _window_bound(text: str, spec: ScanSpec, bound: tuple[int, int]) -> WindowResult:
    """Run one arithmetic bound through the window scanner."""
    return _window(text, bound[0], bound[1], spec)


def _choose(results: tuple[WindowResult, ...]) -> tuple[Event, ...]:
    """Prefix-compose actual interior state and select each window's events."""
    inside = False
    selected: list[Event] = []
    for result in results:
        if inside:
            selected.extend(result.inside_events)
            inside = result.inside_end
        else:
            selected.extend(result.outside_events)
            inside = result.outside_end
    if inside:
        raise UnsupportedConstructError(
            "windowed discovery prototype: unterminated opaque interior"
        )
    return tuple(selected)


def _regions(text: str, events: tuple[Event, ...], spec: ScanSpec) -> list[Region]:
    """Apply the current structural stack semantics to selected events."""
    found: list[Region] = []
    stack: list[tuple[int, str, list[int]]] = []
    for at, char in events:
        if char in spec.pairs:
            stack.append((at, char, []))
        elif char in spec.closers and stack and stack[-1][1] == spec.closers[char]:
            opener, opening, marks = stack.pop()
            if marks and at - opener >= 2_048:
                found.append(Region(opener, at, spec.pairs[opening][1], tuple(marks)))
        elif char in spec.marks and stack:
            stack[-1][2].append(at)
    if stack:
        raise UnsupportedConstructError(
            "windowed discovery prototype: unmatched structural opener"
        )
    return found


def _measure(
    text: str,
    bounds: tuple[tuple[int, int], ...],
    spec: ScanSpec,
    pool: ThreadPoolExecutor | None,
) -> tuple[Reading, list[Region]]:
    """Measure window scans, prefix selection, and structural reconstruction."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        if pool is None:
            results = tuple(_window(text, lo, hi, spec) for lo, hi in bounds)
        else:
            results = tuple(
                pool.map(lambda bound: _window_bound(text, spec, bound), bounds)
            )
        regions = _regions(text, _choose(results), spec)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), regions


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated window-count probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=5)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def _shape(regions: list[Region]) -> tuple[tuple[int, int, str, tuple[int, ...]], ...]:
    """Return the exact discovery value for oracle comparison."""
    return tuple(
        (region.opener, region.closer, region.rule, region.marks) for region in regions
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Compare complete windowed discovery with the current semantic oracle."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    spec = _spec()
    expected = _shape(find(JSON_GRAMMAR, text, min_span=2_048))
    bounds = _windows(len(text), options.windows)
    pool = (
        None
        if options.windows == 1
        else ThreadPoolExecutor(max_workers=options.windows)
    )
    if pool is not None:
        tuple(pool.map(lambda value: value, range(options.windows)))

    readings: list[Reading] = []
    try:
        for number in range(1, options.rounds + 1):
            reading, regions = _measure(text, bounds, spec, pool)
            if _shape(regions) != expected:
                raise AssertionError(
                    "windowed discovery prototype changed the region result"
                )
            readings.append(reading)
            print(
                "round",
                number,
                f"{reading.process_seconds:.6f}",
                f"{reading.wall_seconds:.6f}",
                sep="\t",
            )
            del regions
            gc.collect()
    finally:
        if pool is not None:
            pool.shutdown()
    print("regions", len(expected), sep="\t")
    print("marks", sum(len(region[3]) for region in expected), sep="\t")
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
