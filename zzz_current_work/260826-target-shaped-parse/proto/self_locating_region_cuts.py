"""Measure schema-derived self-locating cuts without an all-mark sidecar."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir import IrLiteral, IrRule
from lexic.parsing.parallel.discovery.regions import pair_rules
from lexic.parsing.pda.core.scanner import (
    Pattern,
    Recognizer,
    build_recognizer,
    compile_source,
    literal_source,
)


class Options(argparse.Namespace):
    """Validated schema section, cut count, and rounds."""

    section: str
    workers: int
    rounds: int

    def validate(self) -> None:
        """Refuse unknown sections, worker counts, and non-positive rounds."""
        if self.section not in ("vocab", "merges"):
            raise UnsupportedConstructError(
                f"self-locating cuts prototype: unknown section {self.section!r}"
            )
        if self.workers not in (1, 2, 4, 8, 16):
            raise UnsupportedConstructError(
                f"self-locating cuts prototype: unsupported workers {self.workers}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "self-locating cuts prototype: rounds must be positive"
            )


class CutProgram(NamedTuple):
    """One region's opener, safe tail, boundary anchor, and fragment language."""

    begin: Pattern
    tail: Pattern
    boundary: Pattern
    fragment: Pattern


class Reading(NamedTuple):
    """One O(workers) cut-plan reading."""

    process_seconds: float
    wall_seconds: float


type Span = tuple[int, int]


def _rules() -> dict[str, IrRule]:
    """Index the real lower grammar for recognizer compilation."""
    return {str(rule.name): rule for rule in JSON_GRAMMAR.rules}


def _recognizer() -> Recognizer:
    """Compile every acyclic lower rule used by either schema section."""
    roots = frozenset(
        {
            "begin-object",
            "end-object",
            "begin-array",
            "end-array",
            "string",
            "int",
            "name-separator",
            "value-separator",
        }
    )
    recognizer = build_recognizer(_rules(), roots)
    if recognizer is None:
        raise UnsupportedConstructError(
            "self-locating cuts prototype: lower closure is not recognizer-safe"
        )
    return recognizer


def _source(recognizer: Recognizer, name: str) -> str:
    """Return one grammar-derived rule pattern source."""
    return recognizer.pats[recognizer.index[name]].pattern


def _opening(name: str) -> str:
    """Return one container rule's grammar-declared opening literal."""
    rule = _rules()[name]
    literals = tuple(
        str(item.atom)
        for arm in rule.body
        for item in arm
        if isinstance(item.atom, IrLiteral)
    )
    if len(literals) != 1:
        raise UnsupportedConstructError(
            f"self-locating cuts prototype: {name} has no unique literal"
        )
    return literals[0]


def _program(section: str) -> CutProgram:
    """Compose lower rules with one upper regular-region schema."""
    recognizer = _recognizer()
    string = _source(recognizer, "string")
    separator = _source(recognizer, "value-separator")
    name_sep = _source(recognizer, "name-separator")
    integer = _source(recognizer, "int")
    whitespace = _source(recognizer, "ws")
    if section == "vocab":
        container = "begin-object"
        begin = _source(recognizer, "begin-object")
        end = _source(recognizer, "end-object")
        entry = rf"(?:{string})(?:{name_sep})(?:{integer})"
    else:
        container = "begin-array"
        begin = _source(recognizer, "begin-array")
        end = _source(recognizer, "end-array")
        entry = rf"(?:{begin})(?:{string})(?:{separator})(?:{string})(?:{end})"
    opening = _opening(container)
    closing = pair_rules(JSON_GRAMMAR)[opening][0]
    following_key = rf"(?:{separator})(?:{string})(?:{name_sep})"
    parent_end = _source(recognizer, "end-object")
    after_region = rf"(?:(?:{following_key})|(?:{parent_end}))"
    return CutProgram(
        compile_source(begin),
        compile_source(
            rf"(?:{entry})(?P<tail>(?:{whitespace})"
            rf"(?:{literal_source(closing)})(?:{whitespace}))(?={after_region})"
        ),
        compile_source(rf"(?:{separator})(?P<entry>{entry})"),
        compile_source(rf"{entry}(?:(?:{separator}){entry})*+"),
    )


def _trim_ws(text: str, start: int, end: int) -> int:
    """Trim the lower grammar's four JSON whitespace characters backward."""
    while end > start and text[end - 1] in " \t\r\n":
        end -= 1
    return end


def _cuts(text: str, start: int, workers: int, program: CutProgram) -> tuple[Span, ...]:
    """Find one tail and O(workers) self-locating entry boundaries."""
    opened = program.begin.match(text, start)
    if opened is None:
        raise UnsupportedConstructError(
            "self-locating cuts prototype: region opener did not match"
        )
    first = opened.end()
    tail = program.tail.search(text, first)
    if tail is None:
        raise UnsupportedConstructError(
            "self-locating cuts prototype: safe region tail was not found"
        )
    last = _trim_ws(text, first, tail.start("tail"))
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


def _validate(text: str, spans: tuple[Span, ...], program: CutProgram) -> None:
    """Require every proposed span to be an exact fragment-language member."""
    for start, end in spans:
        if program.fragment.fullmatch(text, start, end) is None:
            raise AssertionError(
                f"self-locating cut {start}:{end} is not a valid fragment"
            )


def _measure(
    text: str, start: int, workers: int, program: CutProgram
) -> tuple[Reading, tuple[Span, ...]]:
    """Measure opener/tail/boundary searches without fragment execution."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        spans = _cuts(text, start, workers, program)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), spans


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated self-locating-cut probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=7)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Measure one Qwen schema section's O(workers) cut plan."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    marker = f'"{options.section}": ' + ("{" if options.section == "vocab" else "[")
    start = text.index(marker) + len(marker) - 1
    program = _program(options.section)
    readings: list[Reading] = []
    expected: tuple[Span, ...] | None = None
    for number in range(1, options.rounds + 1):
        reading, spans = _measure(text, start, options.workers, program)
        _validate(text, spans, program)
        if expected is None:
            expected = spans
        elif spans != expected:
            raise AssertionError("self-locating cuts changed their spans")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            len(spans),
            sep="\t",
        )
        gc.collect()
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
