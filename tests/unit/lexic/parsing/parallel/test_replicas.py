"""Tests for ``lexic.parsing.parallel.replicas`` — each worker's own tables.

A replica must be invisible: equal grammar, same classes, therefore equal
models. What it changes is which table objects a worker touches, which is
what stops concurrent parses contending on one set of refcount cache lines.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing import ModelBinding, parse_model
from lexic.parsing.parallel import worker_replicas

GRAMMAR = 'root ::= item+\nitem ::= "- " [a-z]+ "\\n"\n'
TEXT = "- alpha\n- beta\n- gamma\n"


def _pair():
    compiled = compile_text(GRAMMAR)
    return compiled.codegen_grammar, compiled.fold


def test_a_replica_is_equal_but_distinct():
    """Equal by value (so models match), distinct by identity (so the
    engine's per-identity table memo gives it its own tables)."""
    grammar, fold = _pair()
    binding = ModelBinding(fold)
    first, second = worker_replicas(grammar, binding, 2)
    assert second[0] == grammar
    assert second[0] is not grammar
    assert first[0] is grammar  # one worker costs nothing


def test_replicas_build_the_same_models():
    """The whole point: replication changes timing, never values."""
    grammar, fold = _pair()
    binding = ModelBinding(fold)
    original = parse_model(grammar, TEXT, binding)
    for replica_grammar, replica_binding in worker_replicas(grammar, binding, 3):
        model = parse_model(replica_grammar, TEXT, replica_binding)
        assert model == original
        assert type(model) is type(original)
        assert model.to_text() == TEXT


def test_replicas_are_reused_and_grown():
    """Built once per pair and kept — a discarded replica would pay its
    table compilation again on the next parse."""
    grammar, fold = _pair()
    binding = ModelBinding(fold)
    two = worker_replicas(grammar, binding, 2)
    four = worker_replicas(grammar, binding, 4)
    assert four[:2] == two
    assert len(four) == 4
    assert worker_replicas(grammar, binding, 2) == two


def test_exactly_the_requested_count_comes_back():
    """A caller asking for N workers gets N views, never the grown pool."""
    grammar, fold = _pair()
    binding = ModelBinding(fold)
    worker_replicas(grammar, binding, 6)
    assert len(worker_replicas(grammar, binding, 3)) == 3
