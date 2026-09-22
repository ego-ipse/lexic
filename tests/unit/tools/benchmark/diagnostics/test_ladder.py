"""Tests for tools.benchmark.diagnostics.ladder — which CPUs, which grammars."""

from __future__ import annotations

from lexic.parsing.parallel import roles
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.diagnostics.ladder import (
    grammars,
    physical_cores,
    read_document,
    rung_for,
    write_document,
)

EIGHT_BY_TWO = {cpu: (cpu % 8, cpu % 8 + 8) for cpu in range(16)}
"""Eight cores, two SMT threads each, siblings ``i`` and ``i + 8`` — the
numbering Linux gives a Ryzen, where a naive ``range(n)`` of CPUs past eight
lands on siblings."""


def test_one_logical_cpu_is_taken_per_physical_core():
    """The lowest sibling of each pair, and only one per pair."""
    assert physical_cores(EIGHT_BY_TWO) == list(range(8))


def test_a_rung_within_the_cores_is_pinned_to_distinct_ones():
    """Eight workers get eight different cores, none sharing execution units."""
    rung = rung_for(8, EIGHT_BY_TWO)
    assert rung.distinct
    assert len({EIGHT_BY_TWO[cpu] for cpu in rung.cpus}) == 8


def test_a_rung_wider_than_the_cores_is_marked_as_paired():
    """Sixteen workers cannot have sixteen cores here; the rung says so."""
    rung = rung_for(16, EIGHT_BY_TWO)
    assert not rung.distinct
    assert rung.cpus == tuple(range(16))


def test_the_grammars_are_derived_not_listed():
    """Exactly the benches with derived bracket pairs, plus the second json."""
    labels = [label for label, _flavour, _source in grammars()]
    with_pairs = [b.name for b in BENCHES if roles(b.compiled.codegen_grammar).pairs]
    assert labels == [*with_pairs, "json.gbnf"]
    assert "json" in with_pairs, "the bench's own json formulation has no pairs"
    assert "csv" not in labels, "a grammar with no regions crept in"


def test_a_stored_document_reads_back_character_for_character(tmp_path):
    """A generated document keeps every carriage return: stored and read back, it is
    the same length and the same bytes, not one with its line ends rewritten."""
    text = '[\r\n {"a":\r"b"}\n,\r\r1]\r'
    path = tmp_path / "doc.txt"
    write_document(path, text)
    back = read_document(path)
    assert len(back) == len(text)
    assert back.encode() == text.encode()
