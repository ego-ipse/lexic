"""Fresh-process execution of one exact benchmark grammar/engine pair."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from tools.benchmark.bench import (
    EngineBuild,
    _interleaved,
    _mt_check,
    _noise_floor,
    one_engine,
)
from tools.benchmark.cases.grammars import BENCHES


def _bench(grammar: str) -> Any:
    """Resolve the one grammar imported into this worker."""
    bench = next(
        (candidate for candidate in BENCHES if candidate.name == grammar), None
    )
    if bench is None:
        raise ValueError(f"unknown benchmark grammar {grammar!r}")
    return bench


def _result(
    name: str, built: EngineBuild, bench: Any, rounds: int, cores: int | None
) -> dict[str, Any]:
    """Sample one already-built row alone and return its wire payload."""
    if built.parse is None:
        return {"refusal": built.refusal}
    parse = built.parse
    samples = _interleaved({name: parse}, {name: built.document}, rounds)[name]
    mt_reason = None
    if built.artifact is not None:
        mt_reason = _mt_check({name: built.artifact}, bench.full, cores).get(name)
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


def _build(
    grammar: str, engine: str, cores: int | None, full: bool
) -> tuple[Any, EngineBuild]:
    """Construct and validate one exact requested row."""
    bench = _bench(grammar)
    return bench, one_engine(bench, engine, cores, full)


def _close(built: EngineBuild) -> None:
    """Close a row parser when its engine owns external resources."""
    if built.parse is not None:
        getattr(built.parse, "close", lambda: None)()


def execute(
    grammar: str,
    engine: str,
    rounds: int,
    cores: int | None,
    full: bool,
) -> dict[str, Any]:
    """Build and sample one exact row in its own process."""
    bench, built = _build(grammar, engine, cores, full)
    try:
        return _result(engine, built, bench, rounds, cores)
    finally:
        _close(built)


def execute_noise(
    grammar: str, engine: str, rounds: int, cores: int | None, full: bool
) -> float:
    """Measure the same-engine control for one exact row."""
    bench = _bench(grammar)
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        raise ValueError(f"benchmark row {grammar}/{engine} refused: {built.refusal}")
    try:
        return _noise_floor(built.parse, built.document, rounds)
    finally:
        getattr(built.parse, "close", lambda: None)()


def main(argv: Sequence[str] | None = None) -> None:
    """Write one machine-readable row result to standard output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grammar", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--rounds", type=int, required=True)
    parser.add_argument("--cores", type=int)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--noise", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args(argv)
    if args.noise:
        if args.wait:
            parser.error("--noise and --wait are mutually exclusive")
        payload: dict[str, Any] = {
            "noise_floor": execute_noise(
                args.grammar, args.engine, args.rounds, args.cores, args.full
            )
        }
    else:
        bench, built = _build(args.grammar, args.engine, args.cores, args.full)
        try:
            if args.wait:
                print('{"ready":true}', flush=True)
                if sys.stdin.readline().strip() != "run":
                    raise ValueError("waiting benchmark worker expected 'run'")
            payload = _result(args.engine, built, bench, args.rounds, args.cores)
        finally:
            _close(built)
    print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
