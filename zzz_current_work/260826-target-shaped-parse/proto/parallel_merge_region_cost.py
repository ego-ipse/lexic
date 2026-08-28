"""Measure a grammar-derived repeated-dyad region and direct rank product."""

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
from lexic.ir import IrRule
from lexic.parsing.pda.core.scanner import (
    Pattern,
    Recognizer,
    build_recognizer,
    compile_source,
)

from python_tree_cost import _load
from schema_region_cost import _decode_key


class Options(argparse.Namespace):
    """Validated product mode, worker count, and rounds."""

    mode: str
    workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unknown modes, worker counts, and non-positive rounds."""
        if self.mode not in ("recognize", "capture"):
            raise UnsupportedConstructError(
                f"merge region prototype: unknown mode {self.mode!r}"
            )
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"merge region prototype: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "merge region prototype: rounds must be positive"
            )


class RegionProgram(NamedTuple):
    """Compiled outer transitions and inner-fragment programs."""

    begin: Pattern
    first: Pattern
    next: Pattern
    fragment: Pattern
    capture_first: Pattern
    capture_next: Pattern


class Chunk(NamedTuple):
    """One adjacent entry range and its first source-order rank."""

    start: int
    end: int
    rank: int


class Reading(NamedTuple):
    """One fragment execution reading."""

    process_seconds: float
    wall_seconds: float


type Ranks = dict[tuple[str, str], int]


def _rules() -> dict[str, IrRule]:
    """Index the real lower grammar for recognizer compilation."""
    return {str(rule.name): rule for rule in JSON_GRAMMAR.rules}


def _recognizer() -> Recognizer:
    """Compile the acyclic lower rules used by the dyad schema."""
    roots = frozenset(
        {"begin-array", "end-array", "string", "value-separator"}
    )
    recognizer = build_recognizer(_rules(), roots)
    if recognizer is None:
        raise UnsupportedConstructError(
            "merge region prototype: lower closure is not recognizer-safe"
        )
    return recognizer


def _source(recognizer: Recognizer, name: str) -> str:
    """Return one grammar-derived rule pattern source."""
    return recognizer.pats[recognizer.index[name]].pattern


def _program() -> RegionProgram:
    """Compose an outer sequence of two-string inner sequences."""
    recognizer = _recognizer()
    begin = _source(recognizer, "begin-array")
    end = _source(recognizer, "end-array")
    string = _source(recognizer, "string")
    separator = _source(recognizer, "value-separator")
    captured = (
        rf"(?P<entry>(?:{begin})(?P<left>{string})(?:{separator})"
        rf"(?P<right>{string})(?:{end}))"
    )
    plain = (
        rf"(?:{begin})(?:{string})(?:{separator})(?:{string})(?:{end})"
    )
    return RegionProgram(
        compile_source(begin),
        compile_source(rf"(?:(?P<outer_end>{end})|{captured})"),
        compile_source(rf"(?:(?P<outer_end>{end})|(?:{separator}){captured})"),
        compile_source(rf"{plain}(?:(?:{separator}){plain})*+"),
        compile_source(captured),
        compile_source(rf"(?:{separator}){captured}"),
    )


def _entry_spans(
    text: str, start: int, program: RegionProgram
) -> tuple[tuple[int, int], ...]:
    """Locate merge entries once, outside every timing interval."""
    opened = program.begin.match(text, start)
    if opened is None:
        raise UnsupportedConstructError(
            "merge region prototype: outer opener did not match"
        )
    pos = opened.end()
    transition = program.first
    spans: list[tuple[int, int]] = []
    while True:
        matched = transition.match(text, pos)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"merge region prototype: outer transition failed at {pos}"
            )
        pos = matched.end()
        if matched.group("outer_end") is not None:
            return tuple(spans)
        spans.append((matched.start("entry"), matched.end("entry")))
        transition = program.next


def _chunks(entries: tuple[tuple[int, int], ...], workers: int) -> tuple[Chunk, ...]:
    """Group adjacent merge entries into near-equal ranked fragments."""
    count = len(entries)
    chunks: list[Chunk] = []
    for worker in range(workers):
        lo = count * worker // workers
        hi = count * (worker + 1) // workers
        if lo < hi:
            chunks.append(Chunk(entries[lo][0], entries[hi - 1][1], lo))
    return tuple(chunks)


def _recognize_chunk(text: str, pattern: Pattern, chunk: Chunk) -> int:
    """Recognize one certified merge fragment."""
    matched = pattern.fullmatch(text, chunk.start, chunk.end)
    if matched is None:
        raise UnsupportedConstructError(
            f"merge region prototype: fragment {chunk.start}:{chunk.end} failed"
        )
    return matched.end()


def _capture_chunk(text: str, program: RegionProgram, chunk: Chunk) -> Ranks:
    """Recognize one fragment and populate its source-ordered ranks."""
    pos = chunk.start
    rank = chunk.rank
    ranks: Ranks = {}
    transition = program.capture_first
    while pos < chunk.end:
        matched = transition.match(text, pos, chunk.end)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"merge region prototype: capture failed at {pos}"
            )
        left = matched.group("left")
        right = matched.group("right")
        if left is None or right is None:
            raise AssertionError("merge region transition lost its captures")
        dyad = (_decode_key(left), _decode_key(right))
        if dyad in ranks:
            raise UnsupportedConstructError(
                "merge region prototype: repeated merge dyad"
            )
        ranks[dyad] = rank
        rank += 1
        pos = matched.end()
        transition = program.capture_next
    if pos != chunk.end:
        raise AssertionError("merge region capture changed its fragment end")
    return ranks


def _join(parts: tuple[Ranks, ...]) -> Ranks:
    """Join owned rank fragments and detect cross-fragment duplicates."""
    ranks: Ranks = {}
    expected = 0
    for part in parts:
        expected += len(part)
        ranks.update(part)
    if len(ranks) != expected:
        raise UnsupportedConstructError(
            "merge region prototype: cross-fragment merge duplicate"
        )
    return ranks


def _expected(text: str) -> Ranks:
    """Read the exact source merges outside timing for semantic comparison."""
    root = _load(text)
    if not isinstance(root, dict):
        raise AssertionError("Qwen source root is not a mapping")
    model = root.get("model")
    if not isinstance(model, dict):
        raise AssertionError("Qwen source model is not a mapping")
    merges = model.get("merges")
    if not isinstance(merges, list):
        raise AssertionError("Qwen source merges is not a sequence")
    ranks: Ranks = {}
    for rank, value in enumerate(merges):
        if not isinstance(value, list) or len(value) != 2:
            raise AssertionError("Qwen source merge is not a dyad")
        left, right = value
        if not isinstance(left, str) or not isinstance(right, str):
            raise AssertionError("Qwen source merge member is not text")
        ranks[(left, right)] = rank
    return ranks


def _measure(
    text: str,
    program: RegionProgram,
    chunks: tuple[Chunk, ...],
    pool: ThreadPoolExecutor | None,
    capture: bool,
) -> tuple[Reading, Ranks | None]:
    """Measure fragment recognition or direct rank construction and join."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        if capture:
            if pool is None:
                parts = tuple(_capture_chunk(text, program, chunk) for chunk in chunks)
            else:
                parts = tuple(
                    pool.map(lambda chunk: _capture_chunk(text, program, chunk), chunks)
                )
            ranks: Ranks | None = _join(parts)
        else:
            if pool is None:
                ends = tuple(
                    _recognize_chunk(text, program.fragment, chunk)
                    for chunk in chunks
                )
            else:
                ends = tuple(
                    pool.map(
                        lambda chunk: _recognize_chunk(
                            text, program.fragment, chunk
                        ),
                        chunks,
                    )
                )
            if ends != tuple(chunk.end for chunk in chunks):
                raise AssertionError("merge region recognition changed an end")
            ranks = None
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), ranks


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated merge-region probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=5)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Prepare merge fragments and a pool, then print raw execution timings."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    marker = '"merges": ['
    start = text.index(marker) + len(marker) - 1
    program = _program()
    planning_started = time.perf_counter()
    entries = _entry_spans(text, start, program)
    chunks = _chunks(entries, options.workers)
    planning_wall = time.perf_counter() - planning_started
    expected = _expected(text)
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
            reading, ranks = _measure(
                text,
                program,
                chunks,
                pool,
                options.mode == "capture",
            )
            if ranks is not None and ranks != expected:
                raise AssertionError("merge region prototype changed ranks")
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
