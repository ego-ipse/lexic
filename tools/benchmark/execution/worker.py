"""Fresh-process execution of one exact benchmark grammar/engine pair.

This process owns the machine for its whole life: it starts, builds its row,
validates it, warms it, takes ONE observation, closes and exits. Nothing else
benchmark-shaped runs beside it. What it writes is a row CONTRACT — the exact
identity of what was measured — beside the numbers, so a comparator can refuse
two arms that did not measure the same thing instead of averaging them.
"""

from __future__ import annotations

import argparse
import gc
import json
from collections.abc import Sequence
from typing import Any

from tools.benchmark.bench import (
    MT_ROWS,
    PRODUCT,
    EngineBuild,
    _interleaved,
    _noise_floor,
    declined_reason,
    observe,
    one_engine,
    result_text,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    Observation,
    RowContract,
    digest,
)

_VARIANT_ROWS = frozenset({"lexic-lex", "lexic-lex-ns", "lexic-mt-lex-ns"})
"""Rows compiled with the case's declared `@lexical` set."""

_NS_ROWS = frozenset({"lexic-lex-ns", "lexic-mt-lex-ns"})
"""Rows that additionally carry the case's declared `@non-semantic` set."""


def _bench(grammar: str) -> Bench:
    """Resolve the one grammar imported into this worker."""
    bench = next(
        (candidate for candidate in BENCHES if candidate.name == grammar), None
    )
    if bench is None:
        raise ValueError(f"unknown benchmark grammar {grammar!r}")
    return bench


def _directives(bench: Bench, engine: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The EXACT directive sets this row compiles with, as declared."""
    lexical = bench.lexical if engine in _VARIANT_ROWS else ()
    non_semantic = bench.non_semantic if engine in _NS_ROWS else ()
    return tuple(sorted(lexical)), tuple(sorted(non_semantic))


def _contract(
    bench: Bench, engine: str, document: str, cores: int | None, full: bool
) -> RowContract:
    """Everything a comparator needs to accept or refuse this row."""
    lexical, non_semantic = _directives(bench, engine)
    scale = "full" if full or engine in MT_ROWS else "corpus"
    return RowContract(
        PROTOCOL,
        engine,
        bench.name,
        digest(bench.source),
        lexical,
        non_semantic,
        digest(document),
        len(document.encode("utf-8")),
        scale,
        PRODUCT[engine],
        1 if cores is None or engine not in MT_ROWS else cores,
        gc.isenabled(),
        CLOCKS,
    )


def _engagement(
    engine: str, built: EngineBuild, cores: int | None
) -> tuple[bool | None, int]:
    """Whether a threaded row actually split, and the workers it occupied.

    A sequential row is not asked: ``None`` says the question does not apply,
    which is different from "asked, and the answer was no".
    """
    if engine not in MT_ROWS or cores is None or built.artifact is None:
        return None, 1
    why = declined_reason(built.artifact, built.document, cores)
    return why is None, cores if why is None else 1


def _payload(
    bench: Bench, engine: str, rounds: int, cores: int | None, full: bool
) -> dict[str, Any]:
    """Build, validate, warm, time and close one row; return its wire form."""
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        return {"refusal": built.refusal}
    try:
        contract = _contract(bench, engine, built.document, cores, full)
        engaged, effective = _engagement(engine, built, cores)
        text = result_text(built)
        timing = observe(built, rounds)
        observation = Observation(
            timing.wall,
            timing.cpu,
            digest(text),
            "accepted",
            engaged,
            effective,
        )
        return {
            "contract": contract.wire(),
            "observations": [observation.wire()],
        }
    finally:
        getattr(built.parse, "close", lambda: None)()


def report_payload(
    bench: Bench, engine: str, rounds: int, cores: int | None, full: bool
) -> dict[str, Any]:
    """The cross-engine REPORT's payload for one row — reading, not a gate.

    The report wants many per-character samples and the warm-up account; the
    acceptance gate wants one process-level observation under a row contract.
    Two questions, two payloads, neither pretending to be the other.
    """
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        return {"refusal": built.refusal}
    parse = built.parse
    try:
        samples = _interleaved({engine: parse}, {engine: built.document}, rounds)
        engaged, _cores = _engagement(engine, built, cores)
        warmed = getattr(parse, "warmed", None)
        return {
            "samples": samples[engine],
            "mt_reason": None
            if engaged is not False
            else "the unified split seam found no eligible work",
            "warmed": list(warmed) if warmed is not None else None,
            "cold_us_per_char": getattr(parse, "cold_us_per_char", None),
            "charstream_share": getattr(parse, "charstream_share", lambda: 0.0)(),
        }
    finally:
        getattr(parse, "close", lambda: None)()


def _noise_payload(
    bench: Bench, engine: str, rounds: int, cores: int | None, full: bool
) -> dict[str, Any]:
    """Measure the same-engine control for one exact row."""
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        raise ValueError(
            f"benchmark row {bench.name}/{engine} refused: {built.refusal}"
        )
    try:
        return {"noise_floor": _noise_floor(built.parse, built.document, rounds)}
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
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.engine not in PRODUCT:
        parser.error(f"unknown benchmark row {args.engine!r}")
    bench = _bench(args.grammar)
    if args.noise:
        build = _noise_payload
    elif args.report:
        build = report_payload
    else:
        build = _payload
    payload = build(bench, args.engine, args.rounds, args.cores, args.full)
    print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
