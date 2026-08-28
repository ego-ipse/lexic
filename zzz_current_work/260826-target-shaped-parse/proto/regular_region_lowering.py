"""Prove, lower, and price a composed regular region as a capturing recognizer."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from schema_region_cost import Tables, _decode_key, _expected_vocab, _insert, _rules

from lexic.compile import canonical_grammar, compile_ast
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrMap, IrRule
from lexic.parsing.pda.core.scanner import (
    Pattern,
    Recognizer,
    build_recognizer,
    compile_source,
)

OP_MATCH, OP_CAP, OP_INSERT = 0, 1, 2
"""Interpreted completion opcodes: recognize one rule, capture its value
string, and run the entry's build — one dispatch per rule completion."""

ENTRY_LIMIT = 4_000
"""Entries kept in the bounded engine-differential slice."""


class Options(NamedTuple):
    """Validated probe mode and round count."""

    mode: str
    rounds: int


def _validate(options: Options) -> None:
    """Refuse unknown modes and non-positive rounds."""
    if options.mode not in ("identity", "capture", "ops"):
        raise UnsupportedConstructError(
            f"regular region prototype: unknown mode {options.mode!r}"
        )
    if options.rounds < 1:
        raise UnsupportedConstructError(
            "regular region prototype: rounds must be positive"
        )


class RegionSpec(NamedTuple):
    """Witness-locator data naming one repeated composed region's rules."""

    opener: str
    entry: tuple[str, ...]
    demanded: tuple[int, ...]
    separator: str
    terminator: str


VOCAB_SPEC = RegionSpec(
    "begin-object",
    ("string", "name-separator", "int"),
    (0, 2),
    "value-separator",
    "end-object",
)
"""The vocabulary region's shape under both JSON formulations."""

RECURSIVE_SPEC = VOCAB_SPEC._replace(entry=("string", "name-separator", "value"))
"""A region whose closure is recursive — the proof must decline it."""


class LoweredRegion(NamedTuple):
    """Capturing transitions derived from one proved-regular region."""

    opener: Pattern
    first: Pattern
    following: Pattern
    terminator: Pattern
    names: tuple[str, str]


class OpsProgram(NamedTuple):
    """Flat int-coded per-entry completion program over per-rule patterns."""

    kinds: tuple[int, ...]
    args: tuple[int, ...]
    patterns: tuple[Pattern, ...]
    opener: Pattern
    separator: Pattern
    terminator: Pattern


class Reading(NamedTuple):
    """One full-region execution reading."""

    process_seconds: float
    wall_seconds: float


def _repo_root() -> Path:
    """The repository root above this effort's prototype directory."""
    return Path(__file__).resolve().parents[3]


def _witness_text() -> str:
    """The resident Qwen3 witness source."""
    source = _repo_root() / "resources" / "tokenizers" / "qwen3.tokenizer.json"
    return source.read_text(encoding="utf-8")


def _region_start(text: str) -> int:
    """The vocab region's opening offset — a witness locator, not policy."""
    marker = '"vocab": {'
    return text.index(marker) + len(marker) - 1


def _gbnf_rules() -> dict[str, IrRule]:
    """Index the GBNF ground-truth JSON formulation's canonical rules."""
    source = _repo_root() / "resources" / "ground_truth" / "json.gbnf"
    ast = canonical_grammar(source.read_text(encoding="utf-8"), GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _prove(rules: dict[str, IrRule], spec: RegionSpec) -> Recognizer | None:
    """The compiler proof: the region's rule closure is acyclic and simple."""
    roots = frozenset((spec.opener, spec.separator, spec.terminator, *spec.entry))
    return build_recognizer(rules, roots)


def _proved(rules: dict[str, IrRule], spec: RegionSpec) -> Recognizer:
    """The proof, required to succeed for the witness region."""
    recognizer = _prove(rules, spec)
    if recognizer is None:
        raise UnsupportedConstructError(
            "regular region prototype: the witness region lost its proof"
        )
    return recognizer


def _rule_source(recognizer: Recognizer, name: str) -> str:
    """One grammar-derived rule pattern source."""
    return recognizer.pats[recognizer.index[name]].pattern


def _lower(recognizer: Recognizer, spec: RegionSpec) -> LoweredRegion:
    """Lower the proved region to capturing entry transitions, generically.

    Demanded items become positional named groups; nothing here reads a JSON
    or tokenizer name — the spec is caller data.
    """
    parts: list[str] = []
    names: list[str] = []
    for index, rule in enumerate(spec.entry):
        source = _rule_source(recognizer, rule)
        if index in spec.demanded:
            names.append(f"c{index}")
            parts.append(f"(?P<c{index}>{source})")
        else:
            parts.append(f"(?:{source})")
    if len(names) != 2:
        raise UnsupportedConstructError(
            "regular region prototype: the vocab morphism demands two captures"
        )
    entry = "".join(parts)
    separator = _rule_source(recognizer, spec.separator)
    return LoweredRegion(
        compile_source(_rule_source(recognizer, spec.opener)),
        compile_source(entry),
        compile_source(f"(?:{separator}){entry}"),
        compile_source(_rule_source(recognizer, spec.terminator)),
        (names[0], names[1]),
    )


def _lower_ops(recognizer: Recognizer, spec: RegionSpec) -> OpsProgram:
    """Lower the same region to one interpreted completion op per rule."""
    kinds: list[int] = []
    args: list[int] = []
    for index in range(len(spec.entry)):
        kinds.append(OP_CAP if index in spec.demanded else OP_MATCH)
        args.append(index)
    kinds.append(OP_INSERT)
    args.append(0)
    return OpsProgram(
        tuple(kinds),
        tuple(args),
        tuple(recognizer.pats[recognizer.index[name]] for name in spec.entry),
        recognizer.pats[recognizer.index[spec.opener]],
        recognizer.pats[recognizer.index[spec.separator]],
        recognizer.pats[recognizer.index[spec.terminator]],
    )


def _open_region(text: str, start: int, opener: Pattern) -> int:
    """Consume the region opener or refuse."""
    opened = opener.match(text, start)
    if opened is None:
        raise UnsupportedConstructError(
            "regular region prototype: region opener did not match"
        )
    return opened.end()


def _close_region(text: str, pos: int, terminator: Pattern) -> int:
    """Consume the region terminator or refuse."""
    closed = terminator.match(text, pos)
    if closed is None:
        raise UnsupportedConstructError(
            f"regular region prototype: no entry or close at {pos}"
        )
    return closed.end()


def _capture_region(text: str, start: int, region: LoweredRegion) -> tuple[int, Tables]:
    """Run the lowered region: one C-level match consumes one whole entry."""
    pos = _open_region(text, start, region.opener)
    tables = Tables({}, {})
    key_name, ordinal_name = region.names
    transition = region.first
    while True:
        matched = transition.match(text, pos)
        if matched is None:
            return _close_region(text, pos, region.terminator), tables
        key = matched.group(key_name)
        ordinal = matched.group(ordinal_name)
        if key is None or ordinal is None:
            raise AssertionError("regular region transition lost its captures")
        _insert(key, ordinal, tables)
        pos = matched.end()
        transition = region.following


def _capture_pairs(
    text: str, start: int, region: LoweredRegion, limit: int
) -> tuple[int, tuple[tuple[str, str], ...]]:
    """The first ``limit`` raw captured entries, and the offset they end at."""
    pos = _open_region(text, start, region.opener)
    pairs: list[tuple[str, str]] = []
    transition = region.first
    while len(pairs) < limit:
        matched = transition.match(text, pos)
        if matched is None:
            break
        key = matched.group(region.names[0])
        ordinal = matched.group(region.names[1])
        if key is None or ordinal is None:
            raise AssertionError("regular region transition lost its captures")
        pairs.append((key, ordinal))
        pos = matched.end()
        transition = region.following
    return pos, tuple(pairs)


def _entry_ops(
    text: str, pos: int, program: OpsProgram, slots: list[str], tables: Tables
) -> int:
    """Execute one entry's flat completion program — one dispatch per rule."""
    args = program.args
    patterns = program.patterns
    filled = 0
    for index, kind in enumerate(program.kinds):
        if kind == OP_INSERT:
            _insert(slots[0], slots[1], tables)
            continue
        matched = patterns[args[index]].match(text, pos)
        if matched is None:
            raise UnsupportedConstructError(
                f"regular region prototype: interpreted op failed at {pos}"
            )
        if kind == OP_CAP:
            slots[filled] = text[pos : matched.end()]
            filled += 1
        pos = matched.end()
    return pos


def _run_ops(text: str, start: int, program: OpsProgram) -> tuple[int, Tables]:
    """Interpret the flat completion program entry by entry over the region."""
    pos = _open_region(text, start, program.opener)
    tables = Tables({}, {})
    slots = ["", ""]
    pos = _entry_ops(text, pos, program, slots, tables)
    while True:
        separated = program.separator.match(text, pos)
        if separated is None:
            return _close_region(text, pos, program.terminator), tables
        pos = _entry_ops(text, separated.end(), program, slots, tables)


def _expected_pairs(pairs: tuple[tuple[str, str], ...]) -> dict[str, int]:
    """Decode raw captured pairs through the lower signature's operations."""
    decoded: dict[str, int] = {}
    for raw_key, raw_ordinal in pairs:
        decoded[_decode_key(raw_key)] = int(raw_ordinal)
    return decoded


def _reduced_table(piece: str) -> dict[str, int]:
    """The generic engine product for the same region slice."""
    reduced = compile_ast(JSON_GRAMMAR).reduce(piece, JSON_REDUCER, cores=1)
    if not isinstance(reduced, IrMap):
        raise AssertionError("the generic product is not a mapping")
    return {str(key): int(value) for key, value in reduced.items()}


def _identity(text: str) -> None:
    """Prove decline, formulation agreement, and generic-product identity."""
    if _prove(_rules(), RECURSIVE_SPEC) is not None:
        raise AssertionError("a recursive region claimed the regular proof")
    native = _lower(_proved(_rules(), VOCAB_SPEC), VOCAB_SPEC)
    foreign = _lower(_proved(_gbnf_rules(), VOCAB_SPEC), VOCAB_SPEC)
    start = _region_start(text)
    end, native_pairs = _capture_pairs(text, start, native, ENTRY_LIMIT)
    _, foreign_pairs = _capture_pairs(text, start, foreign, ENTRY_LIMIT)
    if native_pairs != foreign_pairs:
        raise AssertionError("formulations disagreed on captured entries")
    if len(native_pairs) != ENTRY_LIMIT:
        raise AssertionError("the differential slice lost entries")
    piece = text[start:end] + "}"
    expected = _expected_pairs(native_pairs)
    oracle = json.loads(piece)
    if oracle != expected:
        raise AssertionError("captured entries disagreed with the oracle")
    if _reduced_table(piece) != expected:
        raise AssertionError("captured entries disagreed with the engine product")
    print("entries", len(native_pairs), sep="\t")
    print("slice_chars", len(piece), sep="\t")
    print("identity", "capture == gbnf capture == json == engine reduce", sep="\t")


def _measure_capture(
    text: str, start: int, region: LoweredRegion
) -> tuple[Reading, Tables]:
    """Time one full-region capturing run with the collector left enabled."""
    process_started = time.process_time()
    wall_started = time.perf_counter()
    _end, tables = _capture_region(text, start, region)
    return (
        Reading(
            time.process_time() - process_started,
            time.perf_counter() - wall_started,
        ),
        tables,
    )


def _measure_ops(text: str, start: int, program: OpsProgram) -> tuple[Reading, Tables]:
    """Time one full-region interpreted run with the collector left enabled."""
    process_started = time.process_time()
    wall_started = time.perf_counter()
    _end, tables = _run_ops(text, start, program)
    return (
        Reading(
            time.process_time() - process_started,
            time.perf_counter() - wall_started,
        ),
        tables,
    )


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated probe invocation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--rounds", type=int, default=7)
    space = parser.parse_args(arguments)
    options = Options(str(space.mode), int(space.rounds))
    _validate(options)
    return options


def _report(readings: list[Reading], entries: int) -> None:
    """Print the median row and the per-entry rate."""
    wall = statistics.median(reading.wall_seconds for reading in readings)
    process = statistics.median(reading.process_seconds for reading in readings)
    print("median", f"{process:.6f}", f"{wall:.6f}", sep="\t")
    print("entries_per_second", f"{entries / wall:.0f}", sep="\t")


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the identity proof or one sequential full-region cost mode."""
    options = _parse_options(arguments)
    text = _witness_text()
    if options.mode == "identity":
        _identity(text)
        return
    start = _region_start(text)
    recognizer = _proved(_rules(), VOCAB_SPEC)
    region = _lower(recognizer, VOCAB_SPEC)
    program = _lower_ops(recognizer, VOCAB_SPEC)
    expected = _expected_vocab(text)
    readings: list[Reading] = []
    for number in range(1, options.rounds + 1):
        if options.mode == "capture":
            reading, tables = _measure_capture(text, start, region)
        else:
            reading, tables = _measure_ops(text, start, program)
        if tables != expected:
            raise AssertionError("regular region prototype changed the vocabulary")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            sep="\t",
        )
    _report(readings, len(expected.encode))


if __name__ == "__main__":
    main()
