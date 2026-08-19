"""Tests for ``lexic.parsing.parallel.pool`` — the document pool.

The pool changes WHEN documents parse, never what a parse means: results
equal the sequential parses, in input order, and a failing document raises
its own exception.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.parallel import ParsePool
from lexic.parsing.parallel import policy as policy_module

GRAMMAR = 'root ::= "(" [a-z]+ ")"\n'


def test_map_equals_sequential_in_input_order():
    """Every model matches its own sequential parse, order preserved."""
    compiled = compile_text(GRAMMAR)
    texts = [f"({'x' * (i + 1)})" for i in range(8)]
    pool = ParsePool(compiled.parse, cores=4)
    models = pool.map(texts)
    pool.close()
    assert models == [compiled.parse(text) for text in texts]
    assert [model.to_text() for model in models] == texts


def test_a_failing_document_raises_its_own_exception():
    """The pool never swallows a refusal — the parse's exception surfaces."""
    compiled = compile_text(GRAMMAR)
    pool = ParsePool(compiled.parse, cores=2)
    with pytest.raises(UnsupportedConstructError):
        pool.map(["(ok)", "nope"])
    pool.close()


def test_explicit_cores_is_the_worker_count():
    """An explicit ask is a decision — used as given."""
    compiled = compile_text(GRAMMAR)
    assert ParsePool(compiled.parse, cores=3).workers == 3


def test_auto_sizing_follows_the_policy(monkeypatch: pytest.MonkeyPatch):
    """The pool's default is the policy's auto — one worker under the GIL."""
    monkeypatch.setattr(policy_module, "_free_threaded", lambda: False)
    compiled = compile_text(GRAMMAR)
    assert ParsePool(compiled.parse).workers == 1
    assert ParsePool(compiled.parse, cores=1).workers == 1
