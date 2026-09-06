"""Tests for the benchmark's row-contract and structure gate.

The checked-in absolute ratchet is gone by ruling — `assess`, `Confirmed`,
`save`, the five-percent threshold, `--accept-regression` and the execution
relations over two different documents were its whole subject, so the tests that
pinned them are gone with it. A hook cannot reserve a quiet machine, and the
serial A/B owns acceptance.

What this gate proves instead is that the rows are still the rows, in seconds
and without timing anything. A row whose identity drifted is exactly the failure
the timing gate cannot see from its own numbers.
"""

from __future__ import annotations

import time

import pytest

from tools.benchmark import regression
from tools.benchmark.bench import ENGINE, LEXIC_ROWS, MT_ROWS, PRODUCT
from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.measurement.contract import PROTOCOL, read_contract


def _bench(name: str = "json") -> Bench:
    """One real case, so the gate is tested against real IR."""
    return next(candidate for candidate in BENCHES if candidate.name == name)


def test_the_intact_fixture_set_reports_no_problems() -> None:
    """The shipped cases pass their own structure gate."""
    assert not regression.check()


def test_the_gate_exits_zero_on_an_intact_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The hook's success path names what it proved."""
    assert regression.main([]) == 0
    assert "contracts intact" in capsys.readouterr().out


def test_the_roster_is_twelve_grammars_and_seventy_two_rows() -> None:
    """The A/B's row count is this product, and a silent drop must fail."""
    assert len(BENCHES) == regression.EXPECTED_GRAMMARS == 12
    assert len(LEXIC_ROWS) == 6
    assert len(BENCHES) * len(LEXIC_ROWS) == 72


def test_a_missing_grammar_is_a_failure_not_a_smaller_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A case dropping out cannot quietly shrink the gate."""
    monkeypatch.setattr(regression, "BENCHES", BENCHES[:-1])
    problems = regression.check()

    assert any("expected 12 benchmark grammars" in problem for problem in problems)


def test_every_lexic_row_is_named_by_both_legend_tables() -> None:
    """A row nobody can describe is a number without a noun."""
    for row in LEXIC_ROWS:
        assert row in ENGINE
        assert row in PRODUCT


def test_the_gate_times_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-commit hook cannot reserve a quiet machine, so it must not try."""

    def forbidden() -> float:
        raise AssertionError("the structure gate must not read a clock")

    monkeypatch.setattr(time, "perf_counter", forbidden)
    monkeypatch.setattr(time, "process_time", forbidden)

    assert not regression.check()


def test_a_directive_naming_an_unknown_rule_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declaration must name rules the grammar actually has."""
    broken = _bench()._replace(lexical=("not-a-rule",))
    monkeypatch.setattr(regression, "BENCHES", (broken,))
    problems = regression.check()

    assert any("names unknown rules" in problem for problem in problems)


def test_an_unsorted_directive_declaration_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sorted declarations are what let two arms' contracts compare equal."""
    bench = _bench()
    monkeypatch.setattr(
        regression, "BENCHES", (bench._replace(lexical=tuple(reversed(bench.lexical))),)
    )
    problems = regression.check()

    assert any("is not sorted" in problem for problem in problems)


def test_the_declared_directives_are_the_grammar_s_own_rules() -> None:
    """Every shipped declaration validates against its own grammar."""
    for bench in BENCHES:
        names = {str(rule.name) for rule in bench.ast.rules}
        assert set(bench.lexical) <= names
        assert set(bench.non_semantic) <= names


def test_a_threaded_row_reads_the_full_document_and_a_sequential_one_the_corpus() -> (
    None
):
    """The relation rows must not compare two different documents."""
    bench = _bench()
    threaded = regression.row_contract(bench, "lexic-mt")
    sequential = regression.row_contract(bench, "lexic-pda")

    assert threaded.scale == "full"
    assert sequential.scale == "corpus"
    assert threaded.document_digest != sequential.document_digest
    assert threaded.document_bytes == len(bench.full.encode("utf-8"))


def test_both_threaded_rows_read_the_same_full_document() -> None:
    """An execution-mode relation needs one document, not two scales."""
    bench = _bench()
    digests = {
        regression.row_contract(bench, row).document_digest for row in sorted(MT_ROWS)
    }

    assert len(digests) == 1


def test_only_the_variant_rows_carry_directives() -> None:
    """A row's contract states the exact directives it compiled with."""
    bench = _bench()
    plain = regression.row_contract(bench, "lexic-pda")
    lexical = regression.row_contract(bench, "lexic-lex")
    both = regression.row_contract(bench, "lexic-lex-ns")

    assert plain.lexical == () and plain.non_semantic == ()
    assert lexical.lexical == tuple(sorted(bench.lexical))
    assert lexical.non_semantic == ()
    assert both.non_semantic == tuple(sorted(bench.non_semantic))


def test_acceptance_rows_record_the_collector_as_enabled() -> None:
    """Production does not disable the collector, so a timed row must not."""
    contract = regression.row_contract(_bench(), "lexic-pda")

    assert contract.gc_enabled is True


def test_a_collector_disabled_row_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate says so rather than letting the masked cost through."""
    bench = _bench()
    original = regression.row_contract

    def disabled(case: Bench, row: str):
        return original(case, row)._replace(gc_enabled=False)

    monkeypatch.setattr(regression, "BENCHES", (bench,))
    monkeypatch.setattr(regression, "row_contract", disabled)
    problems = regression.check()

    assert any("collector enabled" in problem for problem in problems)


def test_every_contract_round_trips_through_its_wire_form() -> None:
    """What a worker writes is what the comparator reads back."""
    for bench in BENCHES:
        for row in sorted(LEXIC_ROWS):
            contract = regression.row_contract(bench, row)
            assert read_contract(contract.wire()) == contract


def test_a_foreign_protocol_is_refused_rather_than_compared() -> None:
    """Two harness copies at different versions are not one instrument."""
    wire = regression.row_contract(_bench(), "lexic-pda").wire()
    wire["protocol"] = PROTOCOL + 1

    with pytest.raises(ValueError, match="protocol mismatch"):
        read_contract(wire)


def test_the_gate_reports_every_problem_it_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failing hook names the cases, not just a count."""
    monkeypatch.setattr(
        regression, "BENCHES", (_bench()._replace(lexical=("not-a-rule",)),)
    )

    assert regression.main([]) == 1
    assert "not-a-rule" in capsys.readouterr().out
