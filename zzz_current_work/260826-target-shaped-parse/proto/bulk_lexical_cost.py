"""Measure grammar-derived bulk lexical recognition across real grammars."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf.grammar import ABNF_GRAMMAR
from lexic.grammars.ebnf import EBNF_GRAMMAR
from lexic.grammars.gbnf.grammar import GBNF_GRAMMAR
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir import IrAst, IrRule
from lexic.parsing.pda.core.scanner import (
    Pattern,
    Recognizer,
    build_recognizer,
    compile_source,
)


class Options(argparse.Namespace):
    """Validated grammar witness and round count."""

    grammar: str
    rounds: int

    def validate(self) -> None:
        """Refuse unknown witnesses and non-positive round counts."""
        if self.grammar not in ("json", "gbnf", "abnf", "ebnf"):
            raise UnsupportedConstructError(
                f"bulk lexical prototype: unknown grammar {self.grammar!r}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "bulk lexical prototype: rounds must be positive"
            )


class Witness(NamedTuple):
    """One grammar, lexical roots, and document."""

    grammar: IrAst
    roots: tuple[str, ...]
    text: str


class Reading(NamedTuple):
    """One lexical recognition reading."""

    process_seconds: float
    wall_seconds: float
    tokens: int


def _rules(grammar: IrAst) -> dict[str, IrRule]:
    """Index one real grammar's rules for the shared recognizer compiler."""
    return {str(rule.name): rule for rule in grammar.rules}


def _json_witness() -> Witness:
    """Use the real Qwen document and its complete JSON lexical vocabulary."""
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    roots = (
        "begin-object",
        "end-object",
        "begin-array",
        "end-array",
        "name-separator",
        "value-separator",
        "string",
        "number",
        "true",
        "false",
        "null",
        "ws",
    )
    return Witness(JSON_GRAMMAR, roots, source.read_text(encoding="utf-8"))


def _repeated_witness(grammar: IrAst, roots: tuple[str, ...]) -> Witness:
    """Repeat real-grammar lexical forms to Qwen scale."""
    unit = "alpha-1234567890 "
    repeats = (11_422_654 + len(unit) - 1) // len(unit)
    return Witness(grammar, roots, unit * repeats)


def _witness(name: str) -> Witness:
    """Select one real grammar without changing the recognition mechanism."""
    if name == "json":
        return _json_witness()
    if name == "gbnf":
        return _repeated_witness(GBNF_GRAMMAR, ("rulename", "wschar"))
    if name == "abnf":
        return _repeated_witness(ABNF_GRAMMAR, ("rulename", "wsp"))
    if name == "ebnf":
        return _repeated_witness(EBNF_GRAMMAR, ("rulename", "ws"))
    raise UnsupportedConstructError(f"bulk lexical prototype: unknown grammar {name!r}")


def _recognizer(witness: Witness) -> Recognizer:
    """Compile the selected real grammar's acyclic lexical closures."""
    recognizer = build_recognizer(_rules(witness.grammar), frozenset(witness.roots))
    if recognizer is None:
        raise UnsupportedConstructError(
            "bulk lexical prototype: selected closure is not recognizer-safe"
        )
    return recognizer


def _pattern(recognizer: Recognizer, roots: tuple[str, ...]) -> Pattern:
    """Combine selected rule patterns in declared precedence order."""
    sources = tuple(recognizer.pats[recognizer.index[root]].pattern for root in roots)
    return compile_source("(?:" + "|".join(sources) + ")")


def _scan(text: str, pattern: Pattern) -> tuple[int, int]:
    """Consume the document as grammar-derived maximal lexical events."""
    pos = 0
    tokens = 0
    match = pattern.match
    while pos < len(text):
        found = match(text, pos)
        if found is None or found.end() == pos:
            raise UnsupportedConstructError(
                f"bulk lexical prototype: no lexical event at {pos}"
            )
        pos = found.end()
        tokens += 1
    return pos, tokens


def _measure(text: str, pattern: Pattern) -> Reading:
    """Measure one complete lexical scan with collection disabled."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        end, tokens = _scan(text, pattern)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    if end != len(text):
        raise AssertionError("bulk lexical prototype did not consume the document")
    return Reading(process_elapsed, wall_elapsed, tokens)


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated grammar witness."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--grammar", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Compile outside timing, then print raw scans for one grammar."""
    options = _parse_options(arguments)
    witness = _witness(options.grammar)
    recognizer = _recognizer(witness)
    pattern = _pattern(recognizer, witness.roots)
    readings: list[Reading] = []
    expected_tokens: int | None = None
    for number in range(1, options.rounds + 1):
        reading = _measure(witness.text, pattern)
        if expected_tokens is None:
            expected_tokens = reading.tokens
        elif reading.tokens != expected_tokens:
            raise AssertionError("bulk lexical prototype changed event count")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            reading.tokens,
            sep="\t",
        )
        gc.collect()
    print("document_chars", len(witness.text), sep="\t")
    print("document_bytes", len(witness.text.encode("utf-8")), sep="\t")
    print("pattern_chars", len(pattern.pattern), sep="\t")
    print(
        "median",
        f"{statistics.median(r.process_seconds for r in readings):.6f}",
        f"{statistics.median(r.wall_seconds for r in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
