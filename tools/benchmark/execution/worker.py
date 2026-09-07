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

from tools.benchmark.bench import (
    MT_ROWS,
    PRODUCT,
    EngineBuild,
    build_contract,
    observe,
    one_engine,
    result_identity,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.measurement.contract import (
    Json,
    Observation,
    digest,
)
from tools.benchmark.measurement.occupancy import Occupancy, declined_reason
from tools.benchmark.measurement.sampling import interleaved, noise_spread


def _bench(grammar: str) -> Bench:
    """Resolve the one grammar imported into this worker."""
    bench = next(
        (candidate for candidate in BENCHES if candidate.name == grammar), None
    )
    if bench is None:
        raise ValueError(f"unknown benchmark grammar {grammar!r}")
    return bench


def _engagement(engine: str, built: EngineBuild, cores: int | None) -> Occupancy | None:
    """What one untimed split attempt did, or ``None`` if the row is sequential.

    A sequential row is not asked at all, which is a different answer from
    "asked, and it declined". Everything here comes from that one attempt,
    outside every measured span — the request is not an observation, and a row
    that echoes it certifies nothing.
    """
    if engine not in MT_ROWS or cores is None or built.artifact is None:
        return None
    return declined_reason(built.artifact, built.document, cores)


def _split_fields(seen: Occupancy | None) -> tuple[bool | None, str, int]:
    """One attempt's ``(engaged, split digest, workers)`` for the observation."""
    if seen is None:
        return None, "", 1
    return seen.declined is None, seen.plan, seen.workers


def _payload(
    bench: Bench, engine: str, rounds: int, cores: int | None, full: bool
) -> dict[str, Json]:
    """Build, validate, warm, time and close one row; return its wire form."""
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        return {"refusal": built.refusal}
    try:
        workers = cores if cores and engine in MT_ROWS else 1
        contract = build_contract(
            bench, engine, built.document, workers, gc.isenabled()
        )
        engaged, split, effective = _split_fields(_engagement(engine, built, cores))
        result = result_identity(built)
        timing = observe(built, rounds)
        observation = Observation(
            timing.wall,
            timing.cpu,
            digest(result.text),
            digest(result.shape),
            "accepted",
            engaged,
            split,
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
) -> dict[str, Json]:
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
        samples = interleaved({engine: parse}, {engine: built.document}, rounds)
        engaged, _split, _cores = _split_fields(_engagement(engine, built, cores))
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
) -> dict[str, Json]:
    """Measure the same-engine control for one exact row."""
    built = one_engine(bench, engine, cores, full)
    if built.parse is None:
        raise ValueError(
            f"benchmark row {bench.name}/{engine} refused: {built.refusal}"
        )
    try:
        return {"noise_floor": noise_spread(built.parse, built.document, rounds)}
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
