"""Measure the current Qwen grammar parse without fold or token construction."""

from __future__ import annotations

import argparse
import gc
import hashlib
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.compile import artifact, compile_ast, reset_cache_for_tests
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.parsing.parallel import AUTO, reset_pools


class Options(argparse.Namespace):
    """Validated Qwen parse options."""

    cores: str
    rounds: int

    def validate(self) -> None:
        """Refuse unsupported worker choices and non-positive rounds."""
        if self.cores not in ("1", "auto"):
            raise UnsupportedConstructError(
                f"Qwen parse prototype: unsupported cores {self.cores!r}"
            )
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "Qwen parse prototype: rounds must be positive"
            )

    def worker_count(self) -> int:
        """Return the public worker selection value."""
        return 1 if self.cores == "1" else AUTO


class Reading(NamedTuple):
    """Process and wall seconds for one phase."""

    process_seconds: float
    wall_seconds: float


def _elapsed(process_started: float, wall_started: float) -> Reading:
    """Return elapsed process and wall seconds."""
    return Reading(
        time.process_time() - process_started,
        time.perf_counter() - wall_started,
    )


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated Qwen worker mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cores", required=True)
    parser.add_argument("--rounds", type=int, default=1)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Compile once, then measure only current reduction-variant parsing."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    reset_pools()
    reset_cache_for_tests()

    process_started = time.process_time()
    wall_started = time.perf_counter()
    compiled = compile_ast(JSON_GRAMMAR, cache_key="qwen-parse-baseline")
    compile_reading = _elapsed(process_started, wall_started)

    process_started = time.process_time()
    wall_started = time.perf_counter()
    entry = artifact._reduce_entry(compiled, JSON_REDUCER)
    reduction_setup = _elapsed(process_started, wall_started)

    print("document_chars", len(text), sep="\t")
    print("document_bytes", source.stat().st_size, sep="\t")
    print(
        "grammar_setup",
        f"{compile_reading.process_seconds:.6f}",
        f"{compile_reading.wall_seconds:.6f}",
        sep="\t",
    )
    print(
        "reduction_setup",
        f"{reduction_setup.process_seconds:.6f}",
        f"{reduction_setup.wall_seconds:.6f}",
        sep="\t",
    )

    expected: str | None = None
    for number in range(1, options.rounds + 1):
        process_started = time.process_time()
        wall_started = time.perf_counter()
        model = entry.variant.parse(text, cores=options.worker_count())
        reading = _elapsed(process_started, wall_started)
        observed = hashlib.blake2b(model.to_text().encode("utf-8")).hexdigest()
        if expected is None:
            expected = observed
        elif observed != expected:
            raise AssertionError("Qwen parse prototype changed its model")
        print(
            "parse",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            sep="\t",
        )
        del model
        gc.collect()
    print("model_digest", expected, sep="\t")
    reset_pools()


if __name__ == "__main__":
    main()
