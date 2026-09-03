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

from tools.benchmark.bench import ENGINE, LEXIC_ROWS, MT_ROWS, PRODUCT
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    RowContract,
    digest,
    read_contract,
)

EXPECTED_GRAMMARS = 12
"""How many languages the fixture set defines.

Pinned so a case silently dropping out is a failure rather than a smaller
benchmark. The A/B compares 72 rows; that number is this times the row count.
"""


def row_contract(bench: Bench, row: str) -> RowContract:
    """The contract this row would be measured under, without measuring it."""
    variant = row in {"lexic-lex", "lexic-lex-ns", "lexic-mt-lex-ns"}
    with_noise = row in {"lexic-lex-ns", "lexic-mt-lex-ns"}
    document = bench.full if row in MT_ROWS else bench.corpus
    return RowContract(
        PROTOCOL,
        row,
        bench.name,
        digest(bench.source),
        tuple(sorted(bench.lexical)) if variant else (),
        tuple(sorted(bench.non_semantic)) if with_noise else (),
        digest(document),
        len(document.encode("utf-8")),
        "full" if row in MT_ROWS else "corpus",
        PRODUCT[row],
        1,
        True,
        CLOCKS,
    )


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


def check() -> list[str]:
    """Every structural problem with the benchmark's rows, in report order."""
    problems: list[str] = []
    _check_roster(problems)
    for bench in BENCHES:
        _check_directives(bench, problems)
        _check_contracts(bench, problems)
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
