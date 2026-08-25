"""Command-line orchestration for the cross-parser benchmark report."""

from __future__ import annotations

import argparse
import datetime
import json
import random
from collections.abc import Sequence
from pathlib import Path

from lexic.parsing.parallel import AUTO, available_workers
from tools.benchmark.bench import (
    DEFAULT_ROUNDS,
    LEXIC_ROWS,
    MT_ROWS,
    SUMMARY,
    _candidates,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.execution.isolation import (
    IsolatedRow,
    Job,
    RowRequest,
    noise_floor,
    run_jobs,
    run_row,
)
from tools.benchmark.presentation.reporting import (
    Block,
    _legend,
    _mark,
    _medians,
    _report,
    _use_color,
    _warmup_values,
)

ENGINE_META = {
    "lexic-mt": {"label": "lexic-mt", "runtime": "python"},
    "lexic-mt-lex-ns": {"label": "lexic-mt-lex-ns", "runtime": "python"},
    "lexic-lex": {"label": "lexic-lex", "runtime": "python"},
    "lexic-lex-ns": {"label": "lexic-lex-ns", "runtime": "python"},
    "lexic-pda": {"label": "lexic-pda", "runtime": "python"},
    "lexic-earley": {"label": "lexic-earley", "runtime": "python"},
    "lark-lalr": {"label": "lark (LALR)", "runtime": "python"},
    "lark-lalr-lex": {"label": "lark (LALR, marked)", "runtime": "python"},
    "lark-earley": {"label": "lark (Earley)", "runtime": "python"},
    "lark-earley-lex": {"label": "lark (Earley, marked)", "runtime": "python"},
    "parsimonious": {"label": "parsimonious", "runtime": "python"},
    "parsimonious-lex": {"label": "parsimonious (marked)", "runtime": "python"},
    "pyparsing": {"label": "pyparsing", "runtime": "python"},
    "antlr-py": {"label": "ANTLR (Python)", "runtime": "python"},
    "antlr-py-lex": {"label": "ANTLR (Python, marked)", "runtime": "python"},
    "antlr": {"label": "ANTLR (Java)", "runtime": "java"},
    "antlr-lex": {"label": "ANTLR (Java, marked)", "runtime": "java"},
    "stdlib-json": {"label": "json.loads (stdlib)", "runtime": "python"},
    "msgspec": {"label": "msgspec", "runtime": "python"},
}
"""Display metadata per row, in the artifact's column order."""


def _dump_json(path: Path, rounds: int, cores: int | None, blocks: list[Block]) -> None:
    """Write EVERY measured or refused row as the cross-engine artifact.

    Nothing is dropped: a row the metadata table does not know gets a default
    label rather than silence, so a new seat cannot vanish from the record.
    """
    values: dict[str, dict[str, float | str]] = {}
    rows: list[str] = []
    for block in blocks:
        medians = _medians(block.samples)
        cells: dict[str, float | str] = {
            name: round(median, 6) for name, median in medians.items()
        }
        cells |= dict.fromkeys(block.refused, "refuses")
        known = [name for name in ENGINE_META if name in cells]
        ordered = known + sorted(set(cells) - set(known))
        values[block.bench.name] = {name: cells[name] for name in ordered}
        rows += [name for name in ordered if name not in rows]
    payload = {
        "schema": 1,
        "unit": "microseconds_per_character",
        "measured": datetime.date.today().isoformat(),
        "rounds": rounds,
        "cores": cores,
        "noise_floor_percent": [
            round(min(b.floor for b in blocks), 2),
            round(max(b.floor for b in blocks), 2),
        ],
        "note": "Cross-engine medians of isolated rounds. Refreshed "
        "deliberately by rerunning the full bench with --json; README "
        "rendering reads this file and never triggers a run.",
        "engines": {
            name: ENGINE_META.get(name, {"label": name, "runtime": "python"})
            for name in rows
        },
        "values": values,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _mt_cores(asked: int | None) -> int | None:
    """The lexic-mt thread count — the rows are ON by default when they can be.

    Reads ``cores`` the way lexic does (:mod:`lexic.parsing.parallel.policy`):
    ``--cores N`` is N; bare ``--cores`` and no flag alike are auto. Auto is
    1 on a GIL build, and that is where the rows drop out entirely — a
    "threaded" row running one thread answers a question nobody asked, and
    real threading there measured a net loss.
    """
    workers = available_workers() if asked in (None, AUTO) else asked
    return workers if workers > 1 else None


def _row_names(bench: Bench, cores: int | None) -> list[str]:
    """The isolated worker roster for one grammar."""
    lexic = ["lexic-pda", "lexic-earley", "lexic-lex", "lexic-lex-ns"]
    if cores is not None:
        lexic.extend(("lexic-mt", "lexic-mt-lex-ns"))
    return lexic + [name for name, _make in _candidates(bench)]


def _isolated_bench(
    bench: Bench, cores: int | None, full: bool, rounds: int
) -> tuple[Block, dict[str, IsolatedRow]]:
    """Prepare exact Lexic workers together; time every row in isolation."""
    names = _row_names(bench, cores)
    lexic = [name for name in names if name in LEXIC_ROWS]
    jobs = [
        Job(name, RowRequest(bench.name, name, rounds, cores, full)) for name in lexic
    ]
    results = run_jobs(jobs)
    competitors = [name for name in names if name not in lexic]
    random.Random(f"lexic-bench:{bench.name}").shuffle(competitors)
    results.update(
        {
            name: run_row(RowRequest(bench.name, name, rounds, cores, full))
            for name in competitors
        }
    )
    samples = {
        name: result.samples for name, result in results.items() if result.samples
    }
    refused = {
        name: result.refusal or "refused without a reason"
        for name, result in results.items()
        if result.refusal is not None
    }
    documents = {
        name: bench.full if full or name in MT_ROWS else bench.corpus
        for name in samples
    }
    mt_notes = {
        name: result.mt_reason
        for name, result in results.items()
        if result.mt_reason is not None
    }
    anchor = next((name for name in names if name in samples), None)
    floor = (
        noise_floor(RowRequest(bench.name, anchor, rounds, cores, full))
        if anchor
        else 0.0
    )
    return Block(bench, samples, refused, floor, documents, mt_notes), results


def main(argv: Sequence[str] | None = None) -> None:
    """Time every engine on every benchmark grammar."""
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"timed rounds per engine (default {DEFAULT_ROUNDS}; 1 is a quick pass)",
    )
    parser.add_argument(
        "--cores",
        type=int,
        nargs="?",
        const=0,
        default=None,
        metavar="N",
        help="lexic-mt worker count: the corpus parsed as ONE document "
        "split across N workers (bare --cores = auto, the cpu count; "
        "free-threaded interpreter only — the GIL build measured a net loss)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="time every row on the full corpus (default: only the lexic-mt "
        "rows read it — the slow engines pay seconds per pass there)",
    )
    parser.add_argument(
        "--only", nargs="*", metavar="NAME", help="benchmark only these grammars"
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="force ANSI colour (auto: only on a terminal, honouring NO_COLOR)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="also write the measured medians as the cross-engine artifact "
        "(the file tools/render_readme.py renders the README from)",
    )
    args = parser.parse_args(argv)
    if args.cores and available_workers() == 1:
        raise SystemExit(
            "--cores needs a free-threaded interpreter (python3.14t): "
            "threaded parsing under the GIL measured 0.82-0.92x, a net loss"
        )
    cores = _mt_cores(args.cores)
    color = _use_color(args.color)
    wanted = set(args.only or ())
    benches = [b for b in BENCHES if not wanted or b.name in wanted]
    if not benches:
        raise SystemExit(f"no such grammar: {sorted(wanted)}")
    print(
        f"rounds={args.rounds}{_mark(cores)}  grammars={', '.join(b.name for b in benches)}"
    )
    _legend(color)
    blocks: list[Block] = []
    for bench in benches:
        block, results = _isolated_bench(bench, cores, args.full, args.rounds)
        blocks.append(block)
        _report(block, color)
        for name in _row_names(bench, cores):
            result = results[name]
            if result.warmed is not None:
                _warmup_values(
                    name,
                    result.warmed,
                    result.cold_us_per_char,
                    result.charstream_share,
                )
    if args.json:
        _dump_json(args.json, args.rounds, cores, blocks)


if __name__ == "__main__":
    main()
