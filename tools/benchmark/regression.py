"""The row-contract and benchmark-structure gate.

This is what a pre-commit hook can honestly enforce. A hook cannot reserve a
quiet machine or establish comparable hardware, so it must not run an absolute
timing ratchet against a checked-in table: that table has no machine or protocol
identity, and a number measured on one laptop is not a target for another.

What a hook CAN prove, in seconds and without timing anything, is that the rows
are still the rows: every case declares directives its grammar accepts, every
row name is known to both the legend and the product table, every contract is
well formed, and the scale rule holds. A row whose identity drifted is the
failure the timing gate cannot see from its own numbers.

Performance acceptance belongs to the explicit serial A/B
(:mod:`tools.benchmark.compare`) on a qualified free-threaded runner.

    uv run python -m tools.benchmark.regression
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from tools.benchmark.bench import (
    ENGINE,
    LEXIC_ROWS,
    MT_ROWS,
    PRODUCT,
    build_contract,
    directive_digest,
)
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.measurement.contract import (
    PROTOCOL,
    RowContract,
    digest,
    read_contract,
)

ARTIFACT = Path(__file__).resolve().parent / "competitors_baseline.json"
"""The committed cross-engine numbers — what the README publishes from."""

EXPECTED_GRAMMARS = 12
"""How many languages the fixture set defines.

Pinned so a case silently dropping out is a failure rather than a smaller
benchmark. The A/B compares 72 rows; that number is this times the row count.
"""


def row_contract(bench: Bench, row: str) -> RowContract:
    """The contract this row would be measured under, without measuring it.

    The same constructor a worker writes its own contract with, so the gate
    cannot pass a shape the measurement never produces.
    """
    document = bench.full if row in MT_ROWS else bench.corpus
    return build_contract(bench, row, document, 1, True)


def _check_roster(problems: list[str]) -> None:
    """Every case present, and every lexic row named by the legend tables."""
    if len(BENCHES) != EXPECTED_GRAMMARS:
        problems.append(
            f"expected {EXPECTED_GRAMMARS} benchmark grammars, found {len(BENCHES)}: "
            f"{sorted(bench.name for bench in BENCHES)}"
        )
    for row in sorted(LEXIC_ROWS):
        if row not in ENGINE:
            problems.append(f"row {row!r} has no entry in the engine legend")
        if row not in PRODUCT:
            problems.append(f"row {row!r} has no entry in the product table")


def _check_directives(bench: Bench, problems: list[str]) -> None:
    """Declared directive names are real rules of this case's grammar.

    Validation is a LANGUAGE question, so both revisions answer it the same way.
    The construction of `BENCHES` already refuses an undeclarable set; this
    re-states it as a gate so the hook fails with the case named.
    """
    names = {str(rule.name) for rule in bench.ast.rules}
    for kind, declared in (
        ("@lexical", bench.lexical),
        ("@non-semantic", bench.non_semantic),
    ):
        unknown = sorted(set(declared) - names)
        if unknown:
            problems.append(f"{bench.name}: {kind} names unknown rules {unknown}")
        if list(declared) != sorted(declared):
            problems.append(f"{bench.name}: {kind} declaration is not sorted")


def _check_contracts(bench: Bench, problems: list[str]) -> None:
    """Every row's contract is well formed, round-trips, and obeys the scale rule."""
    for row in sorted(LEXIC_ROWS):
        contract = row_contract(bench, row)
        label = f"{bench.name}/{row}"
        if contract.document_bytes <= 0:
            problems.append(f"{label}: empty document")
        expected_scale = "full" if row in MT_ROWS else "corpus"
        if contract.scale != expected_scale:
            problems.append(
                f"{label}: scale is {contract.scale!r}, expected {expected_scale!r} "
                f"— an mt row and its sequential reference must not be compared "
                f"across two different documents"
            )
        if not contract.gc_enabled:
            problems.append(f"{label}: acceptance rows require the collector enabled")
        try:
            restored = read_contract(contract.wire())
        except ValueError as exc:
            problems.append(f"{label}: contract does not round-trip: {exc}")
            continue
        if restored != contract:
            problems.append(f"{label}: contract changed across its wire form")


def _check_artifact(problems: list[str]) -> None:
    """Every published cell names the grammar, document and directives held here.

    The cheapest thing this gate can prove about the committed numbers, and the
    one a hook must: a fixture edited without a re-measure leaves every stale
    cell in the file reading as a measurement of the current language, and no
    date, round count or character length distinguishes it. The digests do.

    The DIRECTIVE digest is separate, and per seat, because the declarations
    live in `cases/directives.py` and not in the grammar source: editing them
    changes what every marked cell measured while the grammar and document
    digests stay put. Per seat rather than per row, because the marked and
    unmarked seats of one grammar are built with different sets on purpose, so
    one value for the row could not express either.
    """
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    by_name = {bench.name: bench for bench in BENCHES}
    for grammar, cells in artifact["provenance"].items():
        bench = by_name.get(grammar)
        if bench is None:
            problems.append(
                f"{grammar}: the artifact publishes a bench this tree does not define"
            )
            continue
        for seat, record in cells.items():
            _check_cell(bench, seat, record, problems)


def _check_cell(
    bench: Bench, seat: str, record: dict[str, object], problems: list[str]
) -> None:
    """One published cell's three identities against what this tree holds."""
    document = bench.full if record["scale"] == "full" else bench.corpus
    for field, held in (
        ("grammar_digest", digest(bench.source)),
        ("document_digest", digest(document)),
        ("directive_digest", directive_digest(bench, seat)),
    ):
        if record[field] != held:
            problems.append(
                f"{bench.name}/{seat}: measured against {field} {record[field]}, "
                f"this tree holds {held} — the cell is a number for something else"
            )


def check() -> list[str]:
    """Every structural problem with the benchmark's rows, in report order."""
    problems: list[str] = []
    _check_roster(problems)
    for bench in BENCHES:
        _check_directives(bench, problems)
        _check_contracts(bench, problems)
    _check_artifact(problems)
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Report every structural problem, or say the rows are intact."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    problems = check()
    rows = len(BENCHES) * len(LEXIC_ROWS)
    if problems:
        print(f"benchmark structure: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"benchmark structure: {len(BENCHES)} grammars, {rows} rows, "
        f"protocol {PROTOCOL} — contracts intact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
