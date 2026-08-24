"""Fresh-process execution of one exact benchmark grammar/engine pair."""

from __future__ import annotations

# These parameters are the independent command-line dimensions of one row.
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
from collections.abc import Sequence
from typing import Any

from tools.benchmark.bench import _interleaved, _mt_check, _noise_floor, _one_engine
from tools.benchmark.grammars import BENCHES


def execute(
    grammar: str,
    engine: str,
    rounds: int,
    cores: int | None,
    full: bool,
    noise: bool = False,
) -> dict[str, Any]:
    """Build, validate, and sample one row without constructing its neighbours."""
    bench = next(
        (candidate for candidate in BENCHES if candidate.name == grammar), None
    )
    if bench is None:
        raise ValueError(f"unknown benchmark grammar {grammar!r}")
    built = _one_engine(bench, engine, cores, full)
    if built.parse is None:
        return {"refusal": built.refusal}
    parse = built.parse
    try:
        if noise:
            return {"noise_floor": _noise_floor(parse, built.document, rounds)}
        samples = _interleaved({engine: parse}, {engine: built.document}, rounds)[
            engine
        ]
        mt_reason = None
        if built.artifact is not None:
            mt_reason = _mt_check({engine: built.artifact}, bench.full, cores).get(
                engine
            )
        warmed = getattr(parse, "warmed", None)
        cold = getattr(parse, "cold_us_per_char", None)
        share = getattr(parse, "charstream_share", lambda: 0.0)()
        return {
            "samples": samples,
            "document_length": len(built.document),
            "mt_reason": mt_reason,
            "warmed": list(warmed) if warmed is not None else None,
            "cold_us_per_char": cold,
            "charstream_share": share,
        }
    finally:
        getattr(parse, "close", lambda: None)()


def main(argv: Sequence[str] | None = None) -> None:
    """Write one machine-readable row result to standard output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grammar", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--rounds", type=int, required=True)
    parser.add_argument("--cores", type=int)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--noise", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            execute(
                args.grammar,
                args.engine,
                args.rounds,
                args.cores,
                args.full,
                args.noise,
            ),
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
