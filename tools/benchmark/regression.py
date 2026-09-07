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
from collections.abc import Sequence
from math import isfinite
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
from tools.benchmark.presentation.cli import (
    REFUSES,
    UNMEASURED,
    Artifact,
    Cell,
    Provenance,
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
    if not ARTIFACT.exists():
        problems.append(f"{ARTIFACT.name}: the published artifact is not here")
        return
    artifact = Artifact.load(ARTIFACT)
    by_name = {bench.name: bench for bench in BENCHES}
    for grammar, cells in artifact.provenance.items():
        bench = by_name.get(grammar)
        if bench is None:
            problems.append(
                f"{grammar}: the artifact publishes a bench this tree does not define"
            )
            continue
        for seat, record in cells.items():
            _check_cell(bench, seat, record, problems)
    _check_published(artifact, problems)


def _check_cell(
    bench: Bench, seat: str, record: Provenance, problems: list[str]
) -> None:
    """One published cell's three identities against what this tree holds."""
    document = bench.full if record.scale == "full" else bench.corpus
    for field, measured, held in (
        ("grammar_digest", record.grammar_digest, digest(bench.source)),
        ("document_digest", record.document_digest, digest(document)),
        ("directive_digest", record.directive_digest, directive_digest(bench, seat)),
    ):
        if measured != held:
            problems.append(
                f"{bench.name}/{seat}: measured against {field} {measured}, "
                f"this tree holds {held} — the cell is a number for something else"
            )


def _check_published(artifact: Artifact, problems: list[str]) -> None:
    """Every published cell is a number or a declared word, and says which.

    The schema's own contract, read over the WHOLE file rather than over the
    cells one run happened to write: a value is a finite number or one of the
    two declared words, a cell holding no number carries the reason in `note`,
    and a cell holding one carries none. Refusals published that word with
    `note: null`, so the file said a seat could not take a language and would
    not say why — and every per-cell check passed, because none of them read a
    value beside its record.
    """
    for grammar, cells in artifact.values.items():
        records = artifact.provenance.get(grammar, {})
        for seat, cell in cells.items():
            record = records.get(seat)
            if record is None:
                problems.append(
                    f"{grammar}/{seat}: published with no record of what measured it"
                )
                continue
            fault = _cell_fault(cell, record.note)
            if fault is not None:
                problems.append(f"{grammar}/{seat}: {fault}")


def _cell_fault(cell: Cell, note: str | None) -> str | None:
    """Why one published cell breaks that contract, or ``None`` when it holds."""
    if isinstance(cell, str):
        if cell not in (REFUSES, UNMEASURED):
            return f"value {cell!r} is neither a number nor {REFUSES}/{UNMEASURED}"
        if not (note or "").strip():
            return f"holds {cell} and no reason — the schema puts one in `note`"
        return None
    if not _finite(cell):
        return f"value {cell!r} is not a finite number"
    if note is not None:
        return f"holds a number and the reason {note!r}, which says why it holds none"
    return None


def _finite(cell: Cell) -> bool:
    """Whether a nonstring cell is a real finite measurement — a bool is not."""
    if isinstance(cell, bool) or not isinstance(cell, float | int):
        return False
    return isfinite(cell)


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
