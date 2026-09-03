"""Tests for lexic.parsing.executable — the bound model product.

``ModelExecutable`` retains no authored rules — its slots are exactly
``program``/``codes``/``routines``/``executor`` — and every downstream
consumer reads ``routines``, the verified program read back. ``replica()``
shares the verified ``program`` and ``codes`` by identity and rebuilds only
the routine container (equal, but a distinct object) with its own executor
over it, so a worker pays no lowering.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    LoweringOwned,
    PassOp,
    RecordConstructor,
    RecordOp,
    RuleProduct,
)
from lexic.parsing.product.tree import ProductExecutor

_RULES = {
    "a": RuleProduct(
        captures=(CaptureSpec(int(CaptureMode.ONE), 0),), completion=PassOp(0)
    ),
    "b": RuleProduct(captures=(), completion=PassOp(0)),
}


def test_model_binding_holds_no_authored_record_at_all():
    """The slot set IS exactly program/codes/routines/executor — nothing else.

    A test naming a fifth slot (``rules``, ``owned``, ``construction``) would
    fail here, which is the point: those were deleted, not renamed.
    """
    assert set(ModelExecutable.__slots__) == {
        "program",
        "codes",
        "routines",
        "executor",
    }


def test_default_construction_binds_no_rules():
    """A binding built with nothing declares an empty codes/routines pair."""
    binding = ModelExecutable()
    assert binding.codes == {}
    assert binding.routines == {}


def test_codes_and_routines_share_exactly_the_same_key_set():
    """Every rule name in codes has a routine, and vice versa."""
    binding = ModelExecutable(_RULES)
    assert binding.codes.keys() == binding.routines.keys() == _RULES.keys()
    assert binding.codes == {"a": 0, "b": 1}


def test_the_executor_completes_through_the_bindings_own_routine_container():
    """executor.routines IS binding.routines — one container, one reader."""
    binding = ModelExecutable(_RULES)
    assert isinstance(binding.executor, ProductExecutor)
    assert binding.executor.routines is binding.routines


def test_the_meaning_comparator_is_the_engines_own_same_value_law():
    """Every ambiguity gate compares with same_value — the program declares it."""
    binding = ModelExecutable(_RULES)
    assert binding.program.operands.meanings == (same_value,)


def test_the_default_root_finalizer_is_the_identity():
    """The default root finalizer is the start rule's value, unchanged."""
    binding = ModelExecutable(_RULES)
    finalizer = binding.program.operands.roots[0]
    sentinel = object()
    assert finalizer(sentinel, ()) is sentinel


def test_construction_verifies_and_refuses_a_bad_rule():
    """The constructor lowers AND verifies — a malformed rule cannot reach here."""
    bad = {"a": RuleProduct(captures=(), completion=RecordOp(0))}  # no constructor 0
    with pytest.raises(UnsupportedConstructError):
        ModelExecutable(bad)


def test_a_declared_constructor_resolves_through_the_bound_routine():
    """A real RECORD rule's routine carries the resolved construction."""

    class _Pair(NamedTuple):
        a: object = None
        b: object = None

        @classmethod
        def fast_construct(cls):
            return (cls, {}, ("a", "b"))

    rules = {
        "root": RuleProduct(
            captures=(
                CaptureSpec(int(CaptureMode.TEXT), 0),
                CaptureSpec(int(CaptureMode.TEXT), 1),
            ),
            completion=RecordOp(0),
            n_items=2,
        )
    }
    owned = LoweringOwned(
        constructors=(RecordConstructor(cls=_Pair, names=("a", "b")),)
    )
    binding = ModelExecutable(rules, owned)
    construction = binding.routines["root"].construction
    assert construction is not None
    assert construction.call is _Pair


# ── replica() ──────────────────────────────────────────────────────────


def test_replica_shares_the_verified_program_and_codes_by_identity():
    """Nothing is lowered or verified again — same immutable objects."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.program is binding.program
    assert replica.codes is binding.codes


def test_replica_rebuilds_an_equal_but_distinct_routine_container():
    """The routine map is EQUAL by value but a DIFFERENT object — the one
    thing a worker must not share, since it is what every completion reads."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.routines == binding.routines
    assert replica.routines is not binding.routines


def test_replica_gets_its_own_executor_over_its_own_container():
    """A replica's executor is distinct and reads the REPLICA's own routines."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.executor is not binding.executor
    assert replica.executor.routines is replica.routines
    assert replica.executor.routines is not binding.routines
