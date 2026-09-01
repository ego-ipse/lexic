"""Measure a grammar-derived repeated mapping region with direct captures."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from python_tree_cost import _load

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir import IrRule
from lexic.parsing.pda.core.scanner import (
    Pattern,
    Recognizer,
    build_recognizer,
    compile_source,
)


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int
    mode: str

    def validate(self) -> None:
        """Refuse a non-positive round count."""
        if self.mode not in ("recognize", "capture"):
            raise UnsupportedConstructError(
                f"schema region prototype: unknown mode {self.mode!r}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "schema region prototype: rounds must be positive"
            )


class RegionProgram(NamedTuple):
    """Compiled lower-grammar transitions for one repeated mapping schema."""

    begin: Pattern
    first: Pattern
    next: Pattern
    whole: Pattern


class Tables(NamedTuple):
    """The directly populated native vocabulary indexes."""

    encode: dict[str, int]
    decode: dict[int, str]


class Reading(NamedTuple):
    """One region execution reading."""

    process_seconds: float
    wall_seconds: float


def _rules() -> dict[str, IrRule]:
    """Index the real lower grammar for the shared recognizer compiler."""
    return {str(rule.name): rule for rule in JSON_GRAMMAR.rules}


def _recognizer() -> Recognizer:
    """Compile only the acyclic lower rules used by the upper region."""
    roots = frozenset(
        {
            "begin-object",
            "end-object",
            "string",
            "int",
            "name-separator",
            "value-separator",
        }
    )
    recognizer = build_recognizer(_rules(), roots)
    if recognizer is None:
        raise UnsupportedConstructError(
            "schema region prototype: lower closure is not recognizer-safe"
        )
    return recognizer


def _source(recognizer: Recognizer, name: str) -> str:
    """Return one grammar-derived rule pattern source."""
    return recognizer.pats[recognizer.index[name]].pattern


def _program() -> RegionProgram:
    """Compose the lower rules into mapping-entry state transitions."""
    recognizer = _recognizer()
    begin = _source(recognizer, "begin-object")
    end = _source(recognizer, "end-object")
    string = _source(recognizer, "string")
    integer = _source(recognizer, "int")
    name_sep = _source(recognizer, "name-separator")
    value_sep = _source(recognizer, "value-separator")
    entry = rf"(?P<key>{string}){name_sep}(?P<ordinal>{integer})"
    return RegionProgram(
        compile_source(begin),
        compile_source(rf"(?:(?P<end>{end})|{entry})"),
        compile_source(rf"(?:(?P<end>{end})|{value_sep}{entry})"),
        compile_source(
            rf"(?:{begin})(?:(?:{string})(?:{name_sep})(?:{integer})"
            rf"(?:(?:{value_sep})(?:{string})(?:{name_sep})(?:{integer}))*+)?+"
            rf"(?:{end})"
        ),
    )


def _decode_key(raw: str) -> str:
    """Apply the lower signature's decoded-string operation."""
    if "\\" not in raw:
        return raw[1:-1]
    decoded = json.loads(raw)
    if not isinstance(decoded, str):
        raise UnsupportedConstructError(
            "schema region prototype: string capture did not decode to text"
        )
    return decoded


def _insert(match_key: str, match_ordinal: str, tables: Tables) -> None:
    """Decode and insert one captured vocabulary entry."""
    key = _decode_key(match_key)
    ordinal = int(match_ordinal)
    if key in tables.encode or ordinal in tables.decode:
        raise UnsupportedConstructError(
            "schema region prototype: repeated vocabulary key or id"
        )
    tables.encode[key] = ordinal
    tables.decode[ordinal] = key


def _execute(text: str, start: int, program: RegionProgram) -> tuple[int, Tables]:
    """Recognize one specialized mapping region and populate its indexes."""
    opened = program.begin.match(text, start)
    if opened is None or opened.end() == start:
        raise UnsupportedConstructError(
            "schema region prototype: mapping opener did not match"
        )
    pos = opened.end()
    tables = Tables({}, {})
    transition = program.first
    while True:
        matched = transition.match(text, pos)
        if matched is None or matched.end() == pos:
            raise UnsupportedConstructError(
                f"schema region prototype: mapping transition failed at {pos}"
            )
        pos = matched.end()
        if matched.group("end") is not None:
            return pos, tables
        key = matched.group("key")
        ordinal = matched.group("ordinal")
        if key is None or ordinal is None:
            raise AssertionError("schema region transition lost its captures")
        _insert(key, ordinal, tables)
        transition = program.next


def _measure(
    text: str, start: int, program: RegionProgram
) -> tuple[Reading, int, Tables]:
    """Measure one region execution with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        end, tables = _execute(text, start, program)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    return Reading(process_elapsed, wall_elapsed), end, tables


def _measure_recognition(
    text: str, start: int, program: RegionProgram
) -> tuple[Reading, int]:
    """Measure one whole-region grammar match without captures/builders."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        matched = program.whole.match(text, start)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    if matched is None or matched.end() == start:
        raise UnsupportedConstructError(
            "schema region prototype: whole mapping did not match"
        )
    return Reading(process_elapsed, wall_elapsed), matched.end()


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse the isolated region probe."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def _expected_vocab(text: str) -> Tables:
    """Read the exact source section outside timing for semantic comparison."""
    root = _load(text)
    if not isinstance(root, dict):
        raise AssertionError("Qwen source root is not a mapping")
    model = root.get("model")
    if not isinstance(model, dict):
        raise AssertionError("Qwen source model is not a mapping")
    vocab = model.get("vocab")
    if not isinstance(vocab, dict):
        raise AssertionError("Qwen source vocabulary is not a mapping")
    encode: dict[str, int] = {}
    decode: dict[int, str] = {}
    for key, value in vocab.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise AssertionError("Qwen source vocabulary id is not an integer")
        encode[key] = value
        decode[value] = key
    return Tables(encode, decode)


def main(arguments: Sequence[str] | None = None) -> None:
    """Prepare the Qwen witness, then measure its grammar-derived vocab region."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    marker = '"vocab": {'
    start = text.index(marker) + len(marker) - 1
    program = _program()
    expected = _expected_vocab(text)

    readings: list[Reading] = []
    expected_end: int | None = None
    for number in range(1, options.rounds + 1):
        if options.mode == "recognize":
            reading, end = _measure_recognition(text, start, program)
            table_count = 0
        else:
            reading, end, tables = _measure(text, start, program)
            if tables != expected:
                raise AssertionError("schema region prototype changed the vocabulary")
            table_count = len(tables.encode)
        if expected_end is None:
            expected_end = end
        elif end != expected_end:
            raise AssertionError("schema region prototype changed its end position")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            table_count,
            end - start,
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
