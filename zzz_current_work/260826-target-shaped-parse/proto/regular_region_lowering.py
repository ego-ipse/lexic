"""Prove, lower, and price a composed regular region as a capturing recognizer."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from regular_region_proof import prove_region
from schema_region_cost import Tables, _decode_key, _expected_vocab, _insert, _rules

from lexic.compile import canonical_grammar, compile_ast
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrFlavour, IrMap, IrRule
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
    if options.mode not in ("identity", "capture", "ops", "compare"):
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


class RegionSignature(NamedTuple):
    """Reducer-authored semantic roles over one repeated lower region."""

    opener: str
    entry: tuple[str, ...]
    fields: tuple[tuple[str, int], ...]
    separator: str
    terminator: str


class RegionDemand(NamedTuple):
    """Target roles demanded from each repeated entry."""

    fields: tuple[str, ...]


def _derive_region(signature: RegionSignature, demand: RegionDemand) -> RegionSpec:
    """Compose semantic roles into one lower-grammar region program."""
    positions = dict(signature.fields)
    if len(positions) != len(signature.fields):
        raise UnsupportedConstructError(
            "regular region prototype: duplicate signature field role"
        )
    try:
        demanded = tuple(positions[field] for field in demand.fields)
    except KeyError as missing:
        raise UnsupportedConstructError(
            f"regular region prototype: unknown demand role {missing.args[0]!r}"
        ) from None
    return RegionSpec(
        signature.opener,
        signature.entry,
        demanded,
        signature.separator,
        signature.terminator,
    )


JSON_REGION = RegionSignature(
    "begin-object",
    ("string", "name-separator", "int"),
    (("key", 0), ("ordinal", 2)),
    "value-separator",
    "end-object",
)
VOCAB_SPEC = _derive_region(JSON_REGION, RegionDemand(("key", "ordinal")))
"""The vocabulary demand composed through JSON's semantic signature."""

RECURSIVE_SPEC = VOCAB_SPEC._replace(entry=("string", "name-separator", "value"))
"""A region whose closure is recursive — the proof must decline it."""

AMBIGUOUS_GRAMMAR = (
    'root ::= open lead tail close\nopen ::= "{"\nlead ::= "a"*\n'
    'tail ::= "a"\nseparator ::= ","\nclose ::= "}"\n'
)
AMBIGUOUS_SPEC = RegionSpec(
    "open",
    ("lead", "tail"),
    (0,),
    "separator",
    "close",
)
"""A simple acyclic closure whose possessive entry boundary is not exact."""

NULLABLE_REFERENCE_GRAMMAR = (
    'root ::= open maybe tail close\nopen ::= "{"\nmaybe ::= "x" |\n'
    'tail ::= "x"\nseparator ::= ","\nclose ::= "}"\n'
)
NULLABLE_REFERENCE_SPEC = RegionSpec(
    "open",
    ("maybe", "tail"),
    (0,),
    "separator",
    "close",
)
"""A once-required nullable atom which can steal its continuation."""

EARLY_NULLABLE_ARM_GRAMMAR = (
    'root ::= open choice close\nopen ::= "{"\nchoice ::= "a"? | "b"\n'
    'separator ::= ","\nclose ::= "}"\n'
)
EARLY_NULLABLE_ARM_SPEC = RegionSpec(
    "open",
    ("choice",),
    (0,),
    "separator",
    "close",
)
"""An ordered atomic alternation whose nullable arm is not last."""

CATALOG_GRAMMAR = (
    'catalog ::= open ( row ( separator row )* )? close\nopen ::= "["\n'
    'row ::= word assign count\nseparator ::= ";"\nclose ::= "]"\n'
    'word ::= [a-z]+\nassign ::= "="\ncount ::= [0-9]+\n'
)
CATALOG_REGION = RegionSignature(
    "open",
    ("word", "assign", "count"),
    (("label", 0), ("quantity", 2)),
    "separator",
    "close",
)
"""A non-JSON signature with different rules and surface delimiters."""


class LoweredRegion(NamedTuple):
    """Capturing transitions derived from one proved-regular region."""

    opener: Pattern
    first: Pattern
    following: Pattern
    terminator: Pattern
    names: tuple[str, ...]


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


def _formulation_rules(suffix: str, flavour: IrFlavour) -> dict[str, IrRule]:
    """Index one ground-truth JSON formulation's canonical rules."""
    source = _repo_root() / "resources" / "ground_truth" / f"json.{suffix}"
    ast = canonical_grammar(source.read_text(encoding="utf-8"), flavour)
    return {str(rule.name): rule for rule in ast.rules}


def _source_rules(source: str) -> dict[str, IrRule]:
    """Index one embedded GBNF witness's canonical rules."""
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _prove(rules: dict[str, IrRule], spec: RegionSpec) -> Recognizer | None:
    """Prove simple closure plus exact atomic/possessive boundaries."""
    roots = frozenset((spec.opener, spec.separator, spec.terminator, *spec.entry))
    recognizer = build_recognizer(rules, roots)
    if recognizer is None:
        return None
    if not prove_region(
        rules,
        spec.opener,
        spec.entry,
        spec.separator,
        spec.terminator,
    ):
        return None
    return recognizer


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
    entry = "".join(parts)
    separator = _rule_source(recognizer, spec.separator)
    return LoweredRegion(
        compile_source(_rule_source(recognizer, spec.opener)),
        compile_source(entry),
        compile_source(f"(?:{separator}){entry}"),
        compile_source(_rule_source(recognizer, spec.terminator)),
        tuple(names),
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
    if len(region.names) != 2:
        raise UnsupportedConstructError(
            "regular region prototype: vocab construction requires two captures"
        )
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


def _capture_rows(
    text: str, start: int, region: LoweredRegion, limit: int
) -> tuple[int, tuple[tuple[str, ...], ...]]:
    """The first ``limit`` raw capture rows, and the offset they end at."""
    pos = _open_region(text, start, region.opener)
    rows: list[tuple[str, ...]] = []
    transition = region.first
    while len(rows) < limit:
        matched = transition.match(text, pos)
        if matched is None:
            break
        row = tuple(matched.group(name) for name in region.names)
        if any(value is None for value in row):
            raise AssertionError("regular region transition lost its captures")
        rows.append(tuple(value for value in row if value is not None))
        pos = matched.end()
        transition = region.following
    return pos, tuple(rows)


def _entry_ops(
    text: str, pos: int, program: OpsProgram, slots: list[str], tables: Tables
) -> int | None:
    """Execute one entry, returning ``None`` only when its first rule misses."""
    args = program.args
    patterns = program.patterns
    filled = 0
    for index, kind in enumerate(program.kinds):
        if kind == OP_INSERT:
            _insert(slots[0], slots[1], tables)
            continue
        matched = patterns[args[index]].match(text, pos)
        if matched is None:
            if index == 0:
                return None
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
    first = _entry_ops(text, pos, program, slots, tables)
    if first is None:
        return _close_region(text, pos, program.terminator), tables
    pos = first
    while True:
        separated = program.separator.match(text, pos)
        if separated is None:
            return _close_region(text, pos, program.terminator), tables
        following = _entry_ops(text, separated.end(), program, slots, tables)
        if following is None:
            raise UnsupportedConstructError(
                f"regular region prototype: separator has no entry at {separated.end()}"
            )
        pos = following


def _expected_pairs(pairs: tuple[tuple[str, str], ...]) -> dict[str, int]:
    """Decode raw captured pairs through the lower signature's operations."""
    decoded: dict[str, int] = {}
    for raw_key, raw_ordinal in pairs:
        decoded[_decode_key(raw_key)] = int(raw_ordinal)
    return decoded


def _pairs(rows: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, str], ...]:
    """Narrow two-capture rows for the vocabulary consumer."""
    pairs: list[tuple[str, str]] = []
    for row in rows:
        if len(row) != 2:
            raise UnsupportedConstructError(
                "regular region prototype: vocabulary row is not a pair"
            )
        pairs.append((row[0], row[1]))
    return tuple(pairs)


def _reduced_table(piece: str) -> dict[str, int]:
    """The generic engine product for the same region slice."""
    reduced = compile_ast(JSON_GRAMMAR).reduce(piece, JSON_REDUCER, cores=1)
    if not isinstance(reduced, IrMap):
        raise AssertionError("the generic product is not a mapping")
    return {str(key): int(value) for key, value in reduced.items()}


def _identity(text: str) -> None:
    """Prove decline, arity, formulations, valid/invalid, and engine identity."""
    if _prove(_rules(), RECURSIVE_SPEC) is not None:
        raise AssertionError("a recursive region claimed the regular proof")
    ambiguous_rules = _source_rules(AMBIGUOUS_GRAMMAR)
    ambiguous_roots = frozenset(
        (
            AMBIGUOUS_SPEC.opener,
            AMBIGUOUS_SPEC.separator,
            AMBIGUOUS_SPEC.terminator,
            *AMBIGUOUS_SPEC.entry,
        )
    )
    if build_recognizer(ambiguous_rules, ambiguous_roots) is None:
        raise AssertionError("the acyclic ambiguity witness lost its simple closure")
    if _prove(ambiguous_rules, AMBIGUOUS_SPEC) is not None:
        raise AssertionError("an ambiguous possessive boundary claimed the proof")
    nullable_reference = _source_rules(NULLABLE_REFERENCE_GRAMMAR)
    if _prove(nullable_reference, NULLABLE_REFERENCE_SPEC) is not None:
        raise AssertionError("a nullable atom stole its continuation")
    early_nullable_arm = _source_rules(EARLY_NULLABLE_ARM_GRAMMAR)
    if _prove(early_nullable_arm, EARLY_NULLABLE_ARM_SPEC) is not None:
        raise AssertionError("an early nullable arm claimed ordered exactness")
    native = _lower(_proved(_rules(), VOCAB_SPEC), VOCAB_SPEC)
    formulations = (
        (
            "gbnf",
            _lower(
                _proved(_formulation_rules("gbnf", GBNF_FLAVOUR), VOCAB_SPEC),
                VOCAB_SPEC,
            ),
        ),
        (
            "abnf",
            _lower(
                _proved(_formulation_rules("abnf", ABNF_FLAVOUR), VOCAB_SPEC),
                VOCAB_SPEC,
            ),
        ),
        (
            "ebnf",
            _lower(
                _proved(_formulation_rules("ebnf", EBNF_FLAVOUR), VOCAB_SPEC),
                VOCAB_SPEC,
            ),
        ),
    )
    start = _region_start(text)
    end, native_rows = _capture_rows(text, start, native, ENTRY_LIMIT)
    for name, formulation in formulations:
        _, rows = _capture_rows(text, start, formulation, ENTRY_LIMIT)
        if native_rows != rows:
            raise AssertionError(f"{name} disagreed on captured entries")
    native_pairs = _pairs(native_rows)
    if len(native_pairs) != ENTRY_LIMIT:
        raise AssertionError("the differential slice lost entries")
    piece = text[start:end] + "}"
    expected = _expected_pairs(native_pairs)
    oracle = json.loads(piece)
    if oracle != expected:
        raise AssertionError("captured entries disagreed with the oracle")
    if _reduced_table(piece) != expected:
        raise AssertionError("captured entries disagreed with the engine product")
    one_capture = _lower(
        _proved(_rules(), VOCAB_SPEC._replace(demanded=(0,))),
        VOCAB_SPEC._replace(demanded=(0,)),
    )
    _, keys = _capture_rows(text, start, one_capture, ENTRY_LIMIT)
    if tuple(row[0] for row in native_rows) != tuple(row[0] for row in keys):
        raise AssertionError("one-capture lowering changed its demanded field")
    all_capture = _lower(
        _proved(_rules(), VOCAB_SPEC._replace(demanded=(0, 1, 2))),
        VOCAB_SPEC._replace(demanded=(0, 1, 2)),
    )
    _, triples = _capture_rows(text, start, all_capture, ENTRY_LIMIT)
    if any(len(row) != 3 for row in triples):
        raise AssertionError("three-capture lowering lost a demanded field")
    full_end, full_tables = _capture_region(text, start, native)
    if full_tables != _expected_vocab(text) or text[full_end] != ",":
        raise AssertionError("full-region capture changed the vocabulary or boundary")
    empty_end, empty_tables = _capture_region("{}", 0, native)
    if empty_end != 2 or empty_tables != Tables({}, {}):
        raise AssertionError("empty regular region is not valid")
    for malformed in ('{"a":}', '{"a":1,}', '{"a" 1}'):
        try:
            _capture_region(malformed, 0, native)
        except UnsupportedConstructError:
            continue
        raise AssertionError(f"regular lowering accepted malformed {malformed!r}")
    catalog_text = "[alpha=1;beta=22]"
    catalog_spec = _derive_region(
        CATALOG_REGION,
        RegionDemand(("label", "quantity")),
    )
    catalog = _lower(
        _proved(_source_rules(CATALOG_GRAMMAR), catalog_spec), catalog_spec
    )
    catalog_end, catalog_rows = _capture_rows(catalog_text, 0, catalog, 10)
    if catalog_rows != (("alpha", "1"), ("beta", "22")):
        raise AssertionError("derived non-JSON region changed its captures")
    if _close_region(catalog_text, catalog_end, catalog.terminator) != len(
        catalog_text
    ):
        raise AssertionError("derived non-JSON region changed its boundary")
    print("entries", len(native_pairs), sep="\t")
    print("slice_chars", len(piece), sep="\t")
    print(
        "identity",
        "native == gbnf == abnf == ebnf == json == engine reduce",
        sep="\t",
    )
    print(
        "edges",
        "1/2/3 captures; empty valid; malformed refused; three unsafe shapes declined",
        sep="\t",
    )
    print("derived", "JSON vocab + non-JSON catalog", sep="\t")


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


def _minimum(readings: list[Reading]) -> Reading:
    """The minimum CPU and wall readings, each over its own clock."""
    return Reading(
        min(reading.process_seconds for reading in readings),
        min(reading.wall_seconds for reading in readings),
    )


def _compare(
    text: str,
    start: int,
    region: LoweredRegion,
    program: OpsProgram,
    expected: Tables,
    rounds: int,
) -> None:
    """Alternate both implementations and an unreachable two-arm control."""
    capture: list[Reading] = []
    ops: list[Reading] = []
    control_left: list[Reading] = []
    control_right: list[Reading] = []
    for number in range(1, rounds + 1):
        compared = ("capture", "ops") if number % 2 else ("ops", "capture")
        controlled = (
            ("control-left", "control-right")
            if number % 2
            else ("control-right", "control-left")
        )
        for label in (*compared, *controlled):
            if label == "ops":
                reading, tables = _measure_ops(text, start, program)
                ops.append(reading)
            else:
                reading, tables = _measure_capture(text, start, region)
                if label == "capture":
                    capture.append(reading)
                elif label == "control-left":
                    control_left.append(reading)
                else:
                    control_right.append(reading)
            if tables != expected:
                raise AssertionError(
                    f"regular region prototype: {label} changed the vocabulary"
                )
            print(
                "round",
                number,
                label,
                f"{reading.process_seconds:.6f}",
                f"{reading.wall_seconds:.6f}",
                sep="\t",
            )
    rows = (
        ("capture", _minimum(capture)),
        ("ops", _minimum(ops)),
        ("control-left", _minimum(control_left)),
        ("control-right", _minimum(control_right)),
    )
    for label, reading in rows:
        print(
            "minimum",
            label,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            sep="\t",
        )
    capture_row = rows[0][1]
    ops_row = rows[1][1]
    left = rows[2][1]
    right = rows[3][1]
    print(
        "process_ratio_ops_over_capture",
        f"{ops_row.process_seconds / capture_row.process_seconds:.6f}",
        sep="\t",
    )
    print(
        "control_process_floor",
        f"{abs(left.process_seconds - right.process_seconds):.6f}",
        sep="\t",
    )


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
    if options.mode == "compare":
        _compare(text, start, region, program, expected, options.rounds)
        return
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
