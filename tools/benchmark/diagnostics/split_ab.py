"""Focused two-tree benchmark and profiler for repetition split regressions.

The measured noun is one complete parse invocation. Compilation, warm-up and
process startup are outside the timed region. A/B samples run in distinct
processes and alternate tree order because the change under test is structural;
see ``docs/STYLE.md`` section 7.
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import json
import os
import pstats
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple, TypedDict

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import _model_product, earley_model

REFUSALS = (LexicError, PdaFail, RecursionError)
"""What a parse under test may legitimately raise — a refusal is a result."""


class Measured(TypedDict):
    """A row that ran: its batch size and CPU nanoseconds per invocation."""

    outcome: str
    count: int
    ns: float


class Failed(TypedDict):
    """A row whose call raised — the gated baseline refusing, typically."""

    outcome: str
    error: str


Reading = Measured | Failed
"""One row's result over JSON. ``outcome`` is always present and records what
the call did, exception included; ``"error" in reading`` tells the two apart."""


class Row(NamedTuple):
    """One focused measurement: engine route plus reproducer."""

    engine: str
    case: str

    @property
    def name(self) -> str:
        """Stable display and JSON key."""
        return f"{self.engine}:{self.case}"


ROWS = (
    Row("pda", "nested-plus"),
    Row("pda", "vyx"),
    Row("earley-resolved", "nested-plus"),
    Row("earley-resolved", "vyx"),
    Row("pda", "control"),
)

NESTED_PLUS = "root ::= item+\nitem ::= [a-z]+\n"
NESTED_TEXT = "ab"
VYX_TEXT = "!H \\#\\n\\# >"
CONTROL = 'root ::= "abcdefghijklmnop"\n'
CONTROL_TEXT = "abcdefghijklmnop"


def _case(name: str):
    """Compile one case and return its product, fold and text."""
    if name == "nested-plus":
        compiled = compile_text(NESTED_PLUS, cache_key="split-ab-nested")
        text = NESTED_TEXT
    elif name == "vyx":
        root = Path(__file__).resolve().parents[2]
        compiled = compile_from_path(root / "resources/ground_truth/vyx.gbnf")
        text = VYX_TEXT
    elif name == "control":
        compiled = compile_text(CONTROL, cache_key="split-ab-control")
        text = CONTROL_TEXT
    else:  # pragma: no cover - argparse/constant-owned call sites
        raise ValueError(name)
    return compiled, _model_product(compiled.codegen_grammar, compiled.fold), text


def _call(row: Row) -> Callable[[], object]:
    """Build the production-adjacent callable for one row."""
    compiled, product, text = _case(row.case)
    if row.engine == "pda":
        return lambda: pda_model(product.pda, text, compiled.fold)
    if row.engine == "earley-gated":
        return lambda: earley_model(
            product.instance_grammar, text, compiled.fold, product.tables
        )
    if row.engine == "earley-resolved":
        return lambda: earley_model(
            product.instance_grammar,
            text,
            compiled.fold,
            product.tables,
            lambda first, _other: first,
        )
    raise ValueError(row.engine)


def _outcome(call: Callable[[], object]) -> str:
    """One invocation's value or exception, for semantic context."""
    try:
        return repr(call())
    except REFUSALS as exc:  # the gated baseline is expected to refuse
        return f"{type(exc).__name__}: {exc}"


def _batch(call: Callable[[], object], count: int) -> float:
    """CPU nanoseconds per complete successful parse invocation."""
    gc.collect()
    gc.disable()
    start = time.process_time_ns()
    try:
        for _ in range(count):
            call()
    finally:
        elapsed = time.process_time_ns() - start
        gc.enable()
    return elapsed / count


def _calibrate(call: Callable[[], object], target: float) -> int:
    """Choose a batch large enough that timer granularity is immaterial."""
    count = 1
    while count < 1_000_000:
        start = time.process_time()
        for _ in range(count):
            call()
        elapsed = time.process_time() - start
        if elapsed >= target:
            return count
        count = max(count + 1, int(count * target / max(elapsed, 1e-9) * 1.1))
    return count


def _worker(target: float) -> None:
    """Measure every row in this source process and emit one JSON sample."""
    result: dict[str, Reading] = {}
    for row in ROWS:
        call = _call(row)
        outcome = _outcome(call)
        try:
            call()
        except REFUSALS as exc:
            result[row.name] = {
                "error": f"{type(exc).__name__}: {exc}",
                "outcome": outcome,
            }
            continue
        for _ in range(8):
            call()
        count = _calibrate(call, target)
        result[row.name] = {
            "count": count,
            "ns": _batch(call, count),
            "outcome": outcome,
        }
    print(json.dumps(result, sort_keys=True))


def _run_tree(tree: Path, target: float) -> dict[str, Reading]:
    """Run one worker with imports rooted in ``tree``."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = os.pathsep.join((str(tree / "src"), str(tree)))
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--target-seconds",
        str(target),
    ]
    completed = subprocess.run(
        command,
        cwd=tree,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def _ab(trees: tuple[Path, Path], rounds: int, target: float) -> None:
    """Alternate two source trees in separate processes and report medians."""
    samples: list[dict[str, list[float]]] = [
        {row.name: [] for row in ROWS},
        {row.name: [] for row in ROWS},
    ]
    outcomes: list[dict[str, str]] = [{}, {}]
    errors: list[dict[str, str]] = [{}, {}]
    for round_index in range(rounds):
        order = (0, 1) if round_index % 2 == 0 else (1, 0)
        for index in order:
            got = _run_tree(trees[index], target)
            for row in ROWS:
                reading = got[row.name]
                outcomes[index][row.name] = reading["outcome"]
                if "error" in reading:
                    errors[index][row.name] = reading["error"]
                else:
                    samples[index][row.name].append(reading["ns"])
    _report_ab(trees, rounds, samples, outcomes, errors)


def _report_ab(
    trees: tuple[Path, Path],
    rounds: int,
    samples: list[dict[str, list[float]]],
    outcomes: list[dict[str, str]],
    errors: list[dict[str, str]],
) -> None:
    """Print one A/B block: medians, per-row delta, then each row's outcome."""
    print(
        f"noun=parse invocation  clock=process_time  rounds={rounds}  "
        "order=alternating processes"
    )
    print(f"A={trees[0]}")
    print(f"B={trees[1]}")
    print(f"{'row':31} {'A ns/parse':>14} {'B ns/parse':>14} {'B vs A':>10}")
    for row in ROWS:
        name = row.name
        if name in errors[0] or name in errors[1]:
            print(
                f"{name:31} A={errors[0].get(name, 'ok')}  "
                f"B={errors[1].get(name, 'ok')}"
            )
            continue
        one = statistics.median(samples[0][name])
        two = statistics.median(samples[1][name])
        print(f"{name:31} {one:14.1f} {two:14.1f} {(two - one) / one * 100:+9.2f}%")
    print("outcomes:")
    for row in ROWS:
        print(f"  {row.name}: A={outcomes[0][row.name]} | B={outcomes[1][row.name]}")


def _profile(row: Row, invocations: int, output: Path | None) -> None:
    """Profile complete invocations; exceptions remain completed outcomes."""
    call = _call(row)
    outcome = _outcome(call)

    def drive() -> None:
        for _ in range(invocations):
            try:
                call()
            except REFUSALS:
                pass

    profiler = cProfile.Profile()
    profiler.enable()
    drive()
    profiler.disable()
    if output is not None:
        profiler.dump_stats(output)
    print(
        f"noun=parse invocation  row={row.name}  invocations={invocations}  "
        f"outcome={outcome}"
    )
    pstats.Stats(profiler, stream=sys.stdout).strip_dirs().sort_stats(
        "cumulative"
    ).print_stats(35)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the focused A/B, worker, or profiler mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ab", nargs=2, type=Path, metavar=("TREE_A", "TREE_B"))
    parser.add_argument("--rounds", type=int, default=7)
    parser.add_argument("--target-seconds", type=float, default=0.12)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--engine", choices=("pda", "earley-gated", "earley-resolved"))
    parser.add_argument("--case", choices=("nested-plus", "vyx", "control"))
    parser.add_argument("--invocations", type=int, default=1_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.worker:
        _worker(args.target_seconds)
    elif args.profile:
        if args.engine is None or args.case is None:
            parser.error("--profile requires --engine and --case")
        _profile(Row(args.engine, args.case), args.invocations, args.output)
    elif args.ab:
        _ab(
            (args.ab[0].resolve(), args.ab[1].resolve()),
            args.rounds,
            args.target_seconds,
        )
    else:
        parser.error("choose --ab or --profile")


if __name__ == "__main__":
    main()
